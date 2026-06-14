# Architecture: Relic — Code-Aware SRE Agent

## 1. System Overview

Relic consists of 4 components communicating through Model Context Protocol (MCP):

```
┌─────────────────────────────────────────────────────────────────┐
│                    VS Code Extension (TypeScript)                │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  Feature A:      │  │  Feature B:      │  │  Impact Map  │  │
│  │  Risk Decorations │  │  SRE Chat Panel  │  │  (Tree View) │  │
│  │  (Status Bar +    │  │  (Webview)       │  │  (Sidebar)   │  │
│  │   Inline Hints)  │  │                  │  │              │  │
│  └────────┬─────────┘  └────────┬────────┘  └──────┬───────┘  │
│           │                     │                  │            │
│           └─────────────────────┼──────────────────┘            │
│                                 │                               │
│                          ┌──────▼──────┐                        │
│                          │  MCP Client │  (VS Code MCP SDK)     │
│                          │  Manager    │                        │
│                          └──────┬──────┘                        │
└─────────────────────────────────┼───────────────────────────────┘
                                  │ MCP (stdio)
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              Context Engine (Python + MCP Server)               │
│                                                                 │
│  ┌────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  .ctx Parser   │  │  Graph Traverser │  │  Risk Scorer    │ │
│  │  (Tree-sitter) │  │  (adjacency)     │  │  (scoring       │ │
│  │                │  │                 │  │   engine)       │ │
│  └───────┬────────┘  └───────┬─────────┘  └───────┬─────────┘ │
│          │                   │                    │            │
│          └───────────────────┼────────────────────┘            │
│                              │                                 │
│                     ┌────────▼────────┐                       │
│                     │  MCP Server      │  (Python mcp SDK)     │
│                     │  (stdio)         │                       │
│                     └────────┬────────┘                       │
│                              │                                 │
│              ┌───────────────┼───────────────┐                │
│              │               │               │                │
│       ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐        │
│       │ repo.ctx    │ │ incidents/  │ │ splunk_mcp  │        │
│       │ (YAML)      │ │ (JSON mock) │ │ _client.py  │        │
│       └─────────────┘ └─────────────┘ └──────┬──────┘        │
│                                              │                 │
└──────────────────────────────────────────────┼─────────────────┘
                                               │ MCP (HTTP/SSE)
                                               ▼
                              ┌─────────────────────────────┐
                              │    Splunk MCP Server         │
                              │    (Splunkbase App)          │
                              │                              │
                              │  ┌──────────────────────┐   │
                              │  │  Splunk Enterprise    │   │
                              │  │  ┌────────────────┐  │   │
                              │  │  │  Indexes:       │  │   │
                              │  │  │  - app:logs     │  │   │
                              │  │  │  - apm:traces   │  │   │
                              │  │  │  - apm:metrics  │  │   │
                              │  │  └────────────────┘  │   │
                              │  └──────────────────────┘   │
                              └─────────────────────────────┘
```

---

## 2. Component Details

### 2.1 Context Engine (Python)

**Location:** `context-engine/`

The background daemon that parses code, maintains the structural graph, and serves MCP queries.

| Sub-component | File | Responsibility |
|---------------|------|---------------|
| Parser | `parser.py` | Tree-sitter Python AST → `.ctx` nodes + edges |
| Graph Store | `graph.py` | Load `.ctx` YAML, build in-memory adjacency lists |
| MCP Server | `server.py` | Expose 5 core endpoints + 3 SRE-specific endpoints |
| Risk Scorer | `risk.py` | Git diff → changed nodes → blast radius → incident correlation → score |
| OTel Mapper | `otel_mapper.py` | Map `service.operation` strings → `.ctx` node_ids |
| Splunk Client | `splunk_client.py` | HTTP client to Splunk MCP Server (or mock layer) |
| Mock Data | `mock/` | JSON files with fake incident data for demo fallback |

**Interface:** MCP over stdio. The VS Code extension spawns this process.

### 2.2 VS Code Extension (TypeScript)

**Location:** `relic-vscode/`

