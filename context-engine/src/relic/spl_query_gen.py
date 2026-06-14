import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class QueryIntent:
    intent: str
    service: Optional[str] = None
    operation: Optional[str] = None
    time_range: str = "-24h"
    raw_message: str = ""


class SPLQueryGenerator:
    _INTENT_PATTERNS = [
        (r"error[s]?\s+(?:in|for|from)\s+(\w+)", "error_query"),
        (r"error\s+rate\s+(?:for|in)\s+(\w+)", "error_query"),
        (r"(?:in|for|from)\s+(\w+).*error", "error_query"),
        (r"latency\s+(?:for|of|in)\s+(\w+)", "latency_query"),
        (r"slow\s+(\w+)", "latency_query"),
        (r"(\w+).*latency", "latency_query"),
        (r"incident[s]?\s+(?:in|for|of)\s+(\w+)", "incident_query"),
        (r"outage[s]?\s+(?:in|for)\s+(\w+)", "incident_query"),
        (r"who\s+calls?\s+(\w+)", "dependency_query"),
        (r"upstream\s+(?:of|for)\s+(\w+)", "dependency_query"),
        (r"downstream\s+(?:of|for)\s+(\w+)", "dependency_query"),
        (r"impact.*(\w+)", "dependency_query"),
        (r"risk.*(\w+)", "risk_query"),
        (r"what.*services?.*call", "service_graph"),
        (r"service.*graph", "service_graph"),
    ]

    _TIME_PATTERNS = [
        (r"last\s+hour", "-1h"),
        (r"last\s+(\d+)\s*h(?:ours?)?", lambda m: f"-{m.group(1)}h"),
        (r"last\s+24\s*h(?:ours?)?", "-24h"),
        (r"last\s+day", "-24h"),
        (r"last\s+(\d+)\s*d(?:ays?)?", lambda m: f"-{int(m.group(1))*24}h"),
        (r"last\s+week", "-7d"),
    ]

    def parse(self, message: str) -> QueryIntent:
        message_clean = message.strip().strip("?").strip()
        intent_type = "general_query"
        service = None
        time_range = "-24h"

        for pattern, intent in self._INTENT_PATTERNS:
            match = re.search(pattern, message_clean, re.IGNORECASE)
            if match:
                intent_type = intent
                if match.groups():
                    service = match.group(1)
                break

        for pattern, replacement in self._TIME_PATTERNS:
            match = re.search(pattern, message_clean, re.IGNORECASE)
            if match:
                if callable(replacement):
                    time_range = replacement(match)
                else:
                    time_range = replacement
                break

        return QueryIntent(intent=intent_type, service=service, time_range=time_range, raw_message=message_clean)

    def generate(self, intent: QueryIntent) -> str:
        if intent.intent == "error_query":
            return self._generate_error(intent)
        elif intent.intent == "latency_query":
            return self._generate_latency(intent)
        elif intent.intent == "incident_query":
            return self._generate_incident(intent)
        elif intent.intent == "dependency_query":
            return self._generate_dependency(intent)
        else:
            return self._generate_general(intent)

    def _generate_error(self, intent: QueryIntent) -> str:
        svc = intent.service or "*"
        return f"index=app sourcetype=logs service={svc} level=ERROR earliest={intent.time_range} | stats count by operation, message | sort -count"

    def _generate_latency(self, intent: QueryIntent) -> str:
        svc = intent.service or "*"
        return f"index=apm metric=latency_p99_ms service={svc} earliest={intent.time_range} | stats latest(value) as p99 by service, operation | sort -p99"

    def _generate_incident(self, intent: QueryIntent) -> str:
        svc = intent.service or "*"
        return f"index=incidents service={svc} earliest={intent.time_range} | table id, severity, summary, duration_minutes | sort -severity"

    def _generate_dependency(self, intent: QueryIntent) -> str:
        svc = intent.service or "*"
        return f"index=apm service={svc} | stats count by operation, parent_operation | sort -count"

    def _generate_general(self, intent: QueryIntent) -> str:
        svc = intent.service or "*"
        return f"index=app service={svc} earliest={intent.time_range} | head 50"

    def generate_suggestions(self, intent: QueryIntent) -> list[str]:
        svc = intent.service or "your service"
        suggestions = [
            f"Show latency trend for {svc}",
            f"What services call {svc}?",
            f"Show recent incidents for {svc}",
        ]
        return suggestions