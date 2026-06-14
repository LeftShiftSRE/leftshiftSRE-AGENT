# Project Plan: Relic — Code-Aware SRE Agent (MVP)

## Document Purpose
This is the execution plan for building Relic's MVP for the **Splunk Agentic Ops Hackathon** (deadline: June 15, 2026). It covers only the MVP scope. Deferred features are documented in `05_DEFERRED_FEATURES.md`.

---

## 1. Product Summary

**Relic** is an AI-powered SRE agent that lives in VS Code and bridges the gap between **production observability data** (from Splunk) and **structural code context** (from the `.ctx` graph).

**Core value proposition:** When an incident fires in Splunk, Relic maps the alert to the exact function in your codebase, traces the dependency chain, and scores the risk of your pending code changes — all without leaving the IDE.

**Hackathon tagline:** *"From Splunk Alert to Root Cause in 30 Seconds — Without Leaving Your IDE"*

---

## 2. MVP Scope: 2 Features

### Feature A: Code-Risk Predictor
Analyzes every Git commit by traversing the `.ctx` structural graph combined with Splunk incident history. Outputs a risk score (0-100) with inline VS Code decorations showing why the change is risky and which past incidents are similar.

**User flow:**
1. Developer modifies `payment_service/charge.py`
2. Relic detects changed `.ctx` nodes via `git diff`
3. Traverses dependency graph to compute blast radius (how many services/functions downstream)
4. Queries Splunk MCP for incident history on affected nodes
5. Computes risk score and displays red/yellow/green indicator in VS Code status bar + inline decorations on modified lines
6. Hover on decoration shows: *"Risk 87/100: Charge() is on critical path. 3 dependents. Similar change caused INC-1029 (p99 2.4s)"*

### Feature B: Natural Language SRE Chat
A chat panel inside VS Code where the developer types natural language questions. The agent generates Splunk SPL queries, executes them via Splunk MCP Server, and maps results back to `.ctx` code nodes with one-click navigation.

**User flow:**
1. Developer types: *"What errors has payment_service had in the last 24h?"*
2. Agent generates SPL: `index=app sourcetype=logs service=payment_service level=ERROR earliest=-24h | stats count by message | sort -count`
3. Executes via Splunk MCP Server (or falls back to mock data)
4. Returns structured results with `.ctx` node mappings
5. Developer clicks a result → jumps to the exact function in the code editor
6. Inline annotation shows: *"charge() — 47 errors in 24h, p99 latency 2.4s"*

---

## 3. What Is NOT in MVP

The following features are **intentionally deferred**. See `05_DEFERRED_FEATURES.md` for full descriptions and future implementation plans:

- **In-IDE Live Observability Dashboard** — real-time CPU/memory/latency charts
- **Embedded Flame Graphs** — perf-style flame graph visualization in VS Code
- **Production Environment Simulator** — load testing + pre-mortem report
- **Durable Incident Journal** — SQLite-backed crash recovery for agent workflows
- **Multi-Language Support** — only Python in MVP
- **Incremental `.ctx` Parsing** — full re-parse each time

These are **referenced in the README and demo video** as "coming soon" to show product vision, but are **not built** for the hackathon.

---

## 4. Execution Timeline

### Day 1: Foundation (Hours 0-14)

| Hours | Task | Deliverable |
|-------|------|-------------|
| 0-2 | Set up Python project structure (`context-engine/`, `relic-vscode/`, `demo-services/`) | Monorepo skeleton with `pyproject.toml`, `package.json`, `.gitignore` |
| 2-4 | Build `.ctx` parser with Tree-sitter Python | CLI: `relic parse ./demo-services` → `repo.ctx` YAML |
| 4-5 | Create demo fixture repo (3 FastAPI microservices) | `demo-services/` with known call chain |
| 5-7 | Parse demo repo → validate `.ctx` output | Golden snapshot test: `repo.ctx` committed |
| 7-9 | Build MCP Server (stdio) for `.ctx` queries | `relic serve` starts MCP server with 5 endpoints |
| 9-11 | Build Splunk MCP mock layer | JSON files with fake incident data mapped to node_ids |
| 11-13 | Implement risk scoring engine | Git diff → changed nodes → graph traversal → incident lookup → score |
| 13-14 | Test end-to-end: modify demo file → get risk score via MCP | Risk score computed correctly for known scenario |

