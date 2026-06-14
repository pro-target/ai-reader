"""Shared pytest fixtures for ai-reader tests.

Fixtures are deterministic: every fixture that touches the filesystem
creates a temporary directory and never writes outside ``tmp_path`` or
``AI_READER_HOME`` (the latter only when explicitly overridden).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator, List

import pytest


# ---------------------------------------------------------------------------
# Environment isolation
# ---------------------------------------------------------------------------

# Markers that may be added later to the package's own pyproject
pytest_plugins: list[str] = []


@pytest.fixture(autouse=True)
def _isolate_ai_reader_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """Force parsers to look at a per-test temp directory tree.

    The smoke step established that real ``~/.claude``, ``~/.codex``,
    ``~/.local/share/opencode`` and ``~/.gemini`` directories exist on
    this host.  We *want* a few integration tests to hit them
    (read-only), but the default behaviour for most tests must be
    hermetic.  By setting ``AI_READER_HOME`` to a fresh temp dir the
    parsers fall back to it and find nothing.
    """
    monkeypatch.setenv("AI_READER_HOME", str(tmp_path / "fake_home"))
    # OpenCode honours a separate env var.  Wipe it to avoid leaking the
    # real DB into parser-discovery tests.
    monkeypatch.delenv("OPENCODE_DB", raising=False)
    yield


# ---------------------------------------------------------------------------
# Fake session data builders
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")


@pytest.fixture
def tmp_sessions_dir(tmp_path: Path) -> Path:
    """A fresh root directory that mimics ``AI_READER_HOME``.

    Sub-directories matching the parser layout are created but left
    empty unless the requesting test populates them.
    """
    home = tmp_path / "fake_home"
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "projects" / "proj-a").mkdir(parents=True)
    (home / ".codex" / "sessions").mkdir(parents=True)
    (home / ".gemini" / "antigravity" / "brain").mkdir(parents=True)
    (home / ".gemini" / "antigravity-cli" / "brain").mkdir(parents=True)
    return home


@pytest.fixture
def fake_claude_session(tmp_sessions_dir: Path) -> Path:
    """A single Claude session JSONL inside the fake projects tree."""
    session_id = "test-claude-1"
    jsonl = tmp_sessions_dir / ".claude" / "projects" / "proj-a" / f"{session_id}.jsonl"
    _write_jsonl(
        jsonl,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "Hello, world"},
                "timestamp": "2026-06-14T10:00:00Z",
                "sessionId": session_id,
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi there!"}],
                },
                "timestamp": "2026-06-14T10:00:05Z",
                "sessionId": session_id,
            },
        ],
    )
    return jsonl


@pytest.fixture
def fake_codex_session(tmp_sessions_dir: Path) -> Path:
    """A single Codex rollout file inside the fake sessions tree."""
    uuid = "test-codex-1"
    jsonl = (
        tmp_sessions_dir
        / ".codex"
        / "sessions"
        / "2026"
        / "06"
        / "14"
        / f"rollout-2026-06-14T10-00-00-{uuid}.jsonl"
    )
    _write_jsonl(
        jsonl,
        [
            {
                "timestamp": "2026-06-14T10:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": uuid,
                    "cwd": "/tmp/work",
                    "timestamp": "2026-06-14T10:00:00Z",
                },
            },
            {
                "timestamp": "2026-06-14T10:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "text", "text": "Roll out please"}],
                },
            },
            {
                "timestamp": "2026-06-14T10:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Done."}],
                },
            },
        ],
    )
    return jsonl


@pytest.fixture
def fake_opencode_db(tmp_sessions_dir: Path) -> Path:
    """A minimal OpenCode SQLite database with one session + 2 messages."""
    db_path = tmp_sessions_dir / "opencode.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE session (
            id           TEXT PRIMARY KEY,
            parent_id    TEXT,
            title        TEXT,
            time_created INTEGER,
            time_updated INTEGER
        );
        CREATE TABLE message (
            id         TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES session(id)
        );
        """
    )
    conn.execute(
        "INSERT INTO session VALUES (?, ?, ?, ?, ?)",
        (
            "test-oc-1",
            None,
            "First OpenCode session",
            1_716_000_000_000,
            1_716_000_500_000,
        ),
    )
    conn.execute(
        "INSERT INTO session VALUES (?, ?, ?, ?, ?)",
        (
            "test-oc-2",
            "test-oc-1",
            "Child session",
            1_716_000_600_000,
            1_716_000_900_000,
        ),
    )
    for n, sid in enumerate(("test-oc-1", "test-oc-1", "test-oc-2")):
        conn.execute("INSERT INTO message VALUES (?, ?)", (f"m-{n}", sid))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def fake_antigravity_brain(tmp_sessions_dir: Path) -> Path:
    """A single brain directory with a minimal overview.txt + transcript."""
    brain = tmp_sessions_dir / ".gemini" / "antigravity" / "brain" / "test-ag-1"
    (brain / ".system_generated" / "logs").mkdir(parents=True)
    overview = brain / ".system_generated" / "logs" / "overview.txt"
    _write_jsonl(
        overview,
        [
            {
                "timestamp": "2026-06-14T10:00:00Z",
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "content": "<USER_REQUEST>Set up the lab</USER_REQUEST>",
            },
            {
                "timestamp": "2026-06-14T10:00:05Z",
                "source": "MODEL",
                "type": "MODEL_OUTPUT",
                "content": "ok",
            },
        ],
    )
    return brain


