"""Codex session parser.

Source layout (recursive)::

    ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

Each line is a JSON object with one of the following ``type`` values:

* ``"session_meta"``   — payload has the session ``id`` and ``cwd``;
  this is the canonical UUID.
* ``"response_item"``  — payload is a message (``type: "message"``,
  ``role: "user"``/``"assistant"``, ``content: [...]``).
* ``"event_msg"``      — auxiliary events (task_started, agent_message, …).
  Skipped for message counting.
* ``"custom_tool_call"`` and friends — non-message noise, skipped.

The first ``session_meta`` record is authoritative; later ones (rare)
are ignored.  The first user message text becomes the title, with a
fallback to ``payload.cwd`` if no user message is found.

The base directory can be overridden by ``base_dir`` or by setting
``$AI_READER_HOME/.codex/sessions``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from .models import AgentName, Message, Session


_TITLE_MAX_LEN = 100


def _resolve_base_dir(base_dir: Optional[str]) -> Path:
    if base_dir:
        return Path(base_dir).expanduser()
    env_home = os.environ.get("AI_READER_HOME")
    if env_home:
        return Path(env_home).expanduser() / ".codex" / "sessions"
    return Path("~/.codex/sessions").expanduser()


def _parse_iso_timestamp(raw: str) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw[:23].replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _extract_text_from_parts(parts: object) -> str:
    """Concatenate ``input_text``/``output_text``/``text`` parts."""
    if not isinstance(parts, list):
        return ""
    chunks: List[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type", "")
        if part_type in ("input_text", "output_text", "text", ""):
            text = part.get("text", "")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "\n".join(chunks)


def _is_system_noise(text: str) -> bool:
    stripped = text.lstrip()
    return (
        stripped.startswith("<permissions")
        or stripped.startswith("## Apps")
        or stripped.startswith("<command-message>")
        or stripped.startswith("<system-reminder>")
    )


def _scan_file(jsonl_path: Path) -> Optional[Session]:
    """Parse a Codex rollout file into a :class:`Session`."""
    uuid: Optional[str] = None
    cwd: Optional[str] = None
    timestamp: Optional[datetime] = None
    title: Optional[str] = None
    message_count = 0

    try:
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue

                line_ts = _parse_iso_timestamp(record.get("timestamp", ""))
                if line_ts is not None:
                    timestamp = line_ts

                rec_type = record.get("type")
                payload = record.get("payload") or {}
                if not isinstance(payload, dict):
                    continue

                if rec_type == "session_meta" and uuid is None:
                    uuid = payload.get("id") if isinstance(payload.get("id"), str) else None
                    if not uuid:
                        # session_meta without a usable id is unusable
                        return None
                    cwd_val = payload.get("cwd")
                    if isinstance(cwd_val, str):
                        cwd = cwd_val
                    meta_ts = _parse_iso_timestamp(payload.get("timestamp", ""))
                    if meta_ts is not None:
                        timestamp = meta_ts
                    continue

                if (
                    rec_type == "response_item"
                    and payload.get("type") == "message"
                ):
                    role = payload.get("role", "")
                    text = _extract_text_from_parts(payload.get("content", []))
                    if not text or _is_system_noise(text):
                        continue
                    message_count += 1
                    if title is None and role == "user":
                        candidate = text.strip()
                        if candidate and not candidate.startswith("<") \
                                and not candidate.startswith("#"):
                            first_line = candidate.splitlines()[0].strip()
                            if first_line:
                                title = first_line
    except OSError:
        return None

    if uuid is None:
        return None

    if title:
        final_title = title.replace("\n", " ").replace("\r", " ").strip()[
            :_TITLE_MAX_LEN
        ]
    elif cwd:
        final_title = cwd[:_TITLE_MAX_LEN]
    else:
        final_title = "Untitled"

    if timestamp is None:
        try:
            timestamp = datetime.fromtimestamp(
                jsonl_path.stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            return None

    return Session(
        uuid=uuid,
        agent=AgentName.CODEX,
        title=final_title,
        date=timestamp,
        path=str(jsonl_path),
        message_count=message_count,
        extra={"cwd": cwd} if cwd else {},
    )


def _is_valid_uuid(uuid: str) -> bool:
    if not uuid or not isinstance(uuid, str):
        return False
    stripped = uuid.strip()
    if not stripped or stripped != uuid:
        return False
    if any(c.isspace() for c in stripped) or "/" in stripped or "\\" in stripped:
        return False
    return True


def _discover_files(root: Path) -> List[Path]:
    """Return all Codex rollout files under ``root``, sorted by mtime desc."""
    if not root.is_dir():
        return []
    files = [p for p in root.glob("**/rollout-*.jsonl") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def list_sessions(base_dir: Optional[str] = None) -> List[Session]:
    """Return every Codex session visible under ``base_dir``."""
    root = _resolve_base_dir(base_dir)
    sessions: List[Session] = []
    seen_uuids: set[str] = set()
    for path in _discover_files(root):
        session = _scan_file(path)
        if session is None:
            continue
        if session.uuid in seen_uuids:
            # Two files claiming the same session id — keep the first
            # (newest mtime) and ignore the rest.
            continue
        seen_uuids.add(session.uuid)
        sessions.append(session)
    sessions.sort(key=lambda s: s.date, reverse=True)
    return sessions


def _find_session_file(
    uuid: str, base_dir: Optional[str]
) -> Tuple[Path, Session]:
    if not _is_valid_uuid(uuid):
        raise ValueError(f"Invalid Codex session uuid: {uuid!r}")
    root = _resolve_base_dir(base_dir)
    for path in _discover_files(root):
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    if record.get("type") != "session_meta":
                        continue
                    payload = record.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("id") == uuid:
                        return path, _scan_file(path)  # type: ignore[return-value]
        except OSError:
            continue
    raise FileNotFoundError(f"Codex session {uuid!r} not found under {root}")


def read_session(uuid: str, base_dir: Optional[str] = None) -> Session:
    """Read a single Codex session by ``uuid``.

    Raises:
        FileNotFoundError: no file with this id exists.
        ValueError: ``uuid`` is malformed.
    """
    _, session = _find_session_file(uuid, base_dir)
    return session



def _codex_message_text(payload: dict) -> str:
    """Concatenate the text parts of a Codex message payload."""
    return _extract_text_from_parts(payload.get("content", []))


def _extract_messages_from_rollout(path: Path) -> List[Message]:
    """Read a Codex rollout JSONL into structured :class:`Message` objects.

    Codex rollouts store ``response_item`` records.  ``message`` payloads
    become user/assistant :class:`Message` objects.  ``function_call``
    payloads (and the ``local_shell_call`` family) become assistant
    ``tool_use`` entries; ``function_call_output`` payloads become
    ``tool`` messages with a ``tool_result`` entry.  Other record types
    are skipped.

    Lines that are not valid JSON are silently skipped; an
    :class:`OSError` returns whatever was collected so far.
    """
    messages: List[Message] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                ptype = payload.get("type")
                if ptype == "message":
                    role = payload.get("role")
                    if role not in ("user", "assistant"):
                        continue
                    text = _codex_message_text(payload)
                    messages.append(Message(role=role, text=text))
                elif ptype in ("function_call", "local_shell_call"):
                    name = payload.get("name") or ptype
                    arguments = payload.get("arguments", "")
                    if isinstance(arguments, str):
                        input_str = arguments
                    else:
                        try:
                            input_str = json.dumps(arguments, ensure_ascii=False)
                        except (TypeError, ValueError):
                            input_str = str(arguments)
                    messages.append(
                        Message(
                            role="assistant",
                            text="",
                            tool_use=({"name": name, "input": input_str},),
                        )
                    )
                elif ptype in ("function_call_output", "local_shell_call_output"):
                    output = payload.get("output", "")
                    if not isinstance(output, str):
                        try:
                            output = json.dumps(output, ensure_ascii=False)
                        except (TypeError, ValueError):
                            output = str(output)
                    messages.append(
                        Message(
                            role="tool",
                            text="",
                            tool_result=({"content": output},),
                        )
                    )
    except OSError:
        return messages
    return messages


def read_messages(
    uuid: str, base_dir: Optional[str] = None
) -> List[Message]:
    """Return the full message list for a Codex session.

    Reuses :func:`read_session` for path resolution.  Function/shell
    calls and their outputs are preserved on the returned
    :class:`Message` objects.

    Raises:
        FileNotFoundError: the session does not exist.
        ValueError: ``uuid`` is malformed.
    """
    session = read_session(uuid, base_dir)
    return _extract_messages_from_rollout(Path(session.path))


def search(query: str, base_dir: Optional[str] = None) -> List[Session]:
    """Case-insensitive substring search across Codex session titles."""
    needle = (query or "").strip().lower()
    if not needle:
        return []
    return [
        session
        for session in list_sessions(base_dir)
        if needle in session.title.lower()
    ]


def session_exists(uuid: str, base_dir: Optional[str] = None) -> bool:
    if not _is_valid_uuid(uuid):
        return False
    try:
        _find_session_file(uuid, base_dir)
    except (FileNotFoundError, ValueError):
        return False
    return True
