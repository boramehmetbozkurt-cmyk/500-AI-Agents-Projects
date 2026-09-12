from __future__ import annotations

import asyncio
import logging

from graph import investigate
from store import FusionStore

logger = logging.getLogger("osiris_fusion.watcher")


async def run_watcher(store: FusionStore, poll_seconds: int) -> None:
    while True:
        try:
            for watchlist in store.due_watchlists():
                try:
                    result = await investigate(
                        watchlist["query"],
                        requested_tools=watchlist.get("allowed_tools"),
                        scope=watchlist.get("scope", {}),
                    )
                    report = result.get("report", {})
                    confidence = float(report.get("overall_confidence", 0.0))
                    claims = report.get("claims", [])
                    if confidence >= float(watchlist["min_confidence"]) and claims:
                        store.create_alert(
                            watchlist,
                            summary=str(report.get("bluf", "OSIRIS Fusion watchlist update"))[:1000],
                            result=result,
                            severity="attention" if confidence >= 0.8 else "info",
                        )
                except Exception:
                    logger.exception("watchlist_run_failed watchlist_id=%s", watchlist["id"])
                finally:
                    store.mark_watchlist_run(watchlist["id"], int(watchlist["cadence_seconds"]))
        except Exception:
            logger.exception("watcher_iteration_failed")
        await asyncio.sleep(poll_seconds)
