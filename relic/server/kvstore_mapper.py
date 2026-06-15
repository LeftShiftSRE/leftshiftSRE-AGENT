import os
from dataclasses import dataclass
from typing import Optional

from .splunk_client import SplunkClient


@dataclass
class CodeNode:
    node_id: str
    service: str
    operation: str
    owner: str
    tier: str


class KVStoreMapper:
    MAPPER_BACKEND = os.getenv("MAPPER_BACKEND", "kvstore")
    MOCK_DATA = {
        ("payment_service", "charge"): CodeNode(
            node_id="n_payment_service_charge",
            service="payment_service",
            operation="charge",
            owner="payments-team",
            tier="1",
        ),
        ("payment_service", "refund"): CodeNode(
            node_id="n_payment_service_refund",
            service="payment_service",
            operation="refund",
            owner="payments-team",
            tier="1",
        ),
        ("payment_service", "batch_charge"): CodeNode(
            node_id="n_payment_service_batch_charge",
            service="payment_service",
            operation="batch_charge",
            owner="payments-team",
            tier="1",
        ),
        ("payment_service", "validate_amount"): CodeNode(
            node_id="n_payment_service_validate_amount",
            service="payment_service",
            operation="validate_amount",
            owner="payments-team",
            tier="2",
        ),
        ("order_service", "create_order"): CodeNode(
            node_id="n_order_service_create_order",
            service="order_service",
            operation="create_order",
            owner="orders-team",
            tier="2",
        ),
        ("inventory_service", "reserve"): CodeNode(
            node_id="n_inventory_service_reserve",
            service="inventory_service",
            operation="reserve",
            owner="inventory-team",
            tier="3",
        ),
        ("gateway", "route"): CodeNode(
            node_id="n_gateway_route",
            service="gateway",
            operation="route",
            owner="platform-team",
            tier="1",
        ),
    }

    def __init__(self, splunk_client: SplunkClient):
        self.splunk = splunk_client
        self._cache: dict[tuple[str, str], CodeNode] = {}

    async def map(self, service: str, operation: str) -> Optional[CodeNode]:
        key = (service, operation)
        if key in self._cache:
            return self._cache[key]

        if self.MAPPER_BACKEND == "mock":
            node = self.MOCK_DATA.get(key)
            if node:
                self._cache[key] = node
            return node

        query = (
            f'| inputlookup service_operation_map '
            f'WHERE service="{service}" operation="{operation}"'
        )
        result = await self.splunk.search(query)
        rows = result.get("results", [])
        if not rows:
            return None

        row = rows[0]
        node = CodeNode(
            node_id=row.get("node_id", ""),
            service=row.get("service", service),
            operation=row.get("operation", operation),
            owner=row.get("owner", ""),
            tier=row.get("tier", ""),
        )
        if len(self._cache) >= 256:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[key] = node
        return node

    async def reverse_map(self, node_id: str) -> Optional[CodeNode]:
        if self.MAPPER_BACKEND == "mock":
            for (svc, op), node in self.MOCK_DATA.items():
                if node.node_id == node_id:
                    return node
            return None

        query = f'| inputlookup service_operation_map WHERE node_id="{node_id}"'
        result = await self.splunk.search(query)
        rows = result.get("results", [])
        if not rows:
            return None
        row = rows[0]
        return CodeNode(
            node_id=row.get("node_id", ""),
            service=row.get("service", ""),
            operation=row.get("operation", ""),
            owner=row.get("owner", ""),
            tier=row.get("tier", ""),
        )
