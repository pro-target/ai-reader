"""OpenCode session parser.

OpenCode stores everything in a single SQLite database.  The current
installations we know about:

* Native: ``~/.local/share/opencode/opencode.db``.
* Snap VSCode: ``~/snap/code/<revision>/.local/share/opencode/opencode.db``.
* Snap OpenCode: ``~/snap/opencode/<revision>/.local/share/opencode/opencode.db``.

All three are searched (deduplicated by ``realpath``) and queried
transparently.  An override path can be supplied via
``$OPENCODE_DB`` or the ``base_dir`` argument (the latter must point
to a directory containing ``opencode.db``).

Schema (relevant columns only)::

    CREATE TABLE session (
        id              TEXT PRIMARY KEY,
        parent_id       TEXT,
        title           TEXT,
        time_created    INTEGER,    -- ms epoch
        time_updated    INTEGER,    -- ms epoch
        ... (other fields ignored)
    );
    CREATE TABLE message (
        id              TEXT PRIMARY KEY,
        session_id      TEXT NOT NULL REFERENCES session(id),
        data            TEXT,       -- JSON blob
        ... (other fields ignored)
    );
"""

from __future__ import annotations

import glob
import hashlib
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .models import AgentName, Session


_TITLE_MAX_LEN = 100
_DEFAULT_DB = "~/.local/share/opencode/opencode.db"


def _expand(path: str) -> str:
    return str(Path(path).expanduser())


def _resolve_db_paths(
    base_dir: Optional[str] = None,
    override: Optional[str] = None,
) -> List[str]:
    """Return all OpenCode DB paths that exist, in priority order.

    Priority:

    1. ``override`` (if given and a regular file).
    2. ``$OPENCODE_DB`` env var.
    3. ``base_dir/opencode.db`` (if ``base_dir`` is supplied).
    4. Native ``~/.local/share/opencode/opencode.db``.
    5. All ``~/snap/code/*/.local/share/opencode/opencode.db``.
    6. All ``~/snap/opencode/*/.local/share/opencode/opencode.db``.
    """
    candidates: List[str] = []

    def _add(path: str) -> None:
        if path and os.path.isfile(path):
            candidates.append(path)

    if override:
        _add(override)
    env_override = os.environ.get("OPENCODE_DB")
    if env_override:
        _add(env_override)
    if base_dir:
        _add(os.path.join(base_dir, "opencode.db"))

    _add(_expand(_DEFAULT_DB))

    for pattern in (
        "~/snap/code/*/.local/share/opencode/opencode.db",
        "~/snap/opencode/*/.local/share/opencode/opencode.db",
    ):
        for p in sorted(glob.glob(_expand(pattern))):
            _add(p)

    # Dedupe by realpath so the "current" symlink and the real revision
    # don't both appear.
    seen: set[str] = set()
    deduped: List[str] = []
    for p in candidates:
        real = os.path.realpath(p)
        if real in seen:
            continue
        seen.add(real)
        deduped.append(p)
    return deduped


