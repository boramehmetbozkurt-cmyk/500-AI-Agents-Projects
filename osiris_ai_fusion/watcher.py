from __future__ import annotations

import asyncio
import logging

from autonomy import AutonomyStore
from graph import investigate
from sensor_mesh import ingest_investigation_result
from store import FusionStore

logger = logging.getLogger("orbythra.watcher")


async def _run_watchlists(store: FusionStore) -> None:
    for watchlist in store.due_watchlists():
        try:
            result = await investigate(
                watchlist["query"],
                requested_tools=watchlist.get("allowed_tools"),
                scope=watchlist.get("scope", {}),
            )
            workspace_id = str(watchlist.get("workspace_id") or "default")
            ingest_investigation_result(
                workspace_id,
                str(watchlist["query"]),
                result,
                sensor_id="fusion_watchlist",
            )
            report = result.get("report", {})
            confidence = float(report.get("overall_confidence", 0.0))
            claims = report.get("claims", [])
            if confidence >= float(watchlist["min_confidence"]) and claims:
                store.create_alert(
                    watchlist,
                    summary=str(report.get("bluf", "ORBYTHRA watchlist update"))[:1000],
                    result=result,
                    severity="attention" if confidence >= 0.8 else "info",
                )
        except Exception:
            logger.exception("watchlist_run_failed watchlist_id=%s", watchlist["id"])
        finally:
            store.mark_watchlist_run(watchlist["id"], int(watchlist["cadence_seconds"]))


async def _run_persistent_goals(autonomy: AutonomyStore) -> None:
    """Advance due goals with read-only research only.

    This loop is intentionally incapable of executing external connector effects.
    Side-effecting actions remain in the approval-gated action ledger and require
    a separate approved execution path.
    """

    for goal in autonomy.due_goals(limit=10):
        goal_id = str(goal["id"])
        workspace_id = str(goal.get("workspace_id") or "default")
        try:
            policy = autonomy.get_learning_policy(workspace_id)
            scope = {
                "workspace_id": workspace_id,
                "goal_id": goal_id,
                "goal_context": autonomy.goal_context(goal_id, workspace_id),
                "adaptive_policy": {
                    "observations": policy.get("observations", 0),
                    "planner_hints": list(policy.get("planner_hints") or [])[:5],
                },
                "memory_write_enabled": True,
            }
            result = await investigate(str(goal["objective"]), scope=scope)
            autonomy.record_goal_run(goal_id, workspace_id, result)
        except Exception:
            logger.exception("persistent_goal_run_failed goal_id=%s", goal_id)
            autonomy.record_telemetry(
                workspace_id,
                "goal_run_error",
                0.0,
                {"goal_id": goal_id},
            )


async def run_watcher(store: FusionStore, poll_seconds: int) -> None:
    autonomy = AutonomyStore(store.path)
    while True:
        try:
            await _run_watchlists(store)
            await _run_persistent_goals(autonomy)
        except Exception:
            logger.exception("watcher_iteration_failed")
        await asyncio.sleep(poll_seconds)
