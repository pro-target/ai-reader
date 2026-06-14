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


_ENV_KEYS = (
    "CLAUDE_CODE_SUBAGENT",
    "CODEX_SUBAGENT_TASK_ID",
    "OPENCODE_PARENT_ID",
    "GEMINI_SUBAGENT",
    "AI_READER_HOME",
    "OPENCODE_DB",
)


# ---------------------------------------------------------------------------
# Version / help
# ---------------------------------------------------------------------------


def test_cli_version() -> None:
    p = _run_cli("--version")
    assert p.returncode == 0, p.stderr
    assert "ai-reader" in p.stdout
    assert "0.1.0" in p.stdout


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


def test_cli_list_subagent() -> None:
    p = _run_cli(
        "list",
        "--agent", "claude",
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode == 0, p.stderr
    assert "UUID" in p.stdout
    assert "AGENT" in p.stdout


def test_cli_list_json() -> None:
    p = _run_cli(
        "list",
        "--agent", "claude",
        "--json",
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
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


def test_cli_read_subagent_existing() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    p = _run_cli(
        "read",
        "--agent", "claude",
        uuid,
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode == 0, p.stderr
    assert uuid in p.stdout
    assert "UUID:" in p.stdout


def test_cli_read_subagent_json() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    p = _run_cli(
        "read",
        "--agent", "claude",
        "--json",
        uuid,
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["uuid"] == uuid
    assert payload["agent"] == "CLAUDE"


def test_cli_read_parent_denied() -> None:
    """No subagent env -> guard refuses -> exit 2."""
    uuid = _first_claude_uuid() or "fake-uuid"
    p = _run_cli("read", "--agent", "claude", uuid)
    assert p.returncode == 2, p.stderr
    assert "permission denied" in p.stderr.lower()


def test_cli_read_invalid_uuid_format() -> None:
    """A uuid that fails the regex (e.g. contains whitespace) -> non-zero."""
    p = _run_cli(
        "read",
        "--agent", "claude",
        "has spaces",
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode != 0


def test_cli_read_unknown_agent() -> None:
    p = _run_cli(
        "read",
        "--agent", "mystery",
        "some-uuid",
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode != 0


def test_cli_read_missing_uuid() -> None:
    p = _run_cli("read", "--agent", "claude", env={"CLAUDE_CODE_SUBAGENT": "1"})
    assert p.returncode != 0


def test_cli_read_not_found() -> None:
    """Valid uuid format but no such session -> exit 3 (not found)."""
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude", "definitely-not-here"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 3
    assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_cli_search_subagent() -> None:
    p = _run_cli(
        "search",
        "claude",
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode == 0, p.stderr
    assert "UUID" in p.stdout or "(no sessions match" in p.stderr


def test_cli_search_no_results() -> None:
    p = _run_cli(
        "search",
        "this-string-should-match-nothing-xyzzy123",
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode == 0, p.stderr
    assert "no sessions match" in p.stderr.lower()


def test_cli_search_empty_query_rejected() -> None:
    p = _run_cli("search", "", env={"CLAUDE_CODE_SUBAGENT": "1"})
    assert p.returncode != 0
    assert "search query" in p.stderr.lower()


def test_cli_search_json() -> None:
    p = _run_cli(
        "search",
        "claude",
        "--json",
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert isinstance(payload, list)


# ---------------------------------------------------------------------------
# In-process coverage-focused tests
# ---------------------------------------------------------------------------


def test_cli_inproc_list_subagent() -> None:
    """In-process: drives ``cli.main`` directly so coverage counts."""
    rc, out, err = _run_inproc(
        ["list", "--agent", "claude"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 0
    assert "UUID" in out


def test_cli_inproc_list_json() -> None:
    rc, out, err = _run_inproc(
        ["list", "--agent", "claude", "--json"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 0
    payload = json.loads(out)
    assert isinstance(payload, list)


def test_cli_inproc_read_parent_denied() -> None:
    rc, out, err = _run_inproc(["read", "--agent", "claude", "any-uuid"])
    assert rc == 2
    assert "permission denied" in err.lower()


def test_cli_inproc_read_subagent_existing() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude", uuid],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 0
    assert uuid in out


def test_cli_inproc_read_subagent_json() -> None:
    uuid = _first_claude_uuid()
    if uuid is None:
        pytest.skip("no real Claude session on this host")
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude", "--json", uuid],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 0
    payload = json.loads(out)
    assert payload["uuid"] == uuid


def test_cli_inproc_read_invalid_uuid() -> None:
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude", "has spaces"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    # Regex check fails -> ValueError -> exit 1.
    assert rc == 1


def test_cli_inproc_read_unknown_agent() -> None:
    """Argparse rejects unknown ``--agent`` choice -> exit 2."""
    rc, out, err = _run_inproc(
        ["read", "--agent", "mystery", "some-uuid"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 2


def test_cli_inproc_read_missing_uuid_arg() -> None:
    """No uuid -> argparse usage error."""
    rc, out, err = _run_inproc(
        ["read", "--agent", "claude"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc != 0


def test_cli_inproc_search_subagent() -> None:
    rc, out, err = _run_inproc(
        ["search", "claude"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 0
    assert "UUID" in out or "no sessions match" in err.lower()


def test_cli_inproc_search_no_results() -> None:
    rc, out, err = _run_inproc(
        ["search", "xyzzy-zzz-nothing-matches-12345"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 0
    assert "no sessions match" in err.lower()


def test_cli_inproc_search_empty_query() -> None:
    rc, out, err = _run_inproc(
        ["search", ""],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
    assert rc == 1
    assert "search query" in err.lower()


def test_cli_inproc_search_json_no_results() -> None:
    rc, out, err = _run_inproc(
        ["search", "xyzzy", "--json"],
        env={"CLAUDE_CODE_SUBAGENT": "1"},
    )
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
