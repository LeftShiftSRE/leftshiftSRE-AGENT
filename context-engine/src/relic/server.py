import json
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from relic.graph import CtxGraph
from relic.parser import CtxParser
from relic.risk import RiskScorer, Incident
from relic.splunk_client import SplunkClient
from relic.spl_query_gen import SPLQueryGenerator
from relic.otel_mapper import OTelMapper

app = Server("relic-context-engine")


class RelicMCPServer:
    def __init__(
        self,
        repo_path: str,
        ctx_path: str | None = None,
        use_mock: bool = True,
        mock_dir: str | None = None,
        splunk_url: str = "http://localhost:8089",
        splunk_token: str = "",
    ):
        self.repo_path = Path(repo_path)
        self.use_mock = use_mock
        self.mock_dir = Path(mock_dir) if mock_dir else Path(__file__).parent.parent / "mock"

        self.graph: CtxGraph | None = None
        self.risk_scorer: RiskScorer | None = None
        self.splunk_client = SplunkClient(
            url=splunk_url,
            token=splunk_token,
            use_mock=use_mock,
            mock_dir=self.mock_dir,
        )
        self.otel_mapper = OTelMapper(self.mock_dir / "otel_mapping.yaml")
        self.spl_query_gen = SPLQueryGenerator()

        if ctx_path and Path(ctx_path).exists():
            self.graph = CtxGraph.load(ctx_path)
            self.splunk_client.set_graph(self.graph)
            self._load_incidents()
        elif self.repo_path.exists():
            self._ensure_ctx()

    def _load_incidents(self):
        if not self.graph:
            return
        incidents = []
        all_incs = self.splunk_client.get_all_incidents()
        for d in all_incs:
            incidents.append(Incident.from_dict(d))
        self.risk_scorer = RiskScorer(self.graph, incidents)

    def _ensure_ctx(self):
        ctx_file = self.repo_path / ".ctx" / "repo.ctx"
        if not ctx_file.exists():
            parser = CtxParser(str(self.repo_path))
            doc = parser.parse_repo()
            ctx_file = Path(parser.save(doc, str(ctx_file)))

        self.graph = CtxGraph.load(str(ctx_file))
        self.graph.metadata["root_path"] = str(self.repo_path)
        self.splunk_client.set_graph(self.graph)
        self._load_incidents()

    def handle_get_context_summary(self, repo_id: str) -> dict:
        if not self.graph:
            return {"error": "CTX_FILE_NOT_FOUND"}
        return self.graph.get_context_summary()

    def handle_get_node(self, node_id: str) -> dict:
        if not self.graph:
            return {"error": "CTX_FILE_NOT_FOUND"}
        node = self.graph.get_node(node_id)
        if not node:
            return {"error": {"code": "NODE_NOT_FOUND", "message": f"Node '{node_id}' not found"}}
        return {
            "id": node.id,
            "kind": node.kind,
            "name": node.name,
            "path": node.path,
            "span": {"start_line": node.start_line, "end_line": node.end_line},
            "signature": node.signature,
            "parent": node.parent,
        }

    def handle_search_nodes(self, query: str, kind: str | None = None) -> dict:
        if not self.graph:
            return {"error": "CTX_FILE_NOT_FOUND"}
        results = self.graph.search(query, kind)
        return {"results": [{"id": n.id, "kind": n.kind, "name": n.name, "path": n.path} for n in results[:10]]}

    def handle_get_edges(self, node_id: str, direction: str = "downstream", edge_type: str | None = None) -> dict:
        if not self.graph:
            return {"error": "CTX_FILE_NOT_FOUND"}
        edges = self.graph.get_edges(node_id, direction, edge_type)
        nodes_data = []
        for e in edges:
            neighbor_id = e.to_node if direction == "downstream" else e.from_node
            neighbor = self.graph.get_node(neighbor_id)
            if neighbor:
                nodes_data.append({"id": neighbor.id, "kind": neighbor.kind, "name": neighbor.name, "path": neighbor.path})

        return {"edges": [{"from": e.from_node, "to": e.to_node, "type": e.edge_type} for e in edges], "nodes": nodes_data}

    def handle_get_code_span(self, node_id: str) -> dict:
        if not self.graph:
            return {"error": "CTX_FILE_NOT_FOUND"}
        span = self.graph.get_code_span(node_id)
        if not span:
            return {"error": {"code": "NODE_NOT_FOUND", "message": f"Could not retrieve code span for '{node_id}'"}}
        return span

    def handle_get_risk_score(self, repo_path: str, modified_files: list[str]) -> dict:
        if not self.graph or not self.risk_scorer:
            return {"error": "CTX_FILE_NOT_FOUND"}
        result = self.risk_scorer.score(modified_files)
        return {
            "overall_score": result.overall_score,
            "level": result.level,
            "node_scores": [
                {
                    "node_id": ns.node_id,
                    "node_name": ns.node_name,
                    "score": ns.score,
                    "level": ns.level,
                    "reasons": ns.reasons,
                    "incidents": ns.incidents,
                    "downstream_dependents": ns.downstream_dependents,
                    "upstream_callers": ns.upstream_callers,
                }
                for ns in result.node_scores
            ],
        }

    def handle_sre_chat_query(self, message: str) -> dict:
        intent = self.spl_query_gen.parse(message)
        spl_query = self.spl_query_gen.generate(intent)
        results = self.splunk_client.search(spl_query)

        code_mappings = []
        if self.graph and intent.service:
            node_id = self.otel_mapper.lookup(intent.service, intent.operation or "")
            if node_id:
                node = self.graph.get_node(node_id)
                if node:
                    code_mappings.append(
                        {
                            "node_id": node.id,
                            "file": node.path,
                            "line": node.start_line,
                            "function": node.name,
                        }
                    )

        suggestions = self.spl_query_gen.generate_suggestions(intent)

        return {
            "intent": intent.intent,
            "spl_query": spl_query,
            "results": results,
            "code_mappings": code_mappings,
            "suggestions": suggestions,
        }

    def handle_map_metric_to_code(self, service: str, operation: str) -> dict:
        node_id = self.otel_mapper.lookup(service, operation)
        if not node_id or not self.graph:
            return {"error": {"code": "NODE_NOT_FOUND", "message": f"No mapping for {service}.{operation}"}}

        node = self.graph.get_node(node_id)
        if not node:
            return {"error": {"code": "NODE_NOT_FOUND", "message": f"Node '{node_id}' not found"}}

        downstream = self.graph.traverse(node_id, direction="downstream", edge_type="calls", max_depth=2)
        upstream = self.graph.traverse(node_id, direction="upstream", edge_type="calls", max_depth=2)

        return {
            "node_id": node.id,
            "function_name": node.name,
            "file": node.path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "signature": node.signature,
            "upstream_callers": [{"node_id": n.id, "name": n.name, "path": n.path} for n in upstream[:5]],
            "downstream_calls": [{"node_id": n.id, "name": n.name, "path": n.path} for n in downstream[:5]],
        }

    def handle_get_incident_history(self, node_id: str) -> dict:
        incidents = self.splunk_client.get_incidents_for_node(node_id)
        return {"node_id": node_id, "incidents": incidents}


