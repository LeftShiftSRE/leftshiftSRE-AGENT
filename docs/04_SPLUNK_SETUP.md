# Splunk Setup Guide: Relic — Code-Aware SRE Agent

## Overview

This guide walks you through setting up Splunk Enterprise with the MCP Server, ingesting sample observability data, and connecting Relic to it. If Splunk is not available, Relic falls back to mock data automatically.

---

## 1. Prerequisites

| Requirement | Details |
|-------------|---------|
| Operating System | Windows, macOS, or Linux |
| RAM | Minimum 8 GB (16 GB recommended) |
| Disk Space | 5 GB for Splunk Enterprise install + data |
| Python | 3.12+ |
| Network | localhost access (all services run locally) |

---

## 2. Splunk Enterprise Installation

### 2.1 Download

1. Go to https://www.splunk.com/en_us/download/splunk-enterprise.html
2. Download the appropriate installer for your OS
   - Windows: `.msi` installer
   - macOS: `.dmg` 
   - Linux: `.tgz` tarball
3. Run the installer with default settings

### 2.2 Apply Developer License

Your free trial is valid for 60 days. Extend it to 6 months with a developer license:

1. Go to https://dev.splunk.com/
2. Sign up / log in with your Splunk account
3. Navigate to **Developer Program** → **Request Developer License**
4. You will receive a license file (`splunk.lic`) via email
5. Apply the license:
   - Open Splunk Web: http://localhost:8000
   - Login (default: admin / changeme)
   - Go to **Settings** → **Licensing** → **Add license**
   - Upload the `.lic` file
   - Restart Splunk when prompted

### 2.3 Verify Installation

```bash
# Check Splunk is running
# Windows:
& "C:\Program Files\Splunk\bin\splunk.exe" status

# macOS/Linux:
$SPLUNK_HOME/bin/splunk status
```

Open http://localhost:8000 — you should see the Splunk login screen.

---

## 3. Splunk MCP Server Setup

The Splunk MCP Server allows AI agents (like Relic) to query Splunk data via the Model Context Protocol.

### 3.1 Install the MCP Server App

1. Go to Splunkbase: https://splunkbase.splunk.com/app/7931
2. Click **Install** (or download the `.spl` file)
3. In Splunk Web: **Apps** → **Install app from file** → upload the `.spl`
4. Restart Splunk

Alternatively, install via CLI:
```bash
$SPLUNK_HOME/bin/splunk install app <path_to_mcp_server.spl>
```

### 3.2 Configure Authentication

The MCP Server uses token-based authentication (OAuth is in Controlled Availability, not yet GA).

1. In Splunk Web, go to **Settings** → **Token**
2. Click **Create Token**
3. Settings:
   - **Name:** `relic-mcp-token`
   - **Expiration:** 90 days
   - **Role:** admin (for dev only)
   - **Audience:** `rellic-mcp`
4. Copy the generated token value — you will need it for Relic configuration

### 3.3 Configure MCP Server

Edit `$SPLUNK_HOME/etc/apps/splunk_mcp_server/local/mcp_server.conf`:

```ini
[mcp_server]
host = 0.0.0.0
port = 8089
auth_type = token
enabled = 1

[tools]
search_enabled = 1
indexed_search_enabled = 1
saved_search_enabled = 1
```

### 3.4 Verify MCP Server

Test that the MCP Server responds:

```bash
curl -k -H "Authorization: Bearer <YOUR_TOKEN>" \
  https://localhost:8089/services/mcp/v1/health
```

Expected response: `{"status": "ok"}`

---

## 4. Ingest Sample Data

Relic needs three types of data in Splunk: logs, APM traces, and incident records.

### 4.1 Create Indexes

In Splunk Web → **Settings** → **Indexes**:

| Index Name | Data Type | Retention |
|------------|-----------|-----------|
| `app` | Application logs | 30 days |
| `apm` | APM traces + metrics | 30 days |
| `incidents` | Incident records | 90 days |

