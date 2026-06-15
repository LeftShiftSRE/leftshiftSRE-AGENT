# Relic — Goals, Requirements & Hackathon Alignment

## 1. Project Goals

### Primary Goals

| # | Goal | Why It Matters | Measured By |
|---|------|---------------|-------------|
| G1 | **Splunk AI is actually used at runtime** | Single biggest disqualification risk — projects without real Splunk AI are disqualified | Code inspection shows real MCP tool calls to Splunk AI capabilities when the project runs |
| G2 | **Bridge production observability → code context** | Core value proposition — nobody else does this | Developer can go from Splunk alert → exact function in IDE in < 30 seconds |
| G3 | **Demonstrate agentic behavior** | Hackathon emphasizes "Agentic Ops" — tool-chaining, not just query/response | `investigate_incident` chains 4+ MCP tool calls autonomously |
| G4 | **Visual differentiation** | Judges see 50+ submissions — dashboards and flame graphs are memorable | Dashboard webview with live charts, flame graph, network topology |
| G5 | **Use multiple Splunk AI capabilities** | Grand Prize requires demonstrating depth of Splunk integration | 4+ Splunk AI capabilities used: MCP Server, AI Assistant, AI Toolkit, Hosted Models |

### Secondary Goals

| # | Goal | Why It Matters |
|---|------|---------------|
| G6 | Self-contained demo (works on judges' machines) | Judges must be able to run it |
| G7 | Polished README and demo video | Required for submission |
| G8 | Real-time data pipeline (live, not static) | Shows production-readiness, not just a mock demo |
| G9 | Code navigation from observability data | Unique differentiator — no other tool maps metrics → code |

---

## 2. Hackathon Requirements Compliance Matrix

### 2.1 Mandatory Requirements (Disqualification if Missing)

| Requirement | Status | How Relic Satisfies | Evidence Location |
|------------|--------|---------------------|-------------------|
| **Splunk AI capabilities are actually used at runtime** | IN PROGRESS → MUST FIX | Replace regex SPL gen with AI Assistant; replace raw REST with MCP Server tools | `splunk_client.py` MCP tool calls, `server.py` `ai_spl_generate` tool |
| **Not only on other tools (e.g., Gemini or Firebase alone)** | PASS | No external AI services used — all AI via Splunk | `splunk_client.py` has no OpenAI/Anthropic/Gemini calls |
| **Not a mock prototype with simulated Splunk output** | IN PROGRESS → MUST FIX | Connect to real Splunk MCP Server; mock is fallback only, not default | `splunk_client.py` `use_mock=False` is target default |
| **Not only describing a planned Splunk integration** | IN PROGRESS → FIXING | Code must call Splunk at runtime — no "planned" integrations | All MCP tool calls are in `server.py` handler methods |
| **Open source license** | TODO | Add MIT LICENSE file | Repo root |
| **Demo video (under 3 min)** | TODO | Record walkthrough showing real Splunk + code navigation | YouTube/Vimeo link |
| **README with setup and run instructions** | TODO | Rewrite README with Splunk setup, data ingestion, extension launch | `README.md` |
| **Architecture diagram** | TODO | Update `02_ARCHITECTURE.md` with Mermaid diagram + export PNG | `docs/` |

### 2.2 Splunk AI Capability Usage (Must Use 1+, Target 4+)

| Splunk AI Capability | Used? | Where in Code | Runtime Flow | Prize Eligibility |
|----------------------|-------|--------------|-------------|-------------------|
| **Splunk MCP Server** | PARTIAL → FIXING | `splunk_client.py` → rewrite to MCP tool calls | `search` + `indexed_search` + `saved_search` via `/services/mcp/v1/tools/call` | **Best Use of MCP Server ($1,000)** |
| **AI for Splunk Apps** | NOT YET | Could build risk scoring as Splunk app | Python SDK app inside Splunk runs `_score_node` logic | General |
| **Splunk AI Assistant (SPL generation)** | NOT YET → CRITICAL | `server.py` → new `ai_spl_generate` tool | `generate_spl` MCP tool → natural language → SPL | **Avoids DQ** |
| **Splunk AI Assistant (SPL explanation)** | NOT YET | `server.py` → new `ai_spl_explain` tool | `explain_spl` MCP tool → results explanation | General |
| **Splunk AI Toolkit** | NOT YET | `risk.py` → MLTK model prediction | Train anomaly model on APM data → `predict_anomaly` tool | General |
| **Splunk Hosted Models (Deep Time Series)** | NOT YET | Dashboard → forecast chart | `forecast_metric` tool → Cisco Deep Time Series Model | General |
| **Splunk Hosted Models (Foundation Security)** | NOT YET | `splunk_client.py` → anomaly detection | `detect_anomalies` tool → Foundation AI Security Model | General |

**Current count: 0 used at runtime (regex SPL gen does NOT count). Target: 4+.**

---

## 3. Hackathon Prize Alignment

### 3.1 Prize Targeting Strategy

| Prize | Amount | How Relic Wins It | Current Gap | Priority |
|-------|--------|-------------------|-------------|----------|
| **Best Use of Splunk MCP Server** | $1,000 | All Splunk queries go through MCP Server (not raw REST); MCP tools used for search, AI SPL generation, and saved search execution | Currently using raw REST API, not MCP Server | P0 |
| **Best of Observability** | $3,000 | Core value: bridging production metrics → code with dependency graph; real-time dashboard with flame graph; incident → code navigation | Dashboard not built; mock data by default; no visual demo | P1 |
| **Grand Prize** | $7,000 | Combined: real Splunk AI at runtime (AI Assistant + MCP Server + AI Toolkit) + agentic multi-tool investigation + production-grade dashboard + novel code-observability bridge | All of the above gaps | P0-P3 |

### 3.2 Judging Criteria Alignment

Based on typical hackathon judging rubrics:

| Criterion | Weight | How Relic Scores | Strengthening Actions |
|-----------|--------|-----------------|---------------------|
| **Innovation & Novelty** | 25% | HIGH — mapping code → observability via .ctx graph is unique. Flame graph in IDE is novel. Agentic investigation is forward-looking. | Build flame graph; accentuate "no other tool does this" in demo video |
| **Technical Complexity** | 20% | MEDIUM → HIGH with improvements — tree-sitter parsing, MCP protocol, graph traversal, multi-tool orchestration. Low currently because regex SPL is trivial. | Replace regex with AI Assistant; add MLTK prediction; add Deep Time Series forecast |
| **Use of Splunk AI** | 25% | FAILING → HIGH with fixes — currently 0 Splunk AI at runtime. With MCP Server + AI Assistant + AI Toolkit + Hosted Models = 5 capabilities = strong. | P0: wire real MCP + AI Assistant immediately |
| **Completeness & Polish** | 15% | MEDIUM — two features work, but no dashboard, minimal README, no video. | Build dashboard; write thorough README; record professional demo video |
| **Practical Value** | 15% | HIGH — real SRE pain point (incident → root cause takes too long). 30-second path from alert → code is genuinely useful. | Demonstrate with realistic incident scenario; show HEC live data pipeline |

---

## 4. Goal → Implementation Mapping

### G1: Splunk AI at Runtime (CRITICAL — Disqualification Risk)

**Current state:** `SPLQueryGenerator` uses regex pattern matching. `SplunkClient._execute_spl()` calls raw REST. Neither uses Splunk AI.

**Implementation tasks:**
1. Rewrite `SplunkClient` to call MCP Server endpoints (`/services/mcp/v1/tools/call`)
2. Add `ai_generate_spl(natural_language)` → calls MCP Server's `generate_spl` tool
3. Add `ai_explain_spl(spl_query, results)` → calls MCP Server's `explain_spl` tool
4. Update `sre_chat_query` handler: `NL → ai_generate_spl → search → results`
5. Update `investigate_incident` handler: chains 4+ MCP tool calls
6. Change default to `use_mock=False`, mock as fallback only

**Verification:** Run the extension with Splunk running → check logs show MCP tool calls → confirm `generate_spl` returns AI-generated SPL, not regex templates.

### G2: Bridge Observability → Code

**Current state:** OTelMapper provides `service.operation → node_id` mapping. `map_metric_to_code` tool works. Code navigation from chat results works.

**Implementation tasks:**
1. Dashboard: click a metric card → navigate to mapped function in editor
2. Flame graph: click a frame → navigate to `.ctx`-mapped source code
3. Investigation report: click affected node → open in editor with risk highlight
4. Incident → code quickpick: select incident from list → auto-navigate

**Verification:** Click "charge" in dashboard → VS Code opens `payment_service/main.py` at line 8.

### G3: Agentic Behavior

**Current state:** Each tool call is independent. No tool-chaining.

**Implementation tasks:**
1. New `investigate_incident` tool: chains search → explain → map → risk → recommend
2. New `proactive_risk_check` tool: on save, automatically queries recent anomalies → correlates with changed code → suggests "this change might trigger the pattern seen in INC-X"
3. Chat follow-up: AI-generated explanation uses `explain_spl` to give context-aware answers

**Verification:** Trigger investigation → logs show 4 sequential tool calls → returns structured report.

### G4: Visual Differentiation

**Current state:** Status bar + text decorations + tree view + basic chat. No charts, no graphs.

**Implementation tasks:**
1. Dashboard webview with Chart.js (service health cards, latency line chart, error rate bars)
2. D3.js flame graph (from .ctx call structure + Splunk latency data)
3. D3.js force-directed network graph (blast radius visualization)
4. Risk score radial gauge
5. Auto-refresh every 5s with live data from Splunk

**Verification:** Open dashboard → see live-updating charts and interactive flame graph.

### G5: Multiple Splunk AI Capabilities

| Capability | Implementation | Timeline |
|-----------|---------------|----------|
| MCP Server | Rewrite SplunkClient to use MCP endpoints | P0 |
| AI Assistant (SPL gen) | `ai_generate_spl` tool | P0 |
| AI Assistant (SPL explain) | `ai_explain_spl` tool | P2 |
| AI Toolkit (MLTK) | Train anomaly model → `predict_anomaly` | P2 |
| Deep Time Series Model | `forecast_metric` tool → dashboard forecast chart | P2 |

**Verification:** Count of Splunk AI capabilities called at runtime = 4+. Each call logged.

---

## 5. What the Splunk Developer License Gives Us

| Feature | Free Tier | Developer License (Ours) | Impact on Project |
|---------|-----------|--------------------------|-------------------|
| Daily ingest volume | 500 MB/day | **Unlimited** | Can load realistic data volumes for demo (10K+ log events, time-series metrics) |
| Search concurrency | 1 concurrent search | **Multiple** | Dashboard can run 4+ parallel queries without blocking |
| MCP Server access | Yes, basic | **Yes, full** | Required for Prize: Best Use of MCP Server |
| AI Assistant | Limited | **Full access** | Required for SPL generation (disqualification risk) |
| AI Toolkit (MLTK) | Not available | **Full access** | Enables ML-powered risk scoring |
| Hosted Models | Not available | **Full access** | Enables time-series forecasting and security anomaly detection |
| License duration | 60 days | **6 months** | No time pressure |
| Saved searches & alerts | Limited (3) | **Unlimited** | Can create complex saved searches for investigation pipeline |
| RBAC | Single user | **Multi-role** | Can demonstrate secure agent access patterns |
| API access | Read-only | **Full CRUD** | Can programmatically create indexes, ingest data, configure HEC |

**Key license benefit:** The developer license removes the 500MB/day ingest limit, which is critical because the demo needs enough data volume to make dashboards, trend charts, and ML models look realistic (not just 8 JSON lines).

---

## 6. Submission Checklist

### Required By Hackathon

- [ ] Text description of project features and functionality
- [ ] Demo video (under 3 min) on YouTube/Vimeo
  - [ ] Shows project working with real Splunk data
  - [ ] Demonstrates Splunk AI usage (AI SPL generation, MCP tools)
  - [ ] Explains problem and value proposition
  - [ ] Shows code navigation from observability data
- [ ] Public open-source repo with:
  - [ ] Open source license (MIT)
  - [ ] All source code + assets + run instructions
  - [ ] README with setup and run instructions
  - [ ] Required dependencies + example configs/datasets
  - [ ] Architecture diagram
- [ ] Submit under **Observability** track

### Strengthening for Judging

- [ ] At least 4 Splunk AI capabilities used at runtime
- [ ] Generative dashboard with live data
- [ ] Flame graph visualization
- [ ] Agentic investigation workflow (chained tool calls)
- [ ] Real-time HEC data pipeline from demo services
- [ ] Professional architecture diagram (Mermaid → PNG)
- [ ] "Powered by Splunk AI" indicators in UI
- [ ] README with screenshots and animated GIF
- [ ] Clear "How it uses Splunk AI" section in README

---

## 7. Risk → Mitigation Mapping

| Risk | Severity | Mitigation |
|------|----------|-----------|
| **Regex SPL gen = no Splunk AI = DQ** | FATAL | P0: Replace with AI Assistant `generate_spl` via MCP |
| **Raw REST = not using MCP Server = no prize** | HIGH | P0: Rewrite SplunkClient to use MCP Server tools |
| **Mock data default = "simulated Splunk output" = DQ** | HIGH | P0: Change default to `use_mock=False` |
| **Dashboard not built = low visual impact** | MEDIUM | P1: Build Chart.js dashboard with auto-refresh |
| **Only 1 Splunk AI capability used** | MEDIUM | P2: Add AI Toolkit + Hosted Models = 4+ capabilities |
| **No agentic behavior shown** | MEDIUM | P3: `investigate_incident` chains 4+ tool calls |
| **Demo video not recorded** | HIGH | P3: Script and record before deadline |
| **README is 1 line** | HIGH | P3: Write comprehensive README |
