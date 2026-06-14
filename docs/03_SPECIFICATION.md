# Technical Specification: Relic — Code-Aware SRE Agent (MVP)

## 1. Technology Stack

### Context Engine (Python)

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Language | Python | 3.12+ | Core engine runtime |
| Parser | tree-sitter + tree-sitter-python | 0.23+ | AST parsing → `.ctx` generation |
| MCP SDK | `mcp` | 1.x | MCP server implementation (stdio) |
| Git Integration | `gitpython` | 3.1+ | Diff analysis for risk scoring |
| YAML | `pyyaml` | 6.x | `.ctx` file serialization |
| HTTP Client | `httpx` | 0.27+ | Splunk MCP Server REST calls |
| Testing | `pytest` + `pytest-mock` | Latest | Unit + integration tests |

### VS Code Extension (TypeScript)

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Language | TypeScript | 5.x | Extension logic |
| Runtime | Node.js | 20 LTS | Extension host |
| Framework | VS Code Extension API | 1.90+ | All VS Code interactions |
| MCP Client | `@modelcontextprotocol/sdk` | 1.x | Connect to context-engine MCP |
| Webview | Vanilla HTML/CSS/JS | — | Chat panel rendering |
| Packaging | `vsce` | Latest | `.vsix` packaging |

### Demo Services (Python)

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Web Framework | FastAPI | 0.111+ | Microservice skeleton |
| ASGI Server | Uvicorn | 0.30+ | Runtime |
| OTel SDK | `opentelemetry-api` + `sdk` | 1.25+ | Trace generation |
| OTel Exporter | `opentelemetry-exporter-otlp` | 1.25+ | Export to Splunk/collector |
| Database | SQLite (simulated) | — | Mock DB layer |

---

## 2. Repository Structure

```
LeftshiftSRE/
├── docs/                              # All documentation
│   ├── 01_PROJECT_PLAN.md
│   ├── 02_ARCHITECTURE.md
│   ├── 03_SPECIFICATION.md            # This file
│   ├── 04_SPLUNK_SETUP.md
│   └── 05_DEFERRED_FEATURES.md
│
├── context-engine/                    # Python MCP Server
│   ├── pyproject.toml
│   ├── src/
│   │   └── relic/
│   │       ├── __init__.py
│   │       ├── cli.py                 # Entry point: relic parse, relic serve
│   │       ├── parser.py             # Tree-sitter → .ctx
│   │       ├── graph.py             # .ctx loader + adjacency index
│   │       ├── server.py            # MCP server (stdio)
│   │       ├── risk.py              # Risk scoring engine
│   │       ├── otel_mapper.py       # OTel service.op → node_id mapping
│   │       ├── splunk_client.py     # Splunk MCP REST client
│   │       └── spl_query_gen.py     # Natural language → SPL generation
│   ├── mock/
│   │   ├── incidents.json            # Fake incident data
│   │   ├── service_metrics.json      # Fake APM metrics
│   │   └── otel_mapping.yaml         # Service → node_id mapping
│   ├── tests/
│   │   ├── test_parser.py
│   │   ├── test_graph.py
│   │   ├── test_risk.py
│   │   ├── test_server.py
│   │   └── fixtures/
│   │       └── sample_repo/          # Golden test repo
│   └── README.md
│
├── relic-vscode/                      # VS Code Extension
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── extension.ts              # Activation + command registration
│   │   ├── mcpClient.ts              # MCP client manager
│   │   ├── riskProvider.ts           # Status bar + decorations
│   │   ├── impactProvider.ts         # Sidebar tree view
│   │   ├── chatProvider.ts           # SRE Chat webview
│   │   └── config.ts                 # User settings
│   ├── webview/
│   │   ├── chat.html
│   │   ├── chat.css
│   │   └── chat.js
│   └── README.md
│
├── demo-services/                     # Fixture microservices
│   ├── gateway/
│   │   ├── main.py
│   │   └── requirements.txt
│   ├── order_service/
│   │   ├── main.py
│   │   └── requirements.txt
│   ├── payment_service/
│   │   ├── main.py
│   │   └── requirements.txt
│   ├── inventory_service/
│   │   ├── main.py
│   │   └── requirements.txt
│   └── docker-compose.yml             # Run all services locally
│
├── .ctx/                               # Generated .ctx output (gitignored)
│   └── repo.ctx
│
├── Spec.MD                             # Original spec (archive)
├── Requirements.md                      # Original requirements (archive)
├── project_discription.md              # Original description (archive)
├── PROJECT_PLAN.md                      # Original plan (superseded by docs/)
├── ARCHITECTURE.md                      # Root architecture diagram (required by hackathon)
├── LICENSE                              # MIT
└── README.md                            # Hackathon submission README
```

