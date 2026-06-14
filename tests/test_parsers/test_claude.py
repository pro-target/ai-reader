"""Tests for the Claude session parser.

Covers:

* Discovery against the real ``~/.claude/projects`` tree (read-only).
* Title, role and message-count extraction from synthetic fixtures.
* UUID validation: empty, slashes, path-traversal attempts.
* The ``search`` and ``session_exists`` helpers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_reader.parsers import AgentName, claude
from ai_reader.parsers.claude import (
    _extract_text_from_user_message,
    _normalise_title,
    _parse_iso_timestamp,
    _scan_file,
)


# ---------------------------------------------------------------------------
# Real-data smoke
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not Path("~/.claude/projects").expanduser().is_dir(),
    reason="no real Claude projects dir on this host",
)
def test_list_sessions_real(real_claude_dir: Path) -> None:
    sessions = claude.list_sessions()  # uses AI_READER_HOME? no, uses ~/.claude
    # When AI_READER_HOME is set (autouse fixture), parser redirects there.
    # So we must use base_dir to test the real tree.
    sessions = claude.list_sessions(base_dir=str(real_claude_dir))
    assert sessions, "expected at least one Claude session on this host"
    for s in sessions[:5]:
        assert s.agent is AgentName.CLAUDE
        assert s.title
        assert s.path.endswith(".jsonl")
        # Recent sessions must be sorted by date desc.
    dates = [s.date for s in sessions]
    assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# Synthetic fixture (writes into AI_READER_HOME / tmp)
# ---------------------------------------------------------------------------


def test_parse_message_role_user(fake_claude_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".claude" / "projects")
    sessions = claude.list_sessions(base_dir=base)
    assert len(sessions) == 1
    session = sessions[0]
    assert session.uuid == "test-claude-1"
    assert session.agent is AgentName.CLAUDE
    assert session.title == "Hello, world"
    assert session.message_count == 2  # one user, one assistant
    assert session.extra.get("project_slug") == "proj-a"


def test_parse_message_role_assistant(fake_claude_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".claude" / "projects")
    session = claude.read_session("test-claude-1", base_dir=base)
    assert session.message_count == 2  # both records counted
    assert session.title  # first user text becomes title


def test_extract_title(fake_claude_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".claude" / "projects")
    # Strip the user record, leaving only an assistant line.
    jsonl = fake_claude_session
    with jsonl.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "ai-title",
                    "aiTitle": "Auto-generated title",
                    "timestamp": "2026-06-14T09:00:00Z",
                    "sessionId": "test-claude-1",
                }
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "noise"}],
                    },
                    "timestamp": "2026-06-14T09:00:05Z",
                    "sessionId": "test-claude-1",
                }
            )
            + "\n"
        )
    session = claude.read_session("test-claude-1", base_dir=base)
    assert session.title == "Auto-generated title"
    # Only the assistant record counts.
    assert session.message_count == 1


def test_count_messages(tmp_sessions_dir: Path) -> None:
    base = tmp_sessions_dir / ".claude" / "projects" / "proj-a"
    base.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i in range(5):
        lines.append(
            json.dumps(
                {
                    "type": "user" if i % 2 == 0 else "assistant",
                    "message": {
                        "role": "user" if i % 2 == 0 else "assistant",
                        "content": f"msg-{i}",
                    },
                    "timestamp": f"2026-06-14T10:0{i}:00Z",
                    "sessionId": "x",
                }
            )
        )
    (base / "counted.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sessions = claude.list_sessions(base_dir=str(tmp_sessions_dir / ".claude" / "projects"))
    assert len(sessions) == 1
    assert sessions[0].message_count == 5


def test_invalid_uuid_raises(tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".claude" / "projects")
    for bad in ("", " ", "../escape", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            claude.read_session(bad, base_dir=base)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def test_parse_iso_timestamp_tolerates_z() -> None:
    ts = _parse_iso_timestamp("2026-06-14T10:00:00.123Z")
    assert ts is not None
    assert ts.year == 2026 and ts.month == 6 and ts.day == 14


def test_parse_iso_timestamp_returns_none_on_garbage() -> None:
    assert _parse_iso_timestamp("") is None
    assert _parse_iso_timestamp("not-a-date") is None
    assert _parse_iso_timestamp(None) is None  # type: ignore[arg-type]


def test_normalise_title_collapses_and_truncates() -> None:
    assert _normalise_title("hello\nworld") == "hello world"
    assert _normalise_title("") == "Untitled"
    assert _normalise_title("x" * 200) == "x" * 100


def test_extract_text_from_user_message_string() -> None:
    assert _extract_text_from_user_message({"content": "hi"}) == "hi"


def test_extract_text_from_user_message_list() -> None:
    """Returns the *first* non-system, non-empty text part."""
    msg = {
        "content": [
            {"type": "text", "text": "first wins"},
            {"type": "text", "text": "second"},
        ]
    }
    assert _extract_text_from_user_message(msg) == "first wins"


def test_extract_text_from_user_message_skips_system() -> None:
    """Lines that start with ``<`` (e.g. ``<system-reminder>``) are skipped."""
    msg = {
        "content": [
            {"type": "text", "text": "<system-reminder>nope</system-reminder>"},
            {"type": "text", "text": "second"},
        ]
    }
    assert _extract_text_from_user_message(msg) == "second"


def test_extract_text_from_user_message_no_match() -> None:
    assert _extract_text_from_user_message({"content": [{"type": "text", "text": ""}]}) == ""
    assert _extract_text_from_user_message({"content": []}) == ""


def test_scan_file_handles_malformed_lines(tmp_path: Path) -> None:
    bad = tmp_path / "weird.jsonl"
    bad.write_text(
        "this is not json\n"
        '{"type":"user","message":{"role":"user","content":"hello"},"timestamp":"2026-06-14T10:00:00Z"}\n',
        encoding="utf-8",
    )
    session = _scan_file(bad)
    assert session is not None
    assert session.title == "hello"
    assert session.message_count == 1


def test_session_exists(tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".claude" / "projects")
    _ = tmp_sessions_dir  # noqa: F841  (uses the dir layout)
    # create a session
    (tmp_sessions_dir / ".claude" / "projects" / "proj-a" / "present.jsonl").write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "x"},
                "timestamp": "2026-06-14T10:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert claude.session_exists("present", base_dir=base) is True
    assert claude.session_exists("absent", base_dir=base) is False
    assert claude.session_exists("../escape", base_dir=base) is False


def test_search_returns_matches_case_insensitive(fake_claude_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".claude" / "projects")
    out = claude.search("HELLO", base_dir=base)
    assert len(out) == 1
    assert out[0].uuid == "test-claude-1"
    # Empty query -> empty
    assert claude.search("", base_dir=base) == []


def test_list_sessions_missing_dir(tmp_path: Path) -> None:
    assert claude.list_sessions(base_dir=str(tmp_path / "nope")) == []


def test_read_session_missing_raises(tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".claude" / "projects")
    with pytest.raises(FileNotFoundError):
        claude.read_session("definitely-not-here", base_dir=base)
