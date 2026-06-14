from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from relic.graph import CtxGraph


BLAST_RADIUS_WEIGHT = 0.3
INCIDENT_HISTORY_WEIGHT = 0.5
CRITICALITY_WEIGHT = 0.2


@dataclass
class Incident:
    id: str
    service: str
    operation: str
    date: str
    severity: str
    incident_type: str
    summary: str
    metrics: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Incident":
        return cls(
            id=d["id"],
            service=d["service"],
            operation=d["operation"],
            date=d["date"],
            severity=d["severity"],
            incident_type=d["type"],
            summary=d["summary"],
            metrics=d.get("metrics", {}),
        )


@dataclass
class NodeRiskScore:
    node_id: str
    node_name: str
    score: int
    level: str
    reasons: list[str]
    incidents: list[dict]
    downstream_dependents: list[dict]
    upstream_callers: list[dict]


@dataclass
class RiskResult:
    overall_score: int
    level: str
    node_scores: list[NodeRiskScore]


class RiskScorer:
    def __init__(self, graph: CtxGraph, incidents: list[Incident] | None = None):
        self.graph = graph
        self.incidents = incidents or []

    def score(self, modified_files: list[str]) -> RiskResult:
        modified_nodes = self._find_modified_nodes(modified_files)
        if not modified_nodes:
            return RiskResult(overall_score=0, level="none", node_scores=[])

        node_scores: list[NodeRiskScore] = []
        for node in modified_nodes:
            node_result = self._score_node(node)
            node_scores.append(node_result)

        max_score = max((ns.score for ns in node_scores), default=0)
        overall = int(sum(ns.score * 0.3 for ns in node_scores) / max(len(node_scores), 1) + max_score * 0.7)
        overall = min(100, overall)

        level = self._classify_level(overall)

        return RiskResult(overall_score=overall, level=level, node_scores=node_scores)

    def _find_modified_nodes(self, modified_files: list[str]) -> list:
        modified_nodes = []
        for node in self.graph.nodes.values():
            if node.path in modified_files:
                modified_nodes.append(node)
        return modified_nodes

    def _score_node(self, node) -> NodeRiskScore:
        reasons: list[str] = []
        matching_incidents: list[dict] = []

        downstream = self.graph.traverse(node.id, direction="downstream", edge_type="calls", max_depth=3)
        upstream = self.graph.traverse(node.id, direction="upstream", edge_type="calls", max_depth=2)

        blast_radius = len(downstream)
        if blast_radius > 10:
            reasons.append(f"{blast_radius} downstream functions affected")
        elif blast_radius > 0:
            reasons.append(f"{blast_radius} downstream functions affected")

        for inc in self.incidents:
            if inc.service and node.name and (inc.service in node.path or inc.operation == node.name or inc.operation in node.name):
                matching_incidents.append(
                    {
                        "id": inc.id,
                        "date": inc.date,
                        "severity": inc.severity,
                        "summary": inc.summary,
                        "type": inc.incident_type,
                        "metrics": inc.metrics,
                    }
                )
                severity_weight = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.1}.get(inc.severity, 0.1)
                reasons.append(f"Similar change caused {inc.id}: {inc.summary[:60]}")

        is_critical = self._is_on_critical_path(node)
        if is_critical:
            reasons.append("On critical user-facing path")

        incident_score = min(1.0, len(matching_incidents) * 0.3)

        raw_score = (
            BLAST_RADIUS_WEIGHT * min(1.0, blast_radius / 20)
            + INCIDENT_HISTORY_WEIGHT * incident_score
            + CRITICALITY_WEIGHT * (1.0 if is_critical else 0.0)
        ) * 100

        score = int(min(100, raw_score))

        level = self._classify_level(score)

        downstream_deps = [{"node_id": n.id, "name": n.name, "path": n.path} for n in downstream[:5]]
        upstream_callers = [{"node_id": n.id, "name": n.name, "path": n.path} for n in upstream[:5]]

        return NodeRiskScore(
            node_id=node.id,
            node_name=node.name,
            score=score,
            level=level,
            reasons=reasons[:4],
            incidents=matching_incidents[:3],
            downstream_dependents=downstream_deps,
            upstream_callers=upstream_callers,
        )

    def _is_on_critical_path(self, node) -> bool:
        paths = self.graph.find_critical_paths()
        for path in paths:
            if node.id in path:
                return True
        return False

    def _classify_level(self, score: int) -> str:
        if score <= 25:
            return "low"
        elif score <= 60:
            return "medium"
        else:
            return "critical"

    def score_from_git_diff(self, repo_path: str, diff_output: str) -> RiskResult:
        import re

        modified_files: list[str] = []
        for line in diff_output.splitlines():
            if line.startswith("diff --git"):
                match = re.search(r"a/(.+?) b/", line)
                if match:
                    f = match.group(1)
                    if f.endswith(".py"):
                        modified_files.append(f)
            elif line.startswith("+++ b/"):
                f = line[6:].strip()
                if f.endswith(".py") and f not in modified_files:
                    modified_files.append(f)

        return self.score(modified_files)