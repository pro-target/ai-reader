# Custom detectors

The `AccessGuard` is pluggable. Replace the default composite
detector with anything that implements the `SubagentDetector`
Protocol to enforce a different access policy.

## The Protocol

```python
class SubagentDetector(Protocol):
    def is_subagent(self) -> bool:
        """Return True iff the current process is allowed access."""
        ...

    def name(self) -> str:
        """Short identifier, used in AccessResult.detector_used and logs."""
        ...
```

That's the **entire** contract. The guard never inspects the
detector class itself.

## Wiring a custom detector

```python
from ai_reader.access import AccessGuard, AccessRequest
from ai_reader.parsers import AgentName

guard = AccessGuard(detector=MyCustomDetector())

result = guard.check(AccessRequest(
    session_uuid="...",
    agent=AgentName.CLAUDE,
    operation="read",
))
```

You can also plug a custom detector into the composite:

```python
from ai_reader.access import (
    AccessGuard, CompositeDetector, EnvDetector, ProcDetector,
)
from ai_reader.access.detector import SubagentDetector

class HmacTokenDetector:
    def is_subagent(self) -> bool:
        import hmac, hashlib, os
        token = os.environ.get("AI_READER_TOKEN", "")
        secret = open("/etc/ai-reader.key", "rb").read()
        expected = hmac.new(secret, b"ai-reader-v1", hashlib.sha256).hexdigest()
        return hmac.compare_digest(token, expected)

    def name(self) -> str:
        return "hmac-token"

guard = AccessGuard(detector=CompositeDetector([
    EnvDetector(),
    ProcDetector(),
    HmacTokenDetector(),
]))
```

See [`examples/custom_detector.py`](../examples/custom_detector.py)
for two runnable patterns: an HMAC-token detector and a per-user
allowlist.

## Testability

`EnvDetector.__init__` accepts a `Mapping[str, str]` and
`ProcDetector.__init__` accepts a `proc_root: str`. This is by
design — **do not monkey-patch**; pass fixtures:

```python
def test_env_detector():
    d = EnvDetector(env={"CLAUDE_CODE_SUBAGENT": "1"})
    assert d.is_subagent()

def test_proc_detector(tmp_path):
    # tmp_path contains a fake /proc/self/status and /proc/<ppid>/cmdline
    d = ProcDetector(proc_root=str(tmp_path))
    assert d.is_subagent()
```

Custom detectors should follow the same pattern: take their inputs
in `__init__`, not at call time. This makes the guard tree fully
deterministic and unit-testable.

## Combining detectors

`CompositeDetector` is OR-semantics (subagent = any). If you need
AND-semantics, write a small `AllDetector` wrapper:

```python
class AllDetector:
    def __init__(self, *detectors: SubagentDetector) -> None:
        self._detectors = detectors

    def is_subagent(self) -> bool:
        return all(d.is_subagent() for d in self._detectors)

    def name(self) -> str:
        return "all[" + ",".join(d.name() for d in self._detectors) + "]"
```

## Policy patterns

| Policy | Mechanism |
|---|---|
| Allow only HMAC-token callers | `HmacTokenDetector` (example) |
| Allow only specific parent PIDs | Custom `ProcDetector` variant reading `/proc/<ppid>/status` |
| Allow during business hours | Time-window detector reading `datetime.now()` |
| Allow only on certain hosts | Hostname detector reading `socket.gethostname()` |
| Allow per-user (caller's `$USER` must be in allowlist) | `AllowlistDetector` (example) |
| Deny on holiday (paranoid mode) | Calendar-based deny-list |

The guard returns `AccessResult` with `reason`, `detector_used`,
and `message`. Log these for an audit trail. **Do not** log
session contents — that would defeat the whole point.

## Things to avoid

- **Stateful detectors that read the filesystem on every call.**
  Cache the answer if you must, but the guard is invoked once per
  MCP call — the cost is fine, but keep it bounded.
- **Detectors that block for I/O.** The guard is on the hot path
  for every read. Network calls are an anti-pattern.
- **Detectors that can throw.** Catch and return `False`. A
  misbehaving detector should fail closed (deny), not crash the
  caller.
- **Time-of-check / time-of-use gaps.** If your detector reads
  state that can change between `check()` and the actual parser
  dispatch, the answer may be stale. For 0.1.x, the gap is
  microseconds and the trade-off is acceptable.
