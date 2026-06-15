# Relic — Code-Aware SRE Agent

> AI-powered observability that maps production incidents directly to your source code, without leaving the IDE.

**Track:** Observability | **Stack:** Python + TypeScript + VS Code Extension + MCP

---

## The Problem

When production breaks, engineers waste 30-60 minutes per incident just figuring **WHERE in the code** the issue lives. Splunk tells you WHAT is broken (service name, metric spike). Your IDE knows WHERE the code is. Nobody bridges them.

---

## What Relic Does

Relic bridges **Splunk observability data** with **structural code context** — in your IDE. When you get an alert, Relic shows you the exact function, its dependency chain, and historical incidents — all clickable, all with source links.

### Two Core Features

1. **Code-Risk Predictor** — Score every code change from 0-100 based on blast radius through your service dependency graph and historical Splunk incidents
2. **Natural Language SRE Chat** — Ask "What errors has payment_service had?" → Splunk SPL query runs → results mapped directly to code functions

---

## Architecture

```
VS Code Extension (TypeScript)
    | MCP (stdio)
    v
Context Engine (Python CLI)    <-- .ctx graph (Tree-sitter)
    |                                | parse demo-services/
    | MCP (HTTP)                     | 44 nodes, 82 edges in 5ms
    v                                |
Splunk MCP Server (mock or real) <-- JSON mock data
  (or mock fallback)
```

