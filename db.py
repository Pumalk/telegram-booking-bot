"""
Локальная база данных (SQLite). Файл создаётся автоматически рядом
с проектом: data/<клиент>.sqlite3. Наружу торчит только класс Database.
"""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time: {value}")
    return hour * 60 + minute


SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT DEFAULT '',
    client_name TEXT DEFAULT '',
    service TEXT NOT NULL,
    price INTEGER DEFAULT 0,
    duration_min INTEGER DEFAULT 0,
    day TEXT NOT NULL,              -- YYYY-MM-DD
    time TEXT NOT NULL,             -- HH:MM
    status TEXT NOT NULL DEFAULT 'active',  -- active / cancelled / done
    prepayment TEXT NOT NULL DEFAULT 'none',-- none / pending / paid
    reminded_24 INTEGER NOT NULL DEFAULT 0,
    reminded_2 INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blocked_days(
    day TEXT PRIMARY KEY            -- YYYY-MM-DD
);
CREATE TABLE IF NOT EXISTS blocked_slots(
    day TEXT NOT NULL,              -- YYYY-MM-DD
    time TEXT NOT NULL,             -- HH:MM
    PRIMARY KEY (day, time)
);
CREATE INDEX IF NOT EXISTS idx_bookings_day ON bookings(day, status);
"""


class SlotUnavailable(Exception):
    """The requested appointment slot has been taken or blocked."""


class Database:
    """Тонкая обёртка над SQLite с блокировкой для потокобезопасности."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)

    # ---------- записи ----------

    def add_booking(self, *, user_id: int, username: str, client_name: str,
                    service: str, price: int, duration_min: int,
                    day: str, time: str) -> int:
        start_min = _minutes(time)
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            if self._conn.execute(
                "SELECT 1 FROM blocked_days WHERE day=?", (day,)
            ).fetchone():
                raise SlotUnavailable
            if self._conn.execute(
                "SELECT 1 FROM blocked_slots WHERE day=? AND time=?", (day, time)
            ).fetchone():
                raise SlotUnavailable
            rows = self._conn.execute(
                """SELECT time, duration_min FROM bookings
                   WHERE day=? AND status='active'""",
                (day,),
            ).fetchall()
            for row in rows:
                booked_start = _minutes(row["time"])
                booked_end = booked_start + int(row["duration_min"])
                if start_min < booked_end and booked_start < start_min + duration_min:
                    raise SlotUnavailable
            cur = self._conn.execute(
                """INSERT INTO bookings
                   (user_id, username, client_name, service, price,
                    duration_min, day, time, prepayment, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (user_id, username, client_name, service, price,
                 duration_min, day, time, "none",
                 datetime.now().isoformat(timespec="seconds")),
            )
            return cur.lastrowid

    def get_booking(self, booking_id: int):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM bookings WHERE id=?", (booking_id,)
            ).fetchone()
        return dict(row) if row else None

    def cancel_booking(self, booking_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE bookings SET status='cancelled' WHERE id=? AND status='active'",
                (booking_id,),
            )
            return cur.rowcount > 0

    def active_on_day(self, day: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM bookings WHERE day=? AND status='active' ORDER BY time",
                (day,),
            ).fetchall()
        return [dict(r) for r in rows]

    def upcoming_active(self, limit: int = 20) -> list[dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM bookings
                   WHERE status='active' AND (day > ? OR (day = ? AND time >= ?))
                   ORDER BY day, time LIMIT ?""",
                (today, today, datetime.now().strftime("%H:%M"), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminded(self, booking_id: int, which: str) -> None:
        """which: 'reminded_24' или 'reminded_2'"""
        if which not in ("reminded_24", "reminded_2"):
            raise ValueError(which)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE bookings SET {which}=1 WHERE id=?", (booking_id,)
            )

    # ---------- блокировки расписания ----------

    def block_day(self, day: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO blocked_days(day) VALUES (?)", (day,)
            )

    def unblock_day(self, day: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM blocked_days WHERE day=?", (day,))
            self._conn.execute("DELETE FROM blocked_slots WHERE day=?", (day,))

    def is_day_blocked(self, day: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM blocked_days WHERE day=?", (day,)
            ).fetchone()
        return row is not None

    def block_slot(self, day: str, time: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO blocked_slots(day, time) VALUES (?,?)",
                (day, time),
            )

    def unblock_slot(self, day: str, time: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM blocked_slots WHERE day=? AND time=?", (day, time)
            )

    def blocked_slots_on(self, day: str) -> set[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT time FROM blocked_slots WHERE day=?", (day,)
            ).fetchall()
        return {r["time"] for r in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
