from dataclasses import dataclass

from .splunk_client import SplunkClient


@dataclass
class NodeRisk:
    node_id: str
    service: str
    operation: str
    score: int
    level: str
    blast_radius: int
    incidents_30d: int
    p99_ms: float
    confidence: float
    owner: str


@dataclass
class RiskResult:
    overall_score: int
    level: str
    nodes: list
    narrative: str


class RiskScorer:
    def __init__(self, splunk: SplunkClient):
        self.splunk = splunk

    async def score(self, node_ids: list) -> RiskResult:
        if not node_ids:
            return RiskResult(0, "low", [], "No modified nodes detected.")

        node_list = ",".join(f'"{n}"' for n in node_ids)
        query = (
            f"| inputlookup risk_score_summary "
            f"WHERE node_id IN ({node_list})"
        )
        result = await self.splunk.search(query)

        nodes = []
        for row in result.get("results", []):
            nodes.append(
                NodeRisk(
                    node_id=row["node_id"],
                    service=row["service"],
                    operation=row["operation"],
                    score=row["risk_score"],
                    level=row["risk_level"],
                    blast_radius=row["blast_radius"],
                    incidents_30d=row["incidents_30d"],
                    p99_ms=row["p99_ms"],
                    confidence=row["confidence"],
                    owner=row["owner"],
                )
            )

        overall = max((n.score for n in nodes), default=0)
        if overall >= 70:
            level = "critical"
        elif overall >= 40:
            level = "high"
        elif overall >= 20:
            level = "medium"
        else:
            level = "low"

        narrative = self._narrative(nodes)
        return RiskResult(overall, level, nodes, narrative)

    def _narrative(self, nodes: list) -> str:
        if not nodes:
            return "No risk data available."
        top = max(nodes, key=lambda n: n.score)
        parts = [
            f"This change modifies {top.service}.{top.operation}, "
            f"which has {top.blast_radius} downstream callsites and "
            f"{top.incidents_30d} prior incidents in the last 30 days "
            f"(current p99: {top.p99_ms}ms). "
            f"Risk score: {top.score}/100 ({top.level}). "
            f"Owner: {top.owner}."
        ]
        if top.incidents_30d > 0:
            parts.append("Recommend reviewing recent incident postmortems before merge.")
        if top.blast_radius > 10:
            parts.append(
                f"Blast radius ({top.blast_radius}) exceeds threshold. "
                f"Consider incremental rollout."
            )
        return " ".join(parts)