| Sub-component | File | Responsibility |
|---------------|------|---------------|
| Extension Entry | `extension.ts` | Activation, MCP client setup, command registration |
| MCP Client | `mcpClient.ts` | Connect to context-engine MCP server (stdio) |
| Risk Provider | `riskProvider.ts` | Status bar score, inline decorations, hover tooltips |
| Impact Provider | `impactProvider.ts` | Sidebar tree view: dependency chain with incident overlays |
| Chat Provider | `chatProvider.ts` | Webview panel: input → SPL → results → code navigation |
| Config | `config.ts` | Settings: repo path, Splunk URL, mock mode toggle |

**Interface:** VS Code Extension API. Commands registered in palette.

### 2.3 Demo Services (Python)

**Location:** `demo-services/`

Three FastAPI microservices forming a known call chain for demo purposes.

```
gateway/              → receives HTTP requests
  └── POST /order     → calls order_service.create_order()

order_service/        → processes orders
  └── create_order()  → calls payment_service.charge()
                      → calls inventory_service.reserve()

payment_service/      → processes payments (THE BOTTLENECK)
  └── charge()        → calls db.query() [SLOW - N+1 pattern]

inventory_service/    → reserves inventory
  └── reserve()       → calls db.query() [FAST]
```

### 2.4 Splunk MCP Server

**Pre-existing component** (installed from Splunkbase). Relic connects to it as a client.

The Context Engine's `splunk_client.py` makes MCP requests to the Splunk MCP Server to:
- Search for incident records related to `.ctx` nodes
- Execute generated SPL queries
- Retrieve APM trace data for flame graph mapping (future)

---

## 3. Data Flow

### 3.1 Feature A: Code-Risk Predictor

```
Developer saves file
        │
        ▼
VS Code detects file change (onDidSave)
        │
        ▼
MCP Client → context-engine: "get_changed_nodes(git_diff)"
        │
        ▼
Context Engine:
  1. Parse git diff → identify modified file paths
  2. Look up file paths in .ctx → get modified node_ids
  3. Call risk.py with modified node_ids
        │
        ▼
Risk Scorer:
  1. For each modified node:
     a. Traverse .ctx graph for downstream dependents (edge type: calls, imports)
     b. Count blast radius (number of affected nodes)
     c. Check node criticality (is it on a known hot path?)
  2. For each modified node + dependents:
     a. Query Splunk MCP: "get_incidents_for_node(node_id)"
     b. Match: service name + operation name → Splunk source
  3. Compute weighted risk score:
     - blast_radius_weight × len(dependents)
     - incident_history_weight × count(past_incidents)
     - criticality_weight × is_on_critical_path
  4. Return: { node_id, score, reasons[], incidents[], dependents[] }
        │
        ▼
MCP Response → VS Code Extension
        │
        ▼
VS Code renders:
  - Status bar: "Relic: ⚠ 67/100" (color: yellow)
  - Inline decoration on modified line:
    "⚠ Risk 67: charge() affects 3 downstream services.
     Similar change caused INC-1029 (p99 2.4s)"
  - Hover tooltip: full detail with incident links
  - Impact Map sidebar: tree view of affected dependency chain
```

### 3.2 Feature B: Natural Language SRE Chat

```
Developer types in chat panel:
  "What errors has payment_service had in the last 24h?"
        │
        ▼
VS Code Extension sends to Context Engine MCP:
  "sre_chat_query(message: 'What errors has payment_service...')"
        │
        ▼
Context Engine:
  1. Parse intent: error query, service=payment_service, time=24h
  2. Map "payment_service" → .ctx node_ids (service-level nodes)
  3. Generate SPL:
     index=app sourcetype=logs service=payment_service
     level=ERROR earliest=-24h
     | stats count by operation, message
     | sort -count
  4. Execute via Splunk MCP Server (or mock):
     splunk_mcp.search(spl_query)
  5. For each result row:
     a. Extract operation name (e.g., "charge")
     b. Map to .ctx node_id via OTel mapper
  6. Return: { spl_query, results[], code_mappings[] }
        │
        ▼
VS Code renders:
  - Chat panel: shows SPL query + result table
  - Each row has "→ code" link
  - Clicking link → opens file at .ctx node's span location
  - Inline annotation: "charge() — 47 errors in 24h, p99 2.4s"
```

