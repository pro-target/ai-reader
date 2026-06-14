# Architecture

`ai-reader` is a 3-layer package. Each layer has exactly one
responsibility and depends only on the layer below it.

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: Public API                                          │
│   • ai-reader CLI  (src/ai_reader/cli.py)                    │
│   • ai-reader-mcp  (src/ai_reader/mcp_server.py)             │
│   • Python SDK     (importable: ai_reader.access,           │
│                     ai_reader.parsers)                       │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 2: Core parsers                                        │
│   src/ai_reader/parsers/                                     │
│   • claude.py     — JSONL                                    │
│   • codex.py      — JSONL                                    │
│   • opencode.py   — SQLite (with snap/flatpak detection)     │
│   • antigravity.py — brain directory                         │
│                                                              │
│   Shared schema: Session, AgentName                          │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 3: Access control                                      │
│   src/ai_reader/access/                                      │
│   • detector.py — EnvDetector, CompositeDetector,            │
│                   SubagentDetector Protocol                  │
│   • proc.py     — ProcDetector (Linux /proc)                 │
│   • guard.py    — AccessGuard orchestrator                   │
│   • models.py   — AccessRequest, AccessResult, AccessReason  │
└──────────────────────────────────────────────────────────────┘
```

## Layer 1 — Public API

Three entry points, all guarded:

### `ai-reader` (CLI)
Thin wrapper over the same primitives. Exits with distinct codes:
- `0` — success
- `1` — usage / argument error
- `2` — `PermissionError` (parent tried to read)
- `3` — `FileNotFoundError` (session missing)

### `ai-reader-mcp` (MCP server)
Stdio JSON-RPC. Three tools: `list_sessions`, `read_session`,
`search_sessions`. All run the guard first; on denial they return
`{"error": "permission_denied", ...}` (MCP prefers structured errors
to raised exceptions).

### Python SDK
`ai_reader.access.AccessGuard` and `ai_reader.parsers.*` are
importable. See [README.md](../README.md#usage) for the canonical
example.

## Layer 2 — Parsers

Every parser exports the same four functions:

```python
def list_sessions(base_dir: str | None = None) -> list[Session]: ...
def read_session(uuid: str, base_dir: str | None = None) -> Session: ...
def search(query: str, base_dir: str | None = None) -> list[Session]: ...
def session_exists(uuid: str, base_dir: str | None = None) -> bool: ...
```

`base_dir` is the testing hook — when omitted, parsers honour
`$AI_READER_HOME` (treated as the user's `$HOME`) and fall back to
`~`. **This is the only side-effecting test seam**; do not add
others.

Path resolution per agent:

| Agent | Source of truth |
|---|---|
| Claude | `~/.claude/projects/<slug>/<uuid>.jsonl` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-<uuid>.jsonl` |
| OpenCode | `~/.local/share/opencode/opencode.db` (or snap variants) |
| Antigravity | `~/.gemini/antigravity/brain/<uuid>/` |

The `Session` model is shared; see
[`src/ai_reader/parsers/models.py`](../src/ai_reader/parsers/models.py).

## Layer 3 — Access control

### Why hybrid env + proc?

Each mechanism has a failure mode:

| Detector | Catches | Misses |
|---|---|---|
| `EnvDetector` | Runners that set well-known vars (Claude, Codex, OpenCode, Gemini) | Bare `python` shells, custom CLIs, forked runtimes that strip the env |
| `ProcDetector` | Anything whose parent cmdline contains `subagent`, `task`, `worker`, … | macOS/Windows (no `/proc`); binaries whose argv is empty |

Composite OR-semantics: if **either** says subagent, the request is
allowed. This errs on the side of *more permissive* (a false positive
— denying a real subagent — is worse than a false negative — letting
a parent through — for our use case, because parents still must
opt-in to using MCP at all).

### Detector protocol

```python
class SubagentDetector(Protocol):
    def is_subagent(self) -> bool: ...
    def name(self) -> str: ...
```

That is the **only** contract the guard depends on. Custom detectors
— HMAC tokens, allowlists, capability URLs — slot in via
`AccessGuard(detector=...)`. See
[docs/access-control.md](./access-control.md).

### Guard API

```python
result: AccessResult = guard.check(AccessRequest(
    session_uuid=..., agent=AgentName.CLAUDE, operation="read",
))
# result.allowed: bool
# result.reason: AccessReason.SUBAGENT_DETECTED | PARENT_DENIED | ...
# result.detector_used: "env" | "proc" | "composite[env,proc]" | custom
# result.message: Optional[str]

# or, raise-on-deny:
guard.require(request)            # raises PermissionError
session = guard.read_session(uuid, AgentName.CLAUDE)  # dispatches to parser
```

`check()` returns an `AccessResult`; `require()` is the same logic
with `PermissionError` on `allowed=False`. Both validate the
`AccessRequest` structurally first (non-empty `session_uuid`,
`AgentName` instance, `operation in {"read","search","list"}`).

## Security model and known limits

| Surface | Protected by | Bypass risk |
|---|---|---|
| MCP `read_session` | `AccessGuard` | None — guarded |
| `Read` of `~/.claude/...` | Nothing (Level 2 trade-off) | A parent that doesn't use MCP can still read |
| `Bash cat ~/.codex/...` | Nothing | Same as above |
| Network exfil of session data | Nothing | Subagent reads; you trust the subagent |

The trade-off is **opt-in**: parents that wish to enforce the rule
must not give themselves (or their sub-agents) raw `Read`/`Bash`
on the session directories. The guard is a chokepoint, not a fence.

Levels 3 and 4 (hook + filesystem ACL) are tracked but unimplemented
in 0.1.0. See [CONTEXT.md](../CONTEXT.md#implementation-levels).
