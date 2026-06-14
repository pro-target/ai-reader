# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial repository skeleton: `pyproject.toml`, `README.md`, `LICENSE`, `.gitignore`
- Source tree: `src/ai_reader/parsers/`, `src/ai_reader/access/`
- Stub entry points: `ai-reader` (CLI), `ai-reader-mcp` (MCP server)
- Test directory: `tests/`
- Task tracker: `~/.agents/_docs/tasks/active/2026-06-14_ai_reader_build/`

## [0.1.0] — 2026-06-14

### Added
- First public release (alpha)
- Multi-agent session access guard via MCP
- Subagent detection by env vars
- Parsers for Claude, Codex, OpenCode, Antigravity (planned, see task tracker)
