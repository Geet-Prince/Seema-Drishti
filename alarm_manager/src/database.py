"""
alarm_manager/src/database.py  (v2 — high-performance SQLite)

Key improvements over v1:
  - Persistent WAL-mode connection (no open/close per query)
  - PRAGMA synchronous=NORMAL  → fsync only at checkpoints, not every commit
  - Batched activity_log inserts (flush every 50 rows or 2 seconds)
  - Indexes on created_at for fast time-ordered queries
  - Thread-safe write lock for the shared singleton connection
  - Compact JSON serialization (no indent/whitespace)
"""
from __future__ import annotations
import json
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "events.db"

# ── Singleton connection ────────────────────────────────────────────────────
_conn: Optional[sqlite3.Connection] = None
_conn_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    """Return the persistent WAL-mode SQLite connection (creates once)."""
    global _conn
    if _conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # WAL = concurrent readers + one writer, no read-lock blocking writes
        _conn.execute("PRAGMA journal_mode=WAL")
        # NORMAL = fsync only at WAL checkpoints (~every 1000 pages), not every commit
        _conn.execute("PRAGMA synchronous=NORMAL")
        # 64 MB page cache in memory
        _conn.execute("PRAGMA cache_size=-65536")
        # Temp tables/indexes in RAM
        _conn.execute("PRAGMA temp_store=MEMORY")
        _conn.commit()
    return _conn


# ── Write buffer for activity_log ───────────────────────────────────────────
_activity_buf: deque = deque()
_activity_lock = threading.Lock()
_FLUSH_ROWS = 50          # flush every N rows …
_FLUSH_SECS = 2.0         # … or every N seconds, whichever comes first
_last_flush: float = time.time()