Or via CLI:
```bash
$SPLUNK_HOME/bin/splunk add index app -auth admin:changeme
$SPLUNK_HOME/bin/splunk add index apm -auth admin:changeme
$SPLUNK_HOME/bin/splunk add index incidents -auth admin:changeme
```

### 4.2 Ingest Log Data

Create the sample logs file (`demo-services/data/sample_logs.json`):

```json
{"timestamp": "2026-06-14T10:00:00Z", "service": "payment_service", "operation": "charge", "level": "ERROR", "message": "ConnectionTimeout: database connection pool exhausted", "trace_id": "abc123"}
{"timestamp": "2026-06-14T10:05:00Z", "service": "payment_service", "operation": "charge", "level": "ERROR", "message": "PoolExhausted: max connections reached", "trace_id": "def456"}
{"timestamp": "2026-06-14T10:10:00Z", "service": "payment_service", "operation": "charge", "level": "WARN", "message": "Slow query detected: 2.4s", "trace_id": "ghi789"}
{"timestamp": "2026-06-14T10:15:00Z", "service": "order_service", "operation": "create_order", "level": "ERROR", "message": "UpstreamTimeout: payment_service.charge timed out after 5s", "trace_id": "jkl012"}
{"timestamp": "2026-06-14T10:20:00Z", "service": "inventory_service", "operation": "reserve", "level": "INFO", "message": "Successfully reserved 100 units", "trace_id": "mno345"}
{"timestamp": "2026-06-14T10:25:00Z", "service": "gateway", "operation": "POST /order", "level": "ERROR", "message": "OrderFailed: downstream timeout", "trace_id": "pqr678"}
```

Ingest via CLI:
```bash
$SPLUNK_HOME/bin/splunk add oneshot \
  demo-services/data/sample_logs.json \
  -index app \
  -sourcetype _json \
  -auth admin:changeme
```

Or via Splunk Web: **Add Data** → **Upload** → select file → set index `app` and sourcetype `_json`.

### 4.3 Ingest APM Metrics Data

Create `demo-services/data/sample_metrics.json`:

```json
{"timestamp": "2026-06-14T10:00:00Z", "service": "payment_service", "operation": "charge", "metric": "latency_p99_ms", "value": 2400}
{"timestamp": "2026-06-14T10:00:00Z", "service": "payment_service", "operation": "charge", "metric": "error_rate", "value": 0.03}
{"timestamp": "2026-06-14T10:00:00Z", "service": "payment_service", "operation": "charge", "metric": "throughput_rps", "value": 450}
{"timestamp": "2026-06-14T10:00:00Z", "service": "order_service", "operation": "create_order", "metric": "latency_p99_ms", "value": 380}
{"timestamp": "2026-06-14T10:00:00Z", "service": "order_service", "operation": "create_order", "metric": "error_rate", "value": 0.008}
{"timestamp": "2026-06-14T10:00:00Z", "service": "inventory_service", "operation": "reserve", "metric": "latency_p99_ms", "value": 45}
{"timestamp": "2026-06-14T10:00:00Z", "service": "inventory_service", "operation": "reserve", "metric": "error_rate", "value": 0.001}
```

Ingest:
```bash
$SPLUNK_HOME/bin/splunk add oneshot \
  demo-services/data/sample_metrics.json \
  -index apm \
  -sourcetype _json \
  -auth admin:changeme
```

### 4.4 Ingest Incident Records

Create `demo-services/data/sample_incidents.json`:

```json
{"timestamp": "2026-05-28T14:30:00Z", "id": "INC-1029", "service": "payment_service", "operation": "charge", "severity": "high", "type": "latency_spike", "summary": "p99 latency spike 2.4s on payment_service.charge", "duration_minutes": 45, "affected_users": 4500}
{"timestamp": "2026-04-15T09:00:00Z", "id": "INC-876", "service": "payment_service", "operation": "charge", "severity": "critical", "type": "timeout_cascade", "summary": "Timeout cascade: payment_service.charge caused order_service timeout", "duration_minutes": 120, "affected_users": 12000}
{"timestamp": "2026-03-10T18:00:00Z", "id": "INC-412", "service": "order_service", "operation": "create_order", "severity": "medium", "type": "error_rate_spike", "summary": "Error rate spike 8% on create_order due to upstream payment timeout", "duration_minutes": 30, "affected_users": 800}
```

