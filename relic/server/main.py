from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .splunk_client import SplunkClient
from .graph import CallGraph
from .risk import RiskScorer
from .catalog import match_intent

mcp = FastMCP("relic")

_splunk = SplunkClient(use_mock=True)
_graph_cache: dict = {}


def get_graph(repo_path: str) -> CallGraph:
    if repo_path not in _graph_cache:
        _graph_cache[repo_path] = CallGraph(Path(repo_path))
    return _graph_cache[repo_path]


@mcp.tool()
async def get_risk_score(repo_path: str, modified_files: list) -> dict:
    """
    Compute risk score for modified code paths.
    Combines Tree-sitter call graph + Splunk incident history + APM latency.
    Returns deterministic, auditable risk score with narrative.
    """
    graph = get_graph(repo_path)
    node_ids = graph.changed_files_to_nodes(modified_files)
    scorer = RiskScorer(_splunk)
    result = await scorer.score(node_ids)
    return {
        "overall_score": result.overall_score,
        "level": result.level,
        "nodes": [
            {
                "node_id": n.node_id,
                "service": n.service,
                "operation": n.operation,
                "score": n.score,
                "level": n.level,
                "blast_radius": n.blast_radius,
                "incidents_30d": n.incidents_30d,
                "p99_ms": n.p99_ms,
                "owner": n.owner,
            }
            for n in result.nodes
        ],
        "narrative": result.narrative,
        "source": "saved_search:risk_score_for_nodes",
    }


@mcp.tool()
async def sre_chat_query(message: str) -> dict:
    """
    Natural language SRE query -> matched Splunk saved search.
    Matches intent against catalog of pre-built SPL queries.
    """
    intent = match_intent(message)
    if not intent:
        return {
            "intent": "unknown",
            "message": "Try: 'show errors', 'show latency', 'show incidents'",
        }
    query = intent["spl"]
    for k, v in intent.get("params", {}).items():
        query = query.replace(f"${k}$", str(v))
    result = await _splunk.search(query)
    return {
        "intent": intent["name"],
        "description": intent["description"],
        "spl": query,
        "results": result.get("results", []),
        "result_count": len(result.get("results", [])),
    }


@mcp.tool()
async def map_service_to_node(service: str, operation: str) -> dict:
    """Map OTel service+operation to code node_id via Splunk KV Store."""
    query = (
        f"| inputlookup service_operation_map "
        f'WHERE service="{service}" operation="{operation}"'
    )
    result = await _splunk.search(query)
    rows = result.get("results", [])
    if rows:
        return {"found": True, **rows[0]}
    return {"found": False, "service": service, "operation": operation}


@mcp.tool()
async def get_incidents_for_service(
    service: str, earliest: str = "-30d"
) -> dict:
    """Fetch incident history for a service from Splunk."""
    query = (
        f'index=incidents service="{service}" earliest={earliest} '
        f"| table id, severity, summary, date"
    )
    result = await _splunk.search(query)
    return {
        "service": service,
        "incidents": result.get("results", []),
        "count": len(result.get("results", [])),
    }
if __name__ == '__main__':
    mcp.run()
