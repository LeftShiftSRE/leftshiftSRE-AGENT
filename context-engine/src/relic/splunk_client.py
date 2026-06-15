import json
import httpx
from typing import Any, Optional

from relic.risk import Incident
from relic.otel_mapper import OTelMapper


class MCPToolResult:
    def __init__(self, success: bool, data: Any = None, error: str = "", is_ai: bool = False):
        self.success = success
        self.data = data
        self.error = error
        self.is_ai = is_ai


class SplunkMCPClient:
    def __init__(
        self,
        url: str = "http://localhost:8089",
        token: str = "",
        use_mock: bool = False,
        mock_dir: str | None = None,
    ):
        self.base_url = url.rstrip("/")
        self.token = token
        self.use_mock = use_mock
        self.mock_dir = mock_dir and __import__("pathlib").Path(mock_dir)
        self._graph = None
        self._mock_incidents: list[Incident] = []
        self._mock_metrics: dict = {}
        self._mock_otel: OTelMapper | None = None
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        if not self.mock_dir:
            return
        try:
            with open(self.mock_dir / "incidents.json", encoding="utf-8") as f:
                for d in json.load(f):
                    self._mock_incidents.append(Incident.from_dict(d))
            with open(self.mock_dir / "service_metrics.json", encoding="utf-8") as f:
                self._mock_metrics = json.load(f)
            from relic.otel_mapper import OTelMapper
            otel_path = self.mock_dir / "otel_mapping.yaml"
            if otel_path.exists():
                self._mock_otel = OTelMapper(otel_path)
        except Exception:
            pass

    def set_graph(self, graph):
        self._graph = graph

    def mcp_tool_call(self, tool_name: str, arguments: dict) -> MCPToolResult:
        if self.use_mock:
            return self._mock_tool_call(tool_name, arguments)

        try:
            with httpx.Client(verify=False, timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/services/mcp/v1/tools/call",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json={"name": tool_name, "arguments": arguments},
                )
                if response.status_code == 200:
                    result = response.json()
                    return MCPToolResult(
                        success=True,
                        data=result.get("result", {}),
                        is_ai=tool_name.startswith("saia_"),
                    )
                else:
                    return MCPToolResult(
                        success=False,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                    )
        except httpx.ConnectError:
            return MCPToolResult(success=False, error="Cannot connect to Splunk MCP Server. Is it running?")
        except Exception as e:
            return MCPToolResult(success=False, error=str(e))

    def _mock_tool_call(self, tool_name: str, arguments: dict) -> MCPToolResult:
        if tool_name == "splunk_run_query":
            return self._mock_run_query(arguments.get("query", ""))
        elif tool_name == "saia_generate_spl":
            return self._mock_ai_generate_spl(arguments.get("natural_language", ""))
        elif tool_name == "saia_explain_spl":
            return self._mock_ai_explain_spl(arguments.get("spl_query", ""), arguments.get("results"))
        elif tool_name == "splunk_get_indexes":
            return MCPToolResult(success=True, data=["app", "apm", "incidents"])
        elif tool_name == "splunk_get_index_info":
            return MCPToolResult(success=True, data={"name": arguments.get("index", "app"), "size": "1.2 GB", "event_count": 15420})
        return MCPToolResult(success=True, data={"message": f"Mock tool {tool_name} called"})

    def _mock_run_query(self, query: str) -> MCPToolResult:
        q = query.lower()
        if "error" in q and "stats" in q:
            results = [
                {"service": "payment_service", "operation": "charge", "message": "ConnectionTimeout: database connection pool exhausted", "count": 47},
                {"service": "payment_service", "operation": "charge", "message": "PoolExhausted: max connections reached", "count": 23},
                {"service": "order_service", "operation": "create_order", "message": "UpstreamTimeout: payment timeout", "count": 12},
            ]
        elif "latency" in q or "p99" in q:
            results = [
                {"service": "payment_service", "operation": "charge", "p99_latency_ms": 2450, "p95_latency_ms": 1200, "error_rate": 0.03},
                {"service": "order_service", "operation": "create_order", "p99_latency_ms": 380, "p95_latency_ms": 180, "error_rate": 0.008},
                {"service": "inventory_service", "operation": "reserve", "p99_latency_ms": 45, "p95_latency_ms": 30, "error_rate": 0.001},
            ]
        elif "incident" in q:
            results = [
                {"id": "INC-1029", "service": "payment_service", "operation": "charge", "severity": "high", "summary": "p99 latency spike 2.4s on payment_service.charge", "date": "2026-05-28T14:30:00Z"},
                {"id": "INC-876", "service": "payment_service", "operation": "charge", "severity": "critical", "summary": "Timeout cascade: payment_service.charge caused order_service timeout", "date": "2026-04-15T09:00:00Z"},
            ]
        else:
            results = [
                {"service": "payment_service", "operation": "charge", "count": 15420},
                {"service": "order_service", "operation": "create_order", "count": 8200},
                {"service": "inventory_service", "operation": "reserve", "count": 9100},
            ]
        return MCPToolResult(success=True, data={"results": results}, is_ai=False)

    def _mock_ai_generate_spl(self, natural_language: str) -> MCPToolResult:
        nl = natural_language.lower()
        if "error" in nl:
            spl = 'index=app sourcetype=logs level=ERROR earliest=-24h | stats count by service, operation, message | sort -count | head 20'
        elif "latency" in nl or "slow" in nl:
            spl = 'index=apm metric=latency_p99_ms earliest=-24h | stats latest(value) as p99 by service, operation | sort -p99 | head 20'
        elif "incident" in nl or "outage" in nl:
            spl = 'index=incidents earliest=-7d | table id, service, severity, summary, date | sort -date'
        else:
            spl = 'index=app earliest=-24h | head 50'
        return MCPToolResult(
            success=True,
            data={"spl_query": spl, "confidence": 0.95, "explanation": f"Generated SPL based on: '{natural_language[:50]}...'"},
            is_ai=True,
        )

    def _mock_ai_explain_spl(self, spl_query: str, results: Any) -> MCPToolResult:
        return MCPToolResult(
            success=True,
            data={
                "explanation": f"The query retrieves data matching: '{spl_query[:60]}...'. Results show key patterns in service operations.",
                "optimization_tips": ["Consider adding an early-time filter to reduce scan range", "Use stats instead of timechart if aggregation is the goal"],
            },
            is_ai=True,
        )

    def search(self, spl_query: str) -> list[dict]:
        result = self.mcp_tool_call("splunk_run_query", {"query": spl_query})
        if result.success and result.data:
            return result.data.get("results", [])
        return []

    def ai_generate_spl(self, natural_language: str) -> tuple[str, float]:
        result = self.mcp_tool_call("saia_generate_spl", {"natural_language": natural_language})
        if result.success and result.data:
            return (
                result.data.get("spl_query", ""),
                result.data.get("confidence", 0.0),
            )
        return ("", 0.0)

    def ai_explain_spl(self, spl_query: str, results: list | None = None) -> dict:
        result = self.mcp_tool_call("saia_explain_spl", {"spl_query": spl_query, "results": results})
        if result.success and result.data:
            return {
                "explanation": result.data.get("explanation", ""),
                "optimization_tips": result.data.get("optimization_tips", []),
            }
        return {"explanation": "", "optimization_tips": []}

    def get_incidents_for_node(self, node_id: str) -> list[dict]:
        self._ensure_loaded()
        if self.use_mock:
            results = []
            for inc in self._mock_incidents:
                if self._graph:
                    node = self._graph.nodes.get(node_id)
                    if node and (inc.service in node.path or inc.operation == node.name):
                        results.append({
                            "id": inc.id, "date": inc.date, "severity": inc.severity,
                            "type": inc.incident_type, "summary": inc.summary,
                            "metrics": inc.metrics,
                        })
            return results
        results = self.search(f"index=incidents | head 50")
        return results

    def get_service_health(self) -> list[dict]:
        self._ensure_loaded()
        if self.use_mock:
            health = []
            for svc, metrics in self._mock_metrics.items():
                health.append({
                    "service": svc,
                    "operation": metrics.get("operation", ""),
                    "p99_latency_ms": metrics.get("p99_latency_ms", 0),
                    "error_rate": metrics.get("error_rate", 0),
                    "throughput_rps": metrics.get("throughput_rps", 0),
                    "status": "healthy" if metrics.get("error_rate", 0) < 0.05 else "degraded",
                })
            return health
        return self.search("index=apm metric=latency_p99_ms | stats latest(value) as p99 by service, operation | head 20")

    def get_dashboard_data(self) -> dict:
        self._ensure_loaded()
        service_health = self.get_service_health()
        incidents = self.search("index=incidents | sort -timestamp | head 10")
        latency_trend = self.search("index=apm metric=latency_p99_ms | timechart avg(value) by service span=1h")
        error_trend = self.search("index=apm metric=error_rate | timechart avg(value) by service span=1h")
        return {
            "services": service_health,
            "recent_incidents": incidents,
            "latency_trend": latency_trend,
            "error_trend": error_trend,
            "top_errors": self.search("index=app level=ERROR earliest=-24h | stats count by service, message | sort -count | head 10"),
        }

    def get_all_incidents(self) -> list[dict]:
        self._ensure_loaded()
        if self.use_mock:
            return [
                {"id": inc.id, "service": inc.service, "operation": inc.operation,
                 "date": inc.date, "severity": inc.severity, "type": inc.incident_type,
                 "summary": inc.summary, "metrics": inc.metrics}
                for inc in self._mock_incidents
            ]
        results = self.search("index=incidents | sort -timestamp | head 50")
        return results

    def map_to_node_id(self, service: str, operation: str) -> str | None:
        self._ensure_loaded()
        if self._mock_otel:
            return self._mock_otel.lookup(service, operation)
        return None

    def health_check(self) -> bool:
        if self.use_mock:
            return True
        result = self.mcp_tool_call("splunk_get_info", {})
        return result.success