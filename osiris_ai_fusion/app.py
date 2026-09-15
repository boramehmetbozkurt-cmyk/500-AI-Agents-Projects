from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from capabilities import (
    auto_tool_names,
    capability_catalog,
    infer_capability_names,
    likely_requires_external_data,
    resolve_capability_gap,
)
from config import get_settings
from engineering_intelligence import router as engineering_router
from graph import investigate, investigate_stream
from intelligence import router as intelligence_router
from llm import ModelRouter
from metrics import metrics
from osiris_client import FORBIDDEN_ACTIVE_PATHS, READ_ONLY_TOOLS, OsirisClient, tool_catalog
from planner import deterministic_tools
from providers import provider_catalog, provider_domains_for_query, route_providers
from rate_limit import InMemoryRateLimiter
from reality_atlas import router as reality_atlas_router
from saas import AuthContext, require_identity, router as saas_router, saas_manager
from schemas import CaseCreate, InvestigationRequestModel, WatchlistCreate
from science_edges import router as science_graph_router
from science_world import router as science_world_router
from seal import verify_receipt
from sensor_mesh import ingest_investigation_result, router as sensor_mesh_router
from source_policy import policy_report
from store import FusionStore
from watcher import run_watcher
from world import router as world_router

logger = logging.getLogger("orbythra")
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
    title="ORBYTHRA — Verifiable Temporal Reality Operating System",
    version="1.3.0",
    description=(
        "Multi-tenant public SaaS for evidence-first, authorization-aware AI research "
        "with provider federation, a verified living world model, BCE-to-future reality atlas, "
        "an evidence-bound science/genome knowledge graph, multi-layer engineering decision intelligence, "
        "and transparent proprietary world-intelligence signals."
    ),
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-API-Key",
            "X-Request-ID",
            "Stripe-Signature",
        ],
    )

if settings.saas_enabled:
    app.include_router(saas_router)

