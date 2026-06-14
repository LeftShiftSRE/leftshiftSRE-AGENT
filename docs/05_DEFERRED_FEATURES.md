# Deferred Features: Relic — Code-Aware SRE Agent

## Overview

These features were cut from the MVP scope to ensure a polished, working submission for the hackathon deadline (June 15, 2026). Each feature is fully described here with implementation notes so they can be picked up post-hackathon in priority order.

---

## 1. In-IDE Live Observability Dashboard

**Status:** Deferred
**Priority:** High (post-MVP)
**Estimated Effort:** 8-12 hours

### Description
A webview panel inside VS Code showing real-time metrics of the local dev environment and production baseline from Splunk, side by side.

### What It Shows
- **Local metrics:** CPU usage, memory consumption, request latency, throughput (collected via Prometheus exporter or psutil)
- **Production baseline:** Same metrics from Splunk APM
- **Side-by-side comparison:** Local vs Prod delta highlighting
- **Auto-refresh:** Every 5 seconds with live Chart.js/D3.js graphs

### Technical Design

```
┌─────────────────────────────────────────────┐
│  Relic Dashboard                             │
│                                             │
│  ┌──────────────────┐  ┌──────────────────┐ │
│  │  Local Dev        │  │  Production       │ │
│  │  ┌──────────────┐ │  │  ┌──────────────┐ │ │
│  │  │ CPU: 23%     │ │  │  │ CPU: 67%     │ │ │
│  │  │ Mem: 340MB   │ │  │  │ Mem: 1.2GB   │ │ │
│  │  │ p99: 45ms    │ │  │  │ p99: 245ms   │ │ │
│  │  │ RPS: 120     │ │  │  │ RPS: 450     │ │ │
│  │  └──────────────┘ │  │  └──────────────┘ │ │
│  │  [Latency Chart]  │  │  [Latency Chart]  │ │
│  └──────────────────┘  └──────────────────┘ │
│                                             │
│  Δ p99: +200ms (4.4x slower in prod)        │
└─────────────────────────────────────────────┘
```

### Implementation Notes
- **Local collector:** Python `psutil` + custom middleware for FastAPI latency
- **Prometheus exporter:** `prometheus_client` Python library, scrape via HTTP
- **Production data:** Splunk MCP query for APM metrics
- **Webview:** React component with `recharts` (line charts for latency over time)
- **Data bridge:** VS Code webview messaging — context-engine publishes JSON metrics, webview polls every 5s
- **Key challenge:** Making the local collector lightweight enough not to skew the metrics it measures

### Dependencies
- Splunk MCP Server (for production baseline)
- Local Prometheus exporter running alongside demo services
- React + recharts in webview bundle

### Why Deferred
- 8-12 hours of fiddly UI work with chart rendering + auto-refresh
- Low novelty — every observability tool has dashboards
- Does not differentiate Relic from existing Dashboards
- Better to reference as "coming soon" in the README and demo video

---

## 2. Embedded Flame Graphs in VS Code Terminal

**Status:** Deferred
**Priority:** High (post-MVP, strong visual demo)
**Estimated Effort:** 10-15 hours

### Description
Performance profiling flame graphs rendered directly in the VS Code terminal or a webview panel, with click-to-navigate-to-code integration powered by `.ctx` node mapping.

### What It Shows
- **Normal profile:** Gray/blue frames showing baseline performance
- **Anomalous profile:** Red frames highlighting functions with abnormal latency
- **Code integration:** Click a flame graph frame → jump to `.ctx`-mapped source function
- **Comparison:** Overlay two flame graphs from different deployments

### Technical Design

```
┌─────────────────────────────────────────────────────┐
│  Relic Flame Graph                                   │
│                                                     │
│  ┌─────────────────────────────────────────────────┐│
│  │████████████████████████████████████████████████  ││
│  │█████████████  ███████████████████████████████    ││
│  │███████████      █████████████████████████████    ││
│  │█████████          ████████████  ████ ████████   ││
│  │████████              █████████    ██  ███████   ││
│  │███████                ████████    ██   ██████   ││
│  │██████   ┌──────────┐   █████              ████  ││
│  │█████    │🔴db_query │    ████               ███││
│  │████     │ (2.4s)    │     ███                ██ ││
│  │███      └──────────┘      ██                  █││
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  🔴 db_query() — 2.4s (click to open source)       │
│  Mapped to: payment_service/db.py:3 [→ Go to code]  │
└─────────────────────────────────────────────────────┘
```