Full diagram: see [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+ (for VS Code extension)
- Git

### 1. Set Up Context Engine

```bash
cd context-engine
pip install -e .

# Parse the demo repository -> generates .ctx/repo.ctx
relic parse ../demo-services

# Test the risk scorer
relic risk ../demo-services --diff "diff --git a/payment_service/main.py"

# Start MCP server (stdio mode)
relic serve ../demo-services --mock
```

### 2. Set Up VS Code Extension

```bash
cd relic-vscode
npm install
npm run compile

# Open in VS Code (development)
code .
# Press F5 to launch extension debugger
```

### 3. Run Demo Services (Optional)

```bash
cd demo-services
docker compose up -d
# Services: gateway:8000, order_service:8001, payment_service:8002, inventory_service:8003
```

### 4. Connect to Splunk (Optional)

Follow [docs/04_SPLUNK_SETUP.md](docs/04_SPLUNK_SETUP.md) for full Splunk setup. Relic runs in mock mode by default — no Splunk instance required.

---

## Features

### Feature A: Code-Risk Predictor

When you save a Python file, Relic:
1. Detects changed files from git diff
2. Looks up `.ctx` graph nodes for those files
3. Computes blast radius (how many downstream functions depend on this)
4. Correlates with past Splunk incidents (mock or real)
5. Shows a risk score (0-100) in the VS Code status bar + inline decorations

**Example:**
> Modifying `payment_service/main.py` → Risk **30/100 (medium)**
> Reason: Similar change caused INC-1029 (p99 latency 2.4s on `charge()`)

### Feature B: Natural Language SRE Chat

Type in the chat panel:
```
What errors has payment_service had in the last 24h?
```

Relic:
1. Detects intent = `error_query`, service = `payment_service`, time = `-24h`
2. Generates SPL: `index=app sourcetype=logs service=payment_service level=ERROR earliest=-24h | stats count by operation, message | sort -count`
3. Executes via Splunk (or returns mock data)
4. Maps results back to `.ctx` nodes with file/line locations
5. Click any result → jumps to the source function

---

## File Structure

```
.
├── docs/                          # Full documentation
│   ├── 01_PROJECT_PLAN.md         # Execution plan, timeline
│   ├── 02_ARCHITECTURE.md         # System design, data flows
│   ├── 03_SPECIFICATION.md        # Technical spec, MCP API, schema
│   ├── 04_SPLUNK_SETUP.md         # Splunk installation guide
│   └── 05_DEFERRED_FEATURES.md    # Future roadmap (dashboard, flame graphs...)
│
├── context-engine/                # Python MCP Server
│   ├── src/relic/
│   │   ├── parser.py              # Tree-sitter -> .ctx graph
│   │   ├── graph.py               # .ctx loader + traversal
│   │   ├── risk.py                # Blast radius + incident scoring
│   │   ├── server.py             # MCP server (stdio)
│   │   ├── splunk_client.py       # Splunk MCP client + mock
│   │   ├── spl_query_gen.py       # NL -> SPL intent parsing
│   │   └── otel_mapper.py         # service.operation -> node_id
│   ├── mock/                      # Mock Splunk data
│   │   ├── incidents.json
│   │   ├── service_metrics.json
│   │   └── otel_mapping.yaml
│   └── tests/
│
├── relic-vscode/                  # VS Code Extension
│   ├── src/
│   │   ├── extension.ts           # Entry point, command registration
│   │   ├── mcpClient.ts           # MCP client (stdio to context-engine)
│   │   ├── riskProvider.ts        # Status bar + inline decorations
│   │   ├── impactProvider.ts      # Sidebar tree view (dependency chain)
│   │   └── chatProvider.ts        # Webview chat panel
│   ├── dist/                      # Compiled TypeScript
│   └── package.json
│
├── demo-services/                # Fixture microservices
│   ├── gateway/                   # FastAPI, POST /order
│   ├── order_service/             # Calls payment + inventory
│   ├── payment_service/            # The bottleneck (N+1 DB queries)
│   ├── inventory_service/         # Fast reserve endpoint
│   └── data/                      # Sample Splunk ingest files
│
├── .ctx/                          # Generated .ctx files (gitignored)
│   └── repo.ctx
│
├── ARCHITECTURE.md               # Root-level architecture diagram (hackathon req)
├── LICENSE                       # MIT
└── README.md                     # This file
```

---

## The `.ctx` File Format

The `.ctx` file is the core innovation. It distills a Python codebase into a minimal graph:

```yaml
metadata:
  repo_id: demo-services
  generated_at: 2026-06-14T19:50:11Z
  language: python
  version: 1.0
  parser: tree-sitter-python@0.25.0

nodes:
  - id: n_f_charge_f656d2fd152b
    kind: function
    name: charge
    path: payment_service/main.py
    span: { start_line: 48, end_line: 89 }
    signature: "def charge(req: ChargeRequest) -> ChargeResponse"

edges:
  - from: n_f_createorder_5dcec3cf1563
    to: n_f_charge_f656d2fd152b
    type: calls
```

Token cost: ~55-105 tokens/node vs 500-2000+ for raw source. **~13x reduction** for a typical Python repo.

---

## Splunk MCP Integration

Relic uses the Splunk MCP Server (Splunkbase App 7931) to query live Splunk data:

```python
# In mock mode (default), no Splunk needed:
relic serve ../demo-services --mock

# With real Splunk:
relic serve ../demo-services --no-mock --splunk-url http://localhost:8089 --splunk-token <token>
```

The mock layer provides realistic fallback data so your demo never breaks.

---

## Running Tests

```bash
cd context-engine
pip install pytest pytest-asyncio
pytest tests/ -v
```

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Parse time (demo repo, ~500 LOC) | **0.005s** |
| `.ctx` nodes generated | **44** |
| `.ctx` edges generated | **82** |
| Risk score latency | **< 500ms** |
| MCP query latency | **< 50ms** |

---

## Future Work

See [docs/05_DEFERRED_FEATURES.md](docs/05_DEFERRED_FEATURES.md) for:
- Live Observability Dashboard (real-time charts in VS Code)
- Embedded Flame Graphs
- Production Simulator (Pre-Mortem Engine)
- Multi-language support (Go, TypeScript, Rust)
- Durable Incident Journal (SQLite crash recovery)

---

## License

MIT — see [LICENSE](LICENSE)

---

## Judges: What to Look For

1. **Feature A demo**: Open any Python file in `demo-services/` → save → see risk score + decorations
2. **Feature B demo**: Open Relic SRE Chat → type "What errors has payment_service had?" → see SPL + results
3. **Code-to-Observability bridge**: The `.ctx` graph maps service.operation names from Splunk to exact code locations — no other tool does this
4. **Splunk AI integration**: SPL generation from natural language uses intent parsing + Splunk MCP Server