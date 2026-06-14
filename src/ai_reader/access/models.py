"""Data models for the access-control layer.

Defines the three value objects exchanged between callers and
:class:`ai_reader.access.guard.AccessGuard`:

* :class:`AccessRequest`  — what the caller wants to do.
* :class:`AccessResult`   — what the guard decided.
* :class:`AccessReason`   — taxonomy of decision codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ai_reader.parsers import AgentName

__all__ = [
    "AccessReason",
    "AccessRequest",
    "AccessResult",
    "VALID_OPERATIONS",
]


VALID_OPERATIONS: frozenset[str] = frozenset({"read", "search", "list"})


class AccessReason(str, Enum):
    """Decision codes returned in :class:`AccessResult.reason`."""

    SUBAGENT_DETECTED = "subagent_detected"
    PARENT_DENIED = "parent_denied"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN_CALLER = "unknown_caller"


@dataclass(frozen=True)
class AccessRequest:
    """A request to perform an operation on a session.

    Attributes:
        session_uuid: The session identifier the caller wants to act on.
        agent: Which agent owns the session.  Determines which parser
            is dispatched.
        operation: One of ``"read"``, ``"search"``, ``"list"``.
        caller_pid: Optional PID of the calling process.  When set,
            recorded for forensic / multi-process scenarios.  Not yet
            consumed by the bundled detectors, which always inspect
            the current process.
    """

    session_uuid: str
    agent: AgentName
    operation: str
    caller_pid: Optional[int] = None


@dataclass(frozen=True)
class AccessResult:
    """The guard's decision for an :class:`AccessRequest`.

    Attributes:
        allowed: ``True`` only when the caller is a recognized
            sub-agent.
        reason: Structured decision code.  Stable across releases and
            safe to log.
        detector_used: Name of the detector that produced the verdict
            (e.g. ``"env"``, ``"proc"``, ``"composite[env,proc]"``).
        message: Human-readable explanation.  Optional — may be
            ``None`` when the detector name is self-explanatory.
    """

    allowed: bool
    reason: AccessReason
    detector_used: str
    message: Optional[str] = None