### Implementation Notes
- **Data source:** OTel trace spans from Splunk APM (or simulated from `.ctx` call graph)
- **Rendering:** Webview with `d3-flame-graph` library (npm package)
- **Code mapping:** Each flame graph frame = service.operation → `.ctx` node_id → source location
- **Color coding:**
  - Normal frame: `#6699cc` (blue)
  - Anomalous (> 2x baseline): `#ff4444` (red)
  - User's code: `#44aa44` (green) vs dependencies: `#aaaaaa` (gray)
- **Click handler:** `onFrameClick` → VS Code `window.showTextDocument(Uri.file(node.path), { selection: new Range(node.start_line, 0, node.end_line, 0) })`
- **Simulation mode (without OTel):** Generate synthetic flame graph from `.ctx` edge structure by assigning random latency to each node, then rendering as tree

### Dependencies
- `d3-flame-graph` npm package in webview
- Splunk APM trace data (or synthetic generation)
- `.ctx` OTel mapper for frame → code mapping

### Why Deferred
- 10-15 hours for proper rendering + interaction + data pipeline
- Requires convincing Splunk APM to provide structured trace data via MCP
- High visual impact but high risk of demo failure if trace data doesn't load
- Simulation mode reduces it to a visual demo without real data

---

## 3. Production Environment Simulator ("Pre-Mortem Engine")

**Status:** Deferred
**Priority:** Medium (complex, requires separate infrastructure)
**Estimated Effort:** 40-60 hours (significant project)

### Description
Runs your code in a local mini-production clone with realistic traffic patterns, detecting issues (memory leaks, race conditions, N+1 queries, connection pool exhaustion) before deployment. Generates a "Pre-Mortem Report."

### What It Does
- **Traffic simulation:** Configurable concurrent users, request patterns, ramp-up profiles
- **Chaos injection:** Network latency, packet loss, process kills, disk pressure
- **Detection capabilities:**
  - Memory leaks under sustained load (RSS monitoring)
  - Race conditions (thread sanitizer / assertion failures)
  - N+1 query patterns (ORM query counting middleware)
  - Connection pool exhaustion (active connection monitoring)
- **Output:** Pre-Mortem Report with risk summary + code locations

### Technical Design

```
┌──────────────────────────────────────────────────┐
│  Pre-Mortem Engine                                │
│                                                  │
│  1. Spawn demo-services locally (Docker Compose) │
│  2. Attach monitors:                              │
│     - OTel collector (traces + metrics)           │
│     - Memory profiler (tracemalloc / memray)      │
│     - Query counter (SQL middleware)              │
│     - Connection pool watcher                     │
│  3. Run load test:                                │
│     - Locust / k6 / hey HTTP clients             │
│     - Ramp: 0 → 1000 RPS over 5 minutes          │
│     - Hold: 1000 RPS for 10 minutes              │
│     - Inject chaos: 100ms latency, 1% packet loss│
│  4. Collect observations:                         │
│     - Memory growth: +2.3 MB/min (LEAK DETECTED) │
│     - DB queries per request: 47 (N+1 DETECTED)  │
│     - Max connections: 100/100 (POOL EXHAUSTED)  │
│     - P99 latency: 2.4s (SLOW PATH DETECTED)     │
│  5. Map observations to .ctx nodes:              │
│     - Memory leak: → n_class_CacheManager:15     │
│     - N+1 queries: → n_func_charge:8             │
│     - Pool exhaustion: → n_func_db_connect:22    │
│  6. Generate Pre-Mortem Report                   │
└──────────────────────────────────────────────────┘
```

