#!/usr/bin/env python3
"""Seed KV Store and mock data for demo."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SEED_DATA = [
    {"node_id": "n_payment_service_charge", "service": "payment_service", "operation": "charge", "owner": "payments-team", "tier": "1", "downstream_count": 15},
    {"node_id": "n_payment_service_refund", "service": "payment_service", "operation": "refund", "owner": "payments-team", "tier": "1", "downstream_count": 8},
    {"node_id": "n_payment_service_batch_charge", "service": "payment_service", "operation": "batch_charge", "owner": "payments-team", "tier": "1", "downstream_count": 12},
    {"node_id": "n_payment_service_validate_amount", "service": "payment_service", "operation": "validate_amount", "owner": "payments-team", "tier": "2", "downstream_count": 2},
    {"node_id": "n_order_service_create_order", "service": "order_service", "operation": "create_order", "owner": "orders-team", "tier": "2", "downstream_count": 8},
    {"node_id": "n_inventory_service_reserve", "service": "inventory_service", "operation": "reserve", "owner": "inventory-team", "tier": "3", "downstream_count": 3},
    {"node_id": "n_gateway_route", "service": "gateway", "operation": "route", "owner": "platform-team", "tier": "1", "downstream_count": 25},
]

MOCK_RISK_SCORES = [
    {"node_id": "n_payment_service_charge", "risk_score": 85, "risk_level": "critical", "blast_radius": 15, "incidents": 3, "p99": 2450, "confidence": 92, "service": "payment_service", "operation": "charge", "owner": "payments-team"},
    {"node_id": "n_payment_service_refund", "risk_score": 60, "risk_level": "high", "blast_radius": 8, "incidents": 1, "p99": 180, "confidence": 75, "service": "payment_service", "operation": "refund", "owner": "payments-team"},
    {"node_id": "n_payment_service_batch_charge", "risk_score": 72, "risk_level": "high", "blast_radius": 12, "incidents": 2, "p99": 980, "confidence": 80, "service": "payment_service", "operation": "batch_charge", "owner": "payments-team"},
    {"node_id": "n_payment_service_validate_amount", "risk_score": 30, "risk_level": "medium", "blast_radius": 2, "incidents": 0, "p99": 5, "confidence": 50, "service": "payment_service", "operation": "validate_amount", "owner": "payments-team"},
    {"node_id": "n_order_service_create_order", "risk_score": 45, "risk_level": "high", "blast_radius": 8, "incidents": 1, "p99": 380, "confidence": 78, "service": "order_service", "operation": "create_order", "owner": "orders-team"},
    {"node_id": "n_inventory_service_reserve", "risk_score": 25, "risk_level": "medium", "blast_radius": 3, "incidents": 0, "p99": 120, "confidence": 65, "service": "inventory_service", "operation": "reserve", "owner": "inventory-team"},
    {"node_id": "n_gateway_route", "risk_score": 92, "risk_level": "critical", "blast_radius": 25, "incidents": 4, "p99": 1800, "confidence": 95, "service": "gateway", "operation": "route", "owner": "platform-team"},
]

MOCK_INCIDENTS = [
    {"id": "INC-1029", "service": "payment_service", "operation": "charge", "severity": "high", "summary": "p99 latency spike 2.4s on payment_service.charge", "date": "2026-05-28T14:30:00Z"},
    {"id": "INC-876", "service": "payment_service", "operation": "charge", "severity": "critical", "summary": "Timeout cascade: payment_service.charge caused order_service timeout", "date": "2026-04-15T09:00:00Z"},
    {"id": "INC-543", "service": "payment_service", "operation": "charge", "severity": "high", "summary": "Database deadlock under load", "date": "2026-03-22T11:15:00Z"},
    {"id": "INC-210", "service": "gateway", "operation": "route", "severity": "critical", "summary": "Edge routing failure during peak traffic", "date": "2026-05-10T08:00:00Z"},
]


def main():
    backend = os.getenv("MAPPER_BACKEND", "mock")
    mock_dir = Path(__file__).parent.parent / "mock"
    mock_dir.mkdir(exist_ok=True)

    (mock_dir / "service_operation_map.json").write_text(
        json.dumps({"results": SEED_DATA}, indent=2)
    )
    (mock_dir / "risk_score_summary.json").write_text(
        json.dumps({"results": MOCK_RISK_SCORES}, indent=2)
    )
    (mock_dir / "incidents.json").write_text(
        json.dumps({"results": MOCK_INCIDENTS}, indent=2)
    )
    print(f"Mock data written to {mock_dir} (backend={backend})")

    if backend != "mock":
        print("WARNING: MAPPER_BACKEND=kvstore but Splunk may not be running.")
        print("Run with MAPPER_BACKEND=mock for offline demo.")


if __name__ == "__main__":
    main()
