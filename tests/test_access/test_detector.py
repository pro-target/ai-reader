"""Tests for the env-var subagent detector and the composite detector."""
from __future__ import annotations

import pytest

from ai_reader.access.detector import CompositeDetector, EnvDetector


# ---------------------------------------------------------------------------
# EnvDetector
# ---------------------------------------------------------------------------


def test_env_detector_with_claude_marker() -> None:
    d = EnvDetector(env={"CLAUDE_CODE_SUBAGENT": "1"})
    assert d.is_subagent() is True
    assert d.name() == "env"


def test_env_detector_without_marker() -> None:
    d = EnvDetector(env={})
    assert d.is_subagent() is False


def test_env_detector_with_claude_fork_unrecognised() -> None:
    """``CLAUDE_CODE_FORK_SUBAGENT`` is not in the detector's allowlist
    (only ``CLAUDE_CODE_SUBAGENT`` and ``GEMINI_SUBAGENT`` are).  This
    test documents the current behaviour so any future change is
    caught by the suite.
    """
    d = EnvDetector(env={"CLAUDE_CODE_FORK_SUBAGENT": "1"})
    assert d.is_subagent() is False


def test_env_detector_with_gemini_marker() -> None:
    assert EnvDetector(env={"GEMINI_SUBAGENT": "true"}).is_subagent() is True
    assert EnvDetector(env={"GEMINI_SUBAGENT": "on"}).is_subagent() is True
    assert EnvDetector(env={"GEMINI_SUBAGENT": "YES"}).is_subagent() is True
    assert EnvDetector(env={"GEMINI_SUBAGENT": "0"}).is_subagent() is False


def test_env_detector_with_codex_marker() -> None:
    """Codex uses non-empty semantics — any value trips the detector."""
    assert EnvDetector(env={"CODEX_SUBAGENT_TASK_ID": "task-1"}).is_subagent() is True
    # Whitespace-only does *not* count.
    assert EnvDetector(env={"CODEX_SUBAGENT_TASK_ID": "   "}).is_subagent() is False
    assert EnvDetector(env={"CODEX_SUBAGENT_TASK_ID": ""}).is_subagent() is False


def test_env_detector_with_opencode_marker() -> None:
    assert EnvDetector(env={"OPENCODE_PARENT_ID": "p1"}).is_subagent() is True
    assert EnvDetector(env={"OPENCODE_PARENT_ID": ""}).is_subagent() is False


def test_env_detector_truthy_variants() -> None:
    """Recognised truthy spellings: 1, true, yes, on (case-insensitive)."""
    for v in ("1", "true", "TRUE", "yes", "YES", "on", "On"):
        assert EnvDetector(env={"CLAUDE_CODE_SUBAGENT": v}).is_subagent() is True
    for v in ("0", "false", "no", "off", "garbage"):
        assert EnvDetector(env={"CLAUDE_CODE_SUBAGENT": v}).is_subagent() is False


def test_env_detector_combines_multiple_markers() -> None:
    d = EnvDetector(
        env={
            "CLAUDE_CODE_SUBAGENT": "0",  # falsy
            "CODEX_SUBAGENT_TASK_ID": "abc",  # non-empty -> True
        }
    )
    assert d.is_subagent() is True


def test_env_detector_defaults_to_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT", "1")
    d = EnvDetector()  # no explicit env -> uses os.environ
    assert d.is_subagent() is True


# ---------------------------------------------------------------------------
# CompositeDetector
# ---------------------------------------------------------------------------


def test_composite_detector_any_true() -> None:
    env = EnvDetector(env={"CLAUDE_CODE_SUBAGENT": "0"})  # False
    sentinel_true = _AlwaysTrue()
    sentinel_false = _AlwaysFalse()
    composite = CompositeDetector([env, sentinel_false, sentinel_true])
    assert composite.is_subagent() is True


def test_composite_detector_all_false() -> None:
    composite = CompositeDetector([_AlwaysFalse(), _AlwaysFalse()])
    assert composite.is_subagent() is False


def test_composite_detector_empty_returns_false() -> None:
    assert CompositeDetector([]).is_subagent() is False


def test_composite_detector_name() -> None:
    composite = CompositeDetector(
        [EnvDetector(env={}), _AlwaysFalse()]
    )
    assert composite.name() == "composite[env,_stub]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AlwaysTrue:
    def is_subagent(self) -> bool:
        return True

    def name(self) -> str:
        return "_stub"


class _AlwaysFalse:
    def is_subagent(self) -> bool:
        return False

    def name(self) -> str:
        return "_stub"
