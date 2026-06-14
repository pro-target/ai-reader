"""Session parsers for Claude, Codex, OpenCode, and Antigravity.

Each parser module exports the same four-function interface:

* :func:`list_sessions` — enumerate every session visible to the agent.
* :func:`read_session`  — load a single session by uuid; raises
  :class:`FileNotFoundError` if it is missing.
* :func:`search`        — case-insensitive title substring search.
* :func:`session_exists` — boolean existence check.

All public data flows through :class:`ai_reader.parsers.models.Session`
and :class:`ai_reader.parsers.models.AgentName`.

Path resolution
---------------

Every parser accepts an optional ``base_dir`` argument for tests and
also honours the ``AI_READER_HOME`` environment variable, which is
treated as the user's ``$HOME`` for the duration of the call.  This
is the *only* testing hook — do not add other side effects.  When
``AI_READER_HOME`` is unset, parsers fall back to ``~``.

Modules:
    claude:       ``~/.claude/projects/<project-slug>/<uuid>.jsonl``
    codex:        ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``
    opencode:     SQLite at ``~/.local/share/opencode/opencode.db`` and
                  snap variants under ``~/snap/code/*/...`` /
                  ``~/snap/opencode/*/...``.
    antigravity:  brain directories under
                  ``~/.gemini/antigravity/brain`` and
                  ``~/.gemini/antigravity-cli/brain``.
"""

from . import antigravity, claude, codex, opencode
from .models import AgentName, Session

__all__ = [
    "AgentName",
    "Session",
    "antigravity",
    "claude",
    "codex",
    "opencode",
]
