import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads_accounts (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    threads_user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    token_cipher TEXT NOT NULL,
                    expires_at TEXT,
                    scopes TEXT NOT NULL DEFAULT '',
                    connected_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS queue_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_thread_id TEXT NOT NULL UNIQUE,
                    target_username TEXT NOT NULL DEFAULT '',
                    target_text TEXT NOT NULL DEFAULT '',
                    permalink TEXT NOT NULL DEFAULT '',
                    reply_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','approved','sending','sent','failed','skipped')),
                    error TEXT,
                    published_reply_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);
                """
            )

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def save_account(
        self,
        *,
        threads_user_id: str,
        username: str,
        token_cipher: str,
        expires_at: str | None,
        scopes: str,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO threads_accounts
                    (id, threads_user_id, username, token_cipher, expires_at, scopes, connected_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    threads_user_id=excluded.threads_user_id,
                    username=excluded.username,
                    token_cipher=excluded.token_cipher,
                    expires_at=excluded.expires_at,
                    scopes=excluded.scopes,
                    updated_at=excluded.updated_at
                """,
                (threads_user_id, username, token_cipher, expires_at, scopes, now, now),
            )

    def get_account(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM threads_accounts WHERE id=1").fetchone()
        return self._dict(row)

    def disconnect_account(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM threads_accounts WHERE id=1")

    def add_queue_item(
        self,
        *,
        target_thread_id: str,
        target_username: str,
        target_text: str,
        permalink: str,
        reply_text: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO queue_items
                    (target_thread_id, target_username, target_text, permalink, reply_text, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)
                ON CONFLICT(target_thread_id) DO UPDATE SET
                    target_username=excluded.target_username,
                    target_text=excluded.target_text,
                    permalink=excluded.permalink,
                    reply_text=CASE WHEN queue_items.status='sent' THEN queue_items.reply_text ELSE excluded.reply_text END,
                    status=CASE WHEN queue_items.status='sent' THEN 'sent' ELSE 'draft' END,
                    error=CASE WHEN queue_items.status='sent' THEN queue_items.error ELSE NULL END,
                    updated_at=excluded.updated_at
                """,
                (
                    target_thread_id,
                    target_username,
                    target_text[:5000],
                    permalink,
                    reply_text,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM queue_items WHERE target_thread_id=?", (target_thread_id,)
            ).fetchone()
        return dict(row)

    def list_queue(self, *, include_sent: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        clause = "" if include_sent else "WHERE status != 'sent'"
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM queue_items {clause} ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_queue_items(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM queue_items WHERE id IN ({placeholders}) ORDER BY id", ids
            ).fetchall()
        by_id = {int(row["id"]): dict(row) for row in rows}
        return [by_id[item_id] for item_id in ids if item_id in by_id]

    def update_queue_item(self, item_id: int, **fields: Any) -> dict[str, Any] | None:
        allowed = {"reply_text", "status", "error", "published_reply_id", "sent_at"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_queue_item(item_id)
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in updates)
        values = [*updates.values(), item_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE queue_items SET {assignments} WHERE id=?", values)
            row = conn.execute("SELECT * FROM queue_items WHERE id=?", (item_id,)).fetchone()
        return self._dict(row)

    def get_queue_item(self, item_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM queue_items WHERE id=?", (item_id,)).fetchone()
        return self._dict(row)

    def delete_queue_item(self, item_id: int) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM queue_items WHERE id=? AND status NOT IN ('sending','sent')", (item_id,)
            )
        return cursor.rowcount > 0

    def sent_today_count(self, timezone_name: str = "UTC") -> int:
        try:
            timezone = ZoneInfo(timezone_name)
        except Exception:
            timezone = UTC
        now_local = datetime.now(timezone)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_local.astimezone(UTC).isoformat()
        end_utc = (start_local + timedelta(days=1)).astimezone(UTC).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM queue_items WHERE status='sent' AND sent_at>=? AND sent_at<?",
                (start_utc, end_utc),
            ).fetchone()
        return int(row["count"])

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM queue_items
                WHERE status IN ('sent','failed','skipped')
                ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_event(self, event_type: str, message: str, detail: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO audit_events(event_type,message,detail_json,created_at) VALUES(?,?,?,?)",
                (event_type, message, json.dumps(detail or {}, ensure_ascii=False), utc_now()),
            )

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
