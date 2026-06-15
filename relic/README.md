# Relic — Context-aware SRE Agent

AI-powered SRE agent that correlates git diffs with production incidents
via Splunk MCP Server.

## Quick Demo
```bash
python demo/analyze.py
```

## The Moat
git diff → Tree-sitter call graph → OTel mapping → Splunk incidents → blast radius
**One deterministic MCP tool call. No LLM hallucination.**

## Splunk AI Capabilities
- ✅ MCP Server (4 tools)
- ✅ KV Store (service mapping)
- ✅ Summary Index (precomputed risk)
- ✅ AI Toolkit (anomaly detection + predict)

## Architecture
```text
┌──────────────┐     git diff     ┌─────────────────┐
│   VS Code    │ ───────────────▶ │  Tree-sitter    │
│   (future)   │                  │  Call Graph     │
└──────────────┘                  └────────┬────────┘
                                           │ node_ids
                                           ▼
┌──────────────┐    MCP tool    ┌─────────────────┐
│   AI Agent   │ ◀────────────▶ │   MCP Server    │
│ (Claude/etc) │   get_risk_   │   (Relic)       │
└──────────────┘    score       └────────┬────────┘
                                          │ SPL query
                                          ▼
┌──────────────┐                  ┌─────────────────┐
│   Splunk     │ ◀────────────────│  Saved Search   │
│   Summary    │   MLTK anomaly   │  risk_score_    │
│   Index      │   detection      │  for_nodes      │
└──────────────┘                  └─────────────────┘
```

## MCP Tools
| Tool | Description |
|------|-------------|
| get_risk_score | Risk score for modified code |
| sre_chat_query | NL → saved search |
| map_service_to_node | OTel → code node |
| get_incidents_for_service | Incident history |

## Roadmap
- [ ] Real Splunk integration (RELIC_MOCK=0)
- [ ] MLTK model validation
- [ ] VS Code extension
- [ ] Semantic graph (SCIP)