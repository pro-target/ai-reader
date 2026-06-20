# ai-reader

[![CI](https://github.com/pro-target/ai-reader/workflows/CI/badge.svg)](https://github.com/pro-target/ai-reader/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> Read Claude, Codex, OpenCode, and Antigravity sessions through a single MCP server, CLI, or Python package.

## Why?

Every AI agent stores its conversation logs on disk in a different
place and format — JSONL for Claude and Codex, SQLite for OpenCode,
brain directories for Antigravity. `ai-reader` gives you one read-only
interface across all of them.

`ai-reader` is a **reader**, not a guard. Any caller that can reach the
CLI, the MCP server, or the package can read any session. There is no
access-control layer in front of the parsers.

## Quick Start (1 request)

```bash
git clone https://github.com/pro-target/ai-reader.git ~/dev/ai-reader
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
│   • from ai_reader.parsers import ...  (Python SDK)          │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ Layer 2: Core (parsers/, models)                             │
│   • claude, codex, opencode (SQLite), antigravity            │
│   • Auto-detect snap/flatpak OpenCode DBs                    │
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

### As a CLI (testing / scripts)

```bash
ai-reader list --agent claude
ai-reader read --agent claude --uuid <session-uuid>
ai-reader search "refactor"
```

Add `--json` to any subcommand for machine-readable output.

### As a Python SDK

```python
from ai_reader.parsers import AgentName, claude

for session in claude.list_sessions():
    print(session.uuid, session.title)

session = claude.read_session("<session-uuid>")
print(session.message_count)
```

See [docs/architecture.md](./docs/architecture.md) for the full layering.

## Backward Compatibility

If you use the legacy `~/.agents/skills/ai-local-reader/scripts/{get_latest_context.py,agent-audit.py}` — they continue to work as thin wrappers around the new `ai-reader` CLI. See [docs/migration.md](./docs/migration.md).

## Development

```bash
git clone https://github.com/pro-target/ai-reader.git
cd ai-reader
pip install -e ".[dev]"
pytest --cov=src/ai_reader
```

- 140 tests, ≥80% coverage required by CI
- Conventional Commits (`feat:`, `fix:`, `docs:`, …)
- See [CONTRIBUTING.md](./CONTRIBUTING.md) and [docs/parsers.md](./docs/parsers.md) for adding new agents

## License

MIT — see [LICENSE](./LICENSE).
