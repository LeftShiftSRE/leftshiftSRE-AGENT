import numpy as np

INTENT_CATALOG = {
    "errors_by_service": {
        "description": "Show top errors for a service",
        "keywords": ["error", "exception", "fail", "crash", "500"],
        "spl": 'index=app sourcetype=logs level=ERROR service="$service$" earliest=-24h | stats count by operation, message | sort -count | head 20',
        "params": {"service": "payment_service"},
    },
    "latency_p99_by_service": {
        "description": "Show p99 latency trend for a service",
        "keywords": ["latency", "slow", "p99", "performance", "response time"],
        "spl": 'index=apm metric=latency_p99_ms service="$service$" earliest=-24h | stats latest(value) as p99 by service, operation | sort -p99 | head 20',
        "params": {"service": "payment_service"},
    },
    "incidents_by_service": {
        "description": "Show recent incidents for a service",
        "keywords": ["incident", "outage", "sev", "p1", "p2", "postmortem"],
        "spl": 'index=incidents service="$service$" earliest=-30d | table id, severity, summary, date',
        "params": {"service": "payment_service"},
    },
    "upstream_downstream_calls": {
        "description": "Show call graph dependencies",
        "keywords": ["depend", "calls", "upstream", "downstream", "graph", "blast"],
        "spl": 'index=apm service="$service$" earliest=-24h | stats count by operation, parent_operation | sort -count | head 20',
        "params": {"service": "payment_service"},
    },
    "risk_score_summary": {
        "description": "Show risk scores for modified code",
        "keywords": ["risk", "score", "danger", "safe", "blast radius"],
        "spl": '| inputlookup risk_score_summary | sort -risk_score | head 20',
        "params": {},
    },
    "metric_forecast": {
        "description": "Forecast a metric using MLTK predict",
        "keywords": ["forecast", "predict", "trend", "future", "projection"],
        "spl": 'index=apm metric="$metric$" earliest=-7d | timechart span=5m avg(value) as metric_value | predict metric_value algorithm=LLP5 future_timespan=12',
        "params": {"metric": "latency_p99_ms"},
    },
}

ALLOWED_VERBS = {
    "stats",
    "timechart",
    "inputlookup",
    "join",
    "lookup",
    "eval",
    "where",
    "search",
    "sort",
    "head",
    "fields",
    "table",
    "rex",
    "spath",
    "predict",
    "anomaly",
}
BLOCKED_VERBS = {
    "delete",
    "drop",
    "outputlookup",
    "collect",
    "summaryindex",
    "script",
    "map",
    "foreach",
}

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _extract_service(message: str) -> str | None:
    for svc in (
        "payment_service",
        "order_service",
        "inventory_service",
        "gateway",
    ):
        if svc in message.lower():
            return svc
    return None


def match_intent(message: str) -> dict | None:
    msg_lower = message.lower()
    service = _extract_service(message)

    for name, intent in INTENT_CATALOG.items():
        for kw in intent["keywords"]:
            if kw in msg_lower:
                result = {"name": name, **intent}
                if service:
                    result["params"] = {
                        **intent.get("params", {}),
                        "service": service,
                    }
                return result

    model = _get_model()
    query_emb = model.encode(message)

    best_name = None
    best_score = 0.0

    for name, intent in INTENT_CATALOG.items():
        desc_emb = model.encode(intent["description"])
        score = float(
            np.dot(query_emb, desc_emb)
            / (np.linalg.norm(query_emb) * np.linalg.norm(desc_emb))
        )
        if score > best_score:
            best_score = score
            best_name = name

    if best_score > 0.5 and best_name:
        result = {"name": best_name, **INTENT_CATALOG[best_name]}
        if service:
            result["params"] = {
                **INTENT_CATALOG[best_name].get("params", {}),
                "service": service,
            }
        return result
    return None


def validate_spl(spl: str) -> bool:
    tokens = spl.lower().split()
    for verb in BLOCKED_VERBS:
        if verb in tokens:
            return False
    return any(v in tokens for v in ALLOWED_VERBS)
