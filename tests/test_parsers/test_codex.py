"""Tests for the Codex session parser."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ai_reader.parsers import AgentName, codex
from ai_reader.parsers.codex import (
    _extract_text_from_parts,
    _is_system_noise,
    _is_valid_uuid,
    _parse_iso_timestamp,
    _scan_file,
)


def test_list_sessions_real(real_codex_dir: Path) -> None:
    sessions = codex.list_sessions(base_dir=str(real_codex_dir))
    assert sessions, "expected at least one Codex session on this host"
    for s in sessions[:3]:
        assert s.agent is AgentName.CODEX
        assert s.title
        assert "rollout-" in s.path
    # Most-recent first.
    dates = [s.date for s in sessions]
    assert dates == sorted(dates, reverse=True)


def test_list_sessions_synthetic(fake_codex_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".codex" / "sessions")
    sessions = codex.list_sessions(base_dir=base)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.uuid == "test-codex-1"
    assert s.agent is AgentName.CODEX
    assert s.title == "Roll out please"  # first user message becomes title
    assert s.message_count == 2  # 1 user + 1 assistant (system noise ignored)
    assert s.extra.get("cwd") == "/tmp/work"


def test_parse_message(fake_codex_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".codex" / "sessions")
    s = codex.read_session("test-codex-1", base_dir=base)
    assert s.title == "Roll out please"
    assert s.message_count == 2
    assert s.uuid == "test-codex-1"


def test_extract_uuid_from_filename(fake_codex_session: Path) -> None:
    """The filename embeds the uuid — verify the regex extracts it."""
    name = fake_codex_session.name  # rollout-2026-06-14T10-00-00-test-codex-1.jsonl
    m = re.search(r"rollout-\d{4}-\d{2}-\d{2}T[\d-]+-(.+)\.jsonl$", name)
    assert m is not None
    assert m.group(1) == "test-codex-1"


def test_list_sessions_dedupes_same_uuid(tmp_sessions_dir: Path) -> None:
    base = tmp_sessions_dir / ".codex" / "sessions" / "2026" / "06" / "14"
    base.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": "2026-06-14T10:00:00Z",
        "type": "session_meta",
        "payload": {"id": "dup", "timestamp": "2026-06-14T10:00:00Z"},
    }
    (base / "rollout-2026-06-14T10-00-00-dup.jsonl").write_text(
        json.dumps(payload) + "\n", encoding="utf-8"
    )
    (base / "rollout-2026-06-14T11-00-00-dup.jsonl").write_text(
        json.dumps(payload) + "\n", encoding="utf-8"
    )
    sessions = codex.list_sessions(base_dir=str(tmp_sessions_dir / ".codex" / "sessions"))
    assert len(sessions) == 1


def test_session_meta_without_id_returns_none(tmp_path: Path) -> None:
    base = tmp_path / "x"
    base.mkdir()
    (base / "rollout-test.jsonl").write_text(
        json.dumps(
            {"type": "session_meta", "payload": {"timestamp": "2026-06-14T10:00:00Z"}}
        )
        + "\n",
        encoding="utf-8",
    )
    sessions = codex.list_sessions(base_dir=str(base))
    assert sessions == []


def test_read_session_invalid_uuid(tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".codex" / "sessions")
    with pytest.raises(ValueError):
        codex.read_session("../escape", base_dir=base)
    with pytest.raises(ValueError):
        codex.read_session("", base_dir=base)


def test_read_session_missing(tmp_sessions_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        codex.read_session("nope", base_dir=str(tmp_sessions_dir / ".codex" / "sessions"))


def test_search_filters_titles(fake_codex_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".codex" / "sessions")
    out = codex.search("roll out", base_dir=base)
    assert len(out) == 1
    assert codex.search("zzz", base_dir=base) == []
    assert codex.search("", base_dir=base) == []


def test_extract_text_from_parts() -> None:
    parts = [
        {"type": "input_text", "text": "hello"},
        {"type": "output_text", "text": "world"},
        {"type": "image", "text": "ignored"},
        {"text": "no-type"},
        "not-a-dict",
    ]
    assert _extract_text_from_parts(parts) == "hello\nworld\nno-type"


def test_extract_text_from_parts_non_list() -> None:
    """The function only iterates a list; everything else is empty."""
    assert _extract_text_from_parts(None) == ""  # type: ignore[arg-type]
    assert _extract_text_from_parts("a string") == ""  # type: ignore[arg-type]
    assert _extract_text_from_parts(123) == ""  # type: ignore[arg-type]


def test_is_system_noise() -> None:
    assert _is_system_noise("<permissions")
    assert _is_system_noise("## Apps")
    assert _is_system_noise("<command-message>")
    assert _is_system_noise("<system-reminder>")
    assert not _is_system_noise("ordinary prompt text")


def test_is_valid_uuid() -> None:
    assert _is_valid_uuid("abc-123")
    assert not _is_valid_uuid("")
    assert not _is_valid_uuid(" has space")
    assert not _is_valid_uuid("has/slash")
    assert not _is_valid_uuid("has\\slash")
    assert not _is_valid_uuid(None)  # type: ignore[arg-type]


def test_parse_iso_timestamp_variants() -> None:
    assert _parse_iso_timestamp("2026-06-14T10:00:00Z") is not None
    assert _parse_iso_timestamp("2026-06-14T10:00:00.123456Z") is not None
    assert _parse_iso_timestamp("") is None
    assert _parse_iso_timestamp("nope") is None
    assert _parse_iso_timestamp(123) is None  # type: ignore[arg-type]


def test_scan_file_returns_none_on_unreadable(tmp_path: Path) -> None:
    # Point at a path that doesn't exist; the inner ``open`` will raise OSError.
    ghost = tmp_path / "nope.jsonl"
    assert _scan_file(ghost) is None


# ---------------------------------------------------------------------------
# read_messages
# ---------------------------------------------------------------------------


def test_read_messages_basic(fake_codex_session: Path, tmp_sessions_dir: Path) -> None:
    base = str(tmp_sessions_dir / ".codex" / "sessions")
    msgs = codex.read_messages("test-codex-1", base_dir=base)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].text == "Roll out please"
    assert msgs[1].role == "assistant"
    assert msgs[1].text == "Done."


def test_read_messages_preserves_tool_calls(
    fake_codex_session_with_tools: Path, tmp_sessions_dir: Path
) -> None:
    base = str(tmp_sessions_dir / ".codex" / "sessions")
    msgs = codex.read_messages("codex-tools-1", base_dir=base)
    # user message + function_call + function_call_output
    assert len(msgs) == 3
    assert msgs[0].role == "user"
    call = msgs[1]
    assert call.role == "assistant"
    assert len(call.tool_use) == 1
    assert call.tool_use[0]["name"] == "shell"
    assert call.tool_use[0]["input"] == "pytest"
    out = msgs[2]
    assert out.role == "tool"
    assert len(out.tool_result) == 1
    assert out.tool_result[0]["content"] == "5 passed"


def test_read_messages_missing_raises(tmp_sessions_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        codex.read_messages("nope", base_dir=str(tmp_sessions_dir / ".codex" / "sessions"))


def test_read_messages_invalid_uuid(tmp_sessions_dir: Path) -> None:
    with pytest.raises(ValueError):
        codex.read_messages("../escape", base_dir=str(tmp_sessions_dir / ".codex" / "sessions"))


def test_dedup_key_len_default_is_256() -> None:
    assert codex.get_dedup_key_len() == 256


def test_dedup_key_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime env changes are honored — no module reload required."""
    monkeypatch.setenv("AI_READER_DEDUP_KEY_LEN", "1024")
    try:
        assert codex.get_dedup_key_len() == 1024
    finally:
        monkeypatch.delenv("AI_READER_DEDUP_KEY_LEN", raising=False)
    assert codex.get_dedup_key_len() == 256


def test_dedup_key_invalid_env_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_READER_DEDUP_KEY_LEN", "not-a-number")
    try:
        assert codex.get_dedup_key_len() == 256
    finally:
        monkeypatch.delenv("AI_READER_DEDUP_KEY_LEN", raising=False)


def test_dedup_key_non_positive_env_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_READER_DEDUP_KEY_LEN", "0")
    try:
        assert codex.get_dedup_key_len() == 256
    finally:
        monkeypatch.delenv("AI_READER_DEDUP_KEY_LEN", raising=False)
