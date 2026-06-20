"""MCP-server tests using the in-memory client.

The in-memory transport avoids spawning a real stdio server, so the
suite stays fast and hermetic.  We still call the registered tool
functions exactly as a real MCP client would: through
``client.call_tool`` and ``client.list_tools``.

Helper functions (``_extract_messages_claude``,
``_extract_messages_codex``, ``_iso``, ``_coerce_agent`` etc.) are
imported and tested directly because the in-memory transport runs
the server in a side thread whose coverage is *not* attributed to
the test process.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mcp.shared.memory import create_connected_server_and_client_session

from ai_reader.mcp_server import (
    _codex_text,
    _coerce_agent,
    _extract_messages,
    _extract_messages_claude,
    _extract_messages_codex,
    _extract_messages_pi,
    _iso,
    _pi_text,
    _session_summary,
    _target_agents,
    list_sessions,
    mcp,
    read_session,
    search_sessions,
)
from ai_reader.parsers import AgentName


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _tool_names() -> list[str]:
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.list_tools()
        return [t.name for t in result.tools]


async def _call(name: str, args: dict) -> list[str]:
    """Invoke a tool and return the *text* of every content block."""
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(name, args)
        return [c.text for c in result.content]


def _run(coro):
    """Run a coroutine in a fresh event loop.  Avoids the deprecated
    ``asyncio.get_event_loop()`` semantics in Python 3.12+.
    """
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_mcp_tool_registration() -> None:
    names = _run(_tool_names())
    assert "list_sessions" in names
    assert "read_session" in names
    assert "search_sessions" in names

    # The internal _tool_manager dict mirrors the public surface and
    # is the actual call dispatch table.
    internals = set(mcp._tool_manager._tools.keys())
    assert {"list_sessions", "read_session", "search_sessions"} <= internals


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


def test_mcp_list_sessions_claude() -> None:
    """Real sessions come back as summary dicts."""
    texts = _run(_call("list_sessions", {"agent": "claude"}))
    sessions = [json.loads(t) for t in texts if t.strip().startswith("{")]
    if sessions:
        s = sessions[0]
        assert "uuid" in s
        assert "agent" in s
        assert "title" in s
        assert "date" in s
        assert "message_count" in s
        assert s["agent"] == "CLAUDE"


# ---------------------------------------------------------------------------
# read_session
# ---------------------------------------------------------------------------


def _first_claude_uuid() -> str | None:
    base = Path("~/.claude/projects").expanduser()
    if not base.is_dir():
        return None
    for jsonl in base.glob("*/*.jsonl"):
        return jsonl.stem
    return None


def test_mcp_read_session_existing() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    # The autouse ``_isolate_ai_reader_home`` fixture points
    # ``AI_READER_HOME`` at an empty fake tree, so the Claude parser
    # would not find the real session.  Unset it for the duration of
    # this test.
    saved_home = os.environ.get("AI_READER_HOME")
    os.environ.pop("AI_READER_HOME", None)
    try:
        texts = _run(_call("read_session", {"uuid": uuid, "agent": "claude"}))
    finally:
        if saved_home is not None:
            os.environ["AI_READER_HOME"] = saved_home

    payload = json.loads(texts[0])
    assert payload["uuid"] == uuid
    assert payload["agent"] == "CLAUDE"
    assert "messages" in payload
    assert isinstance(payload["messages"], list)


def test_mcp_read_session_invalid_uuid() -> None:
    """The empty uuid is caught first and reported as ``invalid_argument``."""
    texts = _run(_call("read_session", {"uuid": "", "agent": "claude"}))
    payload = json.loads(texts[0])
    assert payload.get("error") == "invalid_argument"


def test_mcp_read_session_unknown_agent() -> None:
    texts = _run(_call("read_session", {"uuid": "x", "agent": "mystery"}))
    payload = json.loads(texts[0])
    assert payload.get("error") == "invalid_argument"


# ---------------------------------------------------------------------------
# search_sessions
# ---------------------------------------------------------------------------


def test_mcp_search_claude() -> None:
    texts = _run(
        _call("search_sessions", {"query": "claude", "agent": "claude"})
    )
    matches = [json.loads(t) for t in texts if t.strip().startswith("{")]
    if matches:
        m = matches[0]
        assert "uuid" in m and "title" in m


def test_mcp_search_empty_query() -> None:
    """An empty query short-circuits to an empty list."""
    texts = _run(_call("search_sessions", {"query": ""}))
    assert texts == [] or json.loads(texts[0]) == []


# ---------------------------------------------------------------------------
# Server identity
# ---------------------------------------------------------------------------


def test_mcp_server_name() -> None:
    assert mcp.name == "ai-reader"


# ---------------------------------------------------------------------------
# Direct unit tests for the helper functions.
#
# The in-memory transport runs the registered tools in a side thread
# whose coverage is not attributed to this process.  Calling the
# helpers (and the tool callables themselves) directly from the test
# thread restores the coverage attribution.
# ---------------------------------------------------------------------------


def test_iso_helper_naive_datetime() -> None:
    """Naive datetimes are emitted with a trailing ``Z``."""
    assert _iso(datetime(2026, 6, 14, 10, 0, 0)) == "2026-06-14T10:00:00Z"


def test_iso_helper_aware_datetime() -> None:
    """Aware datetimes use their own offset."""
    dt = datetime(2026, 6, 14, 10, 0, 0, tzinfo=timezone.utc)
    assert _iso(dt) == "2026-06-14T10:00:00+00:00"


def test_coerce_agent_lowercases() -> None:
    assert _coerce_agent("CLAUDE") is AgentName.CLAUDE
    assert _coerce_agent("codex") is AgentName.CODEX
    assert _coerce_agent(" OpenCode ") is AgentName.OPENCODE
    assert _coerce_agent("pi") is AgentName.PI
    with pytest.raises(ValueError):
        _coerce_agent("mystery")
    with pytest.raises(ValueError):
        _coerce_agent("")


def test_target_agents_all_when_none() -> None:
    """Omitting ``agent`` returns every supported agent."""
    targets = _target_agents(None)
    assert set(targets) == set(AgentName)
    assert _target_agents("") == list(AgentName)


def test_target_agents_single() -> None:
    targets = _target_agents("claude")
    assert targets == [AgentName.CLAUDE]


def test_session_summary_projects_fields() -> None:
    from ai_reader.parsers.models import Session
    s = Session(
        uuid="abc",
        agent=AgentName.CLAUDE,
        title="hello",
        date=datetime(2026, 6, 14, 10, 0, 0, tzinfo=timezone.utc),
        path="/x",
        message_count=3,
    )
    summary = _session_summary(s)
    assert summary["uuid"] == "abc"
    assert summary["agent"] == "CLAUDE"
    assert summary["title"] == "hello"
    assert summary["date"] == "2026-06-14T10:00:00+00:00"
    assert summary["message_count"] == 3


# --- _extract_messages_claude ----------------------------------------------


def test_extract_messages_claude_basic(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    p.write_text(
        '{"type":"user","message":{"role":"user","content":"hi"}}\n'
        '{"type":"assistant","message":{"role":"assistant","content":"hello"}}\n'
        '{"type":"queue-operation","operation":"enqueue"}\n',
        encoding="utf-8",
    )
    msgs = _extract_messages_claude(str(p))
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": "hi"}
    assert msgs[1] == {"role": "assistant", "content": "hello"}


def test_extract_messages_claude_handles_malformed(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    p.write_text(
        "not-json-line\n"
        '{"type":"user","message":{"role":"user","content":"x"}}\n',
        encoding="utf-8",
    )
    msgs = _extract_messages_claude(str(p))
    assert len(msgs) == 1
    assert msgs[0]["content"] == "x"


def test_extract_messages_claude_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    p.write_text("", encoding="utf-8")
    assert _extract_messages_claude(str(p)) == []


def test_extract_messages_claude_content_list(tmp_path: Path) -> None:
    """``content`` is a list of parts; only ``text`` parts contribute to
    the concatenated content.  ``tool_use`` parts are routed to the
    structured ``tool_use`` field on the underlying :class:`Message` and
    do not leak their ``text`` into ``content`` (the MCP shim projects
    only ``text`` into ``content``)."""
    p = tmp_path / "session.jsonl"
    p.write_text(
        '{"type":"assistant","message":{"role":"assistant","content":['
        '{"type":"text","text":"a"},'
        '{"type":"text","text":"b"},'
        '{"type":"tool_use","name":"Bash","input":"ls"}'
        ']}}\n',
        encoding="utf-8",
    )
    msgs = _extract_messages_claude(str(p))
    assert msgs[0]["content"] == "a\nb"


def test_extract_messages_claude_missing_file(tmp_path: Path) -> None:
    """An OSError (file gone) returns whatever was collected so far."""
    msgs = _extract_messages_claude(str(tmp_path / "nope.jsonl"))
    assert msgs == []


# --- _extract_messages_codex -----------------------------------------------


def test_extract_messages_codex_basic(tmp_path: Path) -> None:
    p = tmp_path / "rollout.jsonl"
    p.write_text(
        '{"type":"session_meta","payload":{"id":"x"}}\n'
        '{"type":"response_item","payload":{"type":"message","role":"user",'
        '"content":[{"type":"text","text":"hi"}]}}\n'
        '{"type":"response_item","payload":{"type":"message","role":"assistant",'
        '"content":[{"type":"text","text":"hello"}]}}\n',
        encoding="utf-8",
    )
    msgs = _extract_messages_codex(str(p))
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": "hi"}


def test_extract_messages_codex_handles_malformed(tmp_path: Path) -> None:
    p = tmp_path / "rollout.jsonl"
    p.write_text(
        "garbage\n"
        '{"type":"response_item","payload":{"type":"message","role":"user",'
        '"content":[{"type":"text","text":"real"}]}}\n',
        encoding="utf-8",
    )
    msgs = _extract_messages_codex(str(p))
    assert len(msgs) == 1
    assert msgs[0]["content"] == "real"


def test_extract_messages_codex_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "rollout.jsonl"
    p.write_text("", encoding="utf-8")
    assert _extract_messages_codex(str(p)) == []


def test_codex_text_variants() -> None:
    assert _codex_text([{"type": "text", "text": "a"}]) == "a"
    assert _codex_text([{"text": "no-type"}]) == "no-type"
    # Strings are passed through unchanged.
    assert _codex_text("just a string") == "just a string"
    # None / non-iterable scalars return empty.
    assert _codex_text(None) == ""  # type: ignore[arg-type]
    assert _codex_text(123) == ""  # type: ignore[arg-type]
    assert _codex_text([]) == ""


# --- _extract_messages_pi ---------------------------------------------------


def test_extract_messages_pi_basic(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    p.write_text(
        '{"type":"session","id":"x"}\n'
        '{"type":"message","message":{"role":"user",'
        '"content":[{"type":"text","text":"hi"}]}}\n'
        '{"type":"message","message":{"role":"assistant",'
        '"content":[{"type":"thinking","thinking":"hidden"},{"type":"text","text":"hello"}]}}\n'
        '{"type":"message","message":{"role":"toolResult","content":"ignored"}}\n',
        encoding="utf-8",
    )
    msgs = _extract_messages_pi(str(p))
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": "hi"}
    assert msgs[1] == {"role": "assistant", "content": "hello"}


def test_extract_messages_pi_handles_malformed(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    p.write_text(
        "garbage\n"
        '{"type":"message","message":{"role":"user",'
        '"content":[{"type":"text","text":"real"}]}}\n',
        encoding="utf-8",
    )
    msgs = _extract_messages_pi(str(p))
    assert len(msgs) == 1
    assert msgs[0]["content"] == "real"


def test_extract_messages_pi_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    p.write_text("", encoding="utf-8")
    assert _extract_messages_pi(str(p)) == []


def test_pi_text_variants() -> None:
    assert _pi_text([{"type": "text", "text": "a"}]) == "a"
    assert _pi_text([{"type": "thinking", "thinking": "ignored"}]) == ""
    assert _pi_text([{"text": "no-type"}]) == "no-type"
    assert _pi_text("just a string") == "just a string"
    assert _pi_text(None) == ""  # type: ignore[arg-type]


# --- _extract_messages dispatcher ------------------------------------------


def test_extract_messages_dispatches_to_claude(tmp_path: Path) -> None:
    from ai_reader.parsers.models import Session
    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"type":"user","message":{"role":"user","content":"y"}}\n',
        encoding="utf-8",
    )
    s = Session(
        uuid="u", agent=AgentName.CLAUDE, title="t", date=datetime.now(tz=timezone.utc),
        path=str(p), message_count=1,
    )
    assert _extract_messages(s)[0]["content"] == "y"


def test_extract_messages_dispatches_to_codex(tmp_path: Path) -> None:
    from ai_reader.parsers.models import Session
    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"type":"response_item","payload":{"type":"message","role":"user",'
        '"content":[{"type":"text","text":"z"}]}}\n',
        encoding="utf-8",
    )
    s = Session(
        uuid="u", agent=AgentName.CODEX, title="t", date=datetime.now(tz=timezone.utc),
        path=str(p), message_count=1,
    )
    assert _extract_messages(s)[0]["content"] == "z"


def test_extract_messages_dispatches_to_pi(tmp_path: Path) -> None:
    from ai_reader.parsers.models import Session
    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"type":"message","message":{"role":"user",'
        '"content":[{"type":"text","text":"p"}]}}\n',
        encoding="utf-8",
    )
    s = Session(
        uuid="u", agent=AgentName.PI, title="t", date=datetime.now(tz=timezone.utc),
        path=str(p), message_count=1,
    )
    assert _extract_messages(s)[0]["content"] == "p"


def test_extract_messages_unsupported_agent(tmp_path: Path) -> None:
    from ai_reader.parsers.models import Session
    s = Session(
        uuid="u", agent=AgentName.OPENCODE, title="t",
        date=datetime.now(tz=timezone.utc), path=str(tmp_path / "x"), message_count=0,
    )
    assert _extract_messages(s) == []


# --- list_sessions / read_session / search_sessions error paths -----------


def test_list_sessions_invalid_agent_returns_error_dict() -> None:
    """An unknown ``agent`` is surfaced as a structured error list."""
    result = list_sessions(agent="mystery")
    assert isinstance(result, list)
    assert result and result[0].get("error") == "invalid_argument"


def test_read_session_invalid_uuid_returns_error_dict() -> None:
    result = read_session(uuid="", agent="claude")
    assert isinstance(result, dict)
    assert result.get("error") == "invalid_argument"


def test_read_session_unknown_agent_returns_error_dict() -> None:
    result = read_session(uuid="x", agent="mystery")
    assert isinstance(result, dict)
    assert result.get("error") == "invalid_argument"


def test_read_session_not_found_returns_error_dict() -> None:
    """A nonexistent uuid -> ``not_found`` error dict."""
    # Disable AI_READER_HOME so the parser looks at the real tree,
    # then ask for a uuid that is not in it.
    saved_home = os.environ.get("AI_READER_HOME")
    os.environ.pop("AI_READER_HOME", None)
    try:
        result = read_session(
            uuid="definitely-not-a-real-uuid-xyzzy",
            agent="claude",
        )
    finally:
        if saved_home is not None:
            os.environ["AI_READER_HOME"] = saved_home
    assert isinstance(result, dict)
    assert result.get("error") == "not_found"
    assert result.get("agent") == "CLAUDE"


def test_search_sessions_empty_query_returns_empty() -> None:
    """An empty query short-circuits to ``[]``."""
    assert search_sessions(query="") == []


def test_search_sessions_invalid_agent_returns_error_dict() -> None:
    result = search_sessions(query="x", agent="mystery")
    assert isinstance(result, list)
    assert result and result[0].get("error") == "invalid_argument"


# ---------------------------------------------------------------------------
# read_session regression: capped {role, content} list via the public API
# ---------------------------------------------------------------------------


def test_read_session_returns_capped_role_content_list(
    fake_claude_session: Path, tmp_sessions_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``read_session`` must still return a list of ``{role, content}`` dicts
    (no tool_use/tool_result keys leak into MCP output)."""
    base = str(tmp_sessions_dir / ".claude" / "projects")
    monkeypatch.setattr(
        "ai_reader.parsers.claude._resolve_base_dir", lambda bd=None: Path(base)
    )
    result = read_session(uuid="test-claude-1", agent="claude")
    assert isinstance(result, dict)
    assert "error" not in result
    msgs = result["messages"]
    assert isinstance(msgs, list)
    assert len(msgs) == 2
    for m in msgs:
        assert set(m.keys()) == {"role", "content"}
    assert msgs[0] == {"role": "user", "content": "Hello, world"}
    assert msgs[1] == {"role": "assistant", "content": "Hi there!"}


def test_read_session_mcp_drops_tool_messages(
    fake_pi_session: Path, tmp_sessions_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pi toolResult records become ``tool`` Message objects; MCP output
    must NOT surface them (only user/assistant), preserving the historical
    output shape."""
    base = str(tmp_sessions_dir / ".pi" / "agent" / "sessions")
    monkeypatch.setattr(
        "ai_reader.parsers.pi._resolve_base_dir", lambda bd=None: Path(base)
    )
    result = read_session(uuid="test-pi-1", agent="pi")
    msgs = result["messages"]
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant"]
    for m in msgs:
        assert set(m.keys()) == {"role", "content"}


def test_message_and_read_messages_reexported() -> None:
    """``Message`` and the per-parser ``read_messages`` are public API."""
    from ai_reader.parsers import Message, antigravity, claude, codex, opencode, pi

    sample = Message(role="user", text="hi")
    assert sample.role == "user"
    assert sample.tool_use == ()
    assert sample.tool_result == ()
    for mod in (claude, codex, opencode, antigravity, pi):
        assert callable(getattr(mod, "read_messages"))


def test_messages_cap_constant_unchanged() -> None:
    from ai_reader.mcp_server import _MESSAGES_CAP

    assert _MESSAGES_CAP == 100
