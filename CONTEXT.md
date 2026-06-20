# CONTEXT.md — Domain language for AI agents

This file is the canonical domain glossary for `ai-reader`. Other agents
working in this codebase (Claude Code, Codex, OpenCode, Antigravity,
Roo, Gemini, etc.) should use these terms consistently. See
[`~/.agents/INDEX.md`](../../INDEX.md) for the cross-agent rule set.

## What ai-reader is

`ai-reader` is a read-only multi-agent session reader. It parses the
on-disk conversation logs produced by Claude, Codex, OpenCode, and
Antigravity and exposes them through three surfaces — a CLI, an MCP
server, and a Python parser package. Any caller can read any session;
there is no access layer in front of the parsers.

## Glossary

| Term | Definition |
|---|---|
| **Session** | A conversation log persisted by an agent. Format is agent-specific: JSONL (Claude, Codex), SQLite (OpenCode), brain dir (Antigravity). |
| **Agent** | One of the supported runtimes. Represented in code by the `AgentName` enum (`CLAUDE`, `CODEX`, `OPENCODE`, `ANTIGRAVITY`). |
| **MCP** | [Model Context Protocol](https://modelcontextprotocol.io/) — JSON-RPC over stdio for tool calls. |
| **Parser** | A module that reads an agent's session storage and returns `Session` objects. One per supported agent, under `src/ai_reader/parsers/`. |
| **Brain** | Antigravity's per-session scratchpad directory. Contains `overview.txt`, `transcript.jsonl`, `walkthrough.md`, `task.md`, etc. |
| **Rollout** | Codex's per-session JSONL file under `~/.codex/sessions/YYYY/MM/DD/rollout-<uuid>.jsonl`. |

## Storage layout

| Agent | Storage | Parser |
|---|---|---|
| Claude Code | `~/.claude/projects/<project-slug>/<session-uuid>.jsonl` | `parsers/claude.py` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | `parsers/codex.py` |
| OpenCode | `~/.local/share/opencode/opencode.db` (SQLite; auto-detects snap/flatpak) | `parsers/opencode.py` |
| Antigravity | `~/.gemini/antigravity/brain/<session-uuid>/` | `parsers/antigravity.py` |

Any base directory can be overridden by setting `AI_READER_HOME`.

## Module map (where to look first)

| Question | Look at |
|---|---|
| "How is a Claude session parsed?" | [`src/ai_reader/parsers/claude.py`](./src/ai_reader/parsers/claude.py) |
| "How do I add a new agent?" | [`docs/parsers.md`](./docs/parsers.md) |
| "How do I migrate from `ai-local-reader`?" | [`docs/migration.md`](./docs/migration.md) |
| "What's the layering?" | [`docs/architecture.md`](./docs/architecture.md) |

## Cross-references

- Project rule: [~/.agents/INDEX.md](../../INDEX.md) — global agent rules
- This project's canonical docs: [README.md](./README.md), [CHANGELOG.md](./CHANGELOG.md)
- Open issues: <https://github.com/pro-target/ai-reader/issues>
