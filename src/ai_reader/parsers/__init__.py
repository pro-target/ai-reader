"""Session parsers for Claude, Codex, OpenCode, and Antigravity.

Each parser module exports a common interface for enumerating and reading
session files from a specific agent's local storage.

Modules:
    claude:    ~/.claude/projects/*.jsonl
    codex:     ~/.codex/sessions/*.jsonl
    opencode:  ~/.local/share/opencode/opencode.db (SQLite)
    antigravity: ~/.gemini/antigravity/brain/* and ~/.gemini/antigravity-cli/brain/*
"""