---

## 4. MCP Endpoints

### 4.1 Core `.ctx` Endpoints (from original spec)

| Endpoint | Input | Output |
|----------|-------|--------|
| `get_context_summary` | `repo_id` | `{ files, structs, functions, interfaces, packages }` |
| `get_node` | `node_id` | `{ id, kind, name, path, span, signature }` |
| `search_nodes` | `query, kind?` | `node[]` (fuzzy name match) |
| `get_edges` | `node_id, type?` | `edge[]` (filtered by direction + type) |
| `get_code_span` | `node_id` | `{ code, file, start_line, end_line }` |

### 4.2 SRE-Specific Endpoints (new for hackathon)

| Endpoint | Input | Output |
|----------|-------|--------|
| `get_risk_score` | `repo_path, git_diff?` | `{ node_scores[], overall_score, reasons[], incidents[] }` |
| `sre_chat_query` | `message` | `{ spl_query, results[], code_mappings[] }` |
| `map_metric_to_code` | `service, operation` | `{ node_id, function_name, file, line, dependents[] }` |
| `get_incident_history` | `node_id` | `{ incidents[] }` (from Splunk or mock) |

---

## 5. `.ctx` File Schema

```yaml
metadata:
  repo_id: "demo-services"
  generated_at: "2026-06-15T00:00:00Z"
  language: "python"
  version: "1.0"
  parser: "tree-sitter-python@0.23.4"

nodes:
  - id: "n_file_gateway"
    kind: "file"
    name: "main.py"
    path: "gateway/main.py"
    span: { start_line: 1, end_line: 45 }

  - id: "n_func_create_order"
    kind: "function"
    name: "create_order"
    path: "order_service/main.py"
    span: { start_line: 12, end_line: 38 }
    signature: "def create_order(order: OrderRequest) -> OrderResponse"

  - id: "n_func_charge"
    kind: "function"
    name: "charge"
    path: "payment_service/main.py"
    span: { start_line: 8, end_line: 34 }
    signature: "def charge(payment: PaymentRequest) -> PaymentResponse"

edges:
  - from: "n_func_create_order"
    to: "n_func_charge"
    type: "calls"

  - from: "n_func_create_order"
    to: "n_func_reserve"
    type: "calls"

  - from: "n_func_charge"
    to: "n_func_db_query"
    type: "calls"

  - from: "n_file_gateway"
    to: "n_func_create_order"
    type: "contains"

interfaces:
  - name: "PaymentService"
    members: ["n_func_charge"]

span_map:
  "n_func_create_order":
    file: "order_service/main.py"
    start_line: 12
    end_line: 38
  "n_func_charge":
    file: "payment_service/main.py"
    start_line: 8
    end_line: 34
```

---

## 6. Risk Scoring Algorithm

### Input
- Git diff of modified files
- `.ctx` graph (nodes + edges)
- Splunk incident history (mock or real)

### Steps

```
1. DIFF PARSE
   git diff → list of modified file paths
   modified_files = ["payment_service/main.py", "order_service/models.py"]

2. NODE LOOKUP
   For each modified file, find .ctx nodes:
   modified_nodes = search_nodes(path=modified_file)

3. BLAST RADIUS CALCULATION
   For each modified node:
   - Traverse downstream: follow "calls" + "imports" edges (BFS, depth=3)
   - Traverse upstream: follow reverse "calls" edges (BFS, depth=2)
   - blast_radius = len(unique downstream nodes)

4. INCIDENT CORRELATION
   For each modified node + each downstream node:
   - Query Splunk: incidents where service=node.service, operation=node.name
   - incidents = get_incident_history(node_id)
   - incident_score = sum(incident.severity for incident in incidents)
                    / max_incident_score

5. CRITICALITY CHECK
   Is this node on any path that ends at a user-facing endpoint?
   - Trace upstream from node to any "file" node in gateway/
   - is_critical = True if reachable

6. SCORE COMPUTATION
   risk_score = (
     blast_radius_weight * normalize(blast_radius, max=50) +
     incident_weight * incident_score +
     criticality_weight * is_critical
   ) * 100

   Weights:
   - blast_radius_weight = 0.3
   - incident_weight = 0.5
   - criticality_weight = 0.2

7. REASON GENERATION
   reasons = []
   if blast_radius > 10:
     reasons.append(f"{blast_radius} downstream services affected")
   if len(incidents) > 0:
     for incident in incidents[:3]:
       reasons.append(f"Similar change caused {incident.id}: {incident.summary}")
   if is_critical:
     reasons.append("On critical user-facing path")
```

