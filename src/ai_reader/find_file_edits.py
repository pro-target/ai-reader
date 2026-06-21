"""Cross-agent ``find_file_edits`` core, shared by the CLI and MCP server.

The pure-Python scan logic lives here so the CLI and the MCP tool
both delegate to a single implementation.  The MCP tool is a thin
wrapper (see :mod:`ai_reader.mcp_server`) that catches
:class:`ValueError` and converts it to the MCP error-dict
convention; the CLI handler (:func:`ai_reader.cli._run_find_file_edits`)
catches the same exception and prints it to stderr.

The module also re-exports the small set of helpers that downstream
consumers historically imported from :mod:`ai_reader.mcp_server`
(``_target_agents``, ``_coerce_agent``, ``_PARSERS``,
``_EDIT_TOOLS``, ``_EDIT_PATH_KEYS``) so existing call sites and
tests keep working.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

from ai_reader.parsers import AgentName
from ai_reader.parsers import antigravity, claude, codex, opencode, pi

__all__ = [
    "EDIT_TOOLS",
    "EDIT_PATH_KEYS",
    "PARSERS",
    "coerce_agent",
    "target_agents",
    "iso",
    "parse_iso_bound",
    "to_utc_aware",
    "edit_path_from_input",
    "previous_user_intent",
    "find_file_edits",
]


EDIT_TOOLS: frozenset[str] = frozenset({
    "Edit", "edit", "Write", "write",
    "MultiEdit", "NotebookEdit",
    "str_replace", "patch", "file",
    "file_edit", "write_file", "create_file", "apply_patch",
    "edit_file", "update_file", "multi_edit",
})


EDIT_PATH_KEYS: tuple[str, ...] = ("file_path", "notebook_path", "path")


PARSERS = {
    AgentName.CLAUDE: claude,
    AgentName.CODEX: codex,
    AgentName.OPENCODE: opencode,
    AgentName.ANTIGRAVITY: antigravity,
    AgentName.PI: pi,
}


_AGENT_NAMES_LOWER: dict[str, AgentName] = {
    "claude": AgentName.CLAUDE,
    "codex": AgentName.CODEX,
    "opencode": AgentName.OPENCODE,
    "antigravity": AgentName.ANTIGRAVITY,
    "pi": AgentName.PI,
}


def coerce_agent(name: str) -> AgentName:
    """Map a lowercase agent name to :class:`AgentName`."""
    key = (name or "").strip().lower()
    if key not in _AGENT_NAMES_LOWER:
        raise ValueError(
            f"unknown agent {name!r}; expected one of "
            f"{sorted(_AGENT_NAMES_LOWER)}"
        )
    return _AGENT_NAMES_LOWER[key]


def target_agents(agent: Optional[str]) -> List[AgentName]:
    """Resolve the optional ``agent`` filter to a list of :class:`AgentName`."""
    if agent is None or not str(agent).strip():
        return list(PARSERS.keys())
    return [coerce_agent(agent)]


def iso(date: datetime) -> str:
    """Format a datetime as ISO-8601 with UTC fallback."""
    if date.tzinfo is None:
        return date.replace(tzinfo=None).isoformat() + "Z"
    return date.isoformat()


def parse_iso_bound(value: Optional[str], name: str) -> Optional[datetime]:
    """Parse an ISO 8601 bound string for the ``find_file_edits`` filter.

    Returns ``None`` for empty/``None`` input (meaning "unbounded"). Raises
    :class:`ValueError` with a clear message on unparseable input.  The
    returned datetime is UTC-aware: ``Z`` and explicit offsets are honoured;
    naive strings (no offset) are interpreted as UTC.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"{name} must be an ISO 8601 string, got {value!r}: {exc}"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to UTC-aware for safe comparison with aware bounds.

    ``None`` passes through.  Naive datetimes are assumed to be UTC (which
    matches what every parser produces — they're either tz-aware UTC
    epochs or naive ISO strings; treating both as UTC is the only
    consistent rule).  Aware datetimes are converted to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def edit_path_from_input(payload: object) -> Optional[str]:
    """Return the first non-empty path-like value from a tool input dict.

    Checks the conventional top-level keys (``file_path``,
    ``notebook_path``, ``path``) first; falls back to walking a
    ``files[*].path`` list — used by opencode ``patch`` parts and
    any other multi-file payload.  Returns ``None`` for unrecognised
    shapes.
    """
    if not isinstance(payload, dict):
        return None
    for key in EDIT_PATH_KEYS:
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    files = payload.get("files")
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, dict):
                continue
            for key in EDIT_PATH_KEYS:
                val = entry.get(key)
                if isinstance(val, str) and val:
                    return val
    return None