### Pre-Mortem Report Format
```yaml
pre_mortem_report:
  generated_at: "2026-06-15T12:00:00Z"
  scenario: "1000 concurrent users, 5 min ramp + 10 min steady"
  findings:
    - severity: "critical"
      type: "memory_leak"
      message: "RSS grows +2.3 MB/min under load"
      node_id: "n_class_CacheManager"
      file: "gateway/cache.py"
      line: 15
      recommendation: "Add TTL eviction to cache entries"

    - severity: "high"
      type: "n_plus_1_query"
      message: "47 DB queries per single charge() request"
      node_id: "n_func_charge"
      file: "payment_service/main.py"
      line: 8
      recommendation: "Use eager loading: SELECT * FROM items WHERE order_id IN (...)"

    - severity: "medium"
      type: "connection_pool_exhaustion"
      message: "DB connection pool maxed at 100/100"
      node_id: "n_func_db_connect"
      file: "payment_service/db.py"
      line: 3
      recommendation: "Increase pool size to 200 or add connection timeout"
```

### Implementation Notes
- **Load generation:** `locust` (Python) or `k6` (JavaScript)
- **Containerization:** Docker Compose for demo services + OTel collector + Jaeger
- **Memory profiling:** `tracemalloc` (stdlib) or `memray` (external)
- **N+1 detection:** SQLAlchemy/Django debug toolbar middleware counting queries
- **Chaos injection:** `toxiproxy` (network) + `stress-ng` (CPU/memory)
- **Integration with .ctx:** Map detected slow functions back to node_ids via OTel mapper

### Dependencies
- Docker + Docker Compose
- Locust or k6
- OTel Collector + Jaeger
- toxiproxy (chaos injection)
- Significant infrastructure setup

### Why Deferred
- 40-60 hour effort — impossible for hackathon
- Requires Docker infrastructure that may not work on judges' machines
- High risk of environmental failures during demo
- Better as post-MVP product feature demonstrated with a pre-recorded video
- **Mention in README as "Roadmap: Pre-Mortem Engine" with conceptual description**

---

## 4. Durable Incident Journal

**Status:** Deferred
**Priority:** Medium (important for production, not needed for demo)
**Estimated Effort:** 6-8 hours

### Description
SQLite-backed action journal that logs every SRE agent action with idempotency keys and state checkpoints. Enables crash recovery and incident replay.

### What It Does
- **Action logging:** Every MCP tool call logs an action with idempotency key
- **Checkpoints:** Long-running operations create checkpoints for resume-after-crash
- **Incident timeline:** Full replay of an investigation session
- **Post-incident report:** Auto-generated timeline of all agent actions during incident

### Technical Design

```sql
CREATE TABLE actions (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,           -- "splunk_query", "risk_score", "code_navigation"
  idempotency_key TEXT,         -- For deduplication
  payload TEXT NOT NULL,        -- JSON: input params
  result TEXT,                  -- JSON: output
  status TEXT NOT NULL,         -- "pending", "completed", "failed"
  incident_id TEXT,              -- Groups actions by incident
  created_at TEXT NOT NULL
);

CREATE TABLE checkpoints (
  id TEXT PRIMARY KEY,
  action_id TEXT NOT NULL,
  state TEXT NOT NULL,           -- JSON: serializable state
  created_at TEXT NOT NULL,
  FOREIGN KEY (action_id) REFERENCES actions(id)
);

CREATE TABLE incidents (
  id TEXT PRIMARY KEY,           -- e.g., "INC-2026-0615-001"
  splunk_incident_id TEXT,       -- Links to Splunk incident
  status TEXT NOT NULL,          -- "investigating", "resolved", "postmortem"
  started_at TEXT NOT NULL,
  resolved_at TEXT,
  summary TEXT
);
```

### Workflow

```
Incident fires → Relic creates incident record
  → Action: "Query Splunk for error logs"
    → Checkpoint: {spl_query: "...", results_received: true}
  → Action: "Map to .ctx nodes"
    → Checkpoint: {mapped_nodes: [...], risk_computed: true}
  → Action: "Generate recommendation"
  → Crash happens
  → Relic restarts → reads latest checkpoint → resumes from "Generate recommendation"
  → Incident resolved → generate postmortem from action timeline
```

