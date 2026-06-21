"""Tests for the session-note template validator.

The required-sections list is read from the bundled template at
runtime, so the template file is the single source of truth shared
with whatever tool produces session notes.
"""
from __future__ import annotations

from pathlib import Path

from ai_reader.validators.session_note_check import (
    parse_required_sections,
    validate_session_note,
)

_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "ai_reader"
    / "templates"
    / "session_note.md"
)


def test_parse_required_sections() -> None:
    sections = parse_required_sections(_TEMPLATE)
    assert sections == [
        "Goal",
        "Decisions",
        "Files touched",
        "Open questions",
        "Next actions",
        "Verification",
    ]


def test_validate_complete_note(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text(
        (
            "# Session Note: demo\n\n"
            "**UUID**: u-1\n"
            "**Agent**: codex\n"
            "**Date**: 2026-06-21\n\n"
            "## Goal\nShip PR7b.\n\n"
            "## Decisions\n- validator reads template at runtime.\n\n"
            "## Files touched\n- src/ai_reader/validators/session_note_check.py\n\n"
            "## Open questions\n- none\n\n"
            "## Next actions\n- wire into session-summarizer.\n\n"
            "## Verification\n- run pytest tests/validators/.\n"
        ),
        encoding="utf-8",
    )
    assert validate_session_note(note, _TEMPLATE) == []


def test_validate_missing_section(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text(
        (
            "# Session Note: demo\n\n"
            "## Goal\nShip PR7b.\n\n"
            "## Decisions\n- none.\n\n"
            "## Files touched\n- a.py\n\n"
            "## Open questions\n- none\n\n"
            "## Next actions\n- ship.\n"
        ),
        encoding="utf-8",
    )
    assert "Verification" in validate_session_note(note, _TEMPLATE)


def test_validate_empty_section_body(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text(
        (
            "# Session Note: demo\n\n"
            "## Goal\nShip PR7b.\n\n"
            "## Decisions\n- none.\n\n"
            "## Files touched\n- a.py\n\n"
            "## Open questions\n- none\n\n"
            "## Next actions\n- ship.\n\n"
            "## Verification\n\n"
        ),
        encoding="utf-8",
    )
    assert "Verification" in validate_session_note(note, _TEMPLATE)
