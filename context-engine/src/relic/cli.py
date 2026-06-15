import argparse
import json
import sys
from pathlib import Path

from relic.parser import CtxParser
from relic.graph import CtxGraph
from relic.risk import RiskScorer, Incident
from relic.splunk_client import SplunkClient
from relic.otel_mapper import OTelMapper
from relic import server


def cmd_parse(args):
    parser = CtxParser(args.repo, language=args.language)
    doc = parser.parse_repo()
    output_path = args.output or str(Path(args.repo) / ".ctx" / "repo.ctx")
    saved = parser.save(doc, output_path)
    print(f"Parsed {len(doc.nodes)} nodes, {len(doc.edges)} edges -> {saved}")
    summary = doc.metadata
    print(f"  Files: {sum(1 for n in doc.nodes if n['kind'] == 'file')}")
    print(f"  Functions: {sum(1 for n in doc.nodes if n['kind'] == 'function')}")
    print(f"  Classes: {sum(1 for n in doc.nodes if n['kind'] == 'class')}")
    print(f"  Parse time: {summary.get('parse_time_seconds', 'N/A')}s")


def cmd_serve(args):
    ctx_path = Path(args.repo) / ".ctx" / "repo.ctx"
    if not ctx_path.exists():
        print(f"No .ctx file found at {ctx_path}. Run 'relic parse' first.", file=sys.stderr)
        sys.exit(1)

    mock_dir = Path(__file__).parent.parent / "mock" if args.mock else None
    srv = server.init_server(
        repo_path=args.repo,
        ctx_path=str(ctx_path),
        use_mock=args.mock,
        mock_dir=str(mock_dir) if mock_dir else None,
        splunk_url=args.splunk_url,
        splunk_token=args.splunk_token,
    )

    import asyncio

    print(f"Relic MCP Server running (repo={args.repo}, mock={args.mock})", file=sys.stderr)
    asyncio.run(server.run_server())


def cmd_risk(args):
    ctx_path = Path(args.repo) / ".ctx" / "repo.ctx"
    if not ctx_path.exists():
        print(f"No .ctx file found. Run 'relic parse' first.", file=sys.stderr)
        sys.exit(1)

    graph = CtxGraph.load(str(ctx_path))

    mock_dir = Path(__file__).parent.parent / "mock"
    splunk_client = SplunkClient(use_mock=True, mock_dir=mock_dir)
    splunk_client.set_graph(graph)

    incidents = []
    for d in splunk_client.get_all_incidents():
        incidents.append(Incident.from_dict(d))

    scorer = RiskScorer(graph, incidents)

    if args.diff:
        diff_output = args.diff
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            diff_output = f.read()
    else:
        import subprocess

        diff_output = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=args.repo,
            capture_output=True,
            text=True,
        ).stdout

    result = scorer.score_from_git_diff(args.repo, diff_output)

    print(json.dumps({"overall_score": result.overall_score, "level": result.level, "node_scores": [ns.__dict__ for ns in result.node_scores]}, indent=2, default=str))


def cmd_summary(args):
    ctx_path = Path(args.ctx or args.repo / ".ctx" / "repo.ctx")
    if not Path(ctx_path).exists():
        print(f".ctx not found at {ctx_path}", file=sys.stderr)
        sys.exit(1)

    graph = CtxGraph.load(str(ctx_path))
    summary = graph.get_context_summary()
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="relic", description="Relic — Code-Aware SRE Agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="Parse a repository into .ctx graph")
    p_parse.add_argument("repo", help="Path to repository")
    p_parse.add_argument("--language", default="python", help="Language (default: python)")
    p_parse.add_argument("--output", "-o", help="Output .ctx file path")

    p_serve = sub.add_parser("serve", help="Start MCP server (stdio)")
    p_serve.add_argument("repo", help="Path to repository")
    p_serve.add_argument("--mock", action="store_true", default=True, help="Use mock Splunk data")
    p_serve.add_argument("--no-mock", dest="mock", action="store_false", help="Use real Splunk MCP Server")
    p_serve.add_argument("--splunk-url", default="http://localhost:8089")
    p_serve.add_argument("--splunk-token", default="")

    p_risk = sub.add_parser("risk", help="Compute risk score for git changes")
    p_risk.add_argument("repo", help="Path to repository")
    p_risk.add_argument("--diff", help="Git diff output string")
    p_risk.add_argument("--file", help="File containing git diff output")

    p_summary = sub.add_parser("summary", help="Print .ctx summary")
    p_summary.add_argument("repo", nargs="?", help="Path to repository")
    p_summary.add_argument("--ctx", help="Path to .ctx file")

    args = parser.parse_args()

    if args.cmd == "parse":
        cmd_parse(args)
    elif args.cmd == "serve":
        cmd_serve(args)
    elif args.cmd == "risk":
        cmd_risk(args)
    elif args.cmd == "summary":
        cmd_summary(args)


if __name__ == "__main__":
    main()