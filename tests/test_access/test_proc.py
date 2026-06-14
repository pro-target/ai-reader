"""Tests for the ``/proc``-based subagent detector.

The detector reads ``/proc/self/status`` to find the parent PID and
then looks for subagent-related strings in the parent ``cmdline`` and
``comm``.  All tests inject a fake ``/proc`` tree under
``tmp_path`` so the real kernel state is never touched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_reader.access.proc import (
    ProcDetector,
    _parse_ppid_from_status,
    _read_parent_cmdline,
    _read_parent_comm,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def test_parse_ppid_from_status(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text(
        "Name:\tbash\nPid:\t42\nPPid:\t7\nUid:\t0\n", encoding="utf-8"
    )
    assert _parse_ppid_from_status(status) == 7


def test_parse_ppid_from_status_missing_line(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text("Name:\tbash\nPid:\t42\n", encoding="utf-8")
    assert _parse_ppid_from_status(status) is None


def test_parse_ppid_from_status_missing_file(tmp_path: Path) -> None:
    assert _parse_ppid_from_status(tmp_path / "nope") is None


def test_read_parent_cmdline(tmp_path: Path) -> None:
    cmdline = tmp_path / "7" / "cmdline"
    cmdline.parent.mkdir(parents=True)
    cmdline.write_bytes(b"python\x00-m\x00subagent-runner\x00")
    assert "subagent-runner" in _read_parent_cmdline(tmp_path, 7)


def test_read_parent_cmdline_missing(tmp_path: Path) -> None:
    assert _read_parent_cmdline(tmp_path, 99999) == ""


def test_read_parent_comm(tmp_path: Path) -> None:
    p = tmp_path / "7" / "comm"
    p.parent.mkdir(parents=True)
    p.write_text("claude-task\n", encoding="utf-8")
    assert _read_parent_comm(tmp_path, 7) == "claude-task"


def test_read_parent_comm_missing(tmp_path: Path) -> None:
    assert _read_parent_comm(tmp_path, 99999) == ""


# ---------------------------------------------------------------------------
# ProcDetector with a fake /proc tree
# ---------------------------------------------------------------------------


def _make_fake_proc(root: Path, self_ppid: int, cmdline: bytes, comm: str) -> Path:
    """Build a fake ``/proc`` layout under ``root``."""
    (root / "self").mkdir(parents=True)
    (root / "self" / "status").write_text(
        f"Name:\tpython\nPid:\t1\nPPid:\t{self_ppid}\n", encoding="utf-8"
    )
    (root / str(self_ppid)).mkdir(parents=True)
    (root / str(self_ppid) / "cmdline").write_bytes(cmdline)
    (root / str(self_ppid) / "comm").write_text(comm + "\n", encoding="utf-8")
    return root


def test_proc_detector_current_process_recognises_subagent(tmp_path: Path) -> None:
    _make_fake_proc(
        tmp_path / "proc",
        self_ppid=42,
        cmdline=b"claude-code-subagent-runner\x00--task\x00x\x00",
        comm="claude-code",
    )
    d = ProcDetector(proc_root=str(tmp_path / "proc"))
    assert d.is_subagent() is True
    assert d.name() == "proc"


def test_proc_detector_unknown_process(tmp_path: Path) -> None:
    """A parent whose cmdline matches no needle -> False."""
    _make_fake_proc(
        tmp_path / "proc",
        self_ppid=42,
        cmdline=b"vim\x00hello.txt\x00",
        comm="vim",
    )
    d = ProcDetector(proc_root=str(tmp_path / "proc"))
    assert d.is_subagent() is False


def test_proc_detector_missing_proc_root_returns_false(tmp_path: Path) -> None:
    """A non-existent proc root must degrade gracefully, not raise."""
    d = ProcDetector(proc_root=str(tmp_path / "nope"))
    assert d.is_subagent() is False


def test_proc_detector_self_status_missing_returns_false(tmp_path: Path) -> None:
    """A proc root without ``self/status`` is treated as unavailable."""
    (tmp_path / "proc").mkdir()
    d = ProcDetector(proc_root=str(tmp_path / "proc"))
    assert d.is_subagent() is False


def test_proc_detector_handles_zero_ppid(tmp_path: Path) -> None:
    """``PPid: 0`` (init / no parent) is not a subagent."""
    _make_fake_proc(
        tmp_path / "proc",
        self_ppid=0,
        cmdline=b"init\x00",
        comm="init",
    )
    d = ProcDetector(proc_root=str(tmp_path / "proc"))
    assert d.is_subagent() is False


def test_proc_detector_missing_cmdline_dir(tmp_path: Path) -> None:
    """If the parent dir is gone (e.g. process exited), the detector
    must return ``False`` rather than crash.
    """
    proc = tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self" / "status").write_text(
        "Name:\tx\nPid:\t1\nPPid:\t99999\n", encoding="utf-8"
    )
    # No /proc/99999 directory.
    d = ProcDetector(proc_root=str(proc))
    assert d.is_subagent() is False


def test_proc_detector_no_loop_on_bogus_chain(tmp_path: Path) -> None:
    """Boundedness: even with a self-referential status file, the
    detector returns within microseconds and does not recurse.
    """
    proc = tmp_path / "proc"
    (proc / "self" / "status").parent.mkdir(parents=True)
    (proc / "self" / "status").write_text(
        "PPid:\t1\n", encoding="utf-8"
    )
    # No parent dir -> quick false.
    d = ProcDetector(proc_root=str(proc))
    assert d.is_subagent() is False