def _flush_activity() -> None:
    """Write all buffered activity_log rows in a single transaction."""
    global _last_flush
    with _activity_lock:
        if not _activity_buf:
            return
        rows = list(_activity_buf)
        _activity_buf.clear()

    with _conn_lock:
        conn = get_connection()
        conn.executemany(
            """INSERT INTO activity_log
               (camera_id, module, track_id, object_type, confidence,
                bbox, attributes, frame_id, score, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    _last_flush = time.time()


def _maybe_flush() -> None:
    """Flush if the buffer is large enough or old enough."""
    with _activity_lock:
        buf_len = len(_activity_buf)
    if buf_len >= _FLUSH_ROWS or (time.time() - _last_flush) >= _FLUSH_SECS:
        _flush_activity()


# ── Schema + indexes ────────────────────────────────────────────────────────
def init_db() -> None:
    """Create tables and indexes if they don't exist (idempotent)."""
    with _conn_lock:
        conn = get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id   TEXT,
                module      TEXT,
                track_id    TEXT,
                object_type TEXT,
                confidence  REAL,
                bbox        TEXT,
                attributes  TEXT,
                frame_id    INTEGER,
                score       INTEGER DEFAULT 0,
                created_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id        TEXT PRIMARY KEY,
                event_type      TEXT,
                severity        TEXT,
                camera_id       TEXT,
                track_id        TEXT,
                danger_score    INTEGER,
                snapshot_path   TEXT,
                module          TEXT,
                attributes      TEXT,
                status          TEXT DEFAULT 'new',
                created_at      TEXT
            );

            CREATE TABLE IF NOT EXISTS known_personnel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                badge_number TEXT,
                image_path TEXT,
                embedding_json TEXT
            );

            CREATE TABLE IF NOT EXISTS vehicle_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate TEXT NOT NULL UNIQUE,
                owner TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT
            );

            -- Indexes for fast time-ordered and per-camera reads
            CREATE INDEX IF NOT EXISTS idx_activity_created
                ON activity_log(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_activity_cam_created
                ON activity_log(camera_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_created
                ON events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_cam_created
                ON events(camera_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_severity
                ON events(severity, created_at DESC);
        """)
        conn.commit()


# ── Public write helpers ────────────────────────────────────────────────────
def log_activity(
    camera_id: str, module: str, track_id: str,
    object_type: str, confidence: float, bbox: tuple,
    attributes: dict, frame_id: int, score: int,
) -> None:
    """Buffer an activity_log row; flushes in batch for performance."""
    row = (
        camera_id, module, track_id, object_type, confidence,
        # Compact bbox string avoids json.dumps overhead for a 4-int tuple
        f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}" if len(bbox) == 4 else json.dumps(bbox),
        json.dumps(attributes, separators=(",", ":")),
        frame_id, score,
        datetime.now(timezone.utc).isoformat(),
    )
    with _activity_lock:
        _activity_buf.append(row)
    _maybe_flush()


def log_event(
    event_id: str, event_type: str, severity: str, camera_id: str,
    track_id: str, danger_score: int, snapshot_path: str,
    module: str, attributes: dict,
) -> None:
    """Upsert an event row immediately (events are infrequent, ~1/alert)."""
    with _conn_lock:
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO events
               (event_id, event_type, severity, camera_id, track_id,
                danger_score, snapshot_path, module, attributes, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,'new',?)""",
            (
                event_id, event_type, severity, camera_id, track_id,
                danger_score, snapshot_path, module,
                json.dumps(attributes, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def get_recent_events(limit: int = 50) -> list[dict]:
    """Return the N most recent events, using the indexed created_at column."""
    # Use a separate read connection so reads don't block the write lock.
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    rconn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    rconn.row_factory = sqlite3.Row
    rconn.execute("PRAGMA journal_mode=WAL")
    try:
        rows = rconn.execute(
            "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        rconn.close()


def get_stats() -> dict:
    """Return real-time counts from the database."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    rconn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    try:
        cur = rconn.cursor()
        cur.execute("SELECT COUNT(*) FROM events")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM events WHERE severity='medium'")
        medium = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM events WHERE severity='high'")
        high = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM events WHERE severity='critical'")
        critical = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM activity_log WHERE object_type='human'")
        humans = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM activity_log WHERE object_type='vehicle'")
        vehicles = cur.fetchone()[0]

        return {
            "events":    {"value": total, "label": "Total Events"},
            "humans":    {"value": humans, "label": "Total Humans Detected"},
            "vehicles":  {"value": vehicles, "label": "Total Vehicles Detected"},
            "medium":    {"value": medium, "label": "Medium Severity"},
            "high":      {"value": high, "label": "High Severity"},
            "critical":  {"value": critical, "label": "Critical Severity"},
        }
    finally:
        rconn.close()

def insert_known_personnel(name: str, badge_number: str, image_path: str, embedding: list[float]) -> int:
    with _conn_lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO known_personnel (name, badge_number, image_path, embedding_json) VALUES (?, ?, ?, ?)",
            (name, badge_number, image_path, json.dumps(embedding))
        )
        conn.commit()
        return cur.lastrowid

def get_all_known_personnel() -> list[dict]:
    init_db()
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    rconn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    rconn.row_factory = sqlite3.Row
    try:
        rows = rconn.execute("SELECT * FROM known_personnel").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['embedding'] = json.loads(d['embedding_json']) if d['embedding_json'] else []
            del d['embedding_json']
            result.append(d)
        return result
    except sqlite3.OperationalError:
        return []
    finally:
        rconn.close()


# ── Number-plate watchlist ────────────────────────────────────────────────
import re as _re

def normalize_plate(plate: str) -> str:
    """Canonical plate form: uppercase alphanumeric only (spaces/dashes removed)."""
    return _re.sub(r'[^A-Z0-9]', '', (plate or '').upper())


def add_watchlist_plate(plate: str, owner: str = "", notes: str = "") -> dict:
    """Insert (or update) a watchlist plate. Returns the stored row."""
    norm = normalize_plate(plate)
    if len(norm) < 4:
        raise ValueError("Plate number too short (min 4 characters).")
    init_db()
    with _conn_lock:
        conn = get_connection()
        conn.execute(
            """INSERT INTO vehicle_watchlist (plate, owner, notes, created_at)
               VALUES (?,?,?,?)
               ON CONFLICT(plate) DO UPDATE SET owner=excluded.owner, notes=excluded.notes""",
            (norm, owner or "", notes or "", datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM vehicle_watchlist WHERE plate=?", (norm,)).fetchone()
        return dict(row)


def remove_watchlist_plate(plate: str) -> bool:
    norm = normalize_plate(plate)
    init_db()
    with _conn_lock:
        conn = get_connection()
        cur = conn.execute("DELETE FROM vehicle_watchlist WHERE plate=?", (norm,))
        conn.commit()
        return cur.rowcount > 0


def get_watchlist_plates() -> list[dict]:
    """Return all watchlist rows (plates already stored normalized)."""
    init_db()
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    rconn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    rconn.row_factory = sqlite3.Row
    try:
        try:
            rows = rconn.execute("SELECT * FROM vehicle_watchlist ORDER BY created_at DESC").fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]
    finally:
        rconn.close()
