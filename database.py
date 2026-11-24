"""SQLite 本地資料庫模組：負責記錄已通知項目與查詢未到期任務。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import config


@contextmanager
def _get_connection() -> Iterator[sqlite3.Connection]:
    """建立並管理 SQLite 資料庫連線，確保正常提交與關閉。"""
    conn = sqlite3.connect(str(config.DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """初始化資料庫與 notified_items 資料表。"""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notified_items (
                item_uid TEXT PRIMARY KEY,
                course_name TEXT NOT NULL,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                due_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def is_notified(uid: str) -> bool:
    """檢查指定的 item_uid 是否已經存在於資料庫（已通知過）。"""
    init_db()
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM notified_items WHERE item_uid = ? LIMIT 1",
            (uid,),
        ).fetchone()
        return row is not None


def mark_as_notified(
    item_uid: str,
    course_name: str,
    item_type: str,
    title: str,
    due_at: str | None = None,
) -> None:
    """將項目寫入 notified_items 資料表，標記為已通知。"""
    init_db()
    created_at = datetime.now(timezone.utc).isoformat()
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO notified_items
                (item_uid, course_name, item_type, title, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (item_uid, course_name, item_type, title, due_at, created_at),
        )


def _parse_iso_datetime(dt_str: str | None) -> datetime | None:
    """將 Canvas ISO-8601 時間字串解析為含時區的 datetime 物件。"""
    if not dt_str:
        return None
    try:
        normalized = dt_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def get_upcoming_items(limit: int = 20) -> list[dict[str, Any]]:
    """查詢資料庫中尚未到期的作業（assignment）與測驗（quiz），依截止時間由近到遠排序。"""
    init_db()
    now_utc = datetime.now(timezone.utc)

    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT item_uid, course_name, item_type, title, due_at, created_at
            FROM notified_items
            WHERE item_type IN ('assignment', 'quiz')
              AND due_at IS NOT NULL
              AND due_at != ''
            """
        ).fetchall()

    upcoming: list[tuple[datetime, dict[str, Any]]] = []
    for row in rows:
        due_dt = _parse_iso_datetime(row["due_at"])
        if due_dt is not None and due_dt >= now_utc:
            upcoming.append(
                (
                    due_dt,
                    {
                        "item_uid": row["item_uid"],
                        "course_name": row["course_name"],
                        "item_type": row["item_type"],
                        "title": row["title"],
                        "due_at": row["due_at"],
                        "created_at": row["created_at"],
                    },
                )
            )

    # 依截止時間由近到遠排序
    upcoming.sort(key=lambda pair: pair[0])
    return [item for _, item in upcoming[:limit]]
