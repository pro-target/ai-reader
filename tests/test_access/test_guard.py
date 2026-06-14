"""Tests for the AccessGuard and its data models."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ai_reader.access import (
    AccessGuard,
    AccessReason,
    AccessRequest,
    AccessResult,
    VALID_OPERATIONS,
)
from ai_reader.access.detector import CompositeDetector, EnvDetector
from ai_reader.access.proc import ProcDetector
from ai_reader.parsers import AgentName, Session
from ai_reader.parsers import antigravity, claude, codex, opencode


# ---------------------------------------------------------------------------
# Custom detector stubs
# ---------------------------------------------------------------------------


class _AllowDetector:
    def is_subagent(self) -> bool:
        return True

    def name(self) -> str:
        return "allow-stub"


class _DenyDetector:
    def is_subagent(self) -> bool:
        return False

    def name(self) -> str:
        return "deny-stub"


# ---------------------------------------------------------------------------
# guard.require / guard.check
# ---------------------------------------------------------------------------


def test_guard_parent_denied(parent_env: None) -> None:
    g = AccessGuard(detector=_DenyDetector())
    request = AccessRequest(
        session_uuid="abc", agent=AgentName.CLAUDE, operation="read"
    )
    with pytest.raises(PermissionError) as excinfo:
        g.require(request)
    assert "abc" in str(excinfo.value)


def test_guard_parent_check_returns_disallowed(parent_env: None) -> None:
    g = AccessGuard(detector=_DenyDetector())
    request = AccessRequest(
        session_uuid="abc", agent=AgentName.CLAUDE, operation="read"
    )
    result = g.check(request)
    assert result.allowed is False
    assert result.reason is AccessReason.PARENT_DENIED
    assert result.detector_used == "deny-stub"


def test_guard_subagent_allowed(subagent_env: None) -> None:
    g = AccessGuard(detector=_AllowDetector())
    request = AccessRequest(
        session_uuid="abc", agent=AgentName.CLAUDE, operation="read"
    )
    result = g.require(request)
    assert result.allowed is True
    assert result.reason is AccessReason.SUBAGENT_DETECTED


def test_guard_subagent_uses_real_env_detector(subagent_env: None) -> None:
    g = AccessGuard(detector=EnvDetector())
    result = g.check(
        AccessRequest(
            session_uuid="abc", agent=AgentName.CLAUDE, operation="read"
        )
    )
    assert result.allowed is True
    assert result.detector_used == "env"


def test_guard_parent_uses_real_env_detector(parent_env: None) -> None:
    g = AccessGuard(detector=EnvDetector())
    result = g.check(
        AccessRequest(
            session_uuid="abc", agent=AgentName.CLAUDE, operation="read"
        )
    )
    assert result.allowed is False
    assert result.reason is AccessReason.PARENT_DENIED


def test_guard_default_detector_is_composite(parent_env: None) -> None:
    g = AccessGuard()  # default = composite[env,proc]
    result = g.check(
        AccessRequest(
            session_uuid="abc", agent=AgentName.CLAUDE, operation="read"
        )
    )
    assert "composite" in result.detector_used


# ---------------------------------------------------------------------------
# Validation paths
# ---------------------------------------------------------------------------


def test_guard_invalid_request_raises_value_error(parent_env: None) -> None:
    g = AccessGuard(detector=_AllowDetector())
    with pytest.raises(ValueError):
        g.check("not a request")  # type: ignore[arg-type]


def test_guard_empty_uuid_raises_value_error(subagent_env: None) -> None:
    g = AccessGuard(detector=_AllowDetector())
    with pytest.raises(ValueError, match="session_uuid"):
        g.check(
            AccessRequest(
                session_uuid="", agent=AgentName.CLAUDE, operation="read"
            )
        )
    with pytest.raises(ValueError, match="session_uuid"):
        g.check(
            AccessRequest(
                session_uuid="   ", agent=AgentName.CLAUDE, operation="read"
            )
        )


def test_guard_unknown_agent_raises_value_error(subagent_env: None) -> None:
    g = AccessGuard(detector=_AllowDetector())
    with pytest.raises(ValueError, match="agent"):
        g.check(
            AccessRequest(
                session_uuid="abc", agent="CLAUDE", operation="read"  # type: ignore[arg-type]
            )
        )


def test_guard_invalid_operation_raises_value_error(subagent_env: None) -> None:
    g = AccessGuard(detector=_AllowDetector())
    with pytest.raises(ValueError, match="operation"):
        g.check(
            AccessRequest(
                session_uuid="abc", agent=AgentName.CLAUDE, operation="delete"
            )
        )


def test_guard_all_operations_accepted(subagent_env: None) -> None:
    g = AccessGuard(detector=_AllowDetector())
    for op in VALID_OPERATIONS:
        result = g.check(
            AccessRequest(session_uuid="abc", agent=AgentName.CLAUDE, operation=op)
        )
        assert result.allowed is True


# ---------------------------------------------------------------------------
# guard.read_session
# ---------------------------------------------------------------------------


def test_guard_read_session_dispatches_to_claude(
    subagent_env: None, fake_claude_session: Path
) -> None:
    g = AccessGuard(detector=_AllowDetector())
    session = g.read_session("test-claude-1", AgentName.CLAUDE)
    assert isinstance(session, Session)
    assert session.agent is AgentName.CLAUDE
    assert session.uuid == "test-claude-1"


def test_guard_read_session_dispatches_to_codex(
    subagent_env: None, fake_codex_session: Path
) -> None:
    g = AccessGuard(detector=_AllowDetector())
    session = g.read_session("test-codex-1", AgentName.CODEX)
    assert session.uuid == "test-codex-1"


def test_guard_read_session_dispatches_to_opencode(
    subagent_env: None,
    fake_opencode_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard delegates to the parser; force the parser to consider
    the fake DB only so the assertion is hermetic.
    """
    monkeypatch.setattr(
        "ai_reader.parsers.opencode._resolve_db_paths",
        lambda base_dir=None, override=None: [str(fake_opencode_db)],
    )
    g = AccessGuard(detector=_AllowDetector())
    session = g.read_session("test-oc-1", AgentName.OPENCODE)
    assert session.uuid == "test-oc-1"


def test_guard_read_session_dispatches_to_antigravity(
    subagent_env: None, fake_antigravity_brain: Path
) -> None:
    g = AccessGuard(detector=_AllowDetector())
    session = g.read_session("test-ag-1", AgentName.ANTIGRAVITY)
    assert session.uuid == "test-ag-1"


def test_guard_read_session_permission_denied(parent_env: None) -> None:
    g = AccessGuard(detector=_DenyDetector())
    with pytest.raises(PermissionError):
        g.read_session("any", AgentName.CLAUDE)


def test_guard_read_session_missing_raises(
    subagent_env: None, tmp_sessions_dir: Path
) -> None:
    g = AccessGuard(detector=_AllowDetector())
    with pytest.raises(FileNotFoundError):
        g.read_session("absent", AgentName.CLAUDE)


def test_guard_read_session_value_error_for_empty_uuid(subagent_env: None) -> None:
    g = AccessGuard(detector=_AllowDetector())
    with pytest.raises(ValueError):
        g.read_session("", AgentName.CLAUDE)
