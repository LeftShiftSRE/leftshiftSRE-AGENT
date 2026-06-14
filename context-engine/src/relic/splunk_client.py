import json
from pathlib import Path
from typing import Any, Optional

from relic.risk import Incident
from relic.otel_mapper import OTelMapper


class SplunkClient:
    def __init__(
        self,
        url: str = "http://localhost:8089",
        token: str = "",
        use_mock: bool = True,
        mock_dir: str | Path | None = None,
    ):
        self.url = url
        self.token = token
        self.use_mock = use_mock
        self.mock_dir = Path(mock_dir) if mock_dir else None
        self._mock_incidents: list[Incident] = []
        self._mock_metrics: dict = {}
        self._mock_otel: OTelMapper = OTelMapper()
        self._load_mock_data()

    def _load_mock_data(self):
        if not self.mock_dir:
            return

        incidents_path = self.mock_dir / "incidents.json"
        if incidents_path.exists():
            with open(incidents_path, encoding="utf-8") as f:
                for d in json.load(f):
                    self._mock_incidents.append(Incident.from_dict(d))

        metrics_path = self.mock_dir / "service_metrics.json"
        if metrics_path.exists():
            with open(metrics_path, encoding="utf-8") as f:
                self._mock_metrics = json.load(f)

        otel_path = self.mock_dir / "otel_mapping.yaml"
        if otel_path.exists():
            self._mock_otel = OTelMapper(otel_path)

    def get_incidents_for_node(self, node_id: str) -> list[dict]:
        if self.use_mock:
            node = None
            from relic.graph import CtxGraph
            if hasattr(self, "_graph"):
                node = self._graph.nodes.get(node_id) if hasattr(self, "_graph") else None
            results = []
            for inc in self._mock_incidents:
                if node and (inc.service in node.path or inc.operation == node.name):
                    results.append(
                        {
                            "id": inc.id,
                            "date": inc.date,
                            "severity": inc.severity,
                            "type": inc.incident_type,
                            "summary": inc.summary,
                            "metrics": inc.metrics,
                        }
                    )
            return results

        import httpx

        query = f'search index=incidents | where service="{node_id}" | table id, date, severity, summary'
        return self._execute_spl(query)

    def search(self, spl_query: str) -> list[dict]:
        if self.use_mock:
            return self._mock_search(spl_query)

        import httpx

        return self._execute_spl(spl_query)

    def _mock_search(self, spl_query: str) -> list[dict]:
        spl_lower = spl_query.lower()

        if "error" in spl_lower and "count" in spl_lower:
            return [
                {"operation": "charge", "message": "ConnectionTimeout: database connection pool exhausted", "count": 47},
                {"operation": "charge", "message": "PoolExhausted: max connections reached", "count": 23},
                {"operation": "create_order", "message": "UpstreamTimeout: payment timeout", "count": 12},
            ]
        elif "latency" in spl_lower or "p99" in spl_lower:
            return [
                {"service": "payment_service", "operation": "charge", "p99_latency_ms": 2450, "p95_latency_ms": 1200, "error_rate": 0.03},
                {"service": "order_service", "operation": "create_order", "p99_latency_ms": 380, "p95_latency_ms": 180, "error_rate": 0.008},
                {"service": "inventory_service", "operation": "reserve", "p99_latency_ms": 45, "p95_latency_ms": 30, "error_rate": 0.001},
            ]
        elif "stats" in spl_lower or "count" in spl_lower:
            return [
                {"service": "payment_service", "operation": "charge", "count": 15420},
                {"service": "order_service", "operation": "create_order", "count": 8200},
                {"service": "inventory_service", "operation": "reserve", "count": 9100},
            ]
        return []

    def _execute_spl(self, spl_query: str) -> list[dict]:
        import httpx

        try:
            with httpx.Client(verify=False, timeout=10.0) as client:
                response = client.post(
                    f"{self.url}/services/search/jobs",
                    headers={"Authorization": f"Bearer {self.token}"},
                    data={"search": spl_query, "output_mode": "json"},
                )
                if response.status_code == 200:
                    return response.json().get("results", [])
        except Exception:
            pass
        return []

    def get_service_metrics(self, service: str) -> dict | None:
        if self.use_mock:
            return self._mock_metrics.get(service)
        return {}

    def map_to_node_id(self, service: str, operation: str) -> str | None:
        return self._mock_otel.lookup(service, operation)

    def set_graph(self, graph):
        self._graph = graph

    def get_all_incidents(self) -> list[dict]:
        if self.use_mock:
            return [
                {
                    "id": inc.id,
                    "service": inc.service,
                    "operation": inc.operation,
                    "date": inc.date,
                    "severity": inc.severity,
                    "type": inc.incident_type,
                    "summary": inc.summary,
                    "metrics": inc.metrics,
                }
                for inc in self._mock_incidents
            ]
        return self._execute_spl("index=incidents | table id, service, operation, severity, summary, date")

    def health_check(self) -> bool:
        if self.use_mock:
            return True
        import httpx

        try:
            with httpx.Client(verify=False, timeout=5.0) as client:
                resp = client.get(f"{self.url}/services/server/status", headers={"Authorization": f"Bearer {self.token}"})
                return resp.status_code == 200
        except Exception:
            return False