def _open_db(db_path: str) -> Optional[sqlite3.Connection]:
    """Open an OpenCode DB read-only, retrying on lock, falling back to copy."""
    for backoff in (0.0, 0.5, 1.0, 2.0):
        try:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000")
            return conn
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc):
                break
            if backoff:
                time.sleep(backoff)
        except Exception:
            break

    try:
        h = hashlib.sha1(db_path.encode()).hexdigest()[:16]
        tmp_path = f"/tmp/ai_reader_opencode_{h}.db"
        shutil.copy2(db_path, tmp_path)
        conn = sqlite3.connect(tmp_path, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn
    except Exception:
        return None


def _iter_dbs(
    base_dir: Optional[str], override: Optional[str]
) -> Iterable[Tuple[str, sqlite3.Connection]]:
    """Yield ``(path, conn)`` for every readable OpenCode DB.

    The caller is responsible for closing the connection.  Connections
    that fail to open are silently skipped (we surface the error in
    :func:`list_sessions` only if no DB at all could be opened).
    """
    for path in _resolve_db_paths(base_dir, override):
        conn = _open_db(path)
        if conn is not None:
            yield path, conn


def _epoch_ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _row_to_session(row: sqlite3.Row, db_path: str) -> Session:
    sid, title, time_created, time_updated, parent_id = (
        row["id"],
        row["title"],
        row["time_created"],
        row["time_updated"],
        row["parent_id"],
    )
    date = _epoch_ms_to_datetime(time_updated or time_created or 0)
    clean_title = (title or "").strip() or "Untitled"
    return Session(
        uuid=sid,
        agent=AgentName.OPENCODE,
        title=clean_title[:_TITLE_MAX_LEN],
        date=date,
        path=db_path,
        message_count=0,  # filled by the caller with a per-row count
        parent_uuid=parent_id,
        extra={
            "time_created": time_created,
            "time_updated": time_updated,
        },
    )


_SELECT_SESSION = (
    "SELECT id, title, time_created, time_updated, parent_id "
    "FROM session "
    "WHERE id = ?"
)
_SELECT_ALL_SESSIONS = (
    "SELECT id, title, time_created, time_updated, parent_id "
    "FROM session "
    "ORDER BY time_updated DESC"
)
_SELECT_MESSAGE_COUNT = "SELECT COUNT(*) FROM message WHERE session_id = ?"


def list_sessions(
    base_dir: Optional[str] = None,
    override: Optional[str] = None,
) -> List[Session]:
    """Return every OpenCode session, deduplicated across all DBs.

    The same ``session.id`` may exist in more than one DB (e.g. when
    the native and snap installations are kept in sync).  We only
    surface the first occurrence, which comes from the highest-priority
    DB in :func:`_resolve_db_paths`.
    """
    sessions: List[Session] = []
    seen_ids: set[str] = set()
    for db_path, conn in _iter_dbs(base_dir, override):
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            for row in cursor.execute(_SELECT_ALL_SESSIONS):
                sid = row["id"]
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                count = cursor.execute(
                    _SELECT_MESSAGE_COUNT, (sid,)
                ).fetchone()[0]
                session = _row_to_session(row, db_path)
                session = Session(
                    uuid=session.uuid,
                    agent=session.agent,
                    title=session.title,
                    date=session.date,
                    path=session.path,
                    message_count=int(count),
                    parent_uuid=session.parent_uuid,
                    extra=session.extra,
                )
                sessions.append(session)
        except sqlite3.Error:
            continue
        finally:
            conn.close()

    sessions.sort(key=lambda s: s.date, reverse=True)
    return sessions


def _read_session_by_uuid(
    uuid: str,
    base_dir: Optional[str],
    override: Optional[str],
) -> Session:
    if not uuid or not isinstance(uuid, str):
        raise ValueError(f"Invalid OpenCode session uuid: {uuid!r}")
    if any(c.isspace() for c in uuid) or "/" in uuid or "\\" in uuid:
        raise ValueError(f"Invalid OpenCode session uuid: {uuid!r}")

    for db_path, conn in _iter_dbs(base_dir, override):
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = cursor.execute(_SELECT_SESSION, (uuid,)).fetchone()
            if row is None:
                continue
            count = cursor.execute(
                _SELECT_MESSAGE_COUNT, (uuid,)
            ).fetchone()[0]
            session = _row_to_session(row, db_path)
            return Session(
                uuid=session.uuid,
                agent=session.agent,
                title=session.title,
                date=session.date,
                path=session.path,
                message_count=int(count),
                parent_uuid=session.parent_uuid,
                extra=session.extra,
            )
        except sqlite3.Error:
            continue
        finally:
            conn.close()
    raise FileNotFoundError(f"OpenCode session {uuid!r} not found")


def read_session(
    uuid: str,
    base_dir: Optional[str] = None,
    override: Optional[str] = None,
) -> Session:
    """Read a single OpenCode session by ``uuid``.

    Raises:
        FileNotFoundError: no DB contains a session with this id.
        ValueError: ``uuid`` is malformed.
    """
    return _read_session_by_uuid(uuid, base_dir, override)


def search(
    query: str,
    base_dir: Optional[str] = None,
    override: Optional[str] = None,
) -> List[Session]:
    """Case-insensitive substring search across OpenCode session titles."""
    needle = (query or "").strip().lower()
    if not needle:
        return []
    return [
        session
        for session in list_sessions(base_dir, override)
        if needle in session.title.lower()
    ]


def session_exists(
    uuid: str,
    base_dir: Optional[str] = None,
    override: Optional[str] = None,
) -> bool:
    if not uuid or not isinstance(uuid, str):
        return False
    if any(c.isspace() for c in uuid) or "/" in uuid or "\\" in uuid:
        return False
    for db_path, conn in _iter_dbs(base_dir, override):
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = cursor.execute(_SELECT_SESSION, (uuid,)).fetchone()
        except sqlite3.Error:
            continue
        finally:
            conn.close()
        if row is not None:
            return True
    return False
