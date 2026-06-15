# Relic — System Architecture & Data Flow Reference

## 1. High-Level Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DEVELOPER MACHINE                                  │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    VS CODE EXTENSION (TypeScript)                        │   │
│  │                                                                         │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │   │
│  │  │ RiskProvider  │  │ ImpactMap    │  │ ChatProvider │  │ Dashboard  │ │   │
│  │  │ (status bar + │  │ (tree view   │  │ (webview     │  │ (webview   │ │   │
│  │  │  decorations) │  │  sidebar)    │  │  panel)      │  │  NEW)      │ │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │   │
│  │         │                 │                  │                │         │   │
│  │         └────────┬────────┴─────────┬────────┘                │         │   │
│  │                  ▼                  ▼                         │         │   │
│  │         ┌───────────────────────────────────────┐            │         │   │
│  │         │      McpClientManager                 │            │         │   │
│  │         │  (JSON-RPC 2.0 over stdio)            │◄───────────┘         │   │
│  │         │  - callTool(name, args)               │                      │   │
│  │         │  - 9 tool methods → context-engine     │                      │   │
│  │         └───────────────┬───────────────────────┘                      │   │
│  │                         │ stdin/stdout (JSON-RPC)                       │   │
│  └─────────────────────────┼──────────────────────────────────────────────┘   │
│                            │                                                   │
│  ┌─────────────────────────▼──────────────────────────────────────────────┐   │
│  │               CONTEXT ENGINE (Python MCP Server)                       │   │
│  │                                                                        │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────────┐│   │
│  │  │ CtxParser  │ │ CtxGraph   │ │ RiskScorer │ │ SPLQueryGenerator   ││   │
│  │  │ (tree-sitter│ │ (adj.list  │ │ (weighted  │ │ (regex heuristic    ││   │
│  │  │  → .ctx)   │ │  BFS)      │ │  formula)  │ │  → SPL) [REPLACE]   ││   │
│  │  └─────┬──────┘ └─────┬──────┘ └──────┬─────┘ └───────┬──────────────┘│   │
│  │        │              │               │                │              │   │
│  │        ▼              ▼               ▼                ▼              │   │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │   │
│  │  │                    RelicMCPServer                                │ │   │
│  │  │  9 MCP tools: get_context_summary, get_node, search_nodes,      │ │   │
│  │  │  get_edges, get_code_span, get_risk_score,                     │ │   │
│  │  │  sre_chat_query, map_metric_to_code, get_incident_history       │ │   │
│  │  │  + get_dashboard_data [NEW]                                     │ │   │
│  │  │  + investigate_incident [NEW]                                   │ │   │
│  │  └──────────────────────┬──────────────────────────────────────────┘ │   │
│  │                         │                                            │   │
│  │  ┌──────────────────────▼──────────────────────────────────────────┐ │   │
│  │  │               SplunkClient                                       │ │   │
│  │  │  CURRENT: _execute_spl() → POST /services/search/jobs (raw REST)│ │   │
│  │  │  [REPLACE WITH] → MCP Server tool calls                         │ │   │
│  │  │  + ai_assistant_spl() → MCP "generate_spl" tool [NEW]           │ │   │
│  │  │  + ai_explain_spl() → MCP "explain_spl" tool [NEW]             │ │   │
│  │  └──────────────┬──────────────────────────────────────────────────┘ │   │
│  └─────────────────┼──────────────────────────────────────────────────────┘   │
│                    │                                                           │
│                    │ HTTP/HTTPS (Bearer token auth)                           │
│  ┌─────────────────▼──────────────────────────────────────────────────────┐   │
│  │              SPLUNK ENTERPRISE (localhost:8000/8089)                    │   │
│  │                                                                        │   │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │   │
│  │  │           Splunk MCP Server App (Splunkbase #7931)              │ │   │
│  │  │  Tools exposed: search, indexed_search, saved_search,           │ │   │
│  │  │  generate_spl (AI Assistant), explain_spl (AI Assistant),       │ │   │
│  │  │  list_indexes, get_knowledge_objects                           │ │   │
│  │  └──────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                        │   │
│  │  ┌────────┐  ┌────────┐  ┌──────────┐  ┌──────────────┐  ┌─────────┐ │   │
│  │  │  app   │  │  apm   │  │incidents │  │ AI Toolkit   │  │Hosted   │ │   │
│  │  │ index  │  │ index  │  │  index   │  │ (ML models)  │  │Models   │ │   │
│  │  │(logs)  │  │(metrics│  │(incident │  │              │  │(Dense TS│ │   │
│  │  │        │  │ /trace)│  │ records) │  │              │  │ Security│ │   │
│  │  └────────┘  └────────┘  └──────────┘  └──────────────┘  └─────────┘ │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │              DEMO MICROSERVICES (FastAPI, Docker Compose)                │  │
│  │                                                                          │  │
│  │  ┌──────────┐    ┌─────────────┐    ┌─────────────────┐  ┌───────────┐ │  │
│  │  │ gateway  │───▶│order_service│───▶│payment_service   │  │inventory  │ │  │
│  │  │ :8000    │    │ :8001       │    │:8002 (N+1 query)│  │:8003      │ │  │
│  │  └──────────┘    └─────────────┘    └─────────────────┘  └───────────┘ │  │
│  │        │                                      │                        │  │
│  │        │  HTTP Event Collector (HEC) [NEW]    │  HEC [NEW]             │  │
│  │        └──────────────────────────────────────┘                        │  │
│  │                        │                                                │  │
│  │                        ▼ Real-time log/metrics streaming                │  │
│  │                   Splunk :8088 (HEC endpoint)                          │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Inventory

| # | Component | Language | Location | Role |
|---|-----------|----------|----------|------|
| C1 | VS Code Extension | TypeScript | `relic-vscode/src/` | UI layer — status bar, decorations, tree view, chat, dashboard |
| C2 | McpClientManager | TypeScript | `relic-vscode/src/mcpClient.ts` | JSON-RPC 2.0 client — spawns context-engine, routes tool calls |
| C3 | Context Engine Server | Python | `context-engine/src/relic/server.py` | MCP Server (stdio) — exposes 9+ tools, orchestrates all logic |
| C4 | CtxParser | Python | `context-engine/src/relic/parser.py` | Tree-sitter Python AST → `.ctx` YAML structural graph |
| C5 | CtxGraph | Python | `context-engine/src/relic/graph.py` | In-memory adjacency-list graph with BFS traversal, search, critical path detection |
| C6 | RiskScorer | Python | `context-engine/src/relic/risk.py` | Weighted formula: blast_radius×0.3 + incidents×0.5 + criticality×0.2 |
| C7 | SPLQueryGenerator | Python | `context-engine/src/relic/spl_query_gen.py` | Regex intent parser → template SPL queries [TO BE REPLACED with AI Assistant] |
| C8 | SplunkClient | Python | `context-engine/src/relic/splunk_client.py` | HTTP client to Splunk (raw REST) [TO BE REPLACED with MCP Server tool calls] |
| C9 | OTelMapper | Python | `context-engine/src/relic/otel_mapper.py` | service.operation → .ctx node_id lookup from YAML mapping |
| C10 | Demo Microservices | Python | `demo-services/` | 4 FastAPI services: gateway, order, payment, inventory |
| C11 | Splunk Enterprise | — | localhost:8000 | Observability platform — indexes, search, AI capabilities |
| C12 | Splunk MCP Server App | — | Splunkbase #7931 | MCP interface to Splunk data and AI tools |

---

## 3. Data Structures — Every Object in the System

### 3.1 `.ctx` Graph Data (C4 → YAML → C5)

**CtxDocument** (the YAML file `repo.ctx`):
```yaml
metadata:
  repo_id: string           # Repository folder name
  generated_at: ISO8601     # Parse timestamp
  language: "python"
  version: "1.0"
  parser: "tree-sitter-python@0.25.0"
  parse_time_seconds: float

nodes:                      # List of GraphNode dicts
  - id: string              # Content-addressable: n_{kind_initial}_{sanitized_name}_{sha256[:12]}
    kind: string             # "file" | "function" | "class" | "import" | "method"
    name: string             # Symbol name (function name, class name, import path)
    path: string             # Relative file path from repo root
    span:
      start_line: int        # 1-indexed
      end_line: int
    signature: string|null   # First line of definition (e.g., "def charge(amount, currency)")
    parent: string|null      # Parent node_id (class for methods, file for top-level)

edges:                      # List of GraphEdge dicts
  - from: string             # Source node_id
    to: string               # Target node_id
    type: string             # "calls" | "contains" | "imports" | "inherits"

interfaces: []               # (reserved, not yet populated)

span_map:                    # node_id → {file, start_line, end_line}
  n_f_charge_abc123:
    file: string
    start_line: int
    end_line: int
```

**GraphNode** (in-memory C5):
```python
@dataclass GraphNode:
    id: str                  # e.g., "n_f_charge_2a3b4c5d6e7f"
    kind: str                # "file" | "function" | "class" | "import" | "method"
    name: str                # "charge"
    path: str                # "payment_service/main.py"
    start_line: int          # 8
    end_line: int            # 25
    signature: str | None    # "def charge(amount: float, currency: str)"
    parent: str | None       # "n_f_main_py_a1b2c3"
```

**GraphEdge** (in-memory C5):
```python
@dataclass GraphEdge:
    from_node: str           # Source node_id
    to_node: str             # Target node_id
    edge_type: str           # "calls" | "contains" | "imports" | "inherits"
```

### 3.2 Splunk Data (Indexed in C11)

**App Logs** (`index=app`):
```json
{
  "timestamp": "2026-06-14T10:00:00Z",
  "service": "payment_service",
  "operation": "charge",
  "level": "ERROR",
  "message": "ConnectionTimeout: database connection pool exhausted",
  "trace_id": "abc123",
  "user_id": "usr_456"
}
```

**APM Metrics** (`index=apm`):
```json
{
  "timestamp": "2026-06-14T10:00:00Z",
  "service": "payment_service",
  "operation": "charge",
  "metric": "latency_p99_ms",
  "value": 2400
}
```
Other metric types: `latency_p95_ms`, `error_rate`, `throughput_rps`, `db_pool_usage_pct`

**Incidents** (`index=incidents`):
```json
{
  "id": "INC-1029",
  "service": "payment_service",
  "operation": "charge",
  "date": "2026-05-28T14:30:00Z",
  "severity": "high",
  "type": "latency_spike",
  "summary": "p99 latency spike 2.4s on payment_service.charge",
  "duration_minutes": 45,
  "affected_users": 4500,
  "metrics": {
    "p99_latency_ms": 2400,
    "p95_latency_ms": 1200,
    "error_rate": 0.03,
    "throughput_rps": 450
  }
}
```

### 3.3 OTel Mapping (C9 ↔ C5 bridge)

**otel_mapping.yaml**:
```yaml
mappings:
  - service: "payment_service"
    operation: "charge"
    node_id: "n_f_charge_abc123"     # Links Splunk service.operation → .ctx node
    description: "PaymentService.charge() — the main payment processing function"
```

**OTelMapper** (in-memory):
```python
OTelMapper:
    mappings: list[dict]    # Each: {service: str, operation: str, node_id: str | None}

    lookup(service, operation) → node_id | None
    service_to_node_ids(service) → list[str]
    all_services() → list[str]
    all_operations(service) → list[str]
```

### 3.4 Incident & Risk Data (C6)

**Incident** (Python):
```python
@dataclass Incident:
    id: str              # "INC-1029"
    service: str         # "payment_service"
    operation: str       # "charge"
    date: str            # "2026-05-28T14:30:00Z"
    severity: str        # "critical" | "high" | "medium" | "low"
    incident_type: str   # "latency_spike" | "timeout_cascade" | "error_rate_spike"
    summary: str         # Human-readable description
    metrics: dict        # {p99_latency_ms, p95_latency_ms, error_rate, throughput_rps}
```

**NodeRiskScore** (Python):
```python
@dataclass NodeRiskScore:
    node_id: str
    node_name: str
    score: int             # 0-100
    level: str             # "low" | "medium" | "critical"
    reasons: list[str]     # ["3 downstream functions affected", "Similar change caused INC-1029"]
    incidents: list[dict]  # Matching incident summaries
    downstream_dependents: list[dict]  # [{node_id, name, path}]
    upstream_callers: list[dict]        # [{node_id, name, path}]
```

**RiskResult** (Python):
```python
@dataclass RiskResult:
    overall_score: int     # 0-100
    level: str             # "low" | "medium" | "critical"
    node_scores: list[NodeRiskScore]
```

### 3.5 SPL Query & SRE Chat Data (C7 → C8)

**QueryIntent** (Python, parsed from natural language):
```python
@dataclass QueryIntent:
    intent: str            # "error_query" | "latency_query" | "incident_query" | "dependency_query" | "risk_query" | "general_query"
    service: str | None    # "payment_service" (extracted from message)
    operation: str | None  # "charge" (not currently extracted)
    time_range: str        # "-24h" | "-1h" | "-7d" | "-30d"
    raw_message: str       # Original user message
```

**SREChatResult** (returned to VS Code):
```json
{
  "intent": "error_query",
  "spl_query": "index=app service=payment_service level=ERROR earliest=-24h | stats count by operation, message | sort -count | head 20",
  "results": [
    {"operation": "charge", "message": "ConnectionTimeout: ...", "count": 47}
  ],
  "code_mappings": [
    {"node_id": "n_f_charge_abc123", "file": "payment_service/main.py", "line": 8, "function": "charge"}
  ],
  "suggestions": [
    "Show latency trend for payment_service",
    "What services call payment_service?"
  ]
}
```

### 3.6 MCP Tool Call Wire Format (C2 ↔ C3)

**Request** (VS Code → Context Engine, over stdin):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_risk_score",
    "arguments": {
      "repo_path": "/path/to/repo",
      "modified_files": ["payment_service/main.py"]
    }
  }
}
```

**Response** (Context Engine → VS Code, over stdout):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "type": "text",
    "text": "{\"overall_score\": 87, \"level\": \"critical\", ...}"
  }
}
```