def previous_user_intent(
    messages: Sequence[Any], index: int
) -> Optional[str]:
    """Walk backwards from ``index`` to find the previous user text."""
    for j in range(index - 1, -1, -1):
        if j < 0 or j >= len(messages):
            continue
        msg = messages[j]
        role = getattr(msg, "role", None)
        text = getattr(msg, "text", "") or ""
        if role == "user" and isinstance(text, str) and text.strip():
            return text
    return None


def find_file_edits(
    *,
    path: str,
    agent: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Find every file edit across sessions, cross-agent by default.

    Args:
        path: Substring matched against ``file_path`` / ``notebook_path``
            / ``path`` fields in the tool input (case-sensitive).
        agent: Optional filter, one of ``"claude"``, ``"codex"``,
            ``"opencode"``, ``"antigravity"``, ``"pi"``. ``None`` =
            all agents.
        since: Optional ISO 8601 lower bound (inclusive) on edit
            timestamp. Pass ``""`` or ``None`` to leave open.
        until: Optional ISO 8601 upper bound (inclusive) on edit
            timestamp. Pass ``""`` or ``None`` to leave open.
        limit: Maximum records to return. ``0`` = no cap. Default ``100``.

    Returns:
        A dict ``{"records": [...], "count": N, "truncated": bool}``.

    Raises:
        ValueError: on invalid arguments (``path`` empty, ``limit`` negative,
            unparseable ``since``/``until``, unknown ``agent``).
    """
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
    if not isinstance(limit, int) or limit < 0:
        raise ValueError(
            f"limit must be a non-negative integer, got {limit!r}"
        )

    since_dt = parse_iso_bound(since, "since")
    until_dt = parse_iso_bound(until, "until")
    targets = target_agents(agent)

    records: List[dict[str, Any]] = []

    for agent_name in targets:
        parser = PARSERS[agent_name]
        for session in parser.list_sessions():
            try:
                messages = parser.read_messages(session.uuid)
            except (FileNotFoundError, ValueError, OSError):
                continue
            session_iso = iso(session.date)
            session_title = session.title
            session_ts: Optional[datetime] = to_utc_aware(session.date)
            for idx, msg in enumerate(messages):
                if msg.role != "assistant":
                    continue
                if not msg.tool_use:
                    continue
                msg_ts: Optional[datetime] = to_utc_aware(
                    getattr(msg, "timestamp", None)
                )
                intent = previous_user_intent(messages, idx)
                for tool in msg.tool_use:
                    if not isinstance(tool, dict):
                        continue
                    name = tool.get("name", "")
                    if name not in EDIT_TOOLS:
                        continue
                    tool_ts: Optional[datetime] = to_utc_aware(tool.get("timestamp"))
                    edit_ts: Optional[datetime] = (
                        tool_ts if tool_ts is not None
                        else msg_ts if msg_ts is not None
                        else session_ts
                    )
                    if since_dt is not None and (
                        edit_ts is None or edit_ts < since_dt
                    ):
                        continue
                    if until_dt is not None and (
                        edit_ts is None or edit_ts > until_dt
                    ):
                        continue
                    raw_input = tool.get("input", "")
                    payload: object = raw_input
                    if isinstance(raw_input, str) and raw_input.strip():
                        try:
                            payload = json.loads(raw_input)
                        except (ValueError, TypeError):
                            payload = raw_input
                    file_path = edit_path_from_input(payload)
                    if file_path is None or path not in file_path:
                        continue
                    records.append({
                        "agent": agent_name.value.lower(),
                        "session_uuid": session.uuid,
                        "session_title": session_title,
                        "session_date": session_iso,
                        "message_index": idx,
                        "timestamp": iso(edit_ts) if edit_ts is not None else None,
                        "tool": name,
                        "file": file_path,
                        "intent": intent,
                        "assistant": msg.text or "",
                        "input": payload if isinstance(payload, dict) else {},
                    })

    records.sort(key=lambda r: (r["timestamp"] is None, r["timestamp"] or ""))
    total = len(records)
    truncated = False
    if limit and len(records) > limit:
        records = records[:limit]
        truncated = True
    return {"records": records, "count": total, "truncated": truncated}
