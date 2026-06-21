# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **claude**: `extract_title()` now uses the **first** user message instead
  of the last. Affects downstream summaries or UI that quoted the wrap-up
  turn. If you depended on the old behavior, filter `Session.title` against
  the original last user message via `read_session(...).messages[-1].content`
  until a migration shim is shipped.

### Security

- **codex**: `AI_READER_DEDUP_KEY_LEN` is now re-read from the environment on
  every dedup-key call. Previously the value was captured at import time, so
  any runtime change to the environment (operator re-export, test using
  `monkeypatch.setenv` after import, long-running service restart) was
  silently ignored. New `parsers.codex.get_dedup_key_len()` accessor exposes
  the resolved value for callers that want to introspect it.

## [0.1.0] - 2026-06-14

First public alpha release.

### Added

- **Parsers** for 5 agents:
  - `claude` — JSONL at `~/.claude/projects/<project-slug>/<uuid>.jsonl`
  - `codex` — JSONL at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
  - `opencode` — SQLite at `~/.local/share/opencode/opencode.db` (auto-detects snap/flatpak variants under `~/snap/code/*/...` and `~/snap/opencode/*/...`)
  - `antigravity` — brain directories at `~/.gemini/antigravity/brain/` and `~/.gemini/antigravity-cli/brain/`
  - `pi` — JSONL at `~/.pi/agent/sessions/<encoded-cwd>/*.jsonl`
- **`Session` data model** with `uuid`, `agent`, `title`, `date`, `path`, `message_count`, `parent_uuid`, `extra`
- **CLI** (`ai-reader`): `list`, `read`, `search` subcommands with `--agent` filter and `--json` output
- **MCP server** (`ai-reader-mcp`): 3 tools — `list_sessions`, `read_session`, `search_sessions`
- **install.sh**: idempotent, dual-mode (system-wide with sudo, or per-user), venv or `--break-system-packages` fallback
- **agent-configs.sh**: patches agent MCP configs (claude, codex, opencode, antigravity)
- **uninstall.sh**: clean removal of binaries and MCP entries
- **Tests**: 184 tests, 87% coverage
- **2-layer architecture**: Public API / Core parsers — a read-only reader with no access-control layer in front of the parsers
- **MIT license**

### Notes

- This is an **alpha**. APIs may change before `0.2.0`.
- `ai-reader` is a reader, not a guard. Any caller that can reach the CLI, the MCP server, or the package can read any session. See [docs/architecture.md](./docs/architecture.md).
