import re
from dataclasses import dataclass, field
from typing import Optional

from relic.splunk_client import SplunkMCPClient


@dataclass
class QueryIntent:
    intent: str
    service: Optional[str] = None
    operation: Optional[str] = None
    time_range: str = "-24h"
    raw_message: str = ""
    spl_query: Optional[str] = None
    explanation: Optional[str] = None
    source: str = "regex"


class SPLQueryGenerator:
    def __init__(self, splunk_client: SplunkMCPClient | None = None):
        self.splunk_client = splunk_client

    def parse(self, message: str) -> QueryIntent:
        message_clean = message.strip().strip("?").strip()
        intent_type = "general_query"
        service = None
        time_range = "-24h"

        for word in message_clean.replace(",", " ").replace("_", " ").split():
            clean = word.strip().rstrip("?")
            if not clean:
                continue
            if clean in ("service", "Service", "the", "a", "an", "for", "in", "from", "has", "had", "me", "my", "show", "what", "which", "who", "where"):
                continue
            if clean in ("payment", "order", "inventory", "gateway", "api", "auth", "user"):
                service = clean + "_service" if clean not in ("api", "auth", "user") else clean
                continue
            if any(svc in clean for svc in ("payment", "order", "inventory", "gateway")):
                service = clean.replace(" ", "_")

        error_words = re.findall(r"\berror[s]?\b", message_clean, re.I)
        latency_words = re.findall(r"\blatency\b", message_clean, re.I)
        incident_words = re.findall(r"\bincident[s]?\b|\boutage[s]?\b", message_clean, re.I)
        who_calls = re.findall(r"\bwho calls?\b|\bupstream\b|\bdownstream\b", message_clean, re.I)
        risk_words = re.findall(r"\brisk\b", message_clean, re.I)
        forecast_words = re.findall(r"\bforecast\b|\bpredict\b|\btrend\b", message_clean, re.I)

        if error_words:
            intent_type = "error_query"
        elif latency_words:
            intent_type = "latency_query"
        elif incident_words:
            intent_type = "incident_query"
        elif who_calls:
            intent_type = "dependency_query"
        elif risk_words:
            intent_type = "risk_query"
        elif forecast_words:
            intent_type = "forecast_query"
        else:
            intent_type = "general_query"

        time_patterns = [
            (r"last\s+hour\b", "-1h"),
            (r"last\s+(\d+)\s*h(?:ours?)?\b", lambda m: f"-{m.group(1)}h"),
            (r"last\s+24\s*h(?:ours?)?\b", "-24h"),
            (r"last\s+day\b", "-24h"),
            (r"last\s+(\d+)\s*d(?:ays?)?\b", lambda m: f"-{int(m.group(1))*24}h"),
            (r"last\s+week\b", "-7d"),
            (r"last\s+month\b", "-30d"),
        ]

        for pattern, replacement in time_patterns:
            match = re.search(pattern, message_clean, re.I)
            if match:
                if callable(replacement):
                    time_range = replacement(match)
                else:
                    time_range = replacement
                break

        return QueryIntent(
            intent=intent_type,
            service=service,
            time_range=time_range,
            raw_message=message_clean,
        )

    def generate(self, intent: QueryIntent) -> str:
        if self.splunk_client and intent.raw_message:
            ai_result = self.splunk_client.ai_generate_spl(intent.raw_message)
            if ai_result and ai_result.get("spl_query"):
                intent.spl_query = ai_result["spl_query"]
                intent.explanation = ai_result.get("explanation")
                intent.source = ai_result.get("source", "ai_assistant")
                return intent.spl_query

        return self._regex_generate(intent)

    def explain(self, spl_query: str) -> str:
        if self.splunk_client:
            result = self.splunk_client.ai_explain_spl(spl_query)
            return result.get("explanation", "No explanation available")
        return "AI Assistant not connected"

    def _regex_generate(self, intent: QueryIntent) -> str:
        svc = intent.service or "*"
        intent.source = "regex"

        if intent.intent == "error_query":
            return f"index=app sourcetype=logs service={svc} level=ERROR earliest={intent.time_range} | stats count by operation, message | sort -count | head 20"
        elif intent.intent == "latency_query":
            return f"index=apm metric=latency_p99_ms service={svc} earliest={intent.time_range} | stats latest(value) as p99 by service, operation | sort -p99 | head 20"
        elif intent.intent == "incident_query":
            return f"index=incidents service={svc} earliest={intent.time_range} | table id, severity, summary, duration_minutes | sort -severity"
        elif intent.intent == "dependency_query":
            return f"index=apm service={svc} | stats count by operation, parent_operation | sort -count | head 20"
        elif intent.intent == "risk_query":
            return f"index=incidents service={svc} earliest={intent.time_range} | stats count as incident_count, max(severity) as worst_severity by service, operation"
        elif intent.intent == "forecast_query":
            return f"index=apm service={svc} earliest={intent.time_range} | timechart span=5m avg(value) as metric_value"
        else:
            return f"index=app service={svc} earliest={intent.time_range} | head 50"

    def generate_suggestions(self, intent: QueryIntent) -> list[str]:
        svc = intent.service or "your service"
        suggestions = [
            f"Show latency trend for {svc}",
            f"What services call {svc}?",
            f"Show recent incidents for {svc}",
            f"Risk analysis for {svc}",
        ]
        if intent.intent not in ("forecast_query",):
            suggestions.append(f"Forecast next hour for {svc}")

        return [s for s in suggestions if svc not in s or s]
