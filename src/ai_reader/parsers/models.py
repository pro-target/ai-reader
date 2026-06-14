"""Shared data models for session parsers.

All parser modules return :class:`Session` instances conforming to this
schema.  Adding a new agent is a three-step operation:

1. Add a value to :class:`AgentName`.
2. Implement a parser module under this package exporting the four
   standard functions (``list_sessions``, ``read_session``,
   ``search``, ``session_exists``).
3. Re-export the new module from :mod:`ai_reader.parsers`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class AgentName(str, Enum):
    """Identifier of which AI agent produced a session file."""

    CLAUDE = "CLAUDE"
    CODEX = "CODEX"
    OPENCODE = "OPENCODE"
    ANTIGRAVITY = "ANTIGRAVITY"


@dataclass(frozen=True)
class Session:
    """A discoverable AI agent session.

    Attributes:
        uuid: Unique identifier of the session.  For Claude this is the
            ``<session-uuid>`` portion of the JSONL filename; for Codex
            this is the ``payload.id`` from ``session_meta``; for
            OpenCode this is the ``session.id`` primary key; for
            Antigravity this is the brain directory name.
        agent: Which agent owns the session.
        title: Human-readable title, truncated to 100 characters and
            with newlines collapsed to spaces.
        date: Last activity timestamp.  Prefer an in-file timestamp
            when one is available, otherwise file mtime (Claude, Codex)
            or DB ``time_updated`` (OpenCode).
        path: Absolute path to the source of truth.  For JSONL parsers
            this is the file path; for OpenCode this is the SQLite
            database path; for Antigravity this is the brain directory.
        message_count: Number of conversation messages.  For Claude and
            Codex this is the number of ``user``/``assistant`` records
            read; for OpenCode this is ``SELECT COUNT(*) FROM message``;
            for Antigravity this is the number of records in the
            overview.txt / transcript.jsonl.
        parent_uuid: For OpenCode sub-sessions (``session.parent_id``).
            ``None`` for top-level sessions and for other agents.
        extra: Free-form metadata bag (project slug for Claude, cwd
            for Codex, etc.).  Optional and not part of the equality
            contract.
    """

    uuid: str
    agent: AgentName
    title: str
    date: datetime
    path: str
    message_count: int
    parent_uuid: Optional[str] = None
    extra: dict = field(default_factory=dict, compare=False, repr=False)


__all__ = ["AgentName", "Session"]
