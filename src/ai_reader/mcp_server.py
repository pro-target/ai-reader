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

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

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


def _extract_messages_claude(path: str) -> List[dict[str, Any]]:
    """Return up to :data:`_MESSAGES_CAP` user/assistant records from a Claude JSONL."""
    messages: List[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if len(messages) >= _MESSAGES_CAP:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                rec_type = record.get("type")
                if rec_type not in ("user", "assistant"):
                    continue
                payload = record.get("message") or {}
                if not isinstance(payload, dict):
                    continue
                content = payload.get("content", "")
                if isinstance(content, list):
                    chunks: List[str] = []
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text", "")
                            if isinstance(text, str) and text:
                                chunks.append(text)
                    text_value = "\n".join(chunks)
                elif isinstance(content, str):
                    text_value = content
                else:
                    text_value = ""
                messages.append(
                    {
                        "role": rec_type,
                        "content": text_value,
                    }
                )
    except OSError:
        return messages
    return messages


def _extract_messages_codex(path: str) -> List[dict[str, Any]]:
    """Return up to :data:`_MESSAGES_CAP` user/assistant records from a Codex rollout."""
    messages: List[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if len(messages) >= _MESSAGES_CAP:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") != "message":
                    continue
                role = payload.get("role")
                if role not in ("user", "assistant"):
                    continue
                messages.append(
                    {
                        "role": role,
                        "content": _codex_text(payload.get("content", [])),
                    }
                )
    except OSError:
        return messages
    return messages


def _codex_text(parts: object) -> str:
    """Concatenate Codex message parts into a single string."""
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
    """Concatenate Pi text parts, skipping thinking/tool-call blocks."""
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


def _extract_messages_pi(path: str) -> List[dict[str, Any]]:
    """Return up to :data:`_MESSAGES_CAP` user/assistant records from a Pi JSONL."""
    messages: List[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if len(messages) >= _MESSAGES_CAP:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or record.get("type") != "message":
                    continue
                payload = record.get("message") or {}
                if not isinstance(payload, dict):
                    continue
                role = payload.get("role")
                if role not in ("user", "assistant"):
                    continue
                messages.append(
                    {
                        "role": role,
                        "content": _pi_text(payload.get("content", "")),
                    }
                )
    except OSError:
        return messages
    return messages


def _extract_messages(session: Session) -> List[dict[str, Any]]:
    """Best-effort message extraction; capped at :data:`_MESSAGES_CAP`."""
    if session.agent == AgentName.CLAUDE:
        return _extract_messages_claude(session.path)
    if session.agent == AgentName.CODEX:
        return _extract_messages_codex(session.path)
    if session.agent == AgentName.PI:
        return _extract_messages_pi(session.path)
    return []


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
