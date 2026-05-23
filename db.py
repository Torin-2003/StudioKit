"""
HypeCutter — db.py
Lightweight SQLite wrapper. Each public function opens and closes its own
connection so it is safe to call from any Streamlit re-run or thread.
"""

import json
import logging
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/hypecutter.db")


def _ensure_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    _ensure_dir()
    con = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")  # concurrent reads during write
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                source_url    TEXT,
                source_path   TEXT,
                status        TEXT NOT NULL DEFAULT 'processing',
                created_at    TEXT NOT NULL,
                settings_json TEXT
            );

            CREATE TABLE IF NOT EXISTS clips (
                id            TEXT PRIMARY KEY,
                project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title         TEXT,
                file_path     TEXT,
                viral_score   REAL,
                hook_score    REAL,
                duration      REAL,
                condensed     INTEGER DEFAULT 0,
                metadata_json TEXT,
                created_at    TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_clips_project
                ON clips(project_id);

            CREATE INDEX IF NOT EXISTS idx_projects_created
                ON projects(created_at DESC);
        """)


# ─────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(
    name: str,
    source_url: str = "",
    source_path: str = "",
    settings: dict | None = None,
) -> str:
    """Insert a new project row, return its id."""
    pid = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute(
            """INSERT INTO projects
               (id, name, source_url, source_path, status, created_at, settings_json)
               VALUES (?, ?, ?, ?, 'processing', ?, ?)""",
            (pid, name, source_url, source_path, _now(), json.dumps(settings or {})),
        )
    return pid


def update_project_status(project_id: str, status: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE projects SET status=? WHERE id=?",
            (status, project_id),
        )


def rename_project(project_id: str, new_name: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE projects SET name=? WHERE id=?",
            (new_name, project_id),
        )


def delete_project(project_id: str) -> list[str]:
    """
    Delete project + all its clips from DB.
    Returns list of file_paths that the caller should physically delete
    (clip output files + source download file if present).
    """
    with _conn() as con:
        proj_row = con.execute(
            "SELECT source_path FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        clip_rows = con.execute(
            "SELECT file_path FROM clips WHERE project_id=?", (project_id,)
        ).fetchall()
        file_paths = [r["file_path"] for r in clip_rows if r["file_path"]]
        if proj_row and proj_row["source_path"]:
            file_paths.append(proj_row["source_path"])
        con.execute("DELETE FROM clips WHERE project_id=?", (project_id,))
        con.execute("DELETE FROM projects WHERE id=?", (project_id,))
    return file_paths


def list_projects(
    days: int | None = None,
    search: str = "",
) -> list[dict]:
    """
    Return projects ordered by created_at DESC, each with a clip_count field.
    Single query via LEFT JOIN — no N+1 round-trips.
    """
    conditions: list[str] = []
    params: list = []

    if days is not None:
        conditions.append("datetime(p.created_at) >= datetime('now', ?)")
        params.append(f"-{days} days")

    if search.strip():
        conditions.append("(LOWER(p.name) LIKE ? OR LOWER(p.source_url) LIKE ?)")
        q = f"%{search.strip().lower()}%"
        params += [q, q]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with _conn() as con:
        rows = con.execute(
            f"""
            SELECT p.*, COUNT(c.id) AS clip_count
            FROM projects p
            LEFT JOIN clips c ON c.project_id = p.id
            {where}
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────────
# Clips
# ─────────────────────────────────────────────────────────────────


def save_clip(project_id: str, clip: dict) -> str:
    """Persist one rendered clip. Returns clip id."""
    cid = uuid.uuid4().hex[:12]
    metadata = {
        k: clip.get(k)
        for k in (
            "start",
            "end",
            "reason",
            "reason_for_duration",
            "selected_range",
            "caption",
            "duration_warning",
            "segment_count",
            "condensed",
        )
    }
    with _conn() as con:
        con.execute(
            """INSERT INTO clips
               (id, project_id, title, file_path, viral_score, hook_score,
                duration, condensed, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cid,
                project_id,
                clip.get("title", ""),
                clip.get("output_path", ""),
                float(clip.get("score", 0)),
                float(clip.get("hook_strength", 0)),
                float(clip.get("duration", 0)),
                1 if clip.get("condensed") else 0,
                json.dumps(metadata),
                _now(),
            ),
        )
    return cid


def get_clips(project_id: str) -> list[dict]:
    """Return all clips for a project, newest first."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM clips WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        meta = json.loads(d.pop("metadata_json") or "{}")
        result.append({**d, **meta})
    return result


def clip_count(project_id: str) -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM clips WHERE project_id=?", (project_id,)
        ).fetchone()
    return row[0] if row else 0
