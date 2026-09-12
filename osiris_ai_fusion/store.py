from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from config import get_settings
from provenance import sha256_hex


class FusionStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or get_settings().store_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, title TEXT NOT NULL,
                    status TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, case_id TEXT,
                    query TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL,
                    completed_at INTEGER, result_json TEXT, result_digest TEXT
                );
                CREATE TABLE IF NOT EXISTS watchlists (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
                    query TEXT NOT NULL, scope_json TEXT NOT NULL, allowed_tools_json TEXT,
                    cadence_seconds INTEGER NOT NULL, min_confidence REAL NOT NULL,
                    enabled INTEGER NOT NULL, last_run_at INTEGER, next_run_at INTEGER,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY, watchlist_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    severity TEXT NOT NULL, summary TEXT NOT NULL, result_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_investigations_workspace
                    ON investigations(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_watchlists_due
                    ON watchlists(enabled, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_alerts_workspace
                    ON alerts(workspace_id, created_at DESC);
                """
            )
            conn.commit()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:20]}"

    def create_case(self, title: str, workspace_id: str = "default") -> dict[str, Any]:
        now = int(time.time())
        case_id = self._id("case")
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO cases VALUES (?, ?, ?, 'open', ?, ?)",
                (case_id, workspace_id, title, now, now),
            )
            conn.commit()
        return self.get_case(case_id)

    def get_case(self, case_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        return dict(row)

    def list_cases(self, workspace_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cases WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def start_investigation(self, query: str, workspace_id: str = "default", case_id: str | None = None) -> str:
        investigation_id = self._id("inv")
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO investigations(id, workspace_id, case_id, query, status, created_at) VALUES (?, ?, ?, ?, 'running', ?)",
                (investigation_id, workspace_id, case_id, query, now),
            )
            conn.commit()
        return investigation_id

    def finish_investigation(self, investigation_id: str, result: dict[str, Any]) -> None:
        now = int(time.time())
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
        digest = sha256_hex(result)
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE investigations SET status='completed', completed_at=?, result_json=?, result_digest=? WHERE id=?",
                (now, payload, digest, investigation_id),
            )
            conn.commit()

    def fail_investigation(self, investigation_id: str, error: str) -> None:
        payload = json.dumps({"error": error}, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE investigations SET status='failed', completed_at=?, result_json=? WHERE id=?",
                (int(time.time()), payload, investigation_id),
            )
            conn.commit()

    def list_investigations(self, workspace_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, workspace_id, case_id, query, status, created_at, completed_at, result_digest FROM investigations WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_watchlist(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        watch_id = self._id("watch")
        cadence = int(payload.get("cadence_seconds", 3600))
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO watchlists VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)",
                (watch_id, payload.get("workspace_id", "default"), payload["name"], payload["query"], json.dumps(payload.get("scope", {}), ensure_ascii=False), json.dumps(payload.get("allowed_tools"), ensure_ascii=False), cadence, float(payload.get("min_confidence", 0.6)), 1 if payload.get("enabled", True) else 0, now + cadence, now, now),
            )
            conn.commit()
        return self.get_watchlist(watch_id)

    def get_watchlist(self, watch_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM watchlists WHERE id=?", (watch_id,)).fetchone()
        if row is None:
            raise KeyError(watch_id)
        return self._decode_watchlist(dict(row))

    @staticmethod
    def _decode_watchlist(row: dict[str, Any]) -> dict[str, Any]:
        row["scope"] = json.loads(row.pop("scope_json") or "{}")
        raw_tools = row.pop("allowed_tools_json")
        row["allowed_tools"] = json.loads(raw_tools) if raw_tools else None
        row["enabled"] = bool(row["enabled"])
        return row

    def list_watchlists(self, workspace_id: str = "default") -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM watchlists WHERE workspace_id=? ORDER BY created_at DESC", (workspace_id,)).fetchall()
        return [self._decode_watchlist(dict(row)) for row in rows]

    def due_watchlists(self, now: int | None = None) -> list[dict[str, Any]]:
        current = now or int(time.time())
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM watchlists WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at", (current,)).fetchall()
        return [self._decode_watchlist(dict(row)) for row in rows]

    def mark_watchlist_run(self, watch_id: str, cadence_seconds: int) -> None:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE watchlists SET last_run_at=?, next_run_at=?, updated_at=? WHERE id=?", (now, now + cadence_seconds, now, watch_id))
            conn.commit()

    def create_alert(self, watchlist: dict[str, Any], summary: str, result: dict[str, Any], severity: str = "info") -> dict[str, Any] | None:
        digest = sha256_hex(result)
        with self._lock, self._connect() as conn:
            duplicate = conn.execute("SELECT id FROM alerts WHERE watchlist_id=? AND result_digest=? LIMIT 1", (watchlist["id"], digest)).fetchone()
            if duplicate:
                return None
            alert_id = self._id("alert")
            now = int(time.time())
            conn.execute("INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)", (alert_id, watchlist["id"], watchlist["workspace_id"], severity, summary, digest, json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str), now))
            conn.commit()
        return {"id": alert_id, "result_digest": digest, "created_at": now}

    def list_alerts(self, workspace_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, watchlist_id, workspace_id, severity, summary, result_digest, acknowledged, created_at FROM alerts WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?", (workspace_id, limit)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["acknowledged"] = bool(item["acknowledged"])
            result.append(item)
        return result

    def acknowledge_alert(self, alert_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))
            conn.commit()
            return cursor.rowcount > 0
