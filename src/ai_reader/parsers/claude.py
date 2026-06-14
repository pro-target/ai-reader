"""Claude Code session parser.

Source layout::

    ~/.claude/projects/<project-slug>/<session-uuid>.jsonl

Each line is a JSON object with the following relevant keys:

* ``type``         — ``"user"``, ``"assistant"``, ``"ai-title"`` or
  other event types (``"queue-operation"``, …).
* ``timestamp``    — ISO 8601 string (last record wins for the date).
* ``message``      — for ``user``/``assistant`` records only.  Either a
  string or a list of parts, where each part has ``type`` (``"text"``,
  ``"tool_use"``, ``"tool_result"``) and a ``text`` / ``content`` field.
* ``aiTitle``      — for ``"ai-title"`` records, optional auto-generated
  title.

The base directory can be overridden for tests by passing ``base_dir``
explicitly to the module-level functions.  When unset, the directory
is read from the ``AI_READER_HOME`` environment variable (used as
``$AI_READER_HOME/.claude/projects``), falling back to
``~/.claude/projects``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import AgentName, Session


_TITLE_MAX_LEN = 100


def _resolve_base_dir(base_dir: Optional[str]) -> Path:
    """Return the Claude projects directory.

    Lookup order:

    1. Explicit ``base_dir`` argument.
    2. ``$AI_READER_HOME/.claude/projects``.
    3. ``~/.claude/projects``.
    """
    if base_dir:
        return Path(base_dir).expanduser()
    env_home = os.environ.get("AI_READER_HOME")
    if env_home:
        return Path(env_home).expanduser() / ".claude" / "projects"
    return Path("~/.claude/projects").expanduser()


def _parse_iso_timestamp(raw: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp, tolerating a trailing ``Z``."""
    if not raw:
        return None
    try:
        cleaned = raw[:23]
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _extract_text_from_user_message(message: dict) -> str:
    """Return the first plain-text part of a user message, or empty string."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text", "")
            if not isinstance(text, str):
                continue
            text = text.strip()
            if not text or text.startswith("<"):
                continue
            return text
    return ""


def _normalise_title(raw: str) -> str:
    """Collapse newlines and truncate to ``_TITLE_MAX_LEN`` chars."""
    if not raw:
        return "Untitled"
    return raw.replace("\n", " ").replace("\r", " ").strip()[:_TITLE_MAX_LEN]


def _scan_file(jsonl_path: Path) -> Optional[Session]:
    """Build a :class:`Session` from one Claude JSONL file.

    Returns ``None`` if the file yields no usable title/timestamp.
    """
    ai_title: Optional[str] = None
    last_user_text: Optional[str] = None
    last_timestamp: Optional[datetime] = None
    message_count = 0

    try:
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue

                ts = _parse_iso_timestamp(record.get("timestamp", ""))
                if ts is not None:
                    last_timestamp = ts

                rec_type = record.get("type")
                if rec_type == "ai-title":
                    title = record.get("aiTitle", "")
                    if isinstance(title, str) and title.strip():
                        ai_title = title.strip()
                elif rec_type == "user":
                    message_count += 1
                    text = _extract_text_from_user_message(
                        record.get("message", {}) or {}
                    )
                    if text and not text.startswith("<"):
                        last_user_text = text
                elif rec_type == "assistant":
                    message_count += 1
    except OSError:
        return None

    if ai_title:
        title = _normalise_title(ai_title)
    elif last_user_text:
        title = _normalise_title(last_user_text)
    else:
        return None

    if last_timestamp is None:
        try:
            last_timestamp = datetime.fromtimestamp(
                jsonl_path.stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            return None

    project_slug = jsonl_path.parent.name
    return Session(
        uuid=jsonl_path.stem,
        agent=AgentName.CLAUDE,
        title=title,
        date=last_timestamp,
        path=str(jsonl_path),
        message_count=message_count,
        extra={"project_slug": project_slug},
    )


def list_sessions(base_dir: Optional[str] = None) -> List[Session]:
    """Return every Claude session visible under ``base_dir``.

    Sessions are sorted by date (most recent first).  Files that fail
    to parse are silently skipped — Claude JSONL records are noisy
    and one bad line should not break enumeration.
    """
    root = _resolve_base_dir(base_dir)
    if not root.is_dir():
        return []

    sessions: List[Session] = []
    for jsonl_path in root.glob("*/*.jsonl"):
        if not jsonl_path.is_file():
            continue
        session = _scan_file(jsonl_path)
        if session is not None:
            sessions.append(session)

    sessions.sort(key=lambda s: s.date, reverse=True)
    return sessions


def _find_session_file(uuid: str, base_dir: Optional[str]) -> Path:
    """Locate the JSONL for ``uuid`` and validate the identifier.

    Raises:
        ValueError: ``uuid`` contains path separators or whitespace.
        FileNotFoundError: no file with this name exists under
            ``base_dir`` (or it is not a regular file).
    """
    if not uuid or "/" in uuid or "\\" in uuid or ".." in uuid:
        raise ValueError(f"Invalid Claude session uuid: {uuid!r}")
    if uuid != uuid.strip() or any(c.isspace() for c in uuid):
        raise ValueError(f"Invalid Claude session uuid: {uuid!r}")

    root = _resolve_base_dir(base_dir)
    for jsonl_path in root.glob(f"*/{uuid}.jsonl"):
        if jsonl_path.is_file():
            return jsonl_path

    raise FileNotFoundError(
        f"Claude session {uuid!r} not found under {root}"
    )


def read_session(uuid: str, base_dir: Optional[str] = None) -> Session:
    """Read and return a single Claude session by ``uuid``.

    Raises:
        FileNotFoundError: the session does not exist.
        ValueError: ``uuid`` is malformed.
    """
    path = _find_session_file(uuid, base_dir)
    session = _scan_file(path)
    if session is None:
        raise FileNotFoundError(
            f"Claude session {uuid!r} at {path} yielded no parseable data"
        )
    return session


def search(query: str, base_dir: Optional[str] = None) -> List[Session]:
    """Case-insensitive substring search across Claude session titles."""
    needle = (query or "").strip().lower()
    if not needle:
        return []
    return [
        session
        for session in list_sessions(base_dir)
        if needle in session.title.lower()
    ]


def session_exists(uuid: str, base_dir: Optional[str] = None) -> bool:
    """Return ``True`` if a Claude session with this uuid is on disk."""
    if not uuid or "/" in uuid or "\\" in uuid or ".." in uuid:
        return False
    try:
        _find_session_file(uuid, base_dir)
    except (FileNotFoundError, ValueError):
        return False
    return True
