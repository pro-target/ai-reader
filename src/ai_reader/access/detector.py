"""Subagent detectors: Protocol, env-var detector, and composite.

A *detector* answers one question: "is the current process a
sub-agent?".  The Protocol below is the only thing the guard
depends on; concrete detectors live in this module
(:class:`EnvDetector`, :class:`CompositeDetector`) or in
:mod:`ai_reader.access.proc` (:class:`ProcDetector`).

All detectors are pure with respect to their inputs: the env-var
detector accepts a ``Mapping`` and the proc detector accepts a
``proc_root`` string, so unit tests can substitute fixtures
without monkey-patching.
"""

from __future__ import annotations

import os
from typing import Iterable, Mapping, Protocol

__all__ = [
    "CompositeDetector",
    "EnvDetector",
    "SubagentDetector",
]


class SubagentDetector(Protocol):
    """Detects whether the current process is a sub-agent."""

    def is_subagent(self) -> bool:
        """Return True if the current process is a sub-agent."""
        ...

    def name(self) -> str:
        """Return a short detector name for logging and debugging."""
        ...


_TRUTHY_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})

_TRUTHY_ENV_VARS: tuple[str, ...] = (
    "CLAUDE_CODE_SUBAGENT",
    "GEMINI_SUBAGENT",
)

_NONEMPTY_ENV_VARS: tuple[str, ...] = (
    "CODEX_SUBAGENT_TASK_ID",
    "OPENCODE_PARENT_ID",
)


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in _TRUTHY_VALUES


class EnvDetector:
    """Detects sub-agent status from well-known environment variables.

    Returns True if **any** of the following is set:

    * ``CLAUDE_CODE_SUBAGENT`` — truthy (``"1"``, ``"true"``,
      ``"yes"``, ``"on"``, case-insensitive).
    * ``CODEX_SUBAGENT_TASK_ID`` — non-empty.
    * ``OPENCODE_PARENT_ID`` — non-empty.
    * ``GEMINI_SUBAGENT`` — truthy.
    """

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env: Mapping[str, str] = env if env is not None else os.environ

    def is_subagent(self) -> bool:
        for var in _TRUTHY_ENV_VARS:
            value = self._env.get(var)
            if value is not None and _is_truthy(value):
                return True
        for var in _NONEMPTY_ENV_VARS:
            value = self._env.get(var)
            if value is not None and value.strip():
                return True
        return False

    def name(self) -> str:
        return "env"


class CompositeDetector:
    """Combines several detectors with OR-semantics.

    :meth:`is_subagent` returns True if *any* child detector
    reports sub-agent status.  Short-circuits on the first True.
    """

    def __init__(self, detectors: Iterable[SubagentDetector]) -> None:
        self._detectors: tuple[SubagentDetector, ...] = tuple(detectors)

    def is_subagent(self) -> bool:
        for detector in self._detectors:
            if detector.is_subagent():
                return True
        return False

    def name(self) -> str:
        return "composite[" + ",".join(d.name() for d in self._detectors) + "]"