Ingest:
```bash
$SPLUNK_HOME/bin/splunk add oneshot \
  demo-services/data/sample_incidents.json \
  -index incidents \
  -sourcetype _json \
  -auth admin:changeme
```

### 4.5 Verify Data

In Splunk Web search bar, verify each index:

```
index=app | head 5
index=apm | head 5
index=incidents | head 5
```

You should see the ingested records.

---

## 5. Configure Relic to Use Splunk

### 5.1 VS Code Settings

Open VS Code settings (JSON) and add:

```json
{
  "relic.useMockData": false,
  "relic.splunkMcpUrl": "https://localhost:8089",
  "relic.splunkToken": "<YOUR_TOKEN_FROM_STEP_3.2>"
}
```

### 5.2 Context Engine Configuration

When starting the MCP server in real-Splunk mode:

```bash
relic serve --repo ./demo-services --no-mock
```

The `--no-mock` flag tells the Context Engine to query Splunk MCP Server instead of reading from `mock/` JSON files.

### 5.3 Fallback Behavior

If Splunk MCP Server is unreachable (network error, wrong token, etc.):

1. Context Engine logs a warning: `"Splunk MCP unavailable, falling back to mock data"`
2. All queries return results from `mock/` JSON files
3. Risk scores and chat responses still work, but with static data
4. Status bar shows a small indicator: `⚠ Mock Data`

This ensures the demo **never breaks** — even without Splunk running.

---

## 6. Sample SPL Queries for Testing

These queries can be run in Splunk Web to verify your data is correct:

### Error count by service (last 24h)
```spl
index=app level=ERROR earliest=-24h
| stats count by service, operation
| sort -count
```

### Latency p99 by service
```spl
index=apm metric=latency_p99_ms
| stats latest(value) as p99 by service, operation
| sort -p99
```

### Recent incidents
```spl
index=incidents
| sort -timestamp
| table id, service, severity, summary, duration_minutes
```

### Error rate correlation with incidents
```spl
index=apm metric=error_rate
| stats latest(value) as current_error_rate by service, operation
| join service, operation [
    search index=incidents
    | stats count as incident_count, max(severity) as worst_severity by service, operation
]
| table service, operation, current_error_rate, incident_count, worst_severity
```

---

## 7. Troubleshooting

| Issue | Solution |
|-------|---------|
| Splunk won't start | Check port 8000 is not in use: `netstat -an \| grep 8000` |
| MCP Server not found | Verify app is installed: `$SPLUNK_HOME/bin/splunk display app` |
| Token auth fails | Regenerate token in Settings → Token Management |
| No search results | Check index exists and data was ingested: `index=app \| stats count` |
| HTTPS cert error | Add `-k` flag to curl, or install Splunk's self-signed cert |
| Permission denied | Ensure Splunk process has read access to data files |

### Windows-Specific Notes

```powershell
# Start Splunk
& "C:\Program Files\Splunk\bin\splunk.exe" start

# Check status
& "C:\Program Files\Splunk\bin\splunk.exe" status

# Ingest data
& "C:\Program Files\Splunk\bin\splunk.exe" add oneshot "E:\LeftshiftSRE\demo-services\data\sample_logs.json" -index app -sourcetype _json -auth admin:changeme
```

---

## 8. Demo Day Checklist

- [ ] Splunk Enterprise is running on http://localhost:8000
- [ ] MCP Server app is installed and healthy
- [ ] Token is configured in Relic VS Code settings
- [ ] All three indexes have data (app, apm, incidents)
- [ ] Test SPL queries return results in Splunk Web
- [ ] Relic Context Engine starts without errors
- [ ] SRE Chat returns Splunk-backed results (not mock)
- [ ] Mock fallback works when Splunk is stopped
