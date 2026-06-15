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
from relic.splunk_client import SplunkMCPClient
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
        self.splunk_client = SplunkMCPClient(
            mcp_url=splunk_url,
            token=splunk_token,
            use_mock=use_mock,
            mock_dir=self.mock_dir,
        )
        self.otel_mapper = OTelMapper(self.mock_dir / "otel_mapping.yaml")
        self.spl_query_gen = SPLQueryGenerator(splunk_client=self.splunk_client)

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

        response = {
            "intent": intent.intent,
            "spl_query": spl_query,
            "results": results,
            "code_mappings": code_mappings,
            "suggestions": suggestions,
        }

        if intent.explanation:
            response["explanation"] = intent.explanation
        if intent.source:
            response["spl_source"] = intent.source

        return response

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

    def handle_ai_spl_generate(self, query: str, namespace: str = "default") -> dict:
        result = self.splunk_client.ai_generate_spl(query, namespace)
        return result

    def handle_ai_spl_explain(self, spl: str) -> dict:
        result = self.splunk_client.ai_explain_spl(spl)
        return result

    def handle_forecast_metric(self, metric_name: str, service: str, forecast_horizon: str = "1h", confidence_level: float = 0.95) -> dict:
        result = self.splunk_client.forecast_metric(metric_name, service, forecast_horizon, confidence_level)
        return result

    def handle_investigate_incident(self, incident_id: str) -> dict:
        result = self.splunk_client.investigate_incident(incident_id)
        if self.graph and isinstance(result, dict) and "blast_radius" in result:
            br = result["blast_radius"]
            if isinstance(br, dict) and "downstream_affected" in br:
                for entry in br.get("downstream_affected", []):
                    nid = entry.get("node_id")
                    if nid:
                        node = self.graph.get_node(nid)
                        if node:
                            entry["kind"] = node.kind
                            entry["signature"] = node.signature
        return result

    def handle_get_dashboard_data(self) -> dict:
        services = self.otel_mapper.all_services()
        service_health = {}
        for svc in services:
            metrics = self.splunk_client.get_service_metrics(svc)
            if metrics:
                service_health[svc] = metrics

        all_incidents = self.splunk_client.get_all_incidents()

        incident_timeline = []
        for inc in all_incidents:
            incident_timeline.append({
                "id": inc.get("id", ""),
                "service": inc.get("service", ""),
                "severity": inc.get("severity", ""),
                "date": inc.get("date", ""),
                "summary": inc.get("summary", ""),
                "type": inc.get("type", ""),
            })

        dependency_graph = {"nodes": [], "edges": []}
        if self.graph:
            seen_nodes = set()
            for svc in services:
                node_ids = self.otel_mapper.service_to_node_ids(svc)
                for nid in node_ids:
                    if nid not in seen_nodes:
                        seen_nodes.add(nid)
                        node = self.graph.get_node(nid)
                        if node:
                            dependency_graph["nodes"].append({
                                "id": node.id,
                                "name": node.name,
                                "kind": node.kind,
                                "path": node.path,
                            })
                    edges = self.graph.get_edges(nid, direction="downstream", edge_type="calls")
                    for e in edges:
                        dependency_graph["edges"].append({
                            "from": e.from_node,
                            "to": e.to_node,
                            "type": e.edge_type,
                        })

        risk_summary = None
        if self.risk_scorer and self.graph:
            try:
                all_functions = [n.id for n in self.graph.nodes.values() if n.kind in ("function", "method")]
                sample = all_functions[:5]
                risk_result = self.risk_scorer.score([self.graph.nodes[nid].path for nid in sample if nid in self.graph.nodes])
                risk_summary = {
                    "overall_score": risk_result.overall_score,
                    "level": risk_result.level,
                    "node_count": len(risk_result.node_scores),
                }
            except Exception:
                risk_summary = None

        return {
            "services": services,
            "service_health": service_health,
            "incident_timeline": incident_timeline,
            "dependency_graph": dependency_graph,
            "risk_summary": risk_summary,
        }


_server_instance: RelicMCPServer | None = None


@app.list_tools()
async def list_tools():
    from mcp.types import Tool

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
            description="Process natural language SRE question — uses Splunk AI Assistant to generate SPL when available, with regex fallback",
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
        Tool(
            name="ai_spl_generate",
            description="Use Splunk AI Assistant to generate an SPL query from natural language — requires Splunk MCP Server with AI Assistant",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language SRE question"},
                    "namespace": {"type": "string", "description": "Splunk namespace (default: 'default')"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="ai_spl_explain",
            description="Use Splunk AI Assistant to explain an SPL query — requires Splunk MCP Server with AI Assistant",
            inputSchema={
                "type": "object",
                "properties": {"spl": {"type": "string", "description": "SPL query to explain"}},
                "required": ["spl"],
            },
        ),
        Tool(
            name="forecast_metric",
            description="Forecast a metric using Splunk AI Toolkit / Cisco Deep Time Series Model — includes confidence intervals and anomaly detection",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string", "description": "Metric to forecast (e.g. p99_latency_ms, error_rate)"},
                    "service": {"type": "string", "description": "Service name"},
                    "forecast_horizon": {"type": "string", "description": "Forecast window (e.g. '1h', '24h', '7d')"},
                    "confidence_level": {"type": "number", "description": "Confidence level (0.0-1.0, default: 0.95)"}},
                "required": ["metric_name", "service"],
            },
        ),
        Tool(
            name="investigate_incident",
            description="Agentic incident investigation — chains multiple Splunk tools: fetches incident, service health, related incidents, blast radius, and suggests remediation",
            inputSchema={
                "type": "object",
                "properties": {"incident_id": {"type": "string", "description": "Incident ID (e.g. INC-1029)"}},
                "required": ["incident_id"],
            },
        ),
        Tool(
            name="get_dashboard_data",
            description="Get all dashboard data: service health grid, incident timeline, dependency graph, risk summary — powers the observability dashboard webview",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
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
        elif name == "ai_spl_generate":
            result = _server_instance.handle_ai_spl_generate(
                arguments.get("query", ""),
                arguments.get("namespace", "default"),
            )
        elif name == "ai_spl_explain":
            result = _server_instance.handle_ai_spl_explain(arguments.get("spl", ""))
        elif name == "forecast_metric":
            result = _server_instance.handle_forecast_metric(
                arguments.get("metric_name", ""),
                arguments.get("service", ""),
                arguments.get("forecast_horizon", "1h"),
                arguments.get("confidence_level", 0.95),
            )
        elif name == "investigate_incident":
            result = _server_instance.handle_investigate_incident(arguments.get("incident_id", ""))
        elif name == "get_dashboard_data":
            result = _server_instance.handle_get_dashboard_data()
        else:
            result = {"error": f"Unknown tool: {name}"}

        yield TextContent(type="text", text=json.dumps(result, indent=2))

    except Exception as e:
        yield TextContent(type="text", text=json.dumps({"error": str(e)}))


def init_server(repo_path: str, ctx_path: str | None = None, use_mock: bool = True, mock_dir: str | None = None, splunk_url: str = "http://localhost:8089", splunk_token: str = ""):
    global _server_instance
    _server_instance = RelicMCPServer(
        repo_path=repo_path,
        ctx_path=ctx_path,
        use_mock=use_mock,
        mock_dir=mock_dir,
        splunk_url=splunk_url,
        splunk_token=splunk_token,
    )
    return _server_instance


async def run_server():
    await stdio_server(app)


if __name__ == "__main__":
    import asyncio

    async def main():
        await run_server()

    asyncio.run(main())
