# ai-reader

[![CI](https://github.com/anomalyco/ai-reader/workflows/CI/badge.svg)](https://github.com/anomalyco/ai-reader/actions)
[![Coverage](https://codecov.io/gh/anomalyco/ai-reader/branch/main/graph/badge.svg)](https://codecov.io/gh/anomalyco/ai-reader)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> Read Claude, Codex, OpenCode, and Antigravity sessions via a single MCP server — with sub-agent access guard.

## Why?

When you run multiple AI agents on the same machine, **parent agents can read each other's session files** via `Read` or `Bash cat`. This violates the **Multi-Agent Awareness** rule (see [CONTEXT.md](./CONTEXT.md)).

**ai-reader** solves this by exposing sessions only through a guarded MCP server. **Only sub-agents** (processes that look like they were spawned by an agent) can read sessions. Parents are denied.

## Quick Start (1 request)

```bash
git clone https://github.com/anomalyco/ai-reader.git ~/dev/ai-reader
cd ~/dev/ai-reader && bash install.sh
```

That's it. The installer:
- Detects install mode (system-wide with sudo, or per-user without)
- Creates a venv, installs the package
- Patches MCP configs for **Claude**, **Codex**, **OpenCode**, **Antigravity**
- Runs smoke tests

## Supported Agents

| Agent | Storage | Parser |
|---|---|---|
| Claude Code | `~/.claude/projects/` | JSONL |
| Codex | `~/.codex/sessions/` | JSONL |
| OpenCode | `~/.local/share/opencode/opencode.db` | SQLite (auto-detects snap/flatpak) |
| Antigravity | `~/.gemini/antigravity/brain/` | JSON / markdown brain directories |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: Public API (3 surfaces)                             │
│   • ai-reader CLI (argparse)                                 │
│   • ai-reader-mcp (MCP server, stdio JSON-RPC)               │
│   • from ai_reader import AccessGuard  (Python SDK)          │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ Layer 2: Core (parsers/, models)                             │
│   • claude, codex, opencode (SQLite), antigravity            │
│   • Auto-detect snap/flatpak OpenCode DBs                    │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ Layer 3: Access Control (access/)                            │
│   • EnvDetector (CLAUDE_CODE_SUBAGENT, CODEX_*, OPENCODE_*)  │
│   • ProcDetector (/proc/<ppid>/cmdline walker, Linux)        │
│   • CompositeDetector (env OR proc)                          │
│   • AccessGuard.require() → PermissionError on parent       │
└──────────────────────────────────────────────────────────────┘
```

## Usage

### As an MCP server (recommended)

The MCP server is auto-registered in your agent's config. Tools available:

| Tool | Purpose |
|---|---|
| `list_sessions(agent?)` | List discoverable sessions, optionally filtered by agent. |
| `read_session(uuid, agent)` | Read one session; returns up to 100 messages. |
| `search_sessions(query, agent?)` | Case-insensitive title substring search. |

All three are guarded by `AccessGuard`. Parents receive a structured `permission_denied` error.

### As a CLI (testing / scripts)

```bash
# Parent process — denied:
ai-reader list --agent claude
# ai-reader: permission denied: access denied for session '*' ...

# Sub-agent (env set):
CLAUDE_CODE_SUBAGENT=1 ai-reader list --agent claude
CLAUDE_CODE_SUBAGENT=1 ai-reader read --agent claude --uuid <session-uuid>
CLAUDE_CODE_SUBAGENT=1 ai-reader search "session-access-guard"
```

Add `--json` to any subcommand for machine-readable output.

### As a Python SDK

```python
from ai_reader.access import AccessGuard, AccessRequest
from ai_reader.parsers import AgentName

guard = AccessGuard()
result = guard.check(AccessRequest(
    session_uuid="...",
    agent=AgentName.CLAUDE,
    operation="read",
))
if result.allowed:
    session = guard.read_session(uuid, AgentName.CLAUDE)
```

See [docs/architecture.md](./docs/architecture.md) for the full layering and [docs/access-control.md](./docs/access-control.md) for writing custom detectors.

## Backward Compatibility

If you use the legacy `~/.agents/skills/ai-local-reader/scripts/{get_latest_context.py,agent-audit.py}` — they continue to work as thin wrappers around the new `ai-reader` CLI. See [docs/migration.md](./docs/migration.md).

## Multi-Agent Awareness

This project enforces the [Multi-Agent Awareness](./CONTEXT.md#multi-agent-awareness) rule: parents cannot read sub-agent sessions directly, sub-agents can read any session.

## Development

```bash
git clone https://github.com/anomalyco/ai-reader.git
cd ai-reader
pip install -e ".[dev]"
pytest --cov=src/ai_reader
```

- 184 tests, ≥80% coverage required by CI
- Conventional Commits (`feat:`, `fix:`, `docs:`, …)
- See [CONTRIBUTING.md](./CONTRIBUTING.md) and [docs/parsers.md](./docs/parsers.md) for adding new agents

## License

MIT — see [LICENSE](./LICENSE).
