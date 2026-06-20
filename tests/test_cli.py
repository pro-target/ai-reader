"""End-to-end CLI tests, driven through ``subprocess``.

Why subprocess and not ``cli.main(argv)`` directly?  The CLI is the
executable surface that ships to operators, so testing the *real*
binary entry point — ``python -m ai_reader.cli`` — catches issues
that in-process testing would miss: missing ``__future__`` imports,
``sys.path`` munging, ``argparse`` quirks, the works.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ai_reader import cli as cli_module


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def _run_cli(
    *args: str,
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess:
    """Invoke ``python -m ai_reader.cli`` with the given args.

    The autouse ``_isolate_ai_reader_home`` fixture sets
    ``AI_READER_HOME`` in the *test* process; the subprocess would
    inherit it and look at an empty fake tree.  We explicitly strip
    the variable from the child environment unless the caller asked
    for it.
    """
    cmd = [sys.executable, "-m", "ai_reader.cli", *args]
    full_env = os.environ.copy()
    full_env.pop("AI_READER_HOME", None)
    full_env.pop("OPENCODE_DB", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=timeout,
    )


def _first_claude_uuid() -> str | None:
    """Pick a real session uuid from the local Claude tree (if any)."""
    base = Path("~/.claude/projects").expanduser()
    if not base.is_dir():
        return None
    for jsonl in base.glob("*/*.jsonl"):
        return jsonl.stem
    return None


# ---------------------------------------------------------------------------
# In-process helper — runs ``cli.main`` in this process so coverage
# lines count toward the report.
# ---------------------------------------------------------------------------


_ENV_KEYS = (
    "AI_READER_HOME",
    "OPENCODE_DB",
)


def _run_inproc(
    argv: list[str], env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    """Run ``cli.main(argv)`` in-process; return (rc, stdout, stderr)."""
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
            except SystemExit as exc:  # argparse calls sys.exit
                rc = exc.code if isinstance(exc.code, int) else 1
        return rc, stdout.getvalue(), stderr.getvalue()
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Version / help
# ---------------------------------------------------------------------------


def test_cli_version() -> None:
    p = _run_cli("--version")
    assert p.returncode == 0, p.stderr
    assert "ai-reader" in p.stdout
    assert "0.1.0" in p.stdout


def test_module_invocation() -> None:
    """``python -m ai_reader --version`` exits 0 (module entry point works)."""
    p = subprocess.run(
        [sys.executable, "-m", "ai_reader", "--version"],
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    assert p.returncode == 0, p.stderr
    assert "ai-reader" in p.stdout


def test_cli_help() -> None:
    p = _run_cli("--help")
    assert p.returncode == 0, p.stderr
    assert "list" in p.stdout
    assert "read" in p.stdout
    assert "search" in p.stdout


def test_cli_no_subcommand_returns_1() -> None:
    p = _run_cli()
    assert p.returncode != 0
    assert "usage" in p.stderr.lower() or "usage" in p.stdout.lower()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_cli_list_claude() -> None:
    p = _run_cli("list", "--agent", "claude")
    assert p.returncode == 0, p.stderr
    assert "UUID" in p.stdout
    assert "AGENT" in p.stdout


def test_cli_list_json() -> None:
    p = _run_cli("list", "--agent", "claude", "--json")
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert isinstance(payload, list)
    if payload:  # host has Claude sessions
        for item in payload[:3]:
            assert "uuid" in item
            assert "agent" in item
            assert "date" in item


def test_cli_list_empty() -> None:
    """No sessions in AI_READER_HOME -> stderr message, exit 0."""
    rc, out, err = _run_inproc(
        ["list", "--agent", "claude"],
        env={"AI_READER_HOME": "/nonexistent"},
    )
    assert rc == 0
    assert "no sessions found" in err.lower()


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_cli_read_existing() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    p = _run_cli("read", "--agent", "claude", uuid)
    assert p.returncode == 0, p.stderr
    assert uuid in p.stdout
    assert "UUID:" in p.stdout


def test_cli_read_json() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    p = _run_cli("read", "--agent", "claude", "--json", uuid)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["uuid"] == uuid
    assert payload["agent"] == "CLAUDE"


def test_cli_read_invalid_uuid_format() -> None:
    """A uuid that fails the regex (e.g. contains whitespace) -> non-zero."""
    p = _run_cli("read", "--agent", "claude", "has spaces")
    assert p.returncode != 0


def test_cli_read_unknown_agent() -> None:
    p = _run_cli("read", "--agent", "mystery", "some-uuid")
    assert p.returncode != 0


def test_cli_read_missing_uuid() -> None:
    p = _run_cli("read", "--agent", "claude")
    assert p.returncode != 0


def test_cli_read_not_found() -> None:
    """Valid uuid format but no such session -> exit 3 (not found)."""
    rc, out, err = _run_inproc(["read", "--agent", "claude", "definitely-not-here"])
    assert rc == 3
    assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_cli_search_claude() -> None:
    p = _run_cli("search", "claude")
    assert p.returncode == 0, p.stderr
    assert "UUID" in p.stdout or "(no sessions match" in p.stderr


def test_cli_search_no_results() -> None:
    p = _run_cli("search", "this-string-should-match-nothing-xyzzy123")
    assert p.returncode == 0, p.stderr
    assert "no sessions match" in p.stderr.lower()


def test_cli_search_empty_query_rejected() -> None:
    p = _run_cli("search", "")
    assert p.returncode != 0
    assert "search query" in p.stderr.lower()


def test_cli_search_json() -> None:
    p = _run_cli("search", "claude", "--json")
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert isinstance(payload, list)


# ---------------------------------------------------------------------------
# In-process coverage-focused tests
# ---------------------------------------------------------------------------


def test_cli_inproc_list_claude() -> None:
    """In-process: drives ``cli.main`` directly so coverage counts."""
    rc, out, err = _run_inproc(["list", "--agent", "claude"])
    assert rc == 0
    assert "UUID" in out


def test_cli_inproc_list_json() -> None:
    rc, out, err = _run_inproc(["list", "--agent", "claude", "--json"])
    assert rc == 0
    payload = json.loads(out)
    assert isinstance(payload, list)


def test_cli_inproc_read_existing() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    rc, out, err = _run_inproc(["read", "--agent", "claude", uuid])
    assert rc == 0
    assert uuid in out


def test_cli_inproc_read_json() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    rc, out, err = _run_inproc(["read", "--agent", "claude", "--json", uuid])
    assert rc == 0
    payload = json.loads(out)
    assert payload["uuid"] == uuid


def test_cli_inproc_read_invalid_uuid() -> None:
    rc, out, err = _run_inproc(["read", "--agent", "claude", "has spaces"])
    # Regex check fails -> ValueError -> exit 1.
    assert rc == 1


def test_cli_inproc_read_unknown_agent() -> None:
    """Argparse rejects unknown ``--agent`` choice -> exit 2."""
    rc, out, err = _run_inproc(["read", "--agent", "mystery", "some-uuid"])
    assert rc == 2


def test_cli_inproc_read_missing_uuid_arg() -> None:
    """No uuid -> argparse usage error."""
    rc, out, err = _run_inproc(["read", "--agent", "claude"])
    assert rc != 0


def test_cli_inproc_search_claude() -> None:
    rc, out, err = _run_inproc(["search", "claude"])
    assert rc == 0
    assert "UUID" in out or "no sessions match" in err.lower()


def test_cli_inproc_search_no_results() -> None:
    rc, out, err = _run_inproc(["search", "xyzzy-zzz-nothing-matches-12345"])
    assert rc == 0
    assert "no sessions match" in err.lower()


def test_cli_inproc_search_empty_query() -> None:
    rc, out, err = _run_inproc(["search", ""])
    assert rc == 1
    assert "search query" in err.lower()


def test_cli_inproc_search_json_no_results() -> None:
    rc, out, err = _run_inproc(["search", "xyzzy", "--json"])
    assert rc == 0
    payload = json.loads(out)
    assert payload == []


def test_cli_inproc_no_subcommand() -> None:
    """No subcommand -> parser prints help and returns 1."""
    rc, out, err = _run_inproc([])
    assert rc == 1
    assert "usage" in err.lower() or "usage" in out.lower()


def test_cli_inproc_build_parser() -> None:
    """The parser factory is exercised by every test above, but we
    add an explicit check that the ``list`` and ``search`` subcommand
    paths handle unknown agents cleanly.
    """
    parser = cli_module.build_parser()
    for cmd in ("list", "search"):
        with pytest.raises(SystemExit):
            parser.parse_args([cmd, "--agent", "mystery"])


# ---------------------------------------------------------------------------
# Result-limiting / date flags (--limit, --days, --from-date, --to-date, --all)
# ---------------------------------------------------------------------------


def _make_claude_session(
    home: Path, session_id: str, when: str, title: str = "session"
) -> str:
    """Write a minimal Claude session JSONL into ``home`` and return its uuid."""
    import json as _json

    jsonl = home / ".claude" / "projects" / "proj-x" / f"{session_id}.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "type": "user",
        "message": {"role": "user", "content": title},
        "timestamp": when,
        "sessionId": session_id,
    }
    with jsonl.open("w", encoding="utf-8") as fh:
        fh.write(_json.dumps(record, ensure_ascii=False))
        fh.write("\n")
    return session_id


def test_cli_list_limit_truncates(
    tmp_sessions_dir: Path,
) -> None:
    """``--limit N`` truncates the table to at most N rows."""
    for n in range(5):
        _make_claude_session(
            tmp_sessions_dir,
            f"lim-{n}",
            "2026-06-14T10:00:00Z",
            title=f"row {n}",
        )
    rc, out, err = _run_inproc(
        ["list", "--agent", "claude", "--limit", "2", "--json"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    payload = json.loads(out)
    assert len(payload) == 2


def test_cli_list_days_filter(
    tmp_sessions_dir: Path,
) -> None:
    """``--days`` keeps only recent sessions (vs datetime.now())."""
    now = datetime.now()
    recent_iso = now.strftime("%Y-%m-%dT10:00:00Z")
    old = now - timedelta(days=30)
    old_iso = old.strftime("%Y-%m-%dT10:00:00Z")
    _make_claude_session(tmp_sessions_dir, "recent-1", recent_iso, title="recent")
    _make_claude_session(tmp_sessions_dir, "old-1", old_iso, title="old")
    rc, out, err = _run_inproc(
        ["list", "--agent", "claude", "--days", "7", "--json"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    payload = json.loads(out)
    uuids = [item["uuid"] for item in payload]
    assert "recent-1" in uuids
    assert "old-1" not in uuids


def test_cli_list_from_to_date_filter(
    tmp_sessions_dir: Path,
) -> None:
    """``--from-date``/``--to-date`` keep sessions within the window."""
    _make_claude_session(
        tmp_sessions_dir, "before-1", "2026-05-01T10:00:00Z", title="before"
    )
    _make_claude_session(
        tmp_sessions_dir, "inside-1", "2026-06-14T10:00:00Z", title="inside"
    )
    _make_claude_session(
        tmp_sessions_dir, "after-1", "2026-07-01T10:00:00Z", title="after"
    )
    rc, out, err = _run_inproc(
        [
            "list",
            "--agent",
            "claude",
            "--from-date",
            "2026-06-01",
            "--to-date",
            "2026-06-30",
            "--json",
        ],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    payload = json.loads(out)
    uuids = [item["uuid"] for item in payload]
    assert "inside-1" in uuids
    assert "before-1" not in uuids
    assert "after-1" not in uuids


def test_cli_list_bad_date_exits_1(
    tmp_sessions_dir: Path,
) -> None:
    """Invalid ``--from-date`` -> exit 1 with a stderr message."""
    rc, out, err = _run_inproc(
        ["list", "--agent", "claude", "--from-date", "not-a-date"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 1
    assert "invalid --from-date" in err.lower()


def test_cli_list_all_flag_accepted(
    tmp_sessions_dir: Path,
) -> None:
    """``--all`` is accepted and behaves as a no-op."""
    _make_claude_session(
        tmp_sessions_dir, "all-1", "2026-06-14T10:00:00Z", title="all"
    )
    rc, out, err = _run_inproc(
        ["list", "--agent", "claude", "--all", "--json"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    payload = json.loads(out)
    assert len(payload) == 1


def test_cli_search_limit_and_days(
    tmp_sessions_dir: Path,
) -> None:
    """``--limit``/``--days`` apply to search results too."""
    now = datetime.now()
    for n in range(3):
        iso = now.strftime("%Y-%m-%dT10:00:00Z")
        _make_claude_session(
            tmp_sessions_dir, f"src-{n}", iso, title="searchme"
        )
    rc, out, err = _run_inproc(
        ["search", "searchme", "--agent", "claude", "--limit", "1", "--json"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    assert len(json.loads(out)) == 1


# ---------------------------------------------------------------------------
# read --messages
# ---------------------------------------------------------------------------


def test_cli_read_messages_human(
    fake_claude_session_with_tools: Path,
    tmp_sessions_dir: Path,
) -> None:
    """``read --messages`` dumps message text + tool_use names."""
    uuid = fake_claude_session_with_tools.stem
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude", uuid, "--messages"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    assert uuid in out
    assert "[tool_use: Bash]" in out
    assert "Run the tests" in out


def test_cli_read_messages_json(
    fake_claude_session_with_tools: Path,
    tmp_sessions_dir: Path,
) -> None:
    """``read --json --messages`` embeds a ``messages`` list with tool names."""
    uuid = fake_claude_session_with_tools.stem
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude", uuid, "--messages", "--json"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 0, err
    payload = json.loads(out)
    assert payload["uuid"] == uuid
    msgs = payload["messages"]
    assert isinstance(msgs, list)
    assert any("Bash" in (m["tool_use"]) for m in msgs)


def test_cli_read_messages_missing_session(
    tmp_sessions_dir: Path,
) -> None:
    """``read --messages`` on a missing uuid still exits 3 (metadata path)."""
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude", "no-such-session", "--messages"],
        env={"AI_READER_HOME": str(tmp_sessions_dir)},
    )
    assert rc == 3
    assert "not found" in err.lower()