_server_instance: RelicMCPServer | None = None


@app.list_tools()
async def list_tools():
    from mcp.types import Tool, ToolInputSchema

    return [
        Tool(
            name="get_context_summary",
            description="Get high-level repo summary: file/function/class counts, packages, critical paths",
            inputSchema={
                "type": "object",
                "properties": {"repo_id": {"type": "string"}},
                "required": ["repo_id"],
            },
        ),
        Tool(
            name="get_node",
            description="Retrieve a single .ctx node by ID",
            inputSchema={
                "type": "object",
                "properties": {"node_id": {"type": "string"}},
                "required": ["node_id"],
            },
        ),
        Tool(
            name="search_nodes",
            description="Search .ctx nodes by name with optional kind filter",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "kind": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="get_edges",
            description="Get edges for a node, filtered by direction and type",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "direction": {"type": "string", "enum": ["downstream", "upstream", "both"]},
                    "type": {"type": "string"}},
                "required": ["node_id"],
            },
        ),
        Tool(
            name="get_code_span",
            description="Get actual source code for a node",
            inputSchema={
                "type": "object",
                "properties": {"node_id": {"type": "string"}},
                "required": ["node_id"],
            },
        ),
        Tool(
            name="get_risk_score",
            description="Compute code risk score based on git diff and incident history",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "modified_files": {"type": "array", "items": {"type": "string"}}},
                "required": ["repo_path", "modified_files"],
            },
        ),
        Tool(
            name="sre_chat_query",
            description="Process natural language SRE question, generate SPL, return results with code mappings",
            inputSchema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        ),
        Tool(
            name="map_metric_to_code",
            description="Map Splunk service.operation to a .ctx node",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "operation": {"type": "string"}},
                "required": ["service", "operation"],
            },
        ),
        Tool(
            name="get_incident_history",
            description="Get past incidents for a .ctx node",
            inputSchema={
                "type": "object",
                "properties": {"node_id": {"type": "string"}},
                "required": ["node_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any):
    global _server_instance

    if _server_instance is None:
        yield TextContent(type="text", text=json.dumps({"error": "Server not initialized"}))
        return

    try:
        result: dict = {}

        if name == "get_context_summary":
            result = _server_instance.handle_get_context_summary(arguments.get("repo_id", ""))
        elif name == "get_node":
            result = _server_instance.handle_get_node(arguments.get("node_id", ""))
        elif name == "search_nodes":
            result = _server_instance.handle_search_nodes(arguments.get("query", ""), arguments.get("kind"))
        elif name == "get_edges":
            result = _server_instance.handle_get_edges(
                arguments.get("node_id", ""),
                arguments.get("direction", "downstream"),
                arguments.get("type"),
            )
        elif name == "get_code_span":
            result = _server_instance.handle_get_code_span(arguments.get("node_id", ""))
        elif name == "get_risk_score":
            result = _server_instance.handle_get_risk_score(
                arguments.get("repo_path", ""),
                arguments.get("modified_files", []),
            )
        elif name == "sre_chat_query":
            result = _server_instance.handle_sre_chat_query(arguments.get("message", ""))
        elif name == "map_metric_to_code":
            result = _server_instance.handle_map_metric_to_code(
                arguments.get("service", ""),
                arguments.get("operation", ""),
            )
        elif name == "get_incident_history":
            result = _server_instance.handle_get_incident_history(arguments.get("node_id", ""))
        else:
            result = {"error": f"Unknown tool: {name}"}

        yield TextContent(type="text", text=json.dumps(result, indent=2))

    except Exception as e:
        yield TextContent(type="text", text=json.dumps({"error": str(e)}))


def init_server(repo_path: str, ctx_path: str | None = None, use_mock: bool = True, mock_dir: str | None = None):
    global _server_instance
    _server_instance = RelicMCPServer(
        repo_path=repo_path,
        ctx_path=ctx_path,
        use_mock=use_mock,
        mock_dir=mock_dir,
    )
    return _server_instance


async def run_server():
    await stdio_server(app)


if __name__ == "__main__":
    import asyncio

    async def main():
        await run_server()

    asyncio.run(main())