app.include_router(world_router)
app.include_router(intelligence_router)
app.include_router(engineering_router)
app.include_router(reality_atlas_router)
app.include_router(sensor_mesh_router)
app.include_router(science_world_router)
app.include_router(science_graph_router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or secrets.token_hex(12)
    started = time.monotonic()
    if request.url.path.startswith(
        ("/investigate", "/world", "/science", "/engineering", "/intelligence")
    ):
        raw_identity = (
            request.headers.get("X-API-Key")
            or request.headers.get("Authorization")
            or (request.client.host if request.client else "unknown")
        )
        identity = hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()
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
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        metrics.inc("unhandled_errors")
        metrics.inc("http_500")
        metrics.observe("http_latency_ms", elapsed_ms)
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
        "font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    metrics.inc(f"http_{response.status_code}")
    metrics.observe("http_latency_ms", elapsed_ms)
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
    return {
        "status": "ok",
        "service": "orbythra-reality-os",
        "version": app.version,
        "saas": settings.saas_enabled,
        "world": True,
        "proprietary_world_intelligence": True,
        "temporal_reality_atlas": True,
        "sensor_mesh": True,
        "science_genome_graph": True,
        "science_relationship_graph": True,
        "temporal_globe": True,
        "engineering_intelligence": True,
        "brand": "ORBYTHRA",
    }


@app.get("/ready")
async def ready(_: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    providers = provider_catalog()
    result: dict[str, Any] = {
        "status": "ready",
        "dependencies": {},
        "capabilities_ready": sorted(auto_tool_names()),
        "providers_ready": [row["provider_id"] for row in providers if row.get("ready")],
    }
    try:
        async with OsirisClient() as client:
            result["dependencies"]["orbythra_core"] = await client.health()
    except Exception as exc:
        result["status"] = "degraded"
        result["dependencies"]["orbythra_core"] = {
            "status": "unreachable",
            "error_type": type(exc).__name__,
        }
    try:
        result["dependencies"]["llm"] = await ModelRouter().health()
    except Exception as exc:
        result["status"] = "degraded"
        result["dependencies"]["llm"] = {
            "status": "unreachable",
            "error_type": type(exc).__name__,
        }
    return result


@app.get("/orbythra-contract")
async def orbythra_contract(_: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    async with OsirisClient() as client:
        return await client.passive_contract_probe()


@app.get("/osiris-contract", include_in_schema=False)
async def legacy_osiris_contract(_: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    return await orbythra_contract(_)


@app.get("/tools")
async def tools(_: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    return {
        "mode": "read-only",
        "tools": tool_catalog(),
        "forbidden_active_paths": sorted(FORBIDDEN_ACTIVE_PATHS),
        "excluded_capabilities": [
            "active_scanning",
            "exploitation",
            "credential_access",
            "intrusive_surveillance",
            "face_recognition_tracking",
        ],
    }


@app.get("/capabilities")
async def capabilities(_: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    rows = capability_catalog()
    return {
        "version": "1.3",
        "mode": "multi-tenant-provider-federated-read-only",
        "ready": [row["name"] for row in rows if row.get("ready")],
        "capabilities": rows,
        "rule": (
            "Only ready, read-only, auto_execute capabilities can run autonomously. "
            "External provider selection occurs inside provider_federation; action "
            "connectors remain approval-gated."
        ),
    }


@app.get("/capabilities/resolve")
async def resolve_capabilities(
    query: str = Query(min_length=3, max_length=4000),
    _: AuthContext = Depends(require_identity),
) -> dict[str, Any]:
    inferred = infer_capability_names(query)
    selected = deterministic_tools(query)
    routed = route_providers(query)
    return {
        "query": query,
        "selected": selected,
        "local_capability_inference": inferred,
        "provider_domains": provider_domains_for_query(query),
        "provider_route": [provider.provider_id for provider in routed],
        "external_data_likely_required": likely_requires_external_data(query),
        "capability_gaps": resolve_capability_gap(query, inferred),
        "ready_capabilities": sorted(auto_tool_names()),
    }


@app.get("/providers")
async def providers(_: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    rows = provider_catalog()
    all_tools = sorted(auto_tool_names() | set(READ_ONLY_TOOLS))
    return {
        "federation_mode": "multi-provider-read-only",
        "ready_providers": [row["provider_id"] for row in rows if row.get("ready")],
        "providers": rows,
        "commercial_mode": settings.commercial_mode,
        "strict_commercial_sources": settings.strict_commercial_sources,
        "licensed_providers": sorted(settings.licensed_providers),
        "tool_policies": policy_report(all_tools),
        "rule": (
            "Provider URLs come only from trusted built-ins, environment configuration "
            "or administrator manifests; user prompts cannot supply execution URLs."
        ),
    }


def _tenant_scope(body: InvestigationRequestModel, auth: AuthContext) -> dict[str, Any]:
    scope = body.scope.model_dump(exclude_none=True)
    scope["workspace_id"] = auth.tenant_id
    return scope


@app.post("/investigate")
async def investigate_route(
    body: InvestigationRequestModel,
    request: Request,
    auth: AuthContext = Depends(require_identity),
):
    try:
        saas_manager.reserve_investigation(auth)
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    scope = _tenant_scope(body, auth)
    investigation_id = ""
    if body.save:
        investigation_id = store.start_investigation(
            body.query,
            workspace_id=auth.tenant_id,
            case_id=body.scope.case_id,
        )
    try:
        result = await investigate(
            body.query,
            requested_tools=body.allowed_tools,
            scope=scope,
        )
        result["request_id"] = request.headers.get("X-Request-ID") or "generated-by-middleware"
        result["workspace_id"] = auth.tenant_id
        result["world_ingest"] = ingest_investigation_result(auth.tenant_id, body.query, result)
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
async def investigate_stream_route(
    body: InvestigationRequestModel,
    auth: AuthContext = Depends(require_identity),
):
    try:
        saas_manager.reserve_investigation(auth)
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    scope = _tenant_scope(body, auth)
    investigation_id = ""
    if body.save:
        investigation_id = store.start_investigation(
            body.query,
            workspace_id=auth.tenant_id,
            case_id=body.scope.case_id,
        )

    async def events():
        try:
            async for event in investigate_stream(
                body.query,
                requested_tools=body.allowed_tools,
                scope=scope,
            ):
                if event.get("stage") == "complete":
                    final = event.get("result")
                    if isinstance(final, dict):
                        final["workspace_id"] = auth.tenant_id
                        final["world_ingest"] = ingest_investigation_result(
                            auth.tenant_id,
                            body.query,
                            final,
                        )
                        if investigation_id:
                            final["investigation_id"] = investigation_id
                            store.finish_investigation(investigation_id, final)
                payload = json.dumps(event, ensure_ascii=False, default=str)
                yield "event: fusion\ndata: " + payload + "\n\n"
            metrics.inc("investigations_streamed")
        except Exception as exc:
            if investigation_id:
                store.fail_investigation(investigation_id, type(exc).__name__)
            payload = {
                "stage": "error",
                "error": type(exc).__name__,
                "detail": str(exc)[:500],
            }
            yield "event: fusion\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/receipts/verify")
async def receipt_verify(
    receipt: dict[str, Any],
    _: AuthContext = Depends(require_identity),
) -> dict[str, bool]:
    return {"valid_signature": verify_receipt(receipt)}


@app.post("/cases")
async def create_case(
    body: CaseCreate,
    auth: AuthContext = Depends(require_identity),
) -> dict[str, Any]:
    return store.create_case(body.title, auth.tenant_id)


@app.get("/cases")
async def list_cases(auth: AuthContext = Depends(require_identity)) -> list[dict[str, Any]]:
    return store.list_cases(auth.tenant_id)


@app.get("/investigations")
async def list_investigations(auth: AuthContext = Depends(require_identity)) -> list[dict[str, Any]]:
    return store.list_investigations(auth.tenant_id)


@app.post("/watchlists")
async def create_watchlist(
    body: WatchlistCreate,
    auth: AuthContext = Depends(require_identity),
) -> dict[str, Any]:
    try:
        saas_manager.ensure_watchlist_capacity(auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    payload = body.model_dump()
    payload["workspace_id"] = auth.tenant_id
    scope = dict(payload.get("scope") or {})
    scope["workspace_id"] = auth.tenant_id
    payload["scope"] = scope
    return store.create_watchlist(payload)


@app.get("/watchlists")
async def list_watchlists(auth: AuthContext = Depends(require_identity)) -> list[dict[str, Any]]:
    return store.list_watchlists(auth.tenant_id)


@app.get("/alerts")
async def list_alerts(auth: AuthContext = Depends(require_identity)) -> list[dict[str, Any]]:
    return store.list_alerts(auth.tenant_id)


@app.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(
    alert_id: str,
    auth: AuthContext = Depends(require_identity),
) -> dict[str, bool]:
    visible = {item["id"] for item in store.list_alerts(auth.tenant_id, limit=1000)}
    if alert_id not in visible:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"acknowledged": store.acknowledge_alert(alert_id)}


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics(auth: AuthContext = Depends(require_identity)) -> str:
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return metrics.render_prometheus()


@app.get("/slo")
async def slo_report(auth: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return metrics.slo_report()


if settings.ui_enabled and settings.ui_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.ui_dir / "assets"), name="fusion-assets")

if settings.saas_enabled and settings.saas_ui_dir.exists():
    app.mount(
        "/saas-assets",
        StaticFiles(directory=settings.saas_ui_dir / "assets"),
        name="saas-assets",
    )

    @app.get("/", include_in_schema=False)
    async def saas_index():
        return FileResponse(settings.saas_ui_dir / "index.html")

    @app.get("/app", include_in_schema=False)
    async def command_center():
        if not settings.ui_enabled or not settings.ui_dir.exists():
            raise HTTPException(status_code=404, detail="Command center UI disabled")
        return FileResponse(settings.ui_dir / "index.html")

    @app.get("/atlas", include_in_schema=False)
    async def fusion_atlas_ui():
        if not settings.ui_enabled or not settings.ui_dir.exists():
            raise HTTPException(status_code=404, detail="Fusion Atlas UI disabled")
        return FileResponse(settings.ui_dir / "assets" / "atlas.html")

    @app.get("/world-globe", include_in_schema=False)
    async def temporal_globe_ui():
        if not settings.ui_enabled or not settings.ui_dir.exists():
            raise HTTPException(status_code=404, detail="Temporal Globe UI disabled")
        return FileResponse(settings.ui_dir / "assets" / "temporal-globe.html")

    @app.get("/science-explorer", include_in_schema=False)
    async def science_explorer_ui():
        if not settings.ui_enabled or not settings.ui_dir.exists():
            raise HTTPException(status_code=404, detail="Science Genome Explorer UI disabled")
        return FileResponse(settings.ui_dir / "assets" / "science-explorer.html")

    @app.get("/engineering-lab", include_in_schema=False)
    async def engineering_lab_ui():
        if not settings.ui_enabled or not settings.ui_dir.exists():
            raise HTTPException(status_code=404, detail="Engineering Intelligence UI disabled")
        return FileResponse(settings.ui_dir / "assets" / "engineering-lab.html")

elif settings.ui_enabled and settings.ui_dir.exists():

    @app.get("/", include_in_schema=False)
    async def ui_index():
        return FileResponse(settings.ui_dir / "index.html")

    @app.get("/atlas", include_in_schema=False)
    async def fusion_atlas_ui():
        return FileResponse(settings.ui_dir / "assets" / "atlas.html")

    @app.get("/world-globe", include_in_schema=False)
    async def temporal_globe_ui():
        return FileResponse(settings.ui_dir / "assets" / "temporal-globe.html")

    @app.get("/science-explorer", include_in_schema=False)
    async def science_explorer_ui():
        return FileResponse(settings.ui_dir / "assets" / "science-explorer.html")

    @app.get("/engineering-lab", include_in_schema=False)
    async def engineering_lab_ui():
        return FileResponse(settings.ui_dir / "assets" / "engineering-lab.html")
