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
    _MESSAGES_CAP,
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


def test_extract_messages_dispatches_to_claude(
    fake_claude_session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dispatcher routes Claude sessions through read_messages(uuid)."""
    from ai_reader.parsers.models import Session

    base = fake_claude_session.parent.parent  # .../projects (parent of proj-a)
    monkeypatch.setattr(
        "ai_reader.parsers.claude._resolve_base_dir", lambda bd=None: base
    )
    s = Session(
        uuid="test-claude-1",
        agent=AgentName.CLAUDE,
        title="t",
        date=datetime.now(tz=timezone.utc),
        path=str(fake_claude_session),
        message_count=1,
    )
    assert _extract_messages(s)[0]["content"] == "Hello, world"


def test_extract_messages_dispatches_to_codex(
    fake_codex_session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dispatcher routes Codex sessions through read_messages(uuid)."""
    from ai_reader.parsers.models import Session

    base = fake_codex_session.parent.parent.parent  # .../sessions
    monkeypatch.setattr(
        "ai_reader.parsers.codex._resolve_base_dir", lambda bd=None: base
    )
    s = Session(
        uuid="test-codex-1",
        agent=AgentName.CODEX,
        title="t",
        date=datetime.now(tz=timezone.utc),
        path=str(fake_codex_session),
        message_count=1,
    )
    msgs = _extract_messages(s)
    assert msgs
    assert msgs[0]["role"] == "user"


def test_extract_messages_dispatches_to_pi(
    fake_pi_session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dispatcher routes Pi sessions through read_messages(uuid)."""
    from ai_reader.parsers.models import Session

    base = fake_pi_session.parent  # .../sessions/--tmp-work--
    monkeypatch.setattr(
        "ai_reader.parsers.pi._resolve_base_dir", lambda bd=None: base
    )
    s = Session(
        uuid="test-pi-1",
        agent=AgentName.PI,
        title="t",
        date=datetime.now(tz=timezone.utc),
        path=str(fake_pi_session),
        message_count=1,
    )
    msgs = _extract_messages(s)
    assert msgs
    assert msgs[0]["content"] == "Add Pi support"


def test_extract_messages_dispatches_to_opencode(
    fake_opencode_db_with_tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OpenCode dispatches via the parser registry; {role, content} only."""
    monkeypatch.setenv("OPENCODE_DB", str(fake_opencode_db_with_tools))
    from ai_reader.parsers.models import Session

    s = Session(
        uuid="oc-tools-1",
        agent=AgentName.OPENCODE,
        title="t",
        date=datetime.now(tz=timezone.utc),
        path=str(fake_opencode_db_with_tools),
        message_count=3,
    )
    msgs = _extract_messages(s)
    assert msgs, "expected non-empty opencode messages"
    for m in msgs:
        assert set(m.keys()) == {"role", "content"}
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant"]


def test_extract_messages_dispatches_to_antigravity(
    fake_antigravity_brain: Path,
) -> None:
    """Antigravity dispatches via the parser registry; {role, content} only.

    The autouse ``_isolate_ai_reader_home`` fixture points
    ``AI_READER_HOME`` at the same fake tree ``fake_antigravity_brain``
    builds under, so the parser's ``read_messages`` finds the brain.
    """
    from ai_reader.parsers.models import Session

    s = Session(
        uuid="test-ag-1",
        agent=AgentName.ANTIGRAVITY,
        title="t",
        date=datetime.now(tz=timezone.utc),
        path=str(fake_antigravity_brain),
        message_count=2,
    )
    msgs = _extract_messages(s)
    assert msgs, "expected non-empty antigravity messages"
    for m in msgs:
        assert set(m.keys()) == {"role", "content"}


def test_extract_messages_all_agents_dispatch() -> None:
    """Every supported agent resolves to a parser in the registry.

    The dispatcher has no "unsupported agent" path anymore — all 5
    agents route through ``_PARSERS``.  A nonexistent uuid yields ``[]``
    via the try/except, not via a missing-parser branch.
    """
    from ai_reader.parsers.models import Session

    for agent in AgentName:
        s = Session(
            uuid="never-real-xyzzy",
            agent=agent,
            title="t",
            date=datetime.now(tz=timezone.utc),
            path="/nonexistent",
            message_count=0,
        )
        result = _extract_messages(s)
        assert isinstance(result, list)


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
    (no tool_use/tool_result keys leak into MCP output).  Pagination
    fields ``total``/``offset``/``limit`` ride along; the default limit
    echoes :data:`_MESSAGES_CAP` but is no longer a silent hard cap."""
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
    # Pagination fields.
    assert result["total"] == 2
    assert result["offset"] == 0
    assert result["limit"] == _MESSAGES_CAP


def test_read_session_pagination_default_returns_all(
    fake_claude_session: Path, tmp_sessions_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default offset=0/limit=_MESSAGES_CAP returns the full list."""
    base = str(tmp_sessions_dir / ".claude" / "projects")
    monkeypatch.setattr(
        "ai_reader.parsers.claude._resolve_base_dir", lambda bd=None: Path(base)
    )
    result = read_session(uuid="test-claude-1", agent="claude")
    assert result["total"] == len(result["messages"])
    assert result["offset"] == 0


def test_read_session_pagination_offset_limit_slice(
    fake_claude_session: Path, tmp_sessions_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """offset/limit slice the projected message list."""
    base = str(tmp_sessions_dir / ".claude" / "projects")
    monkeypatch.setattr(
        "ai_reader.parsers.claude._resolve_base_dir", lambda bd=None: Path(base)
    )
    # offset=1 skips the user message; limit=10 leaves the assistant msg.
    result = read_session(uuid="test-claude-1", agent="claude", offset=1, limit=10)
    msgs = result["messages"]
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert result["total"] == 2
    assert result["offset"] == 1
    assert result["limit"] == 10


def test_read_session_pagination_limit_caps_at_more_than_100(
    tmp_sessions_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session with 150 user messages: default limit returns 100, total
    reports 150, limit>100 returns all.  Proves the cap is no longer
    silent/hard."""
    # Synthesize a Claude session with 150 user messages.
    records = [
        {
            "type": "user",
            "message": {"role": "user", "content": f"msg-{i}"},
            "timestamp": "2026-06-14T10:00:00Z",
            "sessionId": "big-1",
        }
        for i in range(150)
    ]
    jsonl = tmp_sessions_dir / ".claude" / "projects" / "proj-big" / "big-1.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    jsonl.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    base = str(tmp_sessions_dir / ".claude" / "projects")
    monkeypatch.setattr(
        "ai_reader.parsers.claude._resolve_base_dir", lambda bd=None: Path(base)
    )

    default_capped = read_session(uuid="big-1", agent="claude")
    assert default_capped["total"] == 150
    assert len(default_capped["messages"]) == _MESSAGES_CAP  # 100
    assert default_capped["messages"][0]["content"] == "msg-0"
    assert default_capped["messages"][-1]["content"] == f"msg-{_MESSAGES_CAP - 1}"

    # Raise the limit → get everything.
    all_msgs = read_session(uuid="big-1", agent="claude", limit=0)
    assert all_msgs["total"] == 150
    assert len(all_msgs["messages"]) == 150

    # offset past the end → empty list, total still 150.
    tail = read_session(uuid="big-1", agent="claude", offset=145, limit=10)
    assert tail["total"] == 150
    assert len(tail["messages"]) == 5
    assert tail["messages"][0]["content"] == "msg-145"


def test_read_session_pagination_negative_offset_rejected(
    fake_claude_session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = str(fake_claude_session.parent.parent)
    monkeypatch.setattr(
        "ai_reader.parsers.claude._resolve_base_dir", lambda bd=None: Path(base)
    )
    result = read_session(uuid="test-claude-1", agent="claude", offset=-1)
    assert result.get("error") == "invalid_argument"


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
