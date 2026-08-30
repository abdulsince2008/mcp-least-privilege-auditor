# MCP Least-Privilege Auditor

**Find exposed but unused tools in MCP servers — reduce attack surface like AWS IAM Access Analyzer, but for Model Context Protocol.**

## Problem

MCP servers often expose dozens of tools, but AI agents only use a fraction of them. Every unused tool is unnecessary attack surface: a vulnerable function, a dangerous capability, or a legacy endpoint waiting to be exploited. This tool audits your MCP server's tool manifest against real usage logs to flag tools that are exposed but never called.

## Why This Is Different

| Tool | Purpose | Gap |
|------|---------|-----|
| [MCP Inspector](https://github.com/modelcontextprotocol/inspector) | Interactive debugging | No usage analysis |
| [mcp-list-tools](https://github.com/johnlindquist/mcp-list-tools) | List tools from server | No manifest/usage comparison |
| [mcp-manifest](https://github.com/mcp-manifest/mcp-sdk-python) | Parse/validate manifests | No runtime usage correlation |
| **mcp-least-privilege-auditor** | **Audit exposed vs. used tools** | **✅ Unique: correlates manifest + runtime + logs** |

**The one thing this does that others don't:** It takes a server's *declared* tool manifest (or discovers tools at runtime), parses *actual usage logs* from your AI client (Claude Desktop, Cursor, custom agents), and produces a risk-scored report of tools that exist but were never invoked — your excess attack surface.

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  Manifest File  │     │  Runtime Server  │     │   Usage Logs       │
│  (mcp.json,     │     │  (stdio connect) │     │  (JSONL, Claude    │
│   manifest.json)│     │                  │     │   export, custom)  │
└────────┬────────┘     └────────┬─────────┘     └────────┬───────────┘
         │                       │                        │
         └───────────────────────┼────────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │   Tool Correlation     │
                    │   Engine               │
                    └───────────┬────────────┘
                                ▼
                    ┌────────────────────────┐
                    │   Audit Result         │
                    │   - Used tools         │
                    │   - Unused tools       │
                    │   - Missing from       │
                    │     manifest           │
                    │   - Risk score (0-100) │
                    └────────────────────────┘
```

1. **Discover tools** from manifest file (`mcp.json`, `manifest.json`) and/or by connecting to a running MCP server via stdio
2. **Parse usage logs** from JSONL, JSON arrays, Claude Desktop exports, or custom formats
3. **Correlate**: match declared tools against actual invocations
4. **Report**: unused tools (excess surface), tools used but not in manifest (shadow tools), risk score

## Installation

```bash
# From source
git clone https://github.com/yourusername/mcp-least-privilege-auditor
cd mcp-least-privilege-auditor
pip install -e .

# Or with uv
uv pip install -e .
```

Requires Python 3.10+.

## Quick Start

```bash
# Generate sample data
mcp-auditor sample ./sample_data

# Run audit against manifest + usage logs
mcp-auditor audit -m ./sample_data/manifest.json -u ./sample_data/usage.jsonl

# Or use a config file
mcp-auditor audit -c ./sample_data/audit_config.json
```

## Usage

### Audit from manifest + usage logs

```bash
mcp-auditor audit \
  --manifest ./mcp.json \
  --usage ./logs/usage.jsonl \
  --usage ./logs/usage2.jsonl \
  --output report.json
```

### Audit by connecting to a running server

```bash
# Discover tools at runtime (no manifest needed)
mcp-auditor audit \
  --server python -m my_mcp_server \
  --usage ./logs/usage.jsonl
```

### Audit with both manifest and runtime (best coverage)

```bash
mcp-auditor audit \
  --manifest ./manifest.json \
  --server python -m my_mcp_server \
  --usage ./logs/usage.jsonl
```

### Output formats

```bash
# Table (default, human-readable)
mcp-auditor audit -m manifest.json -u usage.jsonl

# JSON (machine-readable)
mcp-auditor audit -m manifest.json -u usage.jsonl -f json

# Summary only
mcp-auditor audit -m manifest.json -u usage.jsonl -f summary
```

### Config file

Create `audit_config.json`:

```json
{
  "manifest_path": "./mcp.json",
  "server_command": ["python", "-m", "my_server"],
  "usage_logs": ["./logs/usage.jsonl", "./logs/usage2.jsonl"],
  "server_env": {"DATABASE_URL": "postgresql://..."},
  "timeout": 30
}
```

Then run:

```bash
mcp-auditor audit -c audit_config.json
```

## Example Output

```
$ mcp-auditor audit -m sample_data/manifest.json -u sample_data/usage.jsonl

╭────────────────────────────────────────────────────────────────────╮
│                    MCP Least-Privilege Audit Summary               │
├────────────────────────────────────────────────────────────────────┤
│ Server: example-filesystem-server (1.0.0)                          │
│ Risk Score: 33/100 (LOW)                                           │
│ Exposed Tools: 6                                                   │
│ Tools Used: 3                                                      │
│ Tools Unused: 3                                                    │
│ Exposure Ratio: 50%                                                │
│ Total Calls: 6                                                     │
│ Failed Calls: 1                                                    │
╰────────────────────────────────────────────────────────────────────╯

Unused Tools (Excess Attack Surface):
  • write_file
  • execute_command
  • send_email

Tools Used But Not In Manifest:
  (none)

┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━┓
┃ Tool Name           ┃ Description                          ┃ Source      ┃ Used  ┃ Call Count ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━┩
│ read_file           │ Read a file from the filesystem        │ manifest    │ ✓     │ 3          │
│ write_file          │ Write a file to the filesystem         │ manifest    │ ✗     │ 0          │
│ list_directory      │ List contents of a directory           │ manifest    │ ✓     │ 2          │
│ execute_command     │ Execute a shell command (DANGEROUS...) │ manifest    │ ✗     │ 0          │
│ query_database      │ Query a SQL database                   │ manifest    │ ✓     │ 1          │
│ send_email          │ Send an email (legacy, deprecated)     │ manifest    │ ✗     │ 0          │
└─────────────────────┴────────────────────────────────────────┴─────────────┴───────┴────────────┘
```

JSON output (`-f json -o report.json`):

```json
{
  "server_name": "example-filesystem-server",
  "server_version": "1.0.0",
  "total_exposed_tools": 6,
  "tools_used": 3,
  "tools_unused": 3,
  "exposure_ratio": 0.5,
  "risk_score": 33,
  "total_calls": 6,
  "failed_calls": 1,
  "unused_tool_names": ["write_file", "execute_command", "send_email"],
  "missing_from_manifest": []
}
```

## Supported Log Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| JSONL | `.jsonl`, `.ndjson` | One JSON object per line (recommended) |
| JSON Array | `.json` | Array of tool call objects |
| Claude Desktop | `.json` | Export from Claude Desktop conversations |
| Custom | Any | Best-effort regex extraction |

### JSONL Format (recommended)

```jsonl
{"tool_name": "read_file", "timestamp": "2025-01-15T10:30:00Z", "arguments": {"path": "/etc/hosts"}, "success": true, "duration_ms": 45.2, "session_id": "sess_001"}
{"tool_name": "write_file", "timestamp": "2025-01-15T10:31:00Z", "arguments": {"path": "/tmp/test.txt", "content": "hello"}, "success": true, "duration_ms": 12.1}
```

### Minimal Required Fields

Only `tool_name` is required. All other fields are optional:

```json
{"tool_name": "read_file"}
```

## Risk Scoring

Risk score (0-100) combines three factors:

| Factor | Weight | Calculation |
|--------|--------|-------------|
| Unused tools | 50% | `min(unused_count * 5, 50)` |
| Exposure ratio | 30% | `(1 - used/exposed) * 30` |
| Failure rate | 20% | `(failed/total) * 20` |

**Interpretation:**
- 0-30: Low — minimal excess surface
- 31-69: Medium — several unused tools
- 70-100: High — many unused/dangerous tools

## Tech Stack & Libraries Reused

| Library | Purpose | Why |
|---------|---------|-----|
| [`mcp`](https://pypi.org/project/mcp/) | Official MCP Python SDK | Runtime tool discovery via stdio transport |
| [`mcp-manifest`](https://github.com/mcp-manifest/mcp-sdk-python) | Manifest parsing | Validates and parses MCP manifest files |
| [`pydantic`](https://docs.pydantic.dev/) | Data modeling | Type-safe models for tools, calls, results |
| [`typer`](https://typer.tiangolo.com/) | CLI framework | Modern, type-hint-based CLI |
| [`rich`](https://rich.readthedocs.io/) | Terminal formatting | Beautiful tables, panels, JSON output |
| [`loguru`](https://loguru.readthedocs.io/) | Logging | Structured logging (internal) |

**The genuinely new piece:** The correlation engine that merges manifest-declared tools, runtime-discovered tools, and actual usage logs to produce a least-privilege audit report with risk scoring — analogous to AWS IAM Access Analyzer but for MCP.

## Known Limitations

1. **No real-time monitoring** — analyzes static logs, doesn't attach to running sessions
2. **Log format coverage** — supports common formats; proprietary logging may need custom parsers
3. **No server-side instrumentation** — relies on client-side logs; if your client doesn't log tool calls, you can't audit
4. **Single-server scope** — doesn't yet analyze multi-server deployments or tool chaining
5. **False negatives** — tools used rarely might appear unused in short log windows

## What's Next

- [ ] Real-time log tailing (`--follow` mode)
- [ ] Multi-server / composite audit
- [ ] Integration with Claude Desktop / Cursor log locations
- [ ] CI/CD pipeline integration (fail build on high risk)
- [ ] Tool danger classification (heuristics for dangerous capabilities)
- [ ] HTML/PDF report generation
- [ ] MCPB (`.mcpb` bundle) direct support

## License

MIT — see [LICENSE](LICENSE) file.