---

## 4. Data Flow — End-to-End Per Feature

### 4.1 Feature A: Code-Risk Predictor

```
Developer saves .py file
        │
        ▼
[VS Code] onDidSaveTextDocument fires (only if .py file)
        │
        ▼
[RiskProvider] getModifiedPythonFiles()
  → scans visible editors → ["payment_service/main.py"]
        │
        ▼
[McpClientManager] callTool("get_risk_score", {repo_path, modified_files})
        │ JSON-RPC over stdio
        ▼
[RelicMCPServer] handle_get_risk_score(repo_path, modified_files)
        │
        ├─▶ [RiskScorer] _find_modified_nodes(["payment_service/main.py"])
        │     → matches nodes WHERE node.path IN modified_files AND node.kind IN (function, class, method)
        │     → returns [GraphNode(id="n_f_charge_abc", name="charge", path="payment_service/main.py")]
        │
        ├─▶ [RiskScorer] _score_node(charge_node)
        │     │
        │     ├─▶ [CtxGraph] traverse(node_id, "downstream", "calls", depth=3)
        │     │     → BFS → [db_query(), validate_card(), ...] → blast_radius = 3
        │     │
        │     ├─▶ [CtxGraph] traverse(node_id, "upstream", "calls", depth=2)
        │     │     → BFS → [create_order(), POST /order] → upstream_callers
        │     │
        │     ├─▶ [CtxGraph] find_critical_paths()
        │     │     → DFS from gateway files → is charge() on critical path? → YES
        │     │
        │     ├─▶ [SplunkClient] get_incidents_for_node("n_f_charge_abc")
        │     │     │ IF mock: filter _mock_incidents WHERE service IN node.path
        │     │     │ IF real: SPL query → index=incidents | where service="payment_service"
        │     │     → [INC-1029, INC-876]
        │     │
        │     └─▶ Compute raw_score = 0.3×(3/20) + 0.5×(2×0.3) + 0.2×1.0 = 0.045+0.3+0.2 = 0.545 → 54
        │            (blast_radius=3, incident_score=0.6, is_critical=true)
        │
        └─▶ Build RiskResult {overall_score: 87, level: "critical", node_scores: [...]}
        │
        ▼
[VS Code] receives JSON response
        │
        ├─▶ [RiskProvider] updateStatusBar() → "✕ Relic: 87/100" (red)
        ├─▶ [RiskProvider] applyDecorators() → inline "⚠ Risk 87/100" on charge() line
        └─▶ [ImpactProvider] refresh() → tree view shows charge → callers → dependents → incidents
```

