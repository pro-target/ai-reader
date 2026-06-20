# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed

- **Access-control layer** — `ai_reader.access` (AccessGuard, EnvDetector,
  ProcDetector, CompositeDetector) and the `tests/test_access/` suite are
  gone. `ai-reader` is now a read-only session reader with no gating in
  front of the parsers. Any caller can read any session. CLI/MCP tools call
  the parsers directly; `PermissionError`/`permission_denied` paths and the
  `exit code 2` (permission denied) are removed. `legacy_compat` no longer
  gates on sub-agent detection.
- **Codecov** upload step and coverage badge (no token configured); the
  ≥80% coverage gate still runs locally in CI.

### Fixed

- Project URLs now point at the real remote `github.com/pro-target/ai-reader`
  (README, pyproject, install/README, CONTEXT).

## [0.1.0] - 2026-06-14

First public alpha release. Six development phases shipped end-to-end.

### Added

- **Parsers** for 4 agents:
  - `claude` — JSONL at `~/.claude/projects/<project-slug>/<uuid>.jsonl`
  - `codex` — JSONL at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
  - `opencode` — SQLite at `~/.local/share/opencode/opencode.db` (auto-detects snap/flatpak variants under `~/snap/code/*/...` and `~/snap/opencode/*/...`)
  - `antigravity` — brain directories at `~/.gemini/antigravity/brain/` and `~/.gemini/antigravity-cli/brain/`
- **`Session` data model** with `uuid`, `agent`, `title`, `date`, `path`, `message_count`, `parent_uuid`, `extra`
- **AccessGuard** with composite detector (EnvDetector + ProcDetector)
- **Hybrid detection**:
  - Env vars: `CLAUDE_CODE_SUBAGENT`, `CLAUDE_CODE_FORK_SUBAGENT`, `CODEX_SUBAGENT_TASK_ID`, `OPENCODE_PARENT_ID`, `GEMINI_SUBAGENT`
  - `/proc/<ppid>/cmdline` walker (Linux-only, no-ops on macOS/Windows)
- **CLI** (`ai-reader`): `list`, `read`, `search` subcommands with `--agent` filter and `--json` output
- **MCP server** (`ai-reader-mcp`): 3 tools — `list_sessions`, `read_session`, `search_sessions` — guarded by AccessGuard
- **install.sh**: idempotent, dual-mode (system-wide with sudo, or per-user), venv or `--break-system-packages` fallback
- **agent-configs.sh**: patches 4 agent MCP configs (claude, codex, opencode, antigravity)
- **uninstall.sh**: clean removal of binaries and MCP entries
- **Tests**: 184 tests, 87% coverage
- **Backward compat**: existing `ai-local-reader` skill scripts (`get_latest_context.py`, `agent-audit.py`) continue to work as thin wrappers around the new `ai-reader` CLI
- **3-layer architecture**: Public API / Core parsers / Access control
- **MIT license**

### Security

- Detectors are pure with respect to their inputs (`Mapping` for env, `proc_root` for `/proc`) so unit tests use fixtures, not monkey-patching
- `AccessGuard.check()` validates `request` is an `AccessRequest`, `agent` is an `AgentName`, `operation` is in `{read, search, list}`
- `read_session()` raises `PermissionError` for parents, `FileNotFoundError` for missing sessions, `ValueError` for malformed input
- CLI exits with distinct codes: `0` ok, `1` usage, `2` permission denied, `3` not found

### Notes

- This is an **alpha**. APIs may change before `0.2.0`.
- The guard is at **Level 2** (MCP-guard). A parent that bypasses MCP via `Bash cat` is not protected — this is a known, documented trade-off. See [docs/architecture.md](./docs/architecture.md) for Levels 1, 3, 4.
- The proc detector runs only on Linux. On macOS/Windows the env-var path is the sole signal.