### Day 2: VS Code Extension + Polish (Hours 14-28)

| Hours | Task | Deliverable |
|-------|------|-------------|
| 14-16 | VS Code extension scaffold + MCP client | Extension activates, connects to context-engine MCP |
| 16-18 | Feature A UI: status bar indicator + inline decorations | Red/yellow/green score on modified lines with hover tooltips |
| 18-19 | Feature A: impact map sidebar panel | Tree view showing dependency chain with incident overlays |
| 19-21 | Feature B UI: chat webview panel | Input box + response area in sidebar |
| 21-23 | Feature B: SPL generation + Splunk MCP integration | Chat → SPL → execute → results with node mappings |
| 23-24 | Feature B: code navigation from results | Click result → jump to `.ctx`-mapped function in editor |
| 24-26 | Integrate with real Splunk (if available) or refine mocks | Swap mock layer for real Splunk MCP Server queries |
| 26-27 | Architecture diagram (`ARCHITECTURE.md`) | Required by hackathon submission |
| 27-28 | Demo video recording (3 min) + README polish | Final submission deliverables |

### Milestones

| Milestone | Target Hour | Success Criteria |
|-----------|-------------|------------------|
| M1: `.ctx` Pipeline | Hour 7 | `relic parse` generates valid `.ctx` for demo repo |
| M2: MCP Server Working | Hour 11 | Can query nodes, edges, and incident data via MCP |
| M3: Risk Score Computed | Hour 14 | Modifying a file returns correct risk score |
| M4: VS Code Feature A | Hour 19 | Status bar + decorations + impact map functional |
| M5: VS Code Feature B | Hour 24 | Chat → SPL → results → code navigation working |
| M6: Submission Ready | Hour 28 | Video recorded, README complete, repo public |

---

## 5. Team & Roles

| Role | Person | Responsibilities |
|------|--------|-----------------|
| Full-stack (solo) | You | Context Engine, VS Code Extension, Demo Repo, Docs, Video |

---

## 6. Hackathon Submission Checklist

- [ ] Text description of project features and functionality
- [ ] Demo video (under 3 min) on YouTube/Vimeo
  - [ ] Shows project working
  - [ ] Demonstrates AI usage (risk scoring + SPL generation)
  - [ ] Explains problem and value
- [ ] Public open-source repo with:
  - [ ] Open source license (MIT)
  - [ ] All source code + assets + run instructions
  - [ ] README with setup and run instructions
  - [ ] Required dependencies + example configs/datasets
  - [ ] Architecture diagram (see `02_ARCHITECTURE.md`)
- [ ] Submit under **Observability** track

---

## 7. Prize Targeting Strategy

| Prize | How Relic Targets It |
|-------|---------------------|
| **Best of Observability** ($3,000) | Core value: bridging production metrics → code with dependency graph |
| **Best Use of Splunk MCP Server** ($1,000) | Direct Splunk MCP integration for incident → code mapping |
| **Grand Prize** ($7,000) | Combined novelty + Splunk AI usage + real problem + polished demo |

---

## 8. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Splunk MCP setup takes too long | Medium | High | Build mock layer FIRST, swap real Splunk in later |
| Tree-sitter Python parser misses edge cases | Medium | Medium | Start with subset: functions, classes, imports, calls |
| VS Code webview performance issues | Low | Medium | Keep UI minimal; use tree view API instead of complex webview |
| Risk scoring feels "fake" without real incidents | Medium | Medium | Pre-populate mock with realistic incident patterns; name real-world outage types |
| MCP protocol version mismatch | Low | High | Pin `mcp` Python SDK version; test early |

---

## 9. Success Metrics

1. `.ctx` file generates in < 10s for demo repo (~500 LOC)
2. MCP query latency < 200ms for node/edge lookups
3. Risk score correctly identifies the "N+1 query in payment_service" scenario
4. SRE Chat returns relevant SPL results with code navigation
5. Demo video shows complete flow in under 3 minutes
6. Repository builds and runs from README instructions on a fresh machine
