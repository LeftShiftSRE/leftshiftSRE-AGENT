RISK_SCORES = {
    "n_payment_service_charge": {
        "node_id": "n_payment_service_charge",
        "service": "payment_service",
        "operation": "charge",
        "risk_score": 85,
        "risk_level": "critical",
        "blast_radius": 15,
        "incidents_30d": 3,
        "p99_ms": 2450,
        "confidence": 92,
        "owner": "payments-team",
    },
    "n_payment_service_refund": {
        "node_id": "n_payment_service_refund",
        "service": "payment_service",
        "operation": "refund",
        "risk_score": 60,
        "risk_level": "high",
        "blast_radius": 8,
        "incidents_30d": 1,
        "p99_ms": 180,
        "confidence": 75,
        "owner": "payments-team",
    },
    "n_payment_service_batch_charge": {
        "node_id": "n_payment_service_batch_charge",
        "service": "payment_service",
        "operation": "batch_charge",
        "risk_score": 72,
        "risk_level": "high",
        "blast_radius": 12,
        "incidents_30d": 2,
        "p99_ms": 980,
        "confidence": 80,
        "owner": "payments-team",
    },
    "n_payment_service_validate_amount": {
        "node_id": "n_payment_service_validate_amount",
        "service": "payment_service",
        "operation": "validate_amount",
        "risk_score": 30,
        "risk_level": "medium",
        "blast_radius": 2,
        "incidents_30d": 0,
        "p99_ms": 5,
        "confidence": 50,
        "owner": "payments-team",
    },
    "n_order_service_create_order": {
        "node_id": "n_order_service_create_order",
        "service": "order_service",
        "operation": "create_order",
        "risk_score": 45,
        "risk_level": "high",
        "blast_radius": 8,
        "incidents_30d": 1,
        "p99_ms": 380,
        "confidence": 78,
        "owner": "orders-team",
    },
    "n_inventory_service_reserve": {
        "node_id": "n_inventory_service_reserve",
        "service": "inventory_service",
        "operation": "reserve",
        "risk_score": 25,
        "risk_level": "medium",
        "blast_radius": 3,
        "incidents_30d": 0,
        "p99_ms": 120,
        "confidence": 65,
        "owner": "inventory-team",
    },
    "n_gateway_route": {
        "node_id": "n_gateway_route",
        "service": "gateway",
        "operation": "route",
        "risk_score": 92,
        "risk_level": "critical",
        "blast_radius": 25,
        "incidents_30d": 4,
        "p99_ms": 1800,
        "confidence": 95,
        "owner": "platform-team",
    },
}

INCIDENTS = [
    {
        "id": "INC-1029",
        "service": "payment_service",
        "operation": "charge",
        "severity": "high",
        "summary": "p99 latency spike 2.4s on payment_service.charge",
        "date": "2026-05-28T14:30:00Z",
    },
    {
        "id": "INC-876",
        "service": "payment_service",
        "operation": "charge",
        "severity": "critical",
        "summary": "Timeout cascade: payment_service.charge caused order_service timeout",
        "date": "2026-04-15T09:00:00Z",
    },
    {
        "id": "INC-543",
        "service": "payment_service",
        "operation": "charge",
        "severity": "high",
        "summary": "Database deadlock under load",
        "date": "2026-03-22T11:15:00Z",
    },
    {
        "id": "INC-210",
        "service": "gateway",
        "operation": "route",
        "severity": "critical",
        "summary": "Edge routing failure during peak traffic",
        "date": "2026-05-10T08:00:00Z",
    },
    {
        "id": "INC-312",
        "service": "gateway",
        "operation": "route",
        "severity": "high",
        "summary": "DNS resolution timeout causing 502s",
        "date": "2026-04-02T16:45:00Z",
    },
    {
        "id": "INC-445",
        "service": "order_service",
        "operation": "create_order",
        "severity": "medium",
        "summary": "Slow order creation due to payment dependency",
        "date": "2026-03-10T10:00:00Z",
    },
]

SERVICE_OPERATION_MAP = {
    ("payment_service", "charge"): "n_payment_service_charge",
    ("payment_service", "refund"): "n_payment_service_refund",
    ("payment_service", "batch_charge"): "n_payment_service_batch_charge",
    ("payment_service", "validate_amount"): "n_payment_service_validate_amount",
    ("order_service", "create_order"): "n_order_service_create_order",
    ("inventory_service", "reserve"): "n_inventory_service_reserve",
    ("gateway", "route"): "n_gateway_route",
}


def mock_search(query: str) -> dict:
    q = query.lower()

    if "risk_score_summary" in q or "risk_score_for_nodes" in q:
        node_filter = None
        if "where node_id in" in q:
            import re
            match = re.search(r'node_id in \(([^)]+)\)', q)
            if match:
                node_filter = set(
                    n.strip().strip('"').strip("'")
                    for n in match.group(1).split(",")
                )
        results = []
        for node_id, data in RISK_SCORES.items():
            if node_filter is None or node_id in node_filter:
                results.append(data)
        return {"results": results}

    if "incident" in q:
        if 'service="' in q:
            svc = q.split('service="')[1].split('"')[0]
            return {"results": [i for i in INCIDENTS if i["service"] == svc]}
        return {"results": INCIDENTS}

    if "service_operation_map" in q:
        results = [
            {"node_id": nid, "service": s, "operation": o}
            for (s, o), nid in SERVICE_OPERATION_MAP.items()
        ]
        return {"results": results}

    if "latency" in q or "p99" in q:
        return {
            "results": [
                {
                    "service": d["service"],
                    "operation": d["operation"],
                    "p99_ms": d["p99_ms"],
                }
                for d in RISK_SCORES.values()
            ]
        }

    return {"results": []}