### Why Deferred
- Important for production reliability but invisible in a 3-minute demo
- 6-8 hours of infrastructure work that doesn't add visible features
- **Mention in README as "Roadmap: Durable Execution" with SQLite schema**

---

## 5. Multi-Language Support

**Status:** Deferred
**Priority:** Low (architectural, not user-facing for MVP)
**Estimated Effort:** 8-12 hours per language adapter

### Description
Support for languages beyond Python by adding Tree-sitter parser adapters.

### Supported Languages (Post-MVP)

| Language | Tree-sitter Grammar | Effort | Notes |
|----------|--------------------|--------|-------|
| TypeScript/JavaScript | `tree-sitter-typescript`, `tree-sitter-javascript` | 8-12h | Rich AST, good community support |
| Go | `tree-sitter-go` | 6-8h | Excellent AST, simple language |
| Rust | `tree-sitter-rust` | 8-10h | Complex type system in AST |
| Java | `tree-sitter-java` | 6-8h | Mature grammar, enterprise demand |
| Ruby | `tree-sitter-ruby` | 6-8h | Good for Rails observability |

### Adapter Interface

```python
class ParserAdapter(ABC):
    @abstractmethod
    def language(self) -> str:
        """Return the language identifier."""

    @abstractmethod
    def extract_nodes(self, tree, source: bytes) -> list[Node]:
        """Extract structural nodes from the AST."""

    @abstractmethod
    def extract_edges(self, tree, source: bytes, nodes: list[Node]) -> list[Edge]:
        """Extract dependency edges between nodes."""

    @abstractmethod
    def extract_signatures(self, tree, source: bytes, nodes: list[Node]) -> dict[str, str]:
        """Map node_id → signature string."""
```

### Why Deferred
- Python is sufficient for the demo
- Each language requires custom `.scm` query files + edge extraction heuristics
- Risk scoring and OTel mapping work the same regardless of language (once `.ctx` is generated)
- **Mention in README as "Roadmap: Polyglot Support" with adapter interface description**

---

## 6. Incremental `.ctx` Parsing

**Status:** Deferred
**Priority:** Low (optimization, not user-facing)
**Estimated Effort:** 6-8 hours

### Description
Only re-parse files that have changed since the last `.ctx` generation, instead of re-parsing the entire repository.

### Implementation
1. Store a **manifest** alongside `.ctx`: `{ file_path: content_hash }`
2. On re-parse, compute content hashes for all files
3. Only re-parse files with changed hashes
4. Merge new nodes/edges into existing `.ctx` structure
5. Remove nodes for deleted files

### Manifest File (`.ctx/manifest.json`)
```json
{
  "payment_service/main.py": "sha256:abc123...",
  "order_service/main.py": "sha256:def456...",
  "gateway/main.py": "sha256:ghi789..."
}
```

### Why Deferred
- Full re-parse of demo repo (~500 LOC) takes < 2 seconds
- Optimization is only meaningful for repos > 10k LOC
- Adds complexity (merge logic, deletion detection, edge re-wiring)
- **Not needed for hackathon demo**

---

## 7. Feature Priority Matrix (Post-MVP Build Order)

| Priority | Feature | Effort | Impact | Dependencies |
|----------|---------|--------|--------|-------------|
| 1 | In-IDE Dashboard | 8-12h | High visual value | Splunk MCP, local collector |
| 2 | Flame Graphs | 10-15h | High visual value, strong demo | d3-flame-graph, OTel traces |
| 3 | Durable Journal | 6-8h | Production reliability | SQLite, incident model |
| 4 | Multi-Language (TypeScript) | 8-12h | Broaden user base | Parser adapters |
| 5 | Pre-Mortem Engine | 40-60h | Killer feature (long-term) | Docker, load testing, chaos |
| 6 | Multi-Language (Go) | 6-8h | Enterprise demand | Parser adapters |
| 7 | Incremental Parsing | 6-8h | Performance | Manifest file |
