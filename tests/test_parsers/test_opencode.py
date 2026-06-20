"""Tests for the OpenCode SQLite parser."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_reader.parsers import AgentName, opencode
from ai_reader.parsers.opencode import (
    _epoch_ms_to_datetime,
    _open_db,
    _resolve_db_paths,
    _row_to_session,
)


def test_list_sessions_real(real_opencode_db: Path) -> None:
    sessions = opencode.list_sessions(override=str(real_opencode_db))
    assert sessions, "expected at least one OpenCode session on this host"
    for s in sessions[:3]:
        assert s.agent is AgentName.OPENCODE
        assert s.title
        assert s.message_count >= 0
    # No duplicates across the same DB.
    ids = [s.uuid for s in sessions]
    assert len(ids) == len(set(ids))


def test_get_session_info(fake_opencode_db: Path) -> None:
    s = opencode.read_session("test-oc-1", override=str(fake_opencode_db))
    assert s.uuid == "test-oc-1"
    assert s.agent is AgentName.OPENCODE
    assert s.title == "First OpenCode session"
    assert s.message_count == 2
    assert s.parent_uuid is None

    child = opencode.read_session("test-oc-2", override=str(fake_opencode_db))
    assert child.parent_uuid == "test-oc-1"
    assert child.message_count == 1


def test_handle_locked_db_gracefully(fake_opencode_db: Path) -> None:
    """Opening the same DB twice should not error."""
    conn_a = _open_db(str(fake_opencode_db))
    conn_b = _open_db(str(fake_opencode_db))
    assert conn_a is not None
    assert conn_b is not None
    conn_a.close()
    conn_b.close()


def test_open_db_missing_file_returns_none(tmp_path: Path) -> None:
    assert _open_db(str(tmp_path / "nope.db")) is None


def test_list_sessions_missing_db_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no real DB and a non-existent base_dir, the function returns [].

    The OpenCode parser always considers the well-known default paths
    (native + snap).  We monkeypatch the discovery helper to return no
    candidates, simulating a host with no OpenCode installation.
    """
    monkeypatch.setattr(
        "ai_reader.parsers.opencode._resolve_db_paths",
        lambda base_dir=None, override=None: [],
    )
    assert opencode.list_sessions(base_dir=str(tmp_path / "no-such-dir")) == []


def test_read_session_invalid_uuid(fake_opencode_db: Path) -> None:
    with pytest.raises(ValueError):
        opencode.read_session("../escape", override=str(fake_opencode_db))
    with pytest.raises(ValueError):
        opencode.read_session("", override=str(fake_opencode_db))


def test_read_session_missing(fake_opencode_db: Path) -> None:
    with pytest.raises(FileNotFoundError):
        opencode.read_session("nope", override=str(fake_opencode_db))


def test_session_exists(fake_opencode_db: Path) -> None:
    assert opencode.session_exists("test-oc-1", override=str(fake_opencode_db)) is True
    assert opencode.session_exists("test-oc-2", override=str(fake_opencode_db)) is True
    assert opencode.session_exists("nope", override=str(fake_opencode_db)) is False
    assert opencode.session_exists("../escape", override=str(fake_opencode_db)) is False


def test_search(
    fake_opencode_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fake DB has ``test-oc-1``; hide the real DBs so the search
    result is deterministic.
    """
    monkeypatch.setattr(
        "ai_reader.parsers.opencode._resolve_db_paths",
        lambda base_dir=None, override=None: [str(fake_opencode_db)],
    )
    out = opencode.search("opencode")
    assert len(out) == 1
    assert out[0].uuid == "test-oc-1"
    assert opencode.search("zzz") == []
    assert opencode.search("") == []


def test_resolve_db_paths_dedup(fake_opencode_db: Path, tmp_path: Path) -> None:
    """The override path is deduped against the same realpath (via symlink)."""
    link = tmp_path / "linked.db"
    try:
        link.symlink_to(fake_opencode_db)
    except OSError:
        pytest.skip("symlinks unavailable on this fs")
    paths = _resolve_db_paths(override=str(link))
    realpaths = {Path(p).resolve() for p in paths}
    # The override and the symlink both point at the same file.
    assert Path(link).resolve() in realpaths
    # The dedup pass collapses them — the symlink target realpath
    # appears at most once across ``override`` and the native lookup.
    occurrences = sum(
        1 for p in paths if Path(p).resolve() == Path(link).resolve()
    )
    assert occurrences == 1


def test_epoch_ms_to_datetime() -> None:
    dt = _epoch_ms_to_datetime(1_716_000_000_000)
    assert dt.year == 2024
    assert dt.tzinfo is not None


def test_row_to_session(fake_opencode_db: Path) -> None:
    conn = sqlite3.connect(str(fake_opencode_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, title, time_created, time_updated, parent_id "
        "FROM session WHERE id = ?",
        ("test-oc-1",),
    ).fetchone()
    session = _row_to_session(row, str(fake_opencode_db))
    assert session.uuid == "test-oc-1"
    assert session.title == "First OpenCode session"
    assert session.path == str(fake_opencode_db)
    assert session.parent_uuid is None
    conn.close()


def test_row_to_session_untitled() -> None:
    """A session with a NULL title falls back to ``Untitled``."""
    import sqlite3
    from pathlib import Path
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "CREATE TABLE session (id TEXT PRIMARY KEY, parent_id TEXT, title TEXT, "
        "time_created INTEGER, time_updated INTEGER);"
    )
    conn.execute(
        "INSERT INTO session VALUES (?, NULL, NULL, 1700000000000, 1700000000000)",
        ("u",),
    )
    conn.commit()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM session WHERE id = 'u'").fetchone()
    session = _row_to_session(row, str(path))
    assert session.title == "Untitled"
    conn.close()
    path.unlink()


# ---------------------------------------------------------------------------
# read_messages
# ---------------------------------------------------------------------------


def test_read_messages_basic(fake_opencode_db: Path) -> None:
    """The minimal fixture has no ``data`` column content, so messages are empty."""
    msgs = opencode.read_messages("test-oc-1", override=str(fake_opencode_db))
    assert isinstance(msgs, list)
    # The basic fixture inserts rows without a ``data`` blob; the extractor
    # skips rows with NULL/empty data.
    assert msgs == []


def test_read_messages_preserves_tool_calls(fake_opencode_db_with_tools: Path) -> None:
    msgs = opencode.read_messages("oc-tools-1", override=str(fake_opencode_db_with_tools))
    assert len(msgs) == 3
    assert msgs[0].role == "user"
    assert msgs[0].text == "run tests"
    assistant = msgs[1]
    assert assistant.role == "assistant"
    assert assistant.text == "okay"
    assert len(assistant.tool_use) == 1
    assert assistant.tool_use[0]["name"] == "shell"
    assert assistant.tool_use[0]["input"] == "pytest"
    tool = msgs[2]
    assert tool.role == "tool"
    assert len(tool.tool_result) == 1
    assert tool.tool_result[0]["content"] == "5 passed"


def test_read_messages_missing_raises(fake_opencode_db: Path) -> None:
    with pytest.raises(FileNotFoundError):
        opencode.read_messages("nope", override=str(fake_opencode_db))


def test_read_messages_invalid_uuid(fake_opencode_db: Path) -> None:
    with pytest.raises(ValueError):
        opencode.read_messages("../escape", override=str(fake_opencode_db))
