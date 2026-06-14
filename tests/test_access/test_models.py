"""Tests for the access-control data models."""
from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from ai_reader.access.models import (
    VALID_OPERATIONS,
    AccessReason,
    AccessRequest,
    AccessResult,
)
from ai_reader.parsers import AgentName


def test_valid_operations_constant() -> None:
    """The constant is the single source of truth for allowed ops."""
    assert VALID_OPERATIONS == frozenset({"read", "search", "list"})
    # The set is immutable.
    with pytest.raises(AttributeError):
        VALID_OPERATIONS.add("delete")  # type: ignore[attr-defined]


def test_access_request_construction() -> None:
    req = AccessRequest(
        session_uuid="abc-123",
        agent=AgentName.CLAUDE,
        operation="read",
        caller_pid=9999,
    )
    assert req.session_uuid == "abc-123"
    assert req.agent is AgentName.CLAUDE
    assert req.operation == "read"
    assert req.caller_pid == 9999


def test_access_request_default_caller_pid() -> None:
    req = AccessRequest(
        session_uuid="x", agent=AgentName.CODEX, operation="list"
    )
    assert req.caller_pid is None


def test_access_request_is_frozen() -> None:
    req = AccessRequest(
        session_uuid="x", agent=AgentName.CLAUDE, operation="read"
    )
    with pytest.raises(FrozenInstanceError):
        req.session_uuid = "y"  # type: ignore[misc]


def test_access_result_allowed_true() -> None:
    r = AccessResult(
        allowed=True,
        reason=AccessReason.SUBAGENT_DETECTED,
        detector_used="env",
        message="caller recognised",
    )
    assert r.allowed is True
    assert r.reason is AccessReason.SUBAGENT_DETECTED
    assert r.detector_used == "env"
    assert r.message == "caller recognised"


def test_access_result_allowed_false() -> None:
    r = AccessResult(
        allowed=False,
        reason=AccessReason.PARENT_DENIED,
        detector_used="composite[env,proc]",
    )
    assert r.allowed is False
    assert r.reason is AccessReason.PARENT_DENIED
    assert r.message is None  # default


def test_access_result_is_frozen() -> None:
    r = AccessResult(
        allowed=True,
        reason=AccessReason.SUBAGENT_DETECTED,
        detector_used="env",
    )
    with pytest.raises(FrozenInstanceError):
        r.allowed = False  # type: ignore[misc]


def test_access_reason_values_are_stable_strings() -> None:
    """Reason codes are persisted / logged; their string form is part
    of the public contract.
    """
    assert AccessReason.SUBAGENT_DETECTED.value == "subagent_detected"
    assert AccessReason.PARENT_DENIED.value == "parent_denied"
    assert AccessReason.INVALID_REQUEST.value == "invalid_request"
    assert AccessReason.UNKNOWN_CALLER.value == "unknown_caller"


def test_access_reason_is_str_enum() -> None:
    assert isinstance(AccessReason.SUBAGENT_DETECTED, str)
    assert AccessReason.SUBAGENT_DETECTED == "subagent_detected"