---

## 3. `.ctx` Schema — Complete Specification

### 3.1 Metadata Section

```yaml
metadata:
  repo_id: string            # Unique identifier (repo name or URL)
  generated_at: string        # RFC3339 timestamp
  language: string            # "python" (MVP)
  version: string              # Schema version: "1.0"
  parser: string               # "tree-sitter-python@<version>"
  root_path: string            # Relative path to repo root from .ctx file
```

### 3.2 Nodes Section

Each node represents a structural code entity.

```yaml
nodes:
  - id: string                  # Unique identifier: "n_<type>_<sanitized_name>"
    kind: enum                  # "file" | "class" | "function" | "method" | "import"
    name: string                # Human-readable name (e.g., "charge", "PaymentService")
    path: string                # Relative file path from repo root
    span:
      start_line: int           # 1-indexed
      end_line: int             # Inclusive
    signature: string?           # Function/method signature string (optional for files/import)
    parent: string?             # node_id of containing node (class for methods, file for top-level)
```

**Node ID Generation:**
```
id = "n_" + kind[0] + "_" + sha256(path + name + kind)[:12]
```
This ensures stable, content-addressable IDs across re-parses (as long as the function name + path don't change).

### 3.3 Edges Section

```yaml
edges:
  - from: string                # Source node_id
    to: string                   # Target node_id
    type: enum                   # "calls" | "imports" | "contains" | "implements" | "inherits"
```

**Edge Extraction Rules for Python:**

| Edge Type | Source | Target | Heuristic |
|-----------|--------|--------|-----------|
| `calls` | function/method | function/method | Direct function call in body: `foo()` → edge to `foo` |
| `imports` | file | import | `from X import Y` or `import X` |
| `contains` | file | class/function | File contains entity |
| `contains` | class | method | Class contains method |
| `inherits` | class | class | `class B(A)` → edge from B to A |
| `implements` | class | class | Implicit (Duck typing) — deferred to post-MVP |

### 3.4 Interfaces Section

```yaml
interfaces:
  - name: string                # Interface identifier (class name in Python)
    members: [string]           # List of node_ids for member methods
```

### 3.5 Span Map Section

```yaml
span_map:
  "<node_id>":
    file: string                 # Relative path
    start_line: int
    end_line: int
    start_byte: int?             # Optional, for precise source extraction
    end_byte: int?
```

### 3.6 Determinism Rules

The `.ctx` file MUST be deterministic — same input always produces same output:

1. **Nodes sorted by:** path, then start_line
2. **Edges sorted by:** from, then to, then type
3. **YAML serializer:** preserve insertion order, no anchors/aliases
4. **Metadata.generated_at:** set to file modification time (not parser execution time) for diff-stability

---

## 4. Context Engine — Detailed API Specification

### 4.1 CLI Commands

```bash
# Parse a repo and generate .ctx file
relic parse <repo_path> [--output <path>] [--language python]

# Start MCP server (stdio transport)
relic serve [--repo <path>] [--ctx <path>] [--mock]

# Compute risk score for current changes
relic risk <repo_path> [--diff <git_diff_string>] [--mock]
```

### 4.2 MCP Server Endpoints

#### `get_context_summary`

Returns high-level repo statistics for low-token architectural understanding.

**Input:**
```json
{
  "method": "get_context_summary",
  "params": {
    "repo_id": "demo-services"
  }
}
```

**Output:**
```json
{
  "files": 4,
  "classes": 3,
  "functions": 12,
  "methods": 5,
  "imports": 18,
  "interfaces": 1,
  "packages": ["gateway", "order_service", "payment_service", "inventory_service"],
  "critical_paths": [
    ["gateway:POST /order", "order_service:create_order", "payment_service:charge"]
  ]
}
```

---

#### `get_node`

Retrieve a single node by ID.

**Input:**
```json
{
  "method": "get_node",
  "params": {
    "node_id": "n_func_charge"
  }
}
```

**Output:**
```json
{
  "id": "n_func_charge",
  "kind": "function",
  "name": "charge",
  "path": "payment_service/main.py",
  "span": { "start_line": 8, "end_line": 34 },
  "signature": "def charge(payment: PaymentRequest) -> PaymentResponse",
  "parent": "n_file_payment_service"
}
```

**Error:**
```json
{
  "error": { "code": "NODE_NOT_FOUND", "message": "Node 'n_func_charge' does not exist" }
}
```

---

#### `search_nodes`

Search nodes by name (fuzzy) and kind (optional filter).

**Input:**
```json
{
  "method": "search_nodes",
  "params": {
    "query": "charge",
    "kind": "function"
  }
}
```

**Output:**
```json
{
  "results": [
    {
      "id": "n_func_charge",
      "kind": "function",
      "name": "charge",
      "path": "payment_service/main.py",
      "score": 1.0
    }
  ]
}
```

**Search algorithm:** Exact match → prefix match → substring match. Score: 1.0 / 0.8 / 0.5.

---

#### `get_edges`

Retrieve edges for a node, optionally filtered by type and direction.

**Input:**
```json
{
  "method": "get_edges",
  "params": {
    "node_id": "n_func_charge",
    "type": "calls",
    "direction": "downstream"
  }
}
```

**Output:**
```json
{
  "edges": [
    { "from": "n_func_charge", "to": "n_func_db_query", "type": "calls" }
  ],
  "nodes": [
    { "id": "n_func_db_query", "kind": "function", "name": "db_query", "path": "payment_service/db.py" }
  ]
}
```

**Direction values:** `"downstream"` (from→to), `"upstream"` (to→from), `"both"` (default).

---

#### `get_code_span`

Retrieve the actual source code for a node.

**Input:**
```json
{
  "method": "get_code_span",
  "params": {
    "node_id": "n_func_charge"
  }
}
```

**Output:**
```json
{
  "node_id": "n_func_charge",
  "file": "payment_service/main.py",
  "start_line": 8,
  "end_line": 34,
  "code": "def charge(payment: PaymentRequest) -> PaymentResponse:\n    ..."
}
```

---

#### `get_risk_score`

Compute risk score for modified files. This is the primary Feature A endpoint.

**Input:**
```json
{
  "method": "get_risk_score",
  "params": {
    "repo_path": "/path/to/demo-services",
    "modified_files": ["payment_service/main.py"]
  }
}
```

**Output:**
```json
{
  "overall_score": 87,
  "level": "critical",
  "node_scores": [
    {
      "node_id": "n_func_charge",
      "node_name": "charge",
      "score": 87,
      "reasons": [
        "12 downstream functions affected",
        "Similar change caused INC-1029: p99 latency spike 2.4s",
        "Similar change caused INC-876: timeout cascade to order_service",
        "On critical user-facing path"
      ],
      "incidents": [
        {
          "id": "INC-1029",
          "date": "2026-05-28",
          "severity": "high",
          "summary": "p99 latency spike 2.4s on payment_service.charge"
        }
      ],
      "downstream_dependents": [
        { "node_id": "n_func_create_order", "name": "create_order", "path": "order_service/main.py" }
      ],
      "upstream_callers": [
        { "node_id": "n_func_gateway_post", "name": "POST /order", "path": "gateway/main.py" }
      ]
    }
  ]
}
```

**Scoring weights (configurable):**
```python
BLAST_RADIUS_WEIGHT = 0.3
INCIDENT_HISTORY_WEIGHT = 0.5
CRITICALITY_WEIGHT = 0.2
```

**Level thresholds:**
```
0-25:  low (green)
26-60: medium (yellow)
61-100: critical (red)
```

---

#### `sre_chat_query`

Process a natural language SRE question. Feature B primary endpoint.

**Input:**
```json
{
  "method": "sre_chat_query",
  "params": {
    "message": "What errors has payment_service had in the last 24h?"
  }
}
```

**Output:**
```json
{
  "intent": "error_query",
  "spl_query": "index=app sourcetype=logs service=payment_service level=ERROR earliest=-24h | stats count by operation, message | sort -count",
  "results": [
    {
      "operation": "charge",
      "message": "ConnectionTimeout: database connection pool exhausted",
      "count": 47,
      "code_mapping": {
        "node_id": "n_func_charge",
        "file": "payment_service/main.py",
        "line": 8
      }
    }
  ],
  "suggestions": [
    "Show me the latency trend for charge()",
    "What services call payment_service.charge()?",
    "Show recent deployments that affected payment_service"
  ]
}
```

**Intent parsing (MVP heuristic-based):**

| Pattern | Intent | SPL Template |
|---------|--------|-------------|
| "errors in X" / "error rate for X" | `error_query` | `index=app service={X} level=ERROR {time} \| stats count by operation, message` |
| "latency for X" / "slow X" | `latency_query` | `index=apm service={X} {time} \| timechart p99(latency)` |
| "incidents for X" / "outages in X" | `incident_query` | `index=incidents service={X} {time} \| table id, severity, summary` |
| "who calls X" / "upstream of X" | `dependency_query` | (Uses `.ctx` graph directly, not SPL) |
| "risk of my changes" / "is this safe" | `risk_query` | (Delegates to `get_risk_score`) |

**Time parsing:**
- "last hour" → `earliest=-1h`
- "last 24h" / "last day" → `earliest=-24h`
- "last week" → `earliest=-7d`
- No time specified → `earliest=-24h` (default)

---

#### `map_metric_to_code`

Map a Splunk service+operation to a `.ctx` node.

**Input:**
```json
{
  "method": "map_metric_to_code",
  "params": {
    "service": "payment_service",
    "operation": "charge"
  }
}
```

**Output:**
```json
{
  "node_id": "n_func_charge",
  "function_name": "charge",
  "file": "payment_service/main.py",
  "start_line": 8,
  "end_line": 34,
  "signature": "def charge(payment: PaymentRequest) -> PaymentResponse",
  "upstream_callers": [
    { "node_id": "n_func_create_order", "name": "create_order", "path": "order_service/main.py" }
  ],
  "downstream_calls": [
    { "node_id": "n_func_db_query", "name": "db_query", "path": "payment_service/db.py" }
  ]
}
```

---

#### `get_incident_history`

Retrieve past incidents for a code node.

**Input:**
```json
{
  "method": "get_incident_history",
  "params": {
    "node_id": "n_func_charge"
  }
}
```

**Output:**
```json
{
  "node_id": "n_func_charge",
  "incidents": [
    {
      "id": "INC-1029",
      "date": "2026-05-28T14:30:00Z",
      "severity": "high",
      "type": "latency_spike",
      "summary": "p99 latency spike 2.4s on payment_service.charge",
      "metrics": {
        "p99_latency_ms": 2400,
        "error_rate": 0.03,
        "affected_users": 4500
      }
    }
  ]
}
```

**Data source:** Splunk MCP Server (real) or `mock/incidents.json` (fallback).

---

## 5. VS Code Extension — Detailed Specification

### 5.1 Commands

| Command ID | Title | Action |
|------------|-------|--------|
| `relic.parseRepo` | "Relic: Parse Repository" | Run `relic parse` on configured repo path |
| `relic.startServer` | "Relic: Start Context Engine" | Spawn context-engine MCP server |
| `relic.riskScore` | "Relic: Show Risk Score" | Compute + display risk for current changes |
| `relic.openChat` | "Relic: Open SRE Chat" | Open chat webview panel |
| `relic.impactMap` | "Relic: Show Impact Map" | Open impact tree view |
| `relic.mapToCode` | "Relic: Map Metric to Code" | Input service+operation → navigate to code |

### 5.2 Configuration

```json
{
  "relic.repoPath": {
    "type": "string",
    "default": "${workspaceFolder}",
    "description": "Path to the repository to analyze"
  },
  "relic.ctxFilePath": {
    "type": "string",
    "default": "${workspaceFolder}/.ctx/repo.ctx",
    "description": "Path to the generated .ctx file"
  },
  "relic.enginePath": {
    "type": "string",
    "default": "relic",
    "description": "Path to the relic CLI binary (or 'relic' if on PATH)"
  },
  "relic.useMockData": {
    "type": "boolean",
    "default": true,
    "description": "Use mock Splunk data instead of real Splunk MCP Server"
  },
  "relic.splunkMcpUrl": {
    "type": "string",
    "default": "http://localhost:8000",
    "description": "Splunk MCP Server URL (when not using mock)"
  },
  "relic.splunkToken": {
    "type": "string",
    "default": "",
    "description": "Splunk authentication token"
  },
  "relic.autoRiskOnSave": {
    "type": "boolean",
    "default": true,
    "description": "Automatically compute risk score on file save"
  }
}
```

### 5.3 Status Bar Item

- **Position:** Left side, priority 100
- **Text:** `Relic: ✓ 12/100` (green) | `Relic: ⚠ 67/100` (yellow) | `Relic: ✗ 87/100` (red)
- **Tooltip:** Top 3 risk reasons + click to open impact map
- **Click action:** Opens Impact Map sidebar

### 5.4 Inline Decorations

When a file is open that contains a modified `.ctx` node with risk > 25:

```
  8 │ def charge(payment: PaymentRequest) -> PaymentResponse:
    │ ⚠ Risk 87: 12 downstream functions affected
    │ Similar change caused INC-1029 (p99 2.4s)
    │ [View Impact Map] [See Incident INC-1029]
```

**Implementation:** `vscode.TextEditorDecorationType` with `after` content. Light gray background, colored gutter icon.

### 5.5 Impact Map Tree View

```
📦 Relic Impact Map
├── 🔴 charge() — Risk 87/100 (payment_service/main.py:8)
│   ├── ⬆ Upstream Callers
│   │   ├── create_order() (order_service/main.py:12)
│   │   └── POST /order() (gateway/main.py:5)
│   ├── ⬇ Downstream Calls
│   │   ├── db_query() (payment_service/db.py:3)
│   │   └── validate_card() (payment_service/charge.py:1)
│   └── ⚡ Past Incidents (2)
│       ├── INC-1029: p99 latency spike (2026-05-28)
│       └── INC-876: timeout cascade (2026-04-15)
├── 🟡 create_order() — Risk 45/100 (order_service/main.py:12)
│   └── ⬆ Upstream Callers
│       └── POST /order() (gateway/main.py:5)
└── 🟢 models.py — Risk 8/100 (order_service/models.py:1)
```

**Click behavior:** Single click on any node → navigate to file + line range. Single click on incident → open Splunk link (or show mock detail).

### 5.6 SRE Chat Webview

**Layout:**
```
┌─────────────────────────────────────┐
│  Relic SRE Chat                     │
├─────────────────────────────────────┤
│                                     │
│  🤖 Ask about your system:          │
│  "What errors has payment_service   │
│  had in the last 24h?"              │
│                                     │
│  ── Generated SPL ──────────────── │
│  index=app sourcetype=logs          │
│  service=payment_service            │
│  level=ERROR earliest=-24h          │
│  | stats count by operation, message │
│  | sort -count                       │
│                                     │
│  ── Results ───────────────────────│
│  ┌──────┬────────────────────┬─────┐│
│  │ Op   │ Message            │ Count││
│  ├──────┼────────────────────┼─────┤│
│  │charge│ ConnectionTimeout  │  47  ││ ← Clickable: jumps to code
│  │charge│ PoolExhausted      │  23  ││
│  └──────┴────────────────────┴─────┘│
│                                     │
│  ── Suggestions ────────────────── │
│  • Show latency trend for charge()  │
│  • Who calls payment_service?       │
│                                     │
├─────────────────────────────────────┤
│  Type a question...          [Send] │
└─────────────────────────────────────┘
```

---

## 6. Tree-sitter Query Files

### 6.1 Python Function Extraction (`queries/python_functions.scm`)

```scheme
; Top-level functions
(function_definition
  name: (identifier) @func_name
  parameters: (parameters) @func_params
  return: (type)? @func_return) @func_def

; Class methods
(class_definition
  name: (identifier) @class_name
  body: (block
    (function_definition
      name: (identifier) @method_name
      parameters: (parameters) @method_params) @method_def))

; Class definitions
(class_definition
  name: (identifier) @class_name
  arguments: (argument_list)? @class_inherits) @class_def

; Import statements
(import_statement
  name: (dotted_name) @import_name) @import_stmt

(import_from_statement
  module_name: (dotted_name) @import_module
  name: (import_list) @import_names) @import_from_stmt

; Function calls
(call
  function: (identifier) @call_name) @call_expr

(call
  function: (attribute
    object: (identifier) @call_obj
    attribute: (identifier) @call_attr)) @call_method_expr
```

### 6.2 Signature Extraction

For each function node, extract the signature as a single-line string:

```python
def extract_signature(node, source_bytes):
    """Extract 'def charge(payment: PaymentRequest) -> PaymentResponse' from AST."""
    line = source_bytes.splitlines()[node.start_point[0]]
    return line.strip()
```

---

## 7. Error Handling

All MCP endpoints return typed errors:

| Code | Meaning |
|------|---------|
| `NODE_NOT_FOUND` | Requested node_id does not exist in `.ctx` |
| `REPO_NOT_FOUND` | Repository path does not exist or is not a git repo |
| `PARSE_ERROR` | Tree-sitter failed to parse a file |
| `CTX_FILE_NOT_FOUND` | `.ctx` file has not been generated yet (run `relic parse` first) |
| `SPLUNK_UNAVAILABLE` | Splunk MCP Server is not reachable (fallback to mock) |
| `NO_MODIFIED_FILES` | No uncommitted changes detected for risk scoring |
| `INVALID_QUERY` | Could not parse natural language intent |

---

## 8. Testing Strategy

### 8.1 Parser Tests

```python
def test_parse_function():
    """Parse a simple Python file with one function."""
    result = parse_file("fixtures/simple_function.py")
    assert len(result.nodes) == 2  # 1 file + 1 function
    assert result.nodes[1].kind == "function"
    assert result.nodes[1].name == "charge"

def test_parse_class_with_methods():
    """Parse a class with methods."""
    result = parse_file("fixtures/class_methods.py")
    assert any(n.kind == "class" for n in result.nodes)
    assert any(n.kind == "method" for n in result.nodes)

def test_parse_imports():
    """Parse import statements."""
    result = parse_file("fixtures/imports.py")
    assert any(e.type == "imports" for e in result.edges)
```

### 8.2 Graph Traversal Tests

```python
def test_downstream_traversal():
    """charge() → db_query() is a downstream call."""
    graph = load_ctx("fixtures/repo.ctx")
    downstream = graph.traverse("n_func_charge", direction="downstream", edge_type="calls", max_depth=3)
    assert "n_func_db_query" in [n.id for n in downstream]

def test_upstream_traversal():
    """create_order() calls charge()."""
    graph = load_ctx("fixtures/repo.ctx")
    upstream = graph.traverse("n_func_charge", direction="upstream", edge_type="calls", max_depth=2)
    assert "n_func_create_order" in [n.id for n in upstream]
```

### 8.3 Risk Scoring Tests

```python
def test_risk_high_for_payment_service():
    """Modifying charge() should produce high risk score."""
    scorer = RiskScorer(graph, incidents=MOCK_INCIDENTS)
    result = scorer.score(modified_files=["payment_service/main.py"])
    assert result.overall_score > 60
    assert any("INC-1029" in r for r in result.node_scores[0].reasons)

def test_risk_low_for_utility():
    """Modifying a standalone utility function should produce low risk."""
    scorer = RiskScorer(graph, incidents=MOCK_INCIDENTS)
    result = scorer.score(modified_files=["utils/format.py"])
    assert result.overall_score < 25
```

### 8.4 MCP Server Tests

```python
@pytest.mark.asyncio
async def test_get_node():
    """get_node returns correct node data."""
    server = RelicMCPServer(ctx_path="fixtures/repo.ctx")
    result = await server.handle_get_node(node_id="n_func_charge")
    assert result["name"] == "charge"
    assert result["kind"] == "function"

@pytest.mark.asyncio
async def test_search_nodes():
    """search_nodes finds functions by name."""
    server = RelicMCPServer(ctx_path="fixtures/repo.ctx")
    result = await server.handle_search_nodes(query="charge")
    assert len(result["results"]) >= 1
```

### 8.5 Golden Snapshot Tests

```python
def test_ctx_golden_snapshot():
    """Generated .ctx matches committed golden snapshot."""
    result = parse_repo("demo-services/")
    golden = yaml.safe_load(open("tests/fixtures/golden.ctx"))
    assert result.to_dict() == golden
```

**How to update golden:** `relic parse demo-services/ --output tests/fixtures/golden.ctx --update-golden`

---

## 9. Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Parse time (demo repo ~500 LOC) | < 2s | `time relic parse demo-services/` |
| Parse time (50k LOC) | < 30s | Future target |
| `.ctx` file size (500 LOC) | < 10 KB | `wc -c repo.ctx` |
| `.ctx` file size (50k LOC) | < 500 KB | Future target |
| MCP query latency (single node) | < 50ms | In-memory lookup |
| MCP query latency (graph traversal) | < 200ms | BFS depth=3 |
| Risk score computation | < 500ms | Including Splunk query or mock read |
| SRE Chat response | < 2s | Including SPL gen + Splunk query |
| VS Code decoration render | < 100ms | After receiving risk score |
