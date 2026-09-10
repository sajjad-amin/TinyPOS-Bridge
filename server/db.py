import datetime
import io
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image

from server.config import BASE_DIR, DB_PATH

API_KEYS_JSON = BASE_DIR / "api_keys.json"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize SQLite database schema for persistent print jobs and API keys."""
    with get_connection() as conn:
        # 1. Jobs Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                api_key TEXT,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                strength INTEGER DEFAULT 7,
                scale REAL DEFAULT 1.0,
                autocrop INTEGER DEFAULT 1,
                keep_job INTEGER DEFAULT 0,
                preview_blob BLOB,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_api_key ON jobs (api_key)")

        # Ensure keep_job column exists for existing databases
        cur = conn.execute("PRAGMA table_info(jobs)")
        existing_cols = [row["name"] for row in cur.fetchall()]
        if "keep_job" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN keep_job INTEGER DEFAULT 0")

        # 2. API Keys Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

    # Clean up any expired temporary jobs on startup
    cleanup_temporary_jobs(older_than_seconds=300)

    # Migrate any existing keys from api_keys.json
    migrate_api_keys_from_json()


def migrate_api_keys_from_json():
    """Migrate legacy keys from api_keys.json into the SQLite api_keys table."""
    if not API_KEYS_JSON.exists():
        return
    try:
        with open(API_KEYS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                with get_connection() as conn:
                    for item in data:
                        k = item.get("key")
                        name = item.get("name") or "Unnamed Key"
                        created_at = item.get("created_at") or datetime.datetime.now(datetime.timezone.utc).strftime("%b %d, %Y %I:%M %p")
                        if k:
                            conn.execute(
                                "INSERT OR IGNORE INTO api_keys (key, name, created_at) VALUES (?, ?, ?)",
                                (k, name, created_at),
                            )
                    conn.commit()
    except Exception:
        pass


# ==========================================
# API Keys Operations
# ==========================================

def insert_api_key(key: str, name: str) -> Dict[str, Any]:
    """Insert a new API key into SQLite."""
    created_at = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d, %Y %I:%M %p")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO api_keys (key, name, created_at) VALUES (?, ?, ?)",
            (key, name, created_at),
        )
        conn.commit()
    return {"key": key, "name": name, "created_at": created_at}


def list_api_keys() -> List[Dict[str, Any]]:
    """List all active API keys."""
    with get_connection() as conn:
        cur = conn.execute("SELECT key, name, created_at FROM api_keys ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]


def get_api_key(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single API key by key string."""
    with get_connection() as conn:
        cur = conn.execute("SELECT key, name, created_at FROM api_keys WHERE key = ?", (key,))
        row = cur.fetchone()
        return dict(row) if row else None


def delete_api_key(key: str) -> bool:
    """Delete an API key by key string."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM api_keys WHERE key = ?", (key,))
        conn.commit()
        return cur.rowcount > 0


def is_valid_api_key(key: Optional[str]) -> bool:
    """Validate whether an API key exists in SQLite."""
    if not key:
        return False
    with get_connection() as conn:
        cur = conn.execute("SELECT 1 FROM api_keys WHERE key = ?", (key,))
        return cur.fetchone() is not None


# ==========================================
# Print Jobs Operations
# ==========================================

def insert_job(
    job_id: str,
    job_type: str,
    status: str = "pending",
    api_key: Optional[str] = None,
    image: Optional[Image.Image] = None,
    strength: int = 7,
    scale: float = 1.0,
    autocrop: bool = True,
    keep_job: bool = False,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert a new print job into SQLite."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    preview_bytes = None
    if image:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        preview_bytes = buf.getvalue()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                job_id, api_key, job_type, status, error, strength, scale, autocrop, keep_job, preview_blob, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                api_key,
                job_type,
                status,
                error,
                strength,
                scale,
                1 if autocrop else 0,
                1 if keep_job else 0,
                preview_bytes,
                now_iso,
            ),
        )
        conn.commit()

    return {
        "job_id": job_id,
        "api_key": api_key,
        "job_type": job_type,
        "status": status,
        "error": error,
        "strength": strength,
        "scale": scale,
        "autocrop": autocrop,
        "keep_job": keep_job,
        "created_at": now_iso,
    }


def update_job_status(
    job_id: str,
    status: str,
    error: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> bool:
    """Update job status, error, and completion timestamp."""
    if status == "completed" and not completed_at:
        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE jobs
            SET status = ?, error = ?, completed_at = ?
            WHERE job_id = ?
            """,
            (status, error, completed_at, job_id),
        )
        conn.commit()
        return cur.rowcount > 0


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full job details by ID."""
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_job_preview_bytes(job_id: str) -> Optional[bytes]:
    """Retrieve PNG preview bytes from SQLite."""
    with get_connection() as conn:
        cur = conn.execute("SELECT preview_blob FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        if not row or not row["preview_blob"]:
            return None
        return row["preview_blob"]


def get_job_image(job_id: str) -> Optional[Image.Image]:
    """Retrieve PIL Image for transmission from SQLite preview_blob."""
    raw = get_job_preview_bytes(job_id)
    if not raw:
        return None
    return Image.open(io.BytesIO(raw))


def get_jobs_paginated(
    api_key: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """Retrieve paginated jobs ordered chronologically (newest first)."""
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    offset = (page - 1) * per_page

    with get_connection() as conn:
        if api_key is not None:
            count_cur = conn.execute("SELECT COUNT(*) AS total FROM jobs WHERE api_key = ?", (api_key,))
            data_cur = conn.execute(
                """
                SELECT job_id, api_key, job_type, status, error, strength, scale, autocrop, keep_job, created_at, completed_at
                FROM jobs
                WHERE api_key = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (api_key, per_page, offset),
            )
        else:
            count_cur = conn.execute("SELECT COUNT(*) AS total FROM jobs")
            data_cur = conn.execute(
                """
                SELECT job_id, api_key, job_type, status, error, strength, scale, autocrop, keep_job, created_at, completed_at
                FROM jobs
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (per_page, offset),
            )

        total = count_cur.fetchone()["total"]
        rows = [dict(r) for r in data_cur.fetchall()]
        total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        "jobs": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }


def delete_job(job_id: str) -> bool:
    """Delete a single job and its preview from SQLite."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.commit()
        return cur.rowcount > 0


def delete_jobs_by_filter(api_key: Optional[str] = None) -> int:
    """Bulk delete jobs, optionally filtered by api_key."""
    with get_connection() as conn:
        if api_key is not None:
            cur = conn.execute("DELETE FROM jobs WHERE api_key = ?", (api_key,))
        else:
            cur = conn.execute("DELETE FROM jobs")
        conn.commit()
        return cur.rowcount


def get_job_counts_by_api_keys() -> Dict[str, int]:
    """Returns a dictionary mapping api_key -> count of jobs."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT api_key, COUNT(*) AS cnt
            FROM jobs
            WHERE api_key IS NOT NULL
            GROUP BY api_key
            """
        )
        return {row["api_key"]: row["cnt"] for row in cur.fetchall()}


def cleanup_temporary_jobs(older_than_seconds: int = 300) -> int:
    """
    Deletes all jobs where keep_job == 0 and created_at is older than older_than_seconds.
    Reclaims database pages using incremental vacuum if supported.
    """
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=older_than_seconds)).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE (keep_job = 0 OR keep_job IS NULL) AND created_at <= ?",
            (cutoff,),
        )
        count = cur.rowcount
        conn.commit()
        return count


# Initialize tables on import
init_db()
