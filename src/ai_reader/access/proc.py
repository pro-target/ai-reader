"""``/proc``-based subagent detector (Linux-only).

Inspects the parent process of the current one and decides whether
it looks like an agent sub-process.  This is a best-effort
fallback for the env-var detector — useful when the calling
runtime doesn't set a recognised variable.

Behaviour on non-Linux platforms: :meth:`ProcDetector.is_subagent`
returns ``False`` without raising.  The detector never blocks
non-Linux deployments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

__all__ = ["ProcDetector"]


_SUBAGENT_NEEDLES: tuple[str, ...] = (
    "subagent",
    "task",
    "worker",
    "claude-code-sub",
    "codex-task",
)

_PPID_LINE_PREFIX = "PPid:"


def _parse_ppid_from_status(status_path: Path) -> Optional[int]:
    try:
        text = status_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith(_PPID_LINE_PREFIX):
            raw = line[len(_PPID_LINE_PREFIX):].strip()
            try:
                return int(raw)
            except ValueError:
                return None
    return None


def _read_parent_cmdline(proc: Path, ppid: int) -> str:
    try:
        data = (proc / str(ppid) / "cmdline").read_bytes()
    except OSError:
        return ""
    return data.replace(b"\x00", b" ").decode("utf-8", errors="replace")


def _read_parent_comm(proc: Path, ppid: int) -> str:
    try:
        return (proc / str(ppid) / "comm").read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    except OSError:
        return ""


class ProcDetector:
    """Detects sub-agent status by reading ``/proc/<ppid>``."""

    def __init__(self, proc_root: Optional[str] = None) -> None:
        self._proc: Path = Path(proc_root) if proc_root else Path("/proc")

    def is_subagent(self) -> bool:
        status_path = self._proc / "self" / "status"
        if not status_path.is_file():
            return False

        ppid = _parse_ppid_from_status(status_path)
        if ppid is None or ppid <= 0:
            return False

        cmdline = _read_parent_cmdline(self._proc, ppid).lower()
        if not cmdline and not (self._proc / str(ppid)).exists():
            return False

        comm = _read_parent_comm(self._proc, ppid).lower()

        for needle in _SUBAGENT_NEEDLES:
            if needle in cmdline or needle in comm:
                return True
        return False

    def name(self) -> str:
        return "proc"
