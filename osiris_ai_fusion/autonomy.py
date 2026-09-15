from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from config import get_settings

_ALLOWED_ACTIONS = {
    "followup_research",
    "create_watchlist",
    "create_case",
    "external_connector",
}
_METRIC_HINTS = {
    "evidence_coverage": "Increase evidence-bound factual coverage before synthesis.",
    "source_diversity": "Prefer independent provider families and corroborating sources.",
    "answer_completeness": "Explicitly close every objective in the cognitive plan.",
    "timeline_quality": "Prioritize dated evidence when history or evolution is requested.",
    "spatial_quality": "Prioritize source-backed geocodable locations for spatial questions.",
    "idea_quality": "Make proposals testable with risks and a concrete next experiment.",
    "confidence_calibration": "Reduce confidence when evidence strength is weak or narrow.",
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _decode(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _goal_steps(objective: str) -> list[str]:
    chunks = [
        item.strip(" .,-")
        for item in objective.replace("?", ";").replace("\n", ";").split(";")
        if len(item.strip(" .,-")) >= 5
    ]
    if len(chunks) < 2:
        chunks = [
            "Establish the current evidence baseline",
            "Resolve temporal and spatial context where supported",
            "Analyze findings and identify uncertainty",
            "Develop and test the next research direction",
        ]
    return list(dict.fromkeys(chunks))[:8]


class AutonomyStore:
    """Persistent tenant-scoped goals, learning policy, actions and telemetry.

    The store deliberately separates planning from effects. External actions are
    never executed here; they are proposals that require approval and a connector.
    """

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

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:20]}"

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS persistent_goals (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    success_criteria_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cadence_seconds INTEGER NOT NULL,
                    max_iterations INTEGER NOT NULL,
                    iterations INTEGER NOT NULL DEFAULT 0,
                    progress REAL NOT NULL DEFAULT 0,
                    last_summary TEXT,
                    last_run_at INTEGER,
                    next_run_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_goals_workspace
                    ON persistent_goals(workspace_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_goals_due
                    ON persistent_goals(status, next_run_at);

                CREATE TABLE IF NOT EXISTS goal_steps (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(goal_id) REFERENCES persistent_goals(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_goal_steps_goal
                    ON goal_steps(goal_id, ordinal);

                CREATE TABLE IF NOT EXISTS learning_policies (
                    workspace_id TEXT PRIMARY KEY,
                    observations INTEGER NOT NULL,
                    metric_ema_json TEXT NOT NULL,
                    issue_counts_json TEXT NOT NULL,
                    planner_hints_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS action_requests (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    goal_id TEXT,
                    action_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    approval_required INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    approved_at INTEGER,
                    executed_at INTEGER,
                    result_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_actions_workspace
                    ON action_requests(workspace_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS cognitive_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    value REAL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cognitive_telemetry_workspace
                    ON cognitive_telemetry(workspace_id, created_at DESC);
                """
            )
            conn.commit()

    def create_goal(
        self,
        *,
        workspace_id: str,
        title: str,
        objective: str,
        success_criteria: list[str] | None = None,
        cadence_seconds: int = 86400,
        max_iterations: int = 12,
        enabled: bool = True,
    ) -> dict[str, Any]:
        now = int(time.time())
        goal_id = self._id("goal")
        status = "active" if enabled else "paused"
        criteria = success_criteria or [
            "Answer the objective with evidence-bound claims.",
            "Expose uncertainty and unresolved data gaps.",
            "Reach a self-evaluation score of at least 0.85 before review.",
        ]
        cadence = max(3600, min(int(cadence_seconds), 2_592_000))
        iterations = max(1, min(int(max_iterations), 100))
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO persistent_goals VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, NULL, ?, ?, ?)",
                (
                    goal_id,
                    workspace_id,
                    title,
                    objective,
                    _json(criteria),
                    status,
                    cadence,
                    iterations,
                    now if enabled else None,
                    now,
                    now,
                ),
            )
            for ordinal, step in enumerate(_goal_steps(objective), start=1):
                conn.execute(
                    "INSERT INTO goal_steps VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?)",
                    (self._id("step"), goal_id, workspace_id, ordinal, step, now, now),
                )
            conn.commit()
        return self.get_goal(goal_id, workspace_id)

    def get_goal(self, goal_id: str, workspace_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM persistent_goals WHERE id=? AND workspace_id=?",
                (goal_id, workspace_id),
            ).fetchone()
            steps = conn.execute(
                "SELECT id, ordinal, title, status, result_json, created_at, updated_at "
                "FROM goal_steps WHERE goal_id=? AND workspace_id=? ORDER BY ordinal",
                (goal_id, workspace_id),
            ).fetchall()
        if row is None:
            raise KeyError(goal_id)
        result = dict(row)
        result["success_criteria"] = _decode(result.pop("success_criteria_json"), [])
        result["steps"] = []
        for step_row in steps:
            step = dict(step_row)
            step["result"] = _decode(step.pop("result_json"), None)
            result["steps"].append(step)
        return result

    def list_goals(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM persistent_goals WHERE workspace_id=? "
                "ORDER BY updated_at DESC LIMIT ?",
                (workspace_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self.get_goal(str(row["id"]), workspace_id) for row in rows]

    def due_goals(self, now: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
        current = now or int(time.time())
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, workspace_id FROM persistent_goals "
                "WHERE status='active' AND next_run_at IS NOT NULL AND next_run_at<=? "
                "AND iterations<max_iterations ORDER BY next_run_at LIMIT ?",
                (current, max(1, min(limit, 50))),
            ).fetchall()
        return [self.get_goal(str(row["id"]), str(row["workspace_id"])) for row in rows]

    def set_goal_status(self, goal_id: str, workspace_id: str, status: str) -> dict[str, Any]:
        allowed = {"active", "paused", "review", "completed", "cancelled"}
        if status not in allowed:
            raise ValueError(f"Unsupported goal status: {status}")
        now = int(time.time())
        next_run = now if status == "active" else None
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE persistent_goals SET status=?, next_run_at=?, updated_at=? "
                "WHERE id=? AND workspace_id=?",
                (status, next_run, now, goal_id, workspace_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(goal_id)
        return self.get_goal(goal_id, workspace_id)

    def goal_context(self, goal_id: str | None, workspace_id: str) -> dict[str, Any] | None:
        if not goal_id:
            return None
        goal = self.get_goal(goal_id, workspace_id)
        return {
            "id": goal["id"],
            "title": goal["title"],
            "objective": goal["objective"],
            "success_criteria": goal["success_criteria"],
            "status": goal["status"],
            "progress": goal["progress"],
            "iterations": goal["iterations"],
            "max_iterations": goal["max_iterations"],
            "steps": [
                {"ordinal": row["ordinal"], "title": row["title"], "status": row["status"]}
                for row in goal["steps"]
            ],
        }

    def record_goal_run(
        self,
        goal_id: str,
        workspace_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        goal = self.get_goal(goal_id, workspace_id)
        evaluation = result.get("self_evaluation") or {}
        report = result.get("report") or {}
        score = _clamp(float(evaluation.get("score", 0.0)))
        previous = float(goal.get("progress", 0.0))
        progress = max(previous, score)
        now = int(time.time())
        iterations = int(goal["iterations"]) + 1
        status = str(goal["status"])
        if iterations >= int(goal["max_iterations"]):
            status = "review"
        elif progress >= 0.90 and not report.get("data_gaps"):
            status = "review"
        next_run = now + int(goal["cadence_seconds"]) if status == "active" else None
        summary = str(report.get("bluf") or "")[:2000]
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE persistent_goals SET iterations=?, progress=?, last_summary=?, "
                "last_run_at=?, next_run_at=?, status=?, updated_at=? "
                "WHERE id=? AND workspace_id=?",
                (
                    iterations,
                    progress,
                    summary,
                    now,
                    next_run,
                    status,
                    now,
                    goal_id,
                    workspace_id,
                ),
            )
            if score >= 0.74:
                pending = conn.execute(
                    "SELECT id FROM goal_steps WHERE goal_id=? AND workspace_id=? "
                    "AND status='pending' ORDER BY ordinal LIMIT 1",
                    (goal_id, workspace_id),
                ).fetchone()
                if pending:
                    conn.execute(
                        "UPDATE goal_steps SET status='completed', result_json=?, updated_at=? "
                        "WHERE id=?",
                        (_json({"score": score, "summary": summary}), now, pending["id"]),
                    )
            conn.commit()
        self.record_telemetry(
            workspace_id,
            "goal_run",
            score,
            {"goal_id": goal_id, "iterations": iterations, "status": status},
        )
        return self.get_goal(goal_id, workspace_id)

    def get_learning_policy(self, workspace_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM learning_policies WHERE workspace_id=?",
                (workspace_id,),
            ).fetchone()
        if row is None:
            return {
                "observations": 0,
                "metric_ema": {},
                "issue_counts": {},
                "planner_hints": [],
                "adaptive": False,
            }
        item = dict(row)
        return {
            "observations": int(item["observations"]),
            "metric_ema": _decode(item["metric_ema_json"], {}),
            "issue_counts": _decode(item["issue_counts_json"], {}),
            "planner_hints": _decode(item["planner_hints_json"], []),
            "updated_at": item["updated_at"],
            "adaptive": True,
        }

    def observe_evaluation(
        self,
        workspace_id: str,
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        current = self.get_learning_policy(workspace_id)
        observations = int(current.get("observations", 0)) + 1
        old_metrics = dict(current.get("metric_ema") or {})
        incoming = evaluation.get("metrics") or {}
        alpha = 0.25
        metric_ema: dict[str, float] = dict(old_metrics)
        for key, value in incoming.items():
            try:
                numeric = _clamp(float(value))
            except (TypeError, ValueError):
                continue
            previous = float(old_metrics.get(key, numeric))
            metric_ema[key] = round((1.0 - alpha) * previous + alpha * numeric, 4)

        issue_counts = dict(current.get("issue_counts") or {})
        for issue in evaluation.get("issues") or []:
            key = str(issue)[:300]
            issue_counts[key] = int(issue_counts.get(key, 0)) + 1

        weak = sorted(
            (
                (key, value)
                for key, value in metric_ema.items()
                if key in _METRIC_HINTS and float(value) < 0.78
            ),
            key=lambda pair: pair[1],
        )
        hints = [_METRIC_HINTS[key] for key, _ in weak[:5]]
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO learning_policies VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(workspace_id) DO UPDATE SET "
                "observations=excluded.observations, metric_ema_json=excluded.metric_ema_json, "
                "issue_counts_json=excluded.issue_counts_json, "
                "planner_hints_json=excluded.planner_hints_json, updated_at=excluded.updated_at",
                (
                    workspace_id,
                    observations,
                    _json(metric_ema),
                    _json(issue_counts),
                    _json(hints),
                    now,
                ),
            )
            conn.commit()
        self.record_telemetry(
            workspace_id,
            "self_evaluation",
            float(evaluation.get("score", 0.0)),
            {"issues": list(evaluation.get("issues") or []), "hints": hints},
        )
        return self.get_learning_policy(workspace_id)

    def propose_action(
        self,
        *,
        workspace_id: str,
        action_type: str,
        payload: dict[str, Any],
        goal_id: str | None = None,
        risk_level: str = "low",
    ) -> dict[str, Any]:
        if action_type not in _ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported action_type: {action_type}")
        if risk_level not in {"low", "medium", "high"}:
            raise ValueError("risk_level must be low, medium, or high")
        if goal_id:
            self.get_goal(goal_id, workspace_id)
        action_id = self._id("act")
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO action_requests VALUES "
                "(?, ?, ?, ?, ?, ?, 1, 'proposed', ?, NULL, NULL, NULL)",
                (
                    action_id,
                    workspace_id,
                    goal_id,
                    action_type,
                    _json(payload),
                    risk_level,
                    now,
                ),
            )
            conn.commit()
        return self.get_action(action_id, workspace_id)

    def get_action(self, action_id: str, workspace_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM action_requests WHERE id=? AND workspace_id=?",
                (action_id, workspace_id),
            ).fetchone()
        if row is None:
            raise KeyError(action_id)
        item = dict(row)
        item["payload"] = _decode(item.pop("payload_json"), {})
        item["result"] = _decode(item.pop("result_json"), None)
        item["approval_required"] = bool(item["approval_required"])
        return item

    def list_actions(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM action_requests WHERE workspace_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (workspace_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self.get_action(str(row["id"]), workspace_id) for row in rows]

    def approve_action(self, action_id: str, workspace_id: str) -> dict[str, Any]:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE action_requests SET status='approved', approved_at=? "
                "WHERE id=? AND workspace_id=? AND status='proposed'",
                (now, action_id, workspace_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            current = self.get_action(action_id, workspace_id)
            if current["status"] != "approved":
                raise ValueError(f"Action cannot be approved from {current['status']}")
        return self.get_action(action_id, workspace_id)

    def finish_action(
        self,
        action_id: str,
        workspace_id: str,
        result: dict[str, Any],
        status: str = "executed",
    ) -> dict[str, Any]:
        if status not in {"executed", "failed", "waiting_connector"}:
            raise ValueError("Unsupported action terminal status")
        now = int(time.time())
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE action_requests SET status=?, executed_at=?, result_json=? "
                "WHERE id=? AND workspace_id=? AND status='approved'",
                (status, now, _json(result), action_id, workspace_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise ValueError("Only approved actions can execute")
        self.record_telemetry(
            workspace_id,
            "action_execution",
            1.0 if status == "executed" else 0.0,
            {"action_id": action_id, "status": status},
        )
        return self.get_action(action_id, workspace_id)

    def record_telemetry(
        self,
        workspace_id: str,
        event_type: str,
        value: float | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO cognitive_telemetry "
                "(workspace_id, event_type, value, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    workspace_id,
                    event_type,
                    value,
                    _json(payload or {}),
                    int(time.time()),
                ),
            )
            conn.commit()

    def telemetry_summary(self, workspace_id: str, hours: int = 168) -> dict[str, Any]:
        hours = max(1, min(int(hours), 24 * 90))
        since = int(time.time()) - hours * 3600
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_type, value, payload_json, created_at FROM cognitive_telemetry "
                "WHERE workspace_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 5000",
                (workspace_id, since),
            ).fetchall()
        counts: dict[str, int] = {}
        values: dict[str, list[float]] = {}
        for row in rows:
            event = str(row["event_type"])
            counts[event] = counts.get(event, 0) + 1
            if row["value"] is not None:
                values.setdefault(event, []).append(float(row["value"]))
        averages = {
            key: round(sum(items) / len(items), 4)
            for key, items in values.items()
            if items
        }
        return {
            "workspace_id": workspace_id,
            "window_hours": hours,
            "event_count": len(rows),
            "counts": counts,
            "averages": averages,
            "learning_policy": self.get_learning_policy(workspace_id),
        }
