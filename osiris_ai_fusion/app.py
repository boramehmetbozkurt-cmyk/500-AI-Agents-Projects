from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from graph import investigate, investigate_stream
from llm import ModelRouter
from metrics import metrics
from osiris_client import FORBIDDEN_ACTIVE_PATHS, READ_ONLY_TOOLS, OsirisClient, tool_catalog
from rate_limit import InMemoryRateLimiter
from schemas import CaseCreate, InvestigationRequestModel, WatchlistCreate
from seal import verify_receipt
from source_policy import policy_report
from store import FusionStore
from watcher import run_watcher

logger = logging.getLogger("osiris_fusion")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()
rate_limiter = InMemoryRateLimiter(settings.request_limit_per_minute)
store = FusionStore(settings.store_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    watcher_task: asyncio.Task[None] | None = None
    if settings.watcher_enabled:
        watcher_task = asyncio.create_task(run_watcher(store, settings.watcher_poll_seconds))
    try:
        yield
    finally:
        if watcher_task:
            watcher_task.cancel()
            with suppress(asyncio.CancelledError):
                await watcher_task


app = FastAPI(
    title="OSIRIS Fusion",
    version="1.0.0",
    description="Evidence-first, authorization-aware, read-only AI intelligence operating system.",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    )


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    if not settings.api_key:
        return "development"
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return "authenticated"


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or secrets.token_hex(12)
    started = time.monotonic()
    if request.url.path.startswith("/investigate"):
        identity = request.headers.get("X-API-Key") or (
            request.client.host if request.client else "unknown"
        )
        allowed, retry_after = await rate_limiter.allow(identity)
        if not allowed:
            metrics.inc("rate_limited")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "request_id": request_id},
                headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
            )
    try:
        response = await call_next(request)
    except Exception:
        metrics.inc("unhandled_errors")
        logger.exception("unhandled_request_error request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' "
        "'unsafe-inline' https://unpkg.com; img-src 'self' data: https:; connect-src 'self'; "
        "font-src 'self' data:; frame-ancestors 'none'"
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    metrics.inc(f"http_{response.status_code}")
    logger.info(
        "request_complete request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "osiris-fusion", "version": app.version}


@app.get("/ready")
async def ready(_: str = Depends(require_api_key)) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "ready", "dependencies": {}}
    try:
        async with OsirisClient() as client:
            result["dependencies"]["osiris"] = await client.health()
    except Exception as exc:
        result["status"] = "degraded"
        result["dependencies"]["osiris"] = {"status": "unreachable", "error_type": type(exc).__name__}
    try:
        result["dependencies"]["llm"] = await ModelRouter().health()
    except Exception as exc:
        result["status"] = "degraded"
        result["dependencies"]["llm"] = {"status": "unreachable", "error_type": type(exc).__name__}
    return result


@app.get("/osiris-contract")
async def osiris_contract(_: str = Depends(require_api_key)) -> dict[str, Any]:
    async with OsirisClient() as client:
        return await client.passive_contract_probe()


@app.get("/tools")
async def tools(_: str = Depends(require_api_key)) -> dict[str, Any]:
    return {
        "mode": "read-only",
        "tools": tool_catalog(),
        "forbidden_active_paths": sorted(FORBIDDEN_ACTIVE_PATHS),
        "excluded_capabilities": [
            "active_scanning", "exploitation", "credential_access",
            "intrusive_surveillance", "face_recognition_tracking",
        ],
    }


@app.get("/providers")
async def providers(_: str = Depends(require_api_key)) -> dict[str, Any]:
    return {
        "commercial_mode": settings.commercial_mode,
        "strict_commercial_sources": settings.strict_commercial_sources,
        "licensed_providers": sorted(settings.licensed_providers),
        "policies": policy_report(READ_ONLY_TOOLS),
    }


@app.post("/investigate")
async def investigate_route(body: InvestigationRequestModel, request: Request, _: str = Depends(require_api_key)):
    investigation_id = ""
    if body.save:
        investigation_id = store.start_investigation(
            body.query,
            workspace_id=body.scope.workspace_id,
            case_id=body.scope.case_id,
        )
    try:
        result = await investigate(
            body.query,
            requested_tools=body.allowed_tools,
            scope=body.scope.model_dump(exclude_none=True),
        )
        result["request_id"] = request.headers.get("X-Request-ID") or "generated-by-middleware"
        if investigation_id:
            result["investigation_id"] = investigation_id
            store.finish_investigation(investigation_id, result)
        metrics.inc("investigations_completed")
        return result
    except PermissionError as exc:
        if investigation_id:
            store.fail_investigation(investigation_id, str(exc))
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        if investigation_id:
            store.fail_investigation(investigation_id, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if investigation_id:
            store.fail_investigation(investigation_id, type(exc).__name__)
        raise


@app.post("/investigate/stream")
async def investigate_stream_route(body: InvestigationRequestModel, _: str = Depends(require_api_key)):
    investigation_id = ""
    if body.save:
        investigation_id = store.start_investigation(
            body.query,
            workspace_id=body.scope.workspace_id,
            case_id=body.scope.case_id,
        )

    async def events():
        try:
            async for event in investigate_stream(
                body.query,
                requested_tools=body.allowed_tools,
                scope=body.scope.model_dump(exclude_none=True),
            ):
                if event.get("stage") == "complete":
                    final = event.get("result")
                    if isinstance(final, dict) and investigation_id:
                        final["investigation_id"] = investigation_id
                        store.finish_investigation(investigation_id, final)
                payload = json.dumps(event, ensure_ascii=False, default=str)
                yield "event: fusion\ndata: " + payload + "\n\n"
            metrics.inc("investigations_streamed")
        except Exception as exc:
            if investigation_id:
                store.fail_investigation(investigation_id, type(exc).__name__)
            payload = {"stage": "error", "error": type(exc).__name__, "detail": str(exc)[:500]}
            yield "event: fusion\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/receipts/verify")
async def receipt_verify(receipt: dict[str, Any], _: str = Depends(require_api_key)) -> dict[str, bool]:
    return {"valid_signature": verify_receipt(receipt)}


@app.post("/cases")
async def create_case(body: CaseCreate, _: str = Depends(require_api_key)) -> dict[str, Any]:
    return store.create_case(body.title, body.workspace_id)


@app.get("/cases")
async def list_cases(workspace_id: str = Query(default="default", max_length=100), _: str = Depends(require_api_key)) -> list[dict[str, Any]]:
    return store.list_cases(workspace_id)


@app.get("/investigations")
async def list_investigations(workspace_id: str = Query(default="default", max_length=100), _: str = Depends(require_api_key)) -> list[dict[str, Any]]:
    return store.list_investigations(workspace_id)


@app.post("/watchlists")
async def create_watchlist(body: WatchlistCreate, _: str = Depends(require_api_key)) -> dict[str, Any]:
    return store.create_watchlist(body.model_dump())


@app.get("/watchlists")
async def list_watchlists(workspace_id: str = Query(default="default", max_length=100), _: str = Depends(require_api_key)) -> list[dict[str, Any]]:
    return store.list_watchlists(workspace_id)


@app.get("/alerts")
async def list_alerts(workspace_id: str = Query(default="default", max_length=100), _: str = Depends(require_api_key)) -> list[dict[str, Any]]:
    return store.list_alerts(workspace_id)


@app.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, _: str = Depends(require_api_key)) -> dict[str, bool]:
    return {"acknowledged": store.acknowledge_alert(alert_id)}


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics(_: str = Depends(require_api_key)) -> str:
    return metrics.render_prometheus()


if settings.ui_enabled and settings.ui_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.ui_dir / "assets"), name="fusion-assets")

    @app.get("/", include_in_schema=False)
    async def ui_index():
        return FileResponse(settings.ui_dir / "index.html")
