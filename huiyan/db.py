"""SQLite 持久层:健康指标 + 识物记录。纯标准库,线程安全。"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import date

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "huiyan.db")


def today() -> str:
    return date.today().isoformat()


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("HUIYAN_DB") or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT,
                    date TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    title TEXT,
                    content TEXT,
                    date TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )
                """
            )
            self.conn.commit()

    # ---------- 健康指标 ----------
    def save_metric(self, name: str, value: float, unit: str = "", date: str = "") -> int:
        date = date or today()
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO metrics (name, value, unit, date) VALUES (?,?,?,?)",
                (name.strip(), round(float(value), 2), unit.strip(), date),
            )
            self.conn.commit()
            return cur.lastrowid

    def query_metrics(self, name: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM metrics WHERE name = ? ORDER BY date DESC, id DESC LIMIT ?",
                (name.strip(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_metrics(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM metrics ORDER BY date DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---------- 识物记录 ----------
    def save_note(self, category: str, title: str, content: str, date: str = "") -> int:
        date = date or today()
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO notes (category, title, content, date) VALUES (?,?,?,?)",
                (category.strip(), title.strip(), content.strip(), date),
            )
            self.conn.commit()
            return cur.lastrowid

    def list_notes(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM notes ORDER BY date DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
