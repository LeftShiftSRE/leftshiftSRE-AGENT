#!/usr/bin/env python3
import argparse
import asyncio
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import shutil

from server.graph import CallGraph
from server.splunk_client import SplunkClient
from server.risk import RiskScorer


def get_git_diff(repo_path: Path, diff_ref: str = "HEAD~1..HEAD") -> list:
    git = shutil.which("git") or "git"
    if ".." in diff_ref:
        ref_parts = diff_ref.split("..", 1)
        git_args = [git, "diff", "--name-only", ref_parts[0], ref_parts[1]]
    else:
        git_args = [git, "diff", "--name-only", diff_ref]
    result = subprocess.run(
        git_args,
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        result = subprocess.run(
            [git, "ls-files"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
    return [f for f in result.stdout.strip().splitlines() if f]


async def analyze(repo_path: Path, modified_files: list):
    print(f"\n{'='*60}")
    print("  RELIC - Context-aware SRE Agent")
    print(f"{'='*60}\n")

    print("[1/4] Building call graph with Tree-sitter...")
    t0 = time.perf_counter()
    graph = CallGraph(repo_path)
    print(
        f"      -> {len(graph.nodes)} nodes, "
        f"{len(graph.edges)} edges "
        f"({time.perf_counter()-t0:.2f}s)\n"
    )

    print("[2/4] Mapping modified files to code nodes...")
    node_ids = graph.changed_files_to_nodes(modified_files)
    for nid in node_ids:
        if nid in graph.nodes:
            n = graph.nodes[nid]
            print(f"      -> {n['service']}.{n['operation']} ({nid})")
    print(f"      -> {len(node_ids)} modified nodes\n")

    if not node_ids:
        print("No Python functions modified.")
        return

    print("[3/4] Querying Splunk (saved_search:risk_score_for_nodes)...")
    t0 = time.perf_counter()
    splunk = SplunkClient()
    scorer = RiskScorer(splunk)
    result = await scorer.score(node_ids)
    print(f"      -> Query time: {time.perf_counter()-t0:.3f}s\n")

    print("[4/4] Risk Assessment:\n")
    print("  +------------------------------------------+")
    print(
        f"  |  OVERALL RISK: {result.overall_score:3d}/100 "
        f"({result.level.upper():8s})    |"
    )
    print("  +------------------------------------------+\n")

    for n in result.nodes:
        print(f"  * {n.service}.{n.operation}")
        print(f"      Risk score:   {n.score}/100 ({n.level})")
        print(f"      Blast radius: {n.blast_radius} downstream")
        print(f"      Incidents:    {n.incidents_30d} in last 30d")
        print(f"      p99 latency:  {n.p99_ms}ms")
        print(f"      Owner:        {n.owner}")
        print()

    print("  -- Narrative ---------------------------------")
    print(f"  {result.narrative}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Relic - Context-aware SRE Agent")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path("demo/sample_repo"),
    )
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--diff", default=None, metavar="REF",
                        help="Git diff ref (e.g. HEAD~1..HEAD or a commit)")
    args = parser.parse_args()

    if args.files:
        modified = args.files
    elif args.diff:
        modified = get_git_diff(args.repo, args.diff)
    else:
        modified = get_git_diff(args.repo)

    if not modified:
        print("No modified files. Use --files to specify.")
        sys.exit(1)

    print(f"Analyzing {len(modified)} files in {args.repo}")
    asyncio.run(analyze(args.repo, modified))


if __name__ == "__main__":
    main()
