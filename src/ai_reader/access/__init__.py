"""Access control: subagent detection and permission guard.

Modules:
    detector:   SubagentDetector — env-var + /proc-based detection
    guard:      AccessGuard — orchestrator over parsers and detector
    models:     Data models (Session, Agent, AccessRequest, AccessResult)
"""

from .detector import CompositeDetector, EnvDetector, SubagentDetector
from .guard import AccessGuard
from .models import AccessReason, AccessRequest, AccessResult, VALID_OPERATIONS
from .proc import ProcDetector

__all__ = [
    "AccessGuard",
    "AccessReason",
    "AccessRequest",
    "AccessResult",
    "CompositeDetector",
    "EnvDetector",
    "ProcDetector",
    "SubagentDetector",
    "VALID_OPERATIONS",
]
