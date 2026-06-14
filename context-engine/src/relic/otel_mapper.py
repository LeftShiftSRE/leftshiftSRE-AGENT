import yaml
from pathlib import Path
from typing import Optional


class OTelMapper:
    def __init__(self, mapping_path: str | Path | None = None):
        self.mappings: list[dict] = []
        if mapping_path and Path(mapping_path).exists():
            with open(mapping_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.mappings = data.get("mappings", [])

    def add_mapping(self, service: str, operation: str, node_id: str):
        self.mappings.append({"service": service, "operation": operation, "node_id": node_id})

    def lookup(self, service: str, operation: str) -> str | None:
        for m in self.mappings:
            if m.get("service") == service and m.get("operation") == operation:
                return m.get("node_id")
        return None

    def service_to_node_ids(self, service: str) -> list[str]:
        return [m["node_id"] for m in self.mappings if m.get("service") == service]

    def all_services(self) -> list[str]:
        return sorted(set(m.get("service", "") for m in self.mappings))

    def all_operations(self, service: str) -> list[str]:
        return sorted(set(m.get("operation", "") for m in self.mappings if m.get("service") == service))