**Data flowing in this feature:**
| Step | Source → Destination | Data Format |
|------|---------------------|-------------|
| 1 | VS Code → RiskProvider | File path string |
| 2 | RiskProvider → McpClient | `{repo_path, modified_files: [str]}` |
| 3 | McpClient → Context Engine | JSON-RPC `{method: "tools/call", params: {name, arguments}}` |
| 4 | Context Engine → CtxGraph | `modified_files → [GraphNode]` via path matching |
| 5 | CtxGraph → RiskScorer | `[GraphNode]` via BFS/DFS traversal |
| 6 | RiskScorer → SplunkClient | `node_id → [Incident]` via SPL or mock |
| 7 | RiskScorer → RiskResult | Weighted score computation → `{overall_score, level, node_scores}` |
| 8 | Context Engine → McpClient | JSON-RPC `{result: {text: JSON_string}}` |
| 9 | McpClient → RiskProvider | `RiskResult` (parsed from JSON) |
| 10 | RiskProvider → VS Code UI | Status bar text + decoration ranges |

### 4.2 Feature B: SRE Chat

```
Developer types "What errors has payment_service had in the last 24h?"
        │
        ▼
[ChatProvider] handleMessage({type: "send", text: "..."})
        │
        ▼
[McpClientManager] callTool("sre_chat_query", {message: "What errors..."})
        │ JSON-RPC over stdio
        ▼
[RelicMCPServer] handle_sre_chat_query("What errors has payment_service had?")
        │
        ├─▶ [SPLQueryGenerator] parse(message)
        │     → regex matching: "errors" → intent="error_query", "payment" → service="payment_service"
        │     → QueryIntent{intent="error_query", service="payment_service", time_range="-24h"}
        │
        ├─▶ [SPLQueryGenerator] generate(intent)
        │     → "index=app service=payment_service level=ERROR earliest=-24h | stats count by operation, message | sort -count | head 20"
        │
        ├─▶ [SplunkClient] search(spl_query)
        │     │ IF mock: _mock_search() → hardcoded result based on "error" + "count" keywords
        │     │ IF real: _execute_spl() → POST /services/search/jobs → parse results
        │     → [{operation:"charge", message:"ConnectionTimeout...", count:47}, ...]
        │
        ├─▶ [OTelMapper] lookup("payment_service", "charge")
        │     → "n_f_charge_abc123" (if mapping exists)
        │     → [CtxGraph].get_node(node_id) → GraphNode → code_mappings [{node_id, file, line, function}]
        │
        ├─▶ [SPLQueryGenerator] generate_suggestions(intent)
        │     → ["Show latency trend for payment_service", ...]
        │
        └─▶ Build SREChatResult {intent, spl_query, results, code_mappings, suggestions}
        │
        ▼
[ChatProvider] formats response as markdown → renders in webview
  **Intent:** error_query
  **Generated SPL:** ```spl ... ```
  **Results (3):** | Operation | Value | ...
  **Code mappings:** charge() → payment_service/main.py:8
  **Suggestions:** ...
```

**Data flowing in this feature:**
| Step | Source → Destination | Data Format |
|------|---------------------|-------------|
| 1 | User → ChatProvider | Natural language string |
| 2 | ChatProvider → McpClient | `{message: str}` |
| 3 | McpClient → Context Engine | JSON-RPC `sre_chat_query` |
| 4 | Context Engine → SPLQueryGen | Natural language → `QueryIntent` |
| 5 | SPLQueryGen → Context Engine | `QueryIntent → SPL string` |
| 6 | Context Engine → SplunkClient | `SPL string → [result dicts]` (via REST or mock) |
| 7 | Context Engine → OTelMapper | `service+operation → node_id` |
| 8 | OTelMapper → CtxGraph | `node_id → GraphNode` |
| 9 | Context Engine → McpClient | `SREChatResult JSON` |
| 10 | ChatProvider → Webview | Markdown-formatted response |

### 4.3 Feature C: Generative Dashboard (NEW)

```
Developer opens Dashboard panel
        │
        ▼
[DashboardProvider] show()
        │
        ▼
[McpClientManager] callTool("get_dashboard_data", {})
        │ JSON-RPC over stdio
        ▼
[RelicMCPServer] handle_get_dashboard_data()
        │
        ├─▶ [SplunkClient] search("index=app | stats count by service, level")
        │     → service health data: [{service, level, count}, ...]
        │
        ├─▶ [SplunkClient] search("index=apm metric=latency_p99_ms | timechart avg(value) by service")
        │     → latency time-series data
        │
        ├─▶ [SplunkClient] search("index=apm metric=error_rate | stats latest(value) by service")
        │     → error rates per service
        │
        ├─▶ [SplunkClient] search("index=incidents | sort -timestamp | head 20")
        │     → incident timeline data
        │
        ├─▶ [CtxGraph] get_context_summary()
        │     → {files, classes, functions, packages}
        │
        └─▶ Build DashboardData {services, metrics, incidents, topology}
        │
        ▼
[DashboardProvider] renders webview:
  - Service Health Grid (RED/YELLOW/GREEN cards)
  - Latency Trend Chart (Chart.js line chart)
  - Error Rate Sparklines
  - Incident Timeline
  - Risk Score Gauge (from current RiskResult)
  - Blast Radius Network Graph (D3 force-directed)
  - Flame Graph (D3 flame graph from .ctx + Splunk latency)
```

