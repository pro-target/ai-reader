"""Access guard — orchestrates detection and dispatches to parsers.

:func:`check` / :func:`require` answer "may the current process
touch this session?".  :func:`read_session` is the convenience
method used by the MCP server: it runs the access check and then
calls the right parser.
"""

from __future__ import annotations

from types import ModuleType
from typing import Mapping

from ai_reader.parsers import AgentName, Session
from ai_reader.parsers import antigravity, claude, codex, opencode

from .detector import CompositeDetector, EnvDetector, SubagentDetector
from .models import VALID_OPERATIONS, AccessReason, AccessRequest, AccessResult
from .proc import ProcDetector

__all__ = ["AccessGuard"]


_PARSERS: Mapping[AgentName, ModuleType] = {
    AgentName.CLAUDE: claude,
    AgentName.CODEX: codex,
    AgentName.OPENCODE: opencode,
    AgentName.ANTIGRAVITY: antigravity,
}


def _default_detector() -> SubagentDetector:
    return CompositeDetector([EnvDetector(), ProcDetector()])


class AccessGuard:
    """Orchestrates subagent detection and parser dispatch."""

    def __init__(self, detector: SubagentDetector | None = None) -> None:
        self._detector: SubagentDetector = detector or _default_detector()

    def check(self, request: AccessRequest) -> AccessResult:
        """Decide whether the current process may perform ``request``.

        Returns an :class:`AccessResult` with ``allowed=True`` only
        when the configured detector recognises the caller as a
        sub-agent.  Raises :class:`ValueError` for structurally
        invalid requests.
        """
        if not isinstance(request, AccessRequest):
            raise ValueError(
                f"request must be an AccessRequest, got {type(request).__name__}"
            )
        if not request.session_uuid or not request.session_uuid.strip():
            raise ValueError("session_uuid must be a non-empty string")
        if not isinstance(request.agent, AgentName):
            raise ValueError(
                f"agent must be an AgentName, got {type(request.agent).__name__}"
            )
        if request.operation not in VALID_OPERATIONS:
            raise ValueError(
                f"operation must be one of {sorted(VALID_OPERATIONS)}, "
                f"got {request.operation!r}"
            )

        detector_name = self._detector.name()
        if self._detector.is_subagent():
            return AccessResult(
                allowed=True,
                reason=AccessReason.SUBAGENT_DETECTED,
                detector_used=detector_name,
                message="caller recognised as sub-agent",
            )
        return AccessResult(
            allowed=False,
            reason=AccessReason.PARENT_DENIED,
            detector_used=detector_name,
            message="caller is not a recognised sub-agent",
        )

    def require(self, request: AccessRequest) -> AccessResult:
        """Same as :meth:`check` but raises :class:`PermissionError` on deny.

        Returns the :class:`AccessResult` when access is allowed so
        callers can inspect ``detector_used`` and ``reason`` for
        logging.
        """
        result = self.check(request)
        if not result.allowed:
            raise PermissionError(
                f"access denied for session {request.session_uuid!r} "
                f"(agent={request.agent.value!r}, op={request.operation!r}): "
                f"{result.reason.value}"
            )
        return result

    def read_session(self, uuid: str, agent: AgentName) -> Session:
        """Check access, then load the session via the right parser.

        Raises:
            PermissionError: the current process is not a sub-agent.
            FileNotFoundError: the session does not exist for ``agent``.
            ValueError: structurally invalid input.
        """
        request = AccessRequest(session_uuid=uuid, agent=agent, operation="read")
        self.require(request)
        parser = _PARSERS.get(agent)
        if parser is None:
            raise ValueError(f"no parser registered for agent {agent!r}")
        return parser.read_session(uuid)
