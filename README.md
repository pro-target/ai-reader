# ai-reader

> Multi-agent session access guard with MCP server. Standalone open-source package.

## What is this?

`ai-reader` is a **session access guard** for multi-agent AI systems. It prevents
parent agents from reading session files of other agents, while still allowing
sub-agents to do so. The guard is implemented as an MCP (Model Context Protocol)
server, with a thin Python API for direct use.

## Why?

In multi-agent setups, parent agents can leak sensitive context (API keys,
internal reasoning, private user data) by reading session files of sub-agents or
sibling agents. A `Read` tool call to `~/.claude/projects/.../session.jsonl`
bypasses any in-context safety rules.

`ai-reader` enforces the prohibition at the **tool boundary** by intercepting
MCP calls. Sub-agents are detected via env vars (`CLAUDE_CODE_SUBAGENT`,
`CODEX_SUBAGENT_TASK_ID`, `OPENCODE_PARENT_ID`, `GEMINI_SUBAGENT`) and allowed
through; everything else is denied.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Public API                                          │
│   ai-reader (CLI) ──┐                               │
│   ai-reader-mcp ────┤                               │
└─────────────────────┼───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│ Core Library (src/ai_reader/)                       │
│   parsers/    — Claude, Codex, OpenCode, Antigravity│
│   access/     — SubagentDetector, AccessGuard       │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│ MCP Server (mcp_server.py)                          │
│   Listens on stdio; checks guard before each tool   │
└─────────────────────────────────────────────────────┘
```

## Install

```bash
git clone https://github.com/anomalyco/ai-reader.git /opt/ai-reader
cd /opt/ai-reader
./install.sh
```

The installer is idempotent and registers the MCP server with Claude Code,
Codex, OpenCode, and Antigravity.

## Usage

### As MCP server

Add to your agent's MCP config:

```json
{
  "mcpServers": {
    "ai-reader": {
      "command": "/opt/ai-reader/bin/ai-reader-mcp",
      "args": []
    }
  }
}
```

Then in the agent's session, the `ai-reader` tools become available:
- `list_sessions(agent?)` — list available sessions
- `read_session(uuid)` — read a specific session (denied for parents)
- `search_sessions(query)` — full-text search across sessions

### As CLI

```bash
ai-reader list                # list all sessions
ai-reader read ses_abc123     # read a session
ai-reader search "docker"     # search across all sessions
```

## Design

- **Level 2 guard (MCP only)**: parent agents can technically still read session
  files via `Read` / `Bash cat` directly. This is the user's accepted trade-off
  in exchange for a simple, open-source-friendly design. A future Level 3
  (hooks + MCP) and Level 4 (POSIX ACL) are documented in
  [`docs/architecture.md`](docs/architecture.md) but not implemented.
- **No logs, no notifications, no sanitization**: explicitly chosen by the user.
  The guard is a one-way read control, not a detective control.
- **Any subagent of any parent → allowed**: an attacker who can spawn any
  sub-agent bypasses the guard. A per-parent allowlist is a recommended
  follow-up.
- **Any session = potentially foreign**: no own/foreign distinction. A
  sub-agent can read its own parent's session.

## License

MIT — see [`LICENSE`](LICENSE).

## Status

v0.1.0 — alpha. APIs may change.