**Data flowing in this feature:**
| Step | Source → Destination | Data Format |
|------|---------------------|-------------|
| 1 | DashboardProvider → McpClient | `{}` (no args needed) |
| 2 | McpClient → Context Engine | JSON-RPC `get_dashboard_data` |
| 3 | Context Engine → SplunkClient | 3-4 parallel SPL queries |
| 4 | SplunkClient → Splunk MCP | HTTP tool calls (or mock) |
| 5 | Splunk MCP → SplunkClient | JSON result sets |
| 6 | Context Engine → CtxGraph | Critical paths + adjacency for blast radius |
| 7 | Context Engine → McpClient | Aggregated JSON payload |
| 8 | DashboardProvider → Webview | Chart.js/D3.js data configs |

### 4.4 New: Agentic Incident Investigation (NEW)

```
Developer triggers "Investigate Incident" on INC-1029
        │
        ▼
[Context Engine] handle_investigate_incident(incident_id="INC-1029")
        │
        │  STEP 1: Search Splunk for related errors
        ├─▶ [SplunkClient/MCP] search("index=app service=payment_service level=ERROR earliest=-7d | stats count by operation, message | sort -count")
        │     → [{operation:"charge", message:"ConnectionTimeout", count:47}, ...]
        │
        │  STEP 2: AI Assistant explains the search
        ├─▶ [SplunkClient/MCP] ai_explain_spl(search_results)
        │     → "The payment_service is experiencing connection pool exhaustion..."
        │
        │  STEP 3: Map metrics to code nodes
        ├─▶ [OTelMapper] service_to_node_ids("payment_service")
        │     → ["n_f_charge_abc123", "n_f_db_query_def456"]
        │
        │  STEP 4: Compute risk for affected nodes
        ├─▶ [RiskScorer] score(["payment_service/main.py"])
        │     → RiskResult{overall_score:87, level:"critical"}
        │
        │  STEP 5: Generate remediation suggestion
        ├─▶ [SplunkClient/MCP] generate_spl("Show me connection pool utilization for payment_service")
        │     → Forecast/recommendation data
        │
        └─▶ Build InvestigationReport {
              incident, error_analysis, ai_explanation,
              affected_nodes, risk_scores, recommendations
            }
```

