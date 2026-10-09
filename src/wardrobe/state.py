"""Runtime state in SQLite: wear log, preferences, location, OAuth, renders.

Kept apart from the wardrobe folder so the server never clutters it.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS wears (
    id INTEGER PRIMARY KEY,
    outfit_id TEXT NOT NULL,
    day TEXT NOT NULL,
    item_id TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    place TEXT,
    temp_min REAL,
    temp_max REAL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS wears_item ON wears(item_id, day);
CREATE INDEX IF NOT EXISTS wears_day ON wears(day);
CREATE TABLE IF NOT EXISTS prefs (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS location (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    name TEXT,
    tz TEXT,
    source TEXT,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    data TEXT NOT NULL,
    expires_at REAL,
    PRIMARY KEY (kind, key)
);
CREATE TABLE IF NOT EXISTS renders (
    token TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


@dataclass
class Location:
    lat: float
    lon: float
    name: str | None
    tz: str | None
    source: str
    updated_at: float

    def age_text(self, now: float | None = None) -> str:
        seconds = (now or time.time()) - self.updated_at
        if seconds < 90:
            return "just now"
        if seconds < 3600:
            return f"{int(seconds // 60)} min ago"
        if seconds < 86400 * 2:
            return f"{int(seconds // 3600)} h ago"
        return f"{int(seconds // 86400)} days ago"


class State:
    def __init__(self, state_dir: Path):
        self.dir = state_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.dir / "state.db", check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def _exec(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, params)

    # ------------------------------------------------------------------ secrets

    def secret(self, name: str) -> str:
        """A random secret generated once and kept in the state DB."""
        with self._lock:
            row = self._exec("SELECT value FROM kv WHERE key = ?", (f"secret:{name}",)).fetchone()
            if row:
                return row["value"]
            value = secrets.token_urlsafe(32)
            self._exec("INSERT INTO kv(key, value) VALUES (?, ?)", (f"secret:{name}", value))
            return value

    # ------------------------------------------------------------------ wears

    def log_wear(
        self,
        item_ids: list[str],
        day: date,
        place: str | None = None,
        temp_min: float | None = None,
        temp_max: float | None = None,
        note: str | None = None,
    ) -> str:
        outfit_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            # Saying it again for the same day replaces that day's entry for those items.
            self._exec(
                f"DELETE FROM wears WHERE day = ? AND item_id IN ({','.join('?' * len(item_ids))})",
                (day.isoformat(), *item_ids),
            )
            for item_id in item_ids:
                self._exec(
                    "INSERT INTO wears(outfit_id, day, item_id, logged_at, place, temp_min, temp_max, note)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (outfit_id, day.isoformat(), item_id, now, place, temp_min, temp_max, note),
                )
        return outfit_id

    def last_worn(self) -> dict[str, date]:
        rows = self._exec("SELECT item_id, MAX(day) AS day FROM wears GROUP BY item_id").fetchall()
        return {r["item_id"]: date.fromisoformat(r["day"]) for r in rows}

    def wear_counts(self) -> dict[str, int]:
        rows = self._exec("SELECT item_id, COUNT(DISTINCT day) AS n FROM wears GROUP BY item_id").fetchall()
        return {r["item_id"]: r["n"] for r in rows}

    def recent_outfits(self, since: date) -> list[dict[str, Any]]:
        rows = self._exec(
            "SELECT day, outfit_id, group_concat(item_id) AS items, MAX(place) AS place"
            " FROM wears WHERE day >= ? GROUP BY day, outfit_id ORDER BY day DESC",
            (since.isoformat(),),
        ).fetchall()
        return [{"day": r["day"], "items": r["items"].split(","), "place": r["place"]} for r in rows]

    def wear_history(self) -> list[dict[str, Any]]:
        rows = self._exec("SELECT day, item_id, place, temp_min, temp_max FROM wears ORDER BY day").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ prefs

    def add_pref(self, text: str) -> int:
        cur = self._exec(
            "INSERT INTO prefs(text, created_at) VALUES (?, ?)",
            (text.strip(), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        return int(cur.lastrowid or 0)

    def remove_pref(self, pref_id: int) -> bool:
        return self._exec("DELETE FROM prefs WHERE id = ?", (pref_id,)).rowcount > 0

    def prefs(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._exec("SELECT id, text FROM prefs ORDER BY id").fetchall()]

    # ------------------------------------------------------------------ location

    def set_location(self, lat: float, lon: float, name: str | None, source: str, tz: str | None = None) -> None:
        self._exec(
            "INSERT INTO location(id, lat, lon, name, tz, source, updated_at) VALUES (1, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, name=excluded.name,"
            " tz=excluded.tz, source=excluded.source, updated_at=excluded.updated_at",
            (lat, lon, name, tz, source, time.time()),
        )

    def location(self) -> Location | None:
        row = self._exec("SELECT lat, lon, name, tz, source, updated_at FROM location WHERE id = 1").fetchone()
        return Location(**dict(row)) if row else None

    # ------------------------------------------------------------------ oauth

    def oauth_put(self, kind: str, key: str, data: dict[str, Any], expires_at: float | None) -> None:
        self._exec(
            "INSERT OR REPLACE INTO oauth(kind, key, data, expires_at) VALUES (?, ?, ?, ?)",
            (kind, key, json.dumps(data), expires_at),
        )

    def oauth_get(self, kind: str, key: str) -> dict[str, Any] | None:
        row = self._exec("SELECT data, expires_at FROM oauth WHERE kind = ? AND key = ?", (kind, key)).fetchone()
        if not row:
            return None
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            self.oauth_delete(kind, key)
            return None
        return json.loads(row["data"])

    def oauth_delete(self, kind: str, key: str) -> None:
        self._exec("DELETE FROM oauth WHERE kind = ? AND key = ?", (kind, key))

    def oauth_delete_where(self, kind: str, field: str, value: str) -> None:
        self._exec(
            "DELETE FROM oauth WHERE kind = ? AND json_extract(data, ?) = ?",
            (kind, f"$.{field}", value),
        )

    # ------------------------------------------------------------------ renders

    def add_render(self, path: Path, ttl: float = 86400) -> str:
        token = secrets.token_urlsafe(18)
        self._exec(
            "INSERT INTO renders(token, path, expires_at) VALUES (?, ?, ?)",
            (token, str(path), time.time() + ttl),
        )
        return token

    def render_path(self, token: str) -> Path | None:
        row = self._exec("SELECT path, expires_at FROM renders WHERE token = ?", (token,)).fetchone()
        if not row or row["expires_at"] < time.time():
            return None
        return Path(row["path"])

    def cleanup(self) -> None:
        now = time.time()
        with self._lock:
            for row in self._exec("SELECT path FROM renders WHERE expires_at < ?", (now,)).fetchall():
                Path(row["path"]).unlink(missing_ok=True)
            self._exec("DELETE FROM renders WHERE expires_at < ?", (now,))
            self._exec("DELETE FROM oauth WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
