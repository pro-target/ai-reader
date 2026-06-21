"""MCP server entry point for ai-reader.

Exposes three tools over the Model Context Protocol:

* :func:`list_sessions`  — enumerate sessions, optionally filtered by agent.
* :func:`read_session`   — load a single session by ``uuid`` and ``agent``.
* :func:`search_sessions` — case-insensitive title substring search.

Errors are returned as dicts (never raised) so the MCP client can
surface them in a structured way.

Transport: stdio.  No logging, no stdout writes outside the MCP
protocol — that would corrupt the JSON-RPC stream.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Sequence

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from ai_reader import __version__  # noqa: E402
from ai_reader.parsers import AgentName, Session  # noqa: E402
from ai_reader.parsers import antigravity, claude, codex, opencode, pi  # noqa: E402

__all__ = ["mcp", "main"]


_PARSERS = {
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


_MESSAGES_CAP = 100


mcp = FastMCP(
    name="ai-reader",
    instructions=(
        "ai-reader: read Claude, Codex, OpenCode, Antigravity and Pi session "
        f"files. Server version: {__version__}."
    ),
)


def _coerce_agent(name: str) -> AgentName:
    """Map a lowercase agent name to :class:`AgentName`."""
    key = (name or "").strip().lower()
    if key not in _AGENT_NAMES_LOWER:
        raise ValueError(
            f"unknown agent {name!r}; expected one of "
            f"{sorted(_AGENT_NAMES_LOWER)}"
        )
    return _AGENT_NAMES_LOWER[key]


def _iso(date: datetime) -> str:
    """Format a datetime as ISO-8601 with UTC fallback."""
    if date.tzinfo is None:
        return date.replace(tzinfo=None).isoformat() + "Z"
    return date.isoformat()


def _session_summary(session: Session) -> dict[str, Any]:
    """Project a :class:`Session` to a JSON-safe summary dict."""
    return {
        "uuid": session.uuid,
        "agent": session.agent.value,
        "title": session.title,
        "date": _iso(session.date),
        "message_count": session.message_count,
    }


def _target_agents(agent: Optional[str]) -> List[AgentName]:
    """Resolve the optional ``agent`` filter to a list of :class:`AgentName`."""
    if agent is None or not str(agent).strip():
        return list(_PARSERS.keys())
    return [_coerce_agent(agent)]


def _codex_text(parts: object) -> str:
    """Concatenate Codex message parts into a single string.

    .. deprecated::
        Kept as a thin backcompat helper for existing callers/tests; the
        canonical path is :func:`ai_reader.parsers.codex.read_messages`.
    """
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    chunks: List[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text", "")
        if isinstance(text, str) and text:
            chunks.append(text)
    return "\n".join(chunks)


def _pi_text(parts: object) -> str:
    """Concatenate Pi text parts, skipping thinking/tool-call blocks.

    .. deprecated::
        Kept as a thin backcompat helper for existing callers/tests; the
        canonical path is :func:`ai_reader.parsers.pi.read_messages`.
    """
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    chunks: List[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("type", "") not in ("text", "input_text", "output_text", ""):
            continue
        text = part.get("text", "")
        if isinstance(text, str) and text:
            chunks.append(text)
    return "\n".join(chunks)


def _extract_messages_claude(path: str) -> List[dict[str, Any]]:
    """Return up to :data:`_MESSAGES_CAP` Claude messages as ``{role, content}`` dicts.

    .. deprecated::
        Backcompat shim retained for the unit tests; new code should go
        through :func:`_extract_messages` (which dispatches to the
        parser's public ``read_messages`` by uuid).
    """
    return _messages_from_parser(claude, path)


def _extract_messages_codex(path: str) -> List[dict[str, Any]]:
    """Return up to :data:`_MESSAGES_CAP` Codex messages as ``{role, content}`` dicts.

    .. deprecated::
        Backcompat shim retained for the unit tests; prefer
        :func:`_extract_messages`.
    """
    return _messages_from_parser(codex, path)


def _extract_messages_pi(path: str) -> List[dict[str, Any]]:
    """Return up to :data:`_MESSAGES_CAP` Pi messages as ``{role, content}`` dicts.

    .. deprecated::
        Backcompat shim retained for the unit tests; prefer
        :func:`_extract_messages`.
    """
    return _messages_from_parser(pi, path)


def _messages_from_parser(parser: Any, path: str) -> List[dict[str, Any]]:
    """Project a parser's internal extractor output to ``{role, content}`` dicts.

    Reads the file at ``path`` directly through the parser's internal
    extraction (rather than the uuid-resolved public API) so the mcp
    helpers keep their original ``path``-in / list-out contract used by
    the unit tests.  Only ``user`` and ``assistant`` roles are surfaced,
    matching the historical MCP output; ``tool`` messages (e.g. Pi
    ``toolResult`` records, Codex function-call outputs) are dropped so
    the MCP ``read_session`` output shape is unchanged.
    """
    messages: List[dict[str, Any]] = []
    try:
        if parser is claude:
            msgs = claude._extract_messages_from_jsonl(Path(path))
        elif parser is codex:
            msgs = codex._extract_messages_from_rollout(Path(path))
        elif parser is pi:
            msgs = pi._extract_messages_from_jsonl(Path(path))
        else:
            return []
    except OSError:
        return []
    for m in msgs:
        if len(messages) >= _MESSAGES_CAP:
            break
        if m.role not in ("user", "assistant"):
            continue
        messages.append({"role": m.role, "content": m.text})
    return messages


def _project_messages(messages: Sequence[Any]) -> List[dict[str, Any]]:
    """Project parser ``Message`` objects to ``{role, content}`` dicts.

    Only ``user``/``assistant`` roles are surfaced, preserving the
    historical MCP output shape; ``tool`` messages are dropped.  Capped
    at :data:`_MESSAGES_CAP` so MCP output stays bounded.
    """
    out: List[dict[str, Any]] = []
    for m in messages:
        if len(out) >= _MESSAGES_CAP:
            break
        if m.role not in ("user", "assistant"):
            continue
        out.append({"role": m.role, "content": m.text})
    return out


def _extract_messages(session: Session) -> List[dict[str, Any]]:
    """Best-effort message extraction for a session; capped at :data:`_MESSAGES_CAP`.

    Single dispatcher covering ALL supported agents
    (claude/codex/opencode/pi/antigravity): resolves the owning parser
    from :data:`_PARSERS`, calls its public ``read_messages(session.uuid)``,
    and projects each :class:`~ai_reader.parsers.models.Message` to a
    ``{role, content}`` dict.  Only ``user``/``assistant`` roles surface
    (historical MCP shape); ``tool`` messages are dropped.

    Any parser-level I/O or decode failure (``FileNotFoundError``,
    ``ValueError``, ``OSError``) yields ``[]`` so MCP callers always get
    a list back.
    """
    parser = _PARSERS.get(session.agent)
    if parser is None:
        return []
    try:
        raw = parser.read_messages(session.uuid)
    except (FileNotFoundError, ValueError, OSError):
        return []
    return _project_messages(raw)


@mcp.tool()
def list_sessions(agent: Optional[str] = None) -> List[dict[str, Any]]:
    """List discoverable sessions, optionally filtered by ``agent``.

    Args:
        agent: One of ``claude``, ``codex``, ``opencode``, ``antigravity``,
            ``pi``. When omitted, every supported agent is queried.

    Returns:
        A list of session summaries.
    """
    try:
        targets = _target_agents(agent)
    except ValueError as exc:
        return [{"error": "invalid_argument", "message": str(exc)}]

    summaries: List[dict[str, Any]] = []
    for agent_name in targets:
        parser = _PARSERS[agent_name]
        for session in parser.list_sessions():
            summaries.append(_session_summary(session))
    return summaries


@mcp.tool()
def read_session(uuid: str, agent: str) -> dict[str, Any]:
    """Read a single session by ``uuid`` and ``agent``.

    Args:
        uuid: Session identifier.
        agent: One of ``claude``, ``codex``, ``opencode``, ``antigravity``, ``pi``.

    Returns:
        A dict with session metadata and a ``messages`` list (capped at
        100 entries) on success.  On a missing session, returns an
        ``error`` dict instead of raising.
    """
    if not uuid or not str(uuid).strip():
        return {"error": "invalid_argument", "message": "uuid must be non-empty"}
    try:
        agent_name = _coerce_agent(agent)
    except ValueError as exc:
        return {"error": "invalid_argument", "message": str(exc)}

    parser = _PARSERS[agent_name]
    try:
        session = parser.read_session(uuid)
    except FileNotFoundError:
        return {
            "error": "not_found",
            "uuid": uuid,
            "agent": agent_name.value,
        }

    summary = _session_summary(session)
    summary["messages"] = _extract_messages(session)
    return summary


@mcp.tool()
def search_sessions(query: str, agent: Optional[str] = None) -> List[dict[str, Any]]:
    """Case-insensitive title substring search across sessions.

    Args:
        query: Non-empty search string.
        agent: Optional agent filter; one of ``claude``, ``codex``,
            ``opencode``, ``antigravity``, ``pi``.

    Returns:
        A list of matching session summaries.  An empty list means
        nothing matched (or ``query`` was empty).
    """
    needle = (query or "").strip()
    if not needle:
        return []

    try:
        targets = _target_agents(agent)
    except ValueError as exc:
        return [{"error": "invalid_argument", "message": str(exc)}]

    lowered = needle.lower()
    summaries: List[dict[str, Any]] = []
    for agent_name in targets:
        parser = _PARSERS[agent_name]
        for session in parser.search(needle):
            if lowered in session.title.lower():
                summaries.append(_session_summary(session))
    return summaries


def main() -> int:
    """Entry point for the ``ai-reader-mcp`` console script."""
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
