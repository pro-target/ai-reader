# CONTEXT.md — Domain language for AI agents

This file is the canonical domain glossary for `ai-reader`. Other agents
working in this codebase (Claude Code, Codex, OpenCode, Antigravity,
Roo, Gemini, etc.) should use these terms consistently. See
[`~/.agents/INDEX.md`](../../INDEX.md) for the cross-agent rule set.

## Multi-Agent Awareness

> **Parents cannot read sub-agent sessions directly. Sub-agents can read any session.**

### Rationale

When multiple AI agents share a filesystem, they can leak context to each
other through direct `Read` or `Bash cat` operations on session files.
This breaks sandboxing and confidentiality — a parent agent could
exfiltrate API keys, internal reasoning, or private user data from a
sibling's transcript by simply opening the JSONL.

The **Multi-Agent Awareness** rule (a global rule in `~/.agents/`)
forbids this. `ai-reader` is its enforcement mechanism.

### Implementation levels

| Level | Mechanism | Status |
|---|---|---|
| 1 | Filesystem ACLs, `permissions.deny` rules | Rejected for v1 — fragile, per-agent |
| 2 | **MCP-guard** (this project) | **Shipped** — single chokepoint |
| 3 | Hooks + MCP (deny `Read`/`Bash` to session paths) | Roadmap — v0.2 |
| 4 | POSIX ACLs on session directories | Roadmap — v1.0 |

Level 2 is sufficient when every agent in the system routes reads
through MCP. A parent that bypasses MCP with `Bash cat ~/.claude/...`
bypasses the guard. This trade-off is documented in
[docs/architecture.md](./docs/architecture.md).

### Detection mechanisms

The default `AccessGuard` uses a `CompositeDetector` with two
strategies, combined with **OR-semantics** (subagent = env OR proc):

1. **`EnvDetector`** — checks environment variables. Sub-agent is
   recognised when **any** of these is set:
   - `CLAUDE_CODE_SUBAGENT` (truthy: `1`/`true`/`yes`/`on`)
   - `CLAUDE_CODE_FORK_SUBAGENT` (truthy)
   - `CODEX_SUBAGENT_TASK_ID` (non-empty)
   - `OPENCODE_PARENT_ID` (non-empty)
   - `GEMINI_SUBAGENT` (truthy)
2. **`ProcDetector`** (Linux-only) — walks `/proc/<ppid>/cmdline` and
   looks for these substrings: `subagent`, `task`, `worker`,
   `claude-code-sub`, `codex-task`. No-ops on macOS/Windows.

Custom detectors are first-class: any object with
`is_subagent() -> bool` and `name() -> str` plugs into
`AccessGuard(detector=...)`. See
[docs/access-control.md](./docs/access-control.md).

## Glossary

| Term | Definition |
|---|---|
| **Parent** | An agent process invoked by a user, not from another agent. Denied by the guard. |
| **Sub-agent** | An agent process spawned by another agent (via Task tool, fork, or similar). Allowed by the guard. |
| **Session** | A conversation log persisted by an agent. Format is agent-specific: JSONL (Claude, Codex), SQLite (OpenCode), brain dir (Antigravity). |
| **Guard** | The `AccessGuard` class — orchestrates detection and dispatches to parsers. |
| **Detector** | A strategy to identify parent vs sub-agent. Implementations: `EnvDetector`, `ProcDetector`, `CompositeDetector`. |
| **MCP** | [Model Context Protocol](https://modelcontextprotocol.io/) — JSON-RPC over stdio for tool calls. |
| **Parser** | A module that reads an agent's session storage and returns `Session` objects. One per supported agent. |
| **MCP-guard** | The architectural pattern (Level 2) where all session reads go through a single MCP server, which is the only place the guard is enforced. |
| **Brain** | Antigravity's per-session scratchpad directory. Contains `overview.txt`, `transcript.jsonl`, `walkthrough.md`, `task.md`, etc. |
| **Rollout** | Codex's per-session JSONL file under `~/.codex/sessions/YYYY/MM/DD/rollout-<uuid>.jsonl`. |

## Module map (where to look first)

| Question | Look at |
|---|---|
| "What does the guard check?" | [`src/ai_reader/access/detector.py`](./src/ai_reader/access/detector.py) |
| "How does the guard decide?" | [`src/ai_reader/access/guard.py`](./src/ai_reader/access/guard.py) |
| "How is a Claude session parsed?" | [`src/ai_reader/parsers/claude.py`](./src/ai_reader/parsers/claude.py) |
| "How do I add a new agent?" | [`docs/parsers.md`](./docs/parsers.md) |
| "How do I write a custom detector?" | [`docs/access-control.md`](./docs/access-control.md) |
| "How do I migrate from `ai-local-reader`?" | [`docs/migration.md`](./docs/migration.md) |
| "What's the layering?" | [`docs/architecture.md`](./docs/architecture.md) |

## Cross-references

- Project rule: [~/.agents/INDEX.md](../../INDEX.md) — global agent rules
- This project's canonical docs: [README.md](./README.md), [CHANGELOG.md](./CHANGELOG.md)
- Open issues: <https://github.com/anomalyco/ai-reader/issues>
