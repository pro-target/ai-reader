"""Session-note template validator.

The canonical session-note template lives in
``src/ai_reader/templates/session_note.md``.  The required-sections list
is read from that template at runtime so the prompt and the validator
cannot drift apart — adding or removing a required section in the
template is the only edit needed.
"""

from __future__ import annotations

import re
from pathlib import Path

_HEADING_RE = re.compile(r"^## (.+)$")
_REQUIRED_MARKER = "<!-- required:"

_DEFAULT_TEMPLATE = (
    Path(__file__).parent.parent / "templates" / "session_note.md"
)


def parse_required_sections(template_path: Path) -> list[str]:
    """Return the list of section names marked ``required`` in the template.

    A section is considered required when its ``## <name>`` heading is
    followed (anywhere in the body up to the next ``##`` heading) by a
    comment of the form ``<!-- required: ... -->``.
    """
    text = template_path.read_text(encoding="utf-8")
    required: list[str] = []
    current: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current is not None and _REQUIRED_MARKER in "\n".join(current_body):
                required.append(current)
            current = m.group(1).strip()
            current_body = []
        elif current is not None:
            current_body.append(line)
    if current is not None and _REQUIRED_MARKER in "\n".join(current_body):
        required.append(current)
    return required


def _section_body_map(text: str) -> dict[str, str]:
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                bodies[current] = "\n".join(current_body)
            current = m.group(1).strip()
            current_body = []
        elif current is not None:
            current_body.append(line)
    if current is not None:
        bodies[current] = "\n".join(current_body)
    return bodies


def validate_session_note(
    note_path: Path,
    template_path: Path | None = None,
) -> list[str]:
    """Return the list of required sections that are missing or empty.

    A section counts as missing when its ``## <name>`` heading is
    absent from the note.  A section counts as empty when the heading
    is present but the body (after stripping required-marker comments)
    is blank.
    """
    template = template_path or _DEFAULT_TEMPLATE
    required = parse_required_sections(template)
    note_text = note_path.read_text(encoding="utf-8")
    note_bodies = _section_body_map(note_text)
    missing: list[str] = []
    for name in required:
        body = note_bodies.get(name)
        if body is None:
            missing.append(name)
            continue
        stripped = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
        if not stripped:
            missing.append(name)
    return missing