---

## 5. Splunk AI Capabilities Integration Map

| Splunk AI Capability | Current State | Target State | Data Flow Change |
|----------------------|--------------|--------------|-----------------|
| **MCP Server** | Raw REST API (`/services/search/jobs`) | MCP tool calls (`/services/mcp/v1/tools/call`) | `SplunkClient._execute_spl()` → `SplunkClient.mcp_tool_call(name, args)` |
| **AI Assistant (SPL generation)** | Regex `SPLQueryGenerator` | MCP `generate_spl` tool | `SPLQueryGenerator.generate()` → `SplunkClient.ai_generate_spl(nl_query)` |
| **AI Assistant (SPL explanation)** | Not implemented | MCP `explain_spl` tool | New: `SplunkClient.ai_explain_spl(spl, results)` |
| **AI Toolkit (ML)** | Hardcoded weighted formula | MLTK model prediction | `RiskScorer._score_node()` → `SplunkClient.mltk_predict(features)` |
| **Deep Time Series Model** | Not implemented | Forecast via hosted model | New: `SplunkClient.forecast_timeseries(metric, horizon)` |
| **Foundation Security Model** | Not implemented | Anomaly detection on logs | New: `SplunkClient.detect_anomalies(index, sourcetype)` |

---

## 6. External Data Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA THAT ENTERS THE SYSTEM                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  FROM: Developer's Git Repository                                │
│  DATA: Python source files (.py)                                │
│  VIA:  CtxParser reads files from disk                          │
│  INTO: .ctx YAML → CtxGraph in-memory                          │
│                                                                  │
│  FROM: Splunk Enterprise                                         │
│  DATA: Log events, APM metrics, incident records                 │
│  VIA:  SplunkClient → HTTP requests (REST or MCP)              │
│  INTO: Python dicts → Incident objects → RiskScorer              │
│                                                                  │
│  FROM: Developer (user input)                                    │
│  DATA: Natural language questions                                │
│  VIA:  VS Code chat webview → MCP client → Context Engine       │
│  INTO: QueryIntent → SPL query → SplunkClient → results         │
│                                                                  │
│  FROM: Demo Services (live)                                      │
│  DATA: HTTP logs, async metrics                                  │
│  VIA:  HEC POST to Splunk :8088                                 │
│  INTO: Splunk indexes (app, apm, incidents) → queryable          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     DATA THAT LEAVES THE SYSTEM                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TO: VS Code UI                                                  │
│  DATA: Risk scores, SPL results, code mappings, suggestions     │
│  VIA:  JSON-RPC responses from Context Engine → Extension UI    │
│  AS:   Status bar text, text decorations, tree items, webview   │
│                                                                  │
│  TO: VS Code Dashboard Webview                                   │
│  DATA: Service health, metric charts, flame graph, topology     │
│  VIA:  postMessage from DashboardProvider → HTML webview        │
│  AS:   Chart.js configs, D3.js data, HTML/CSS                   │
│                                                                  │
│  TO: Developer's Editor                                          │
│  DATA: File opens + cursor positions (code navigation)          │
│  VIA:  vscode.window.showTextDocument(uri, {selection})         │
│  AS:   Editor focus at exact function line                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. MCP Tool Registry (Current + Planned)

