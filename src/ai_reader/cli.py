"""CLI entry point for ai-reader.

Thin command-line wrapper over the same parsers the MCP server
exposes: list, read, and search sessions for Claude, Codex,
OpenCode, Antigravity, and Pi.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Sequence

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ai_reader import __version__  # noqa: E402
from ai_reader.parsers import AgentName, Session  # noqa: E402
from ai_reader.parsers import antigravity, claude, codex, opencode, pi  # noqa: E402

__all__ = ["main", "build_parser"]


_PARSERS = {
    AgentName.CLAUDE: claude,
    AgentName.CODEX: codex,
    AgentName.OPENCODE: opencode,
    AgentName.ANTIGRAVITY: antigravity,
    AgentName.PI: pi,
}


_AGENT_CHOICES = tuple(a.value.lower() for a in _PARSERS.keys())


_UUID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


_TABLE_COLUMNS = ("uuid", "agent", "date", "title", "messages")


def _coerce_agent(name: str) -> AgentName:
    """Map a lowercase agent name to :class:`AgentName`."""
    key = (name or "").strip().lower()
    for agent_name in _PARSERS:
        if agent_name.value.lower() == key:
            return agent_name
    raise ValueError(
        f"unknown agent {name!r}; expected one of {sorted(_AGENT_CHOICES)}"
    )


def _target_agents(agent: Optional[str]) -> List[AgentName]:
    if agent is None or not str(agent).strip():
        return list(_PARSERS.keys())
    return [_coerce_agent(agent)]


def _validate_uuid(value: str) -> str:
    if not value or not _UUID_PATTERN.match(value):
        raise ValueError(
            f"invalid uuid {value!r}: must be 1-128 chars of [A-Za-z0-9_.-]"
        )
    return value


def _iso(date: datetime) -> str:
    if date.tzinfo is None:
        return date.isoformat() + "Z"
    return date.isoformat()


def _format_table(rows: Sequence[dict[str, Any]]) -> str:
    """Render a list of session summaries as a fixed-width table."""
    headers = {
        "uuid": "UUID",
        "agent": "AGENT",
        "date": "DATE",
        "title": "TITLE",
        "messages": "MSGS",
    }
    widths = {
        "uuid": 36,
        "agent": 10,
        "date": 20,
        "title": 0,
        "messages": 5,
    }
    lines: List[str] = []
    header_line = (
        f"{headers['uuid']:<{widths['uuid']}} "
        f"{headers['agent']:<{widths['agent']}} "
        f"{headers['date']:<{widths['date']}} "
        f"{headers['title']} "
        f"{headers['messages']:>{widths['messages']}}"
    )
    lines.append(header_line)
    lines.append("-" * len(header_line))
    for row in rows:
        title = row.get("title", "") or ""
        if len(title) > 80:
            title = title[:77] + "..."
        lines.append(
            f"{row.get('uuid', ''):<{widths['uuid']}} "
            f"{row.get('agent', ''):<{widths['agent']}} "
            f"{row.get('date', ''):<{widths['date']}} "
            f"{title} "
            f"{int(row.get('message_count', 0)):>{widths['messages']}d}"
        )
    return "\n".join(lines)


def _format_session_detail(
    session: Session, messages: Optional[List[dict[str, Any]]] = None
) -> str:
    """Render a single session in human-readable form."""
    lines: List[str] = []
    lines.append(f"UUID:      {session.uuid}")
    lines.append(f"Agent:     {session.agent.value}")
    lines.append(f"Title:     {session.title}")
    lines.append(f"Date:      {_iso(session.date)}")
    lines.append(f"Path:      {session.path}")
    lines.append(f"Messages:  {session.message_count}")
    if messages is not None:
        lines.append("")
        if not messages:
            lines.append("(no messages extracted)")
        else:
            for idx, msg in enumerate(messages, start=1):
                role = msg.get("role", "?")
                content = msg.get("content", "") or ""
                if len(content) > 400:
                    content = content[:397] + "..."
                lines.append(f"--- [{idx}] {role} ---")
                lines.append(content)
    return "\n".join(lines)


def _session_to_dict(session: Session) -> dict[str, Any]:
    return {
        "uuid": session.uuid,
        "agent": session.agent.value,
        "title": session.title,
        "date": _iso(session.date),
        "message_count": session.message_count,
    }


def _exit_with_error(message: str, code: int = 1) -> "int":
    print(f"ai-reader: {message}", file=sys.stderr)
    return code


def _run_list(args: argparse.Namespace) -> int:
    try:
        targets = _target_agents(args.agent)
    except ValueError as exc:
        return _exit_with_error(str(exc))

    summaries: List[dict[str, Any]] = []
    for agent_name in targets:
        parser = _PARSERS[agent_name]
        for session in parser.list_sessions():
            summaries.append(_session_to_dict(session))

    if args.json:
        json.dump(summaries, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if not summaries:
        print("(no sessions found)", file=sys.stderr)
        return 0
    print(_format_table(summaries))
    return 0


def _run_read(args: argparse.Namespace) -> int:
    try:
        uuid = _validate_uuid(args.uuid)
        agent_name = _coerce_agent(args.agent)
    except ValueError as exc:
        return _exit_with_error(str(exc))

    parser = _PARSERS[agent_name]
    try:
        session = parser.read_session(uuid)
    except FileNotFoundError as exc:
        return _exit_with_error(f"not found: {exc}", code=3)
    except ValueError as exc:
        return _exit_with_error(str(exc))

    if args.json:
        json.dump(
            _session_to_dict(session),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    print(_format_session_detail(session))
    return 0


def _run_search(args: argparse.Namespace) -> int:
    query = (args.query or "").strip()
    if not query:
        return _exit_with_error("search query must be non-empty")

    try:
        targets = _target_agents(args.agent)
    except ValueError as exc:
        return _exit_with_error(str(exc))

    summaries: List[dict[str, Any]] = []
    for agent_name in targets:
        parser = _PARSERS[agent_name]
        for session in parser.search(query):
            summaries.append(_session_to_dict(session))

    if args.json:
        json.dump(summaries, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if not summaries:
        print(f"(no sessions match {query!r})", file=sys.stderr)
        return 0
    print(_format_table(summaries))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="ai-reader",
        description=(
            "Inspect Claude, Codex, OpenCode, Antigravity and Pi sessions."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ai-reader {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    list_p = sub.add_parser("list", help="List discoverable sessions")
    list_p.add_argument(
        "--agent",
        choices=_AGENT_CHOICES,
        help="Restrict to a single agent (default: all).",
    )
    list_p.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a human-readable table.",
    )
    list_p.set_defaults(func=_run_list)

    read_p = sub.add_parser("read", help="Read a single session by uuid")
    read_p.add_argument("uuid", help="Session uuid (validated against [A-Za-z0-9_.-]).")
    read_p.add_argument(
        "--agent",
        required=True,
        choices=_AGENT_CHOICES,
        help="Which agent owns the session.",
    )
    read_p.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a human-readable dump.",
    )
    read_p.set_defaults(func=_run_read)

    search_p = sub.add_parser("search", help="Case-insensitive title search")
    search_p.add_argument("query", help="Substring to search for in session titles.")
    search_p.add_argument(
        "--agent",
        choices=_AGENT_CHOICES,
        help="Restrict to a single agent (default: all).",
    )
    search_p.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a human-readable table.",
    )
    search_p.set_defaults(func=_run_search)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help(sys.stderr)
        return 1
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
