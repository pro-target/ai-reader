"""Custom SubagentDetector examples.

Each example below is a self-contained class that satisfies the
``SubagentDetector`` Protocol (see ai_reader.access.detector).

Wire any of them into AccessGuard like so::

    from ai_reader.access import AccessGuard, CompositeDetector, EnvDetector, ProcDetector
    guard = AccessGuard(detector=CompositeDetector([
        EnvDetector(),
        ProcDetector(),
        HmacTokenDetector("/etc/ai-reader.key"),
    ]))

Run this file directly to exercise the detectors against a few
test inputs (no I/O, no network, no fixtures on disk required)::

    $ python examples/custom_detector.py
    HmacTokenDetector: name=hmac-token is_subagent=False (no token set)
    AllowlistDetector(['dmitrii', 'agent-bot']): name=allowlist is_subagent=False
"""
from __future__ import annotations

import hmac
import hashlib
import os
import pwd
from typing import Iterable


# ---------------------------------------------------------------------------
# Example 1: HMAC-token detector (v2 feature preview)
# ---------------------------------------------------------------------------
class HmacTokenDetector:
    """Allow access only when ``$AI_READER_TOKEN`` matches an HMAC.

    The shared secret lives in a key file (default ``/etc/ai-reader.key``).
    The expected token is ``HMAC-SHA256(secret, b"ai-reader-v1")`` formatted
    as a hex string. The caller sets ``AI_READER_TOKEN`` in its environment
    (typically injected by the parent's spawn routine). Comparison is
    constant-time.
    """

    def __init__(self, key_path: str = "/etc/ai-reader.key") -> None:
        self._key_path = key_path

    def is_subagent(self) -> bool:
        secret = self._load_key()
        if secret is None:
            return False
        expected = hmac.new(secret, b"ai-reader-v1", hashlib.sha256).hexdigest()
        presented = os.environ.get("AI_READER_TOKEN", "")
        return hmac.compare_digest(presented, expected)

    def name(self) -> str:
        return "hmac-token"

    def _load_key(self) -> bytes | None:
        try:
            with open(self._key_path, "rb") as fh:
                return fh.read().strip()
        except OSError:
            return None


# ---------------------------------------------------------------------------
# Example 2: per-user allowlist detector
# ---------------------------------------------------------------------------
class AllowlistDetector:
    """Allow access only when the caller's Unix user is in the allowlist.

    Uses ``pwd.getpwuid(os.getuid()).pw_name`` — works on POSIX systems
    (Linux, macOS). On Windows the detector always returns ``False``.
    """

    def __init__(self, allowed_users: Iterable[str]) -> None:
        self._allowed: frozenset[str] = frozenset(allowed_users)

    def is_subagent(self) -> bool:
        try:
            me = pwd.getpwuid(os.getuid()).pw_name
        except (KeyError, OSError):
            return False
        return me in self._allowed

    def name(self) -> str:
        return f"allowlist[{','.join(sorted(self._allowed))}]"


# ---------------------------------------------------------------------------
# Demo: exercise the detectors without touching the filesystem.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    h = HmacTokenDetector(key_path="/nonexistent")
    print(f"HmacTokenDetector: name={h.name()!r} is_subagent={h.is_subagent()} (no token set)")

    a = AllowlistDetector(["dmitrii", "agent-bot"])
    print(
        f"AllowlistDetector(['dmitrii', 'agent-bot']): "
        f"name={a.name()!r} is_subagent={a.is_subagent()}"
    )