# ---------------------------------------------------------------------------
# Subagent environment helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def subagent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the canonical Claude subagent marker so the guard allows access."""
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT", "1")
    # Wipe other agent markers to keep tests deterministic.
    for var in (
        "CODEX_SUBAGENT_TASK_ID",
        "OPENCODE_PARENT_ID",
        "GEMINI_SUBAGENT",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def parent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure *no* subagent marker is visible to the guard."""
    for var in (
        "CLAUDE_CODE_SUBAGENT",
        "CLAUDE_CODE_FORK_SUBAGENT",
        "CODEX_SUBAGENT_TASK_ID",
        "OPENCODE_PARENT_ID",
        "GEMINI_SUBAGENT",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Real-data probes (read-only, used by integration-style tests)
# ---------------------------------------------------------------------------


_REAL_CLAUDE_DIR = Path("~/.claude/projects").expanduser()
_REAL_CODEX_DIR = Path("~/.codex/sessions").expanduser()
_REAL_OPENCODE_DB = Path("~/.local/share/opencode/opencode.db")
_REAL_ANTIGRAVITY_DIRS: List[Path] = [
    Path("~/.gemini/antigravity/brain").expanduser(),
    Path("~/.gemini/antigravity-cli/brain").expanduser(),
]


@pytest.fixture(scope="session")
def real_claude_dir() -> Path | None:
    return _REAL_CLAUDE_DIR if _REAL_CLAUDE_DIR.is_dir() else None


@pytest.fixture(scope="session")
def real_codex_dir() -> Path | None:
    return _REAL_CODEX_DIR if _REAL_CODEX_DIR.is_dir() else None


@pytest.fixture(scope="session")
def real_opencode_db() -> Path | None:
    return _REAL_OPENCODE_DB if _REAL_OPENCODE_DB.is_file() else None


@pytest.fixture(scope="session")
def real_antigravity_root() -> Path | None:
    for root in _REAL_ANTIGRAVITY_DIRS:
        if root.is_dir() and any(root.iterdir()):
            return root
    return None


# ---------------------------------------------------------------------------
# Sample fixtures copied to a writable location for parser-specific tests
# ---------------------------------------------------------------------------


@pytest.fixture
def claude_sample_jsonl(tmp_path: Path) -> Path:
    src = Path(__file__).parent / "fixtures" / "claude_sample.jsonl"
    dest = tmp_path / "claude_sample.jsonl"
    shutil.copyfile(src, dest)
    return dest


@pytest.fixture
def codex_sample_jsonl(tmp_path: Path) -> Path:
    src = Path(__file__).parent / "fixtures" / "codex_sample.jsonl"
    dest = tmp_path / "codex_sample.jsonl"
    shutil.copyfile(src, dest)
    return dest
