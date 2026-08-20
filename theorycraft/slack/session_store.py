from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SlackSession:
    thread_ts: str
    channel: str
    session_name: str
    session_db_path: str
    thread_id: str
    status: str  # "waiting" | "running" | "complete"


class SlackSessionStore:
    """SQLite-backed map of Slack thread_ts → theorycraft session."""

    def __init__(self, db_path: Path) -> None:
        self._db = str(db_path)
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self._db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    thread_ts       TEXT PRIMARY KEY,
                    channel         TEXT NOT NULL,
                    session_name    TEXT NOT NULL,
                    session_db_path TEXT NOT NULL,
                    thread_id       TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'waiting'
                )
            """)

    def get(self, thread_ts: str) -> Optional[SlackSession]:
        with sqlite3.connect(self._db) as conn:
            row = conn.execute(
                "SELECT thread_ts, channel, session_name, session_db_path, thread_id, status "
                "FROM sessions WHERE thread_ts = ?",
                (thread_ts,),
            ).fetchone()
        return SlackSession(*row) if row else None

    def create(
        self,
        thread_ts: str,
        channel: str,
        session_name: str,
        session_db_path: str,
        thread_id: str,
    ) -> SlackSession:
        with sqlite3.connect(self._db) as conn:
            conn.execute(
                "INSERT INTO sessions "
                "(thread_ts, channel, session_name, session_db_path, thread_id, status) "
                "VALUES (?, ?, ?, ?, ?, 'waiting')",
                (thread_ts, channel, session_name, session_db_path, thread_id),
            )
        return SlackSession(thread_ts, channel, session_name, session_db_path, thread_id, "waiting")

    def set_status(self, thread_ts: str, status: str) -> None:
        with sqlite3.connect(self._db) as conn:
            conn.execute(
                "UPDATE sessions SET status = ? WHERE thread_ts = ?",
                (status, thread_ts),
            )

    def list_active(self) -> list[SlackSession]:
        with sqlite3.connect(self._db) as conn:
            rows = conn.execute(
                "SELECT thread_ts, channel, session_name, session_db_path, thread_id, status "
                "FROM sessions WHERE status != 'complete'"
            ).fetchall()
        return [SlackSession(*r) for r in rows]
