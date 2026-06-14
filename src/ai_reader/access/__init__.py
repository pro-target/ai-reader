"""Access control: subagent detection and permission guard.

Modules:
    detector:   SubagentDetector — env-var + /proc-based detection
    guard:      AccessGuard — orchestrator over parsers and detector
    models:     Data models (Session, Agent, AccessRequest, AccessResult)
"""