### Output Format

```json
{
  "overall_score": 87,
  "level": "critical",
  "node_scores": [
    {
      "node_id": "n_func_charge",
      "score": 87,
      "reasons": [
        "12 downstream functions affected",
        "Similar change caused INC-1029: p99 latency spike 2.4s",
        "Similar change caused INC-876: timeout cascade to order_service",
        "On critical user-facing path (gateway → order → payment)"
      ],
      "incidents": [
        {
          "id": "INC-1029",
          "date": "2026-05-28",
          "severity": "high",
          "summary": "p99 latency spike 2.4s on payment_service.charge",
          "splunk_link": "https://splunk.example.com/incident/1029"
        }
      ],
      "dependents": [
        { "node_id": "n_func_create_order", "name": "create_order", "path": "order_service/main.py" },
        { "node_id": "n_func_gateway_post", "name": "POST /order", "path": "gateway/main.py" }
      ]
    }
  ]
}
```

---

## 7. Splunk Data Model (Mock)

When Splunk MCP Server is not available, the Context Engine reads from mock JSON files:

### `mock/incidents.json`
```json
[
  {
    "id": "INC-1029",
    "service": "payment_service",
    "operation": "charge",
    "date": "2026-05-28T14:30:00Z",
    "severity": "high",
    "type": "latency_spike",
    "summary": "p99 latency spike 2.4s on payment_service.charge",
    "spl_query": "index=apm service=payment_service operation=charge | timechart p99(latency)",
    "metrics": {
      "p99_latency_ms": 2400,
      "error_rate": 0.03,
      "affected_users": 4500
    }
  },
  {
    "id": "INC-876",
    "service": "payment_service",
    "operation": "charge",
    "date": "2026-04-15T09:00:00Z",
    "severity": "critical",
    "type": "timeout_cascade",
    "summary": "Timeout cascade: payment_service.charge → order_service.create_order timeout",
    "metrics": {
      "p99_latency_ms": 5200,
      "error_rate": 0.12,
      "affected_users": 12000
    }
  }
]
```

### `mock/service_metrics.json`
```json
{
  "payment_service": {
    "operation": "charge",
    "p99_latency_ms": 245,
    "p95_latency_ms": 120,
    "error_rate": 0.003,
    "throughput_rps": 450,
    "last_incident": "2026-05-28T14:30:00Z"
  },
  "order_service": {
    "operation": "create_order",
    "p99_latency_ms": 380,
    "p95_latency_ms": 180,
    "error_rate": 0.008,
    "throughput_rps": 320,
    "last_incident": "2026-04-15T09:00:00Z"
  }
}
```

### OTel Mapper Configuration

The mapping from Splunk service/operation names to `.ctx` node_ids:

```yaml
# mock/otel_mapping.yaml
mappings:
  - service: "payment_service"
    operation: "charge"
    node_id: "n_func_charge"

  - service: "order_service"
    operation: "create_order"
    node_id: "n_func_create_order"

  - service: "inventory_service"
    operation: "reserve"
    node_id: "n_func_reserve"

  - service: "gateway"
    operation: "POST /order"
    node_id: "n_func_gateway_post"
```

---

## 8. Security & Privacy

- All code parsing runs locally (Tree-sitter, no cloud calls)
- `.ctx` file stays on disk unless explicitly shared
- Splunk queries use token-based auth (no OAuth needed for MVP)
- No code is sent to LLMs — only structural signatures from `.ctx`
- Mock mode requires no external network access