| # | Tool Name | Input | Output | Status |
|---|-----------|-------|--------|--------|
| 1 | `get_context_summary` | `repo_id: str` | `{files, classes, functions, methods, imports, interfaces, packages}` | Implemented |
| 2 | `get_node` | `node_id: str` | `{id, kind, name, path, span, signature, parent}` | Implemented |
| 3 | `search_nodes` | `query: str, kind?: str` | `{results: [{id, kind, name, path}]}` (max 10) | Implemented |
| 4 | `get_edges` | `node_id: str, direction: str, type?: str` | `{edges: [{from, to, type}], nodes: [{id, kind, name, path}]}` | Implemented |
| 5 | `get_code_span` | `node_id: str` | `{node_id, file, start_line, end_line, code: str}` | Implemented |
| 6 | `get_risk_score` | `repo_path: str, modified_files: [str]` | `RiskResult JSON` | Implemented |
| 7 | `sre_chat_query` | `message: str` | `SREChatResult JSON` | Implemented (regex SPL) |
| 8 | `map_metric_to_code` | `service: str, operation: str` | `{node_id, function_name, file, start_line, ..., upstream, downstream}` | Implemented |
| 9 | `get_incident_history` | `node_id: str` | `{node_id, incidents: [dict]}` | Implemented |
| 10 | `get_dashboard_data` | `{}` | `{services, metrics, incidents, topology, risk_score}` | **NEW** |
| 11 | `investigate_incident` | `incident_id: str` | `{incident, error_analysis, ai_explanation, affected_nodes, risk, recommendations}` | **NEW** |
| 12 | `ai_spl_generate` | `natural_language: str, index?: str` | `{spl_query: str, confidence: float}` | **NEW** (delegates to MCP) |
| 13 | `ai_spl_explain` | `spl_query: str, results?: [dict]` | `{explanation: str, optimization_tips: [str]}` | **NEW** (delegates to MCP) |
| 14 | `forecast_metric` | `service: str, metric: str, horizon: str` | `{forecast: [{timestamp, predicted_value}], confidence: float}` | **NEW** (Deep Time Series) |
