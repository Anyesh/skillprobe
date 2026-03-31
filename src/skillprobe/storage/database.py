import sqlite3
from pathlib import Path
from typing import Any

from skillprobe.storage.models import Capture, CaptureStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    provider TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    request_body TEXT NOT NULL,
    response_body TEXT,
    response_status INTEGER,
    status TEXT NOT NULL,
    parsed_data TEXT,
    duration_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_captures_timestamp ON captures(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_captures_provider ON captures(provider);
"""


class Database:
    def __init__(self, path: Path):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    def initialize(self):
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        try:
            self._conn.execute("ALTER TABLE captures ADD COLUMN session TEXT DEFAULT NULL")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_captures_session ON captures(session)")
            self._conn.commit()
        except Exception:
            pass

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def list_tables(self) -> list[str]:
        cursor = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [row["name"] for row in cursor.fetchall()]

    def save_capture(self, capture: Capture) -> int:
        d = capture.to_dict()
        cursor = self._conn.execute(
            """INSERT INTO captures (timestamp, provider, method, path, request_body,
               response_body, response_status, status, parsed_data, duration_ms, session)
               VALUES (:timestamp, :provider, :method, :path, :request_body,
               :response_body, :response_status, :status, :parsed_data, :duration_ms, :session)""",
            d,
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_capture(self, capture_id: int) -> Capture | None:
        cursor = self._conn.execute("SELECT * FROM captures WHERE id = ?", (capture_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return Capture.from_dict(dict(row))

    def list_captures(self, limit: int = 50, provider: str | None = None) -> list[Capture]:
        query = "SELECT * FROM captures"
        params: list[Any] = []
        if provider:
            query += " WHERE provider = ?"
            params.append(provider)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cursor = self._conn.execute(query, params)
        return [Capture.from_dict(dict(row)) for row in cursor.fetchall()]

    def list_captures_by_session(self, session: str, limit: int = 1000) -> list[Capture]:
        cursor = self._conn.execute(
            "SELECT * FROM captures WHERE session = ? ORDER BY timestamp DESC LIMIT ?",
            (session, limit),
        )
        return [Capture.from_dict(dict(row)) for row in cursor.fetchall()]

    def list_sessions(self) -> list[str]:
        cursor = self._conn.execute(
            "SELECT DISTINCT session FROM captures WHERE session IS NOT NULL ORDER BY session"
        )
        return [row["session"] for row in cursor.fetchall()]
