"""Tests for the exporters.rounds module and the ``export rounds`` CLI."""
from __future__ import annotations

import contextlib
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Tuple

import pytest

from ai_reader import cli as cli_module
from ai_reader.exporters.rounds import session_to_rounds
from ai_reader.parsers.models import AgentName, Message, Session


_ENV_KEYS = ("AI_READER_HOME", "OPENCODE_DB")


def _run_inproc(
    argv: list[str], env: dict[str, str] | None = None
) -> Tuple[int, str, str]:
    saved_env = {k: os.environ.get(k) for k in _ENV_KEYS}
    try:
        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        if env:
            os.environ.update(env)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                rc = cli_module.main(argv)
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 1
        return rc, stdout.getvalue(), stderr.getvalue()
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _make_session(
    uuid: str = "abc-123",
    title: str = "Test session",
    date: datetime | None = None,
    extra: dict | None = None,
) -> Session:
    return Session(
        uuid=uuid,
        agent=AgentName.CLAUDE,
        title=title,
        date=date or datetime(2026, 6, 14, 10, 0, 0),
        path="/tmp/fake/abc-123.jsonl",
        message_count=0,
        extra=extra or {},
    )


def test_session_to_rounds_minimal() -> None:
    session = _make_session()
    out = session_to_rounds(session)
    assert "# Session: Test session" in out
    assert "**UUID**: abc-123" in out
    assert "**Agent**: CLAUDE" in out
    assert "**Date**: 2026-06-14" in out
    assert (
        "- 2026-06-14 \u2014 CLAUDE \u2014 Test session [non-actionable]" in out
    )
    assert "## Round:" not in out


def test_session_to_rounds_with_messages() -> None:
    session = _make_session()
    messages: list[Message] = [
        Message(
            role="user",
            text="Refactor the parser module",
            tool_use=(),
            tool_result=(),
        ),
        Message(
            role="assistant",
            text="Reading the current code now",
            tool_use=(
                {
                    "name": "Read",
                    "input": json.dumps(
                        {"file_path": "src/ai_reader/parsers/claude.py"}
                    ),
                },
            ),
            tool_result=(),
        ),
        Message(
            role="assistant",
            text="Found a bug to fix",
            tool_use=(),
            tool_result=(),
        ),
        Message(
            role="assistant",
            text="Editing now",
            tool_use=(
                {
                    "name": "Edit",
                    "input": json.dumps(
                        {
                            "file_path": "src/ai_reader/parsers/claude.py",
                            "old_string": "x",
                            "new_string": "y",
                        }
                    ),
                },
            ),
            tool_result=(),
        ),
        Message(
            role="user",
            text="Run the tests please",
            tool_use=(),
            tool_result=(),
        ),
    ]
    out = session_to_rounds(session, messages=messages)
    assert "## Round: Test session" in out
    assert "### Goal" in out
    assert "Refactor the parser module" in out
    assert "### Status" in out
    assert "in-progress" in out
    assert "### Files touched" in out
    assert "`src/ai_reader/parsers/claude.py`" in out
    assert "### Decisions" in out
    assert "### Open" in out
    assert "Run the tests please" in out
    assert "### Next actions" in out
    assert "Editing now" in out
    assert "### Snapshot" in out


def test_cli_export_rounds_stdout(tmp_sessions_dir: Path) -> None:
    uuid = "test-export-1"
    path = (
        tmp_sessions_dir
        / ".claude"
        / "projects"
        / "proj-a"
        / f"{uuid}.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "First message"},
                "timestamp": "2026-06-14T10:00:00Z",
                "sessionId": uuid,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rc, out, err = _run_inproc(
        ["export", "rounds", uuid],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    assert "# Session:" in out
    assert uuid in out
    assert "[non-actionable]" in out
    assert "## Round:" not in out
