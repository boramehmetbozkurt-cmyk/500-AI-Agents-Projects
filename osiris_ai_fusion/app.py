from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import get_settings
from graph import investigate
from llm import ModelRouter
from osiris_client import READ_ONLY_TOOLS, OsirisClient
from rate_limit import InMemoryRateLimiter

logger = logging.getLogger("osiris_fusion")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()
rate_limiter = InMemoryRateLimiter(settings.request_limit_per_minute)

app = FastAPI(
    title="OSIRIS AI Fusion",
    version="0.3.0",
    description="Evidence-first, authorization-aware, read-only OSINT research API.",
)


class InvestigationScope(BaseModel):
    region: str | None = Field(default=None, max_length=200)
    time_range: str | None = Field(default=None, max_length=100)
    case_id: str | None = Field(default=None, max_length=100)


class InvestigationRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    allowed_tools: list[str] | None = Field(default=None, max_length=10)
    scope: InvestigationScope = Field(default_factory=InvestigationScope)


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

    if request.url.path == "/investigate":
        identity = request.headers.get("X-API-Key") or (
            request.client.host if request.client else "unknown"
        )
        allowed, retry_after = await rate_limiter.allow(identity)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "request_id": request_id},
                headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
            )

    try:
        response = await call_next(request)
    except Exception:
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
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
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
        "service": "osiris-ai-fusion",
        "version": app.version,
    }


@app.get("/ready")
async def ready(_: str = Depends(require_api_key)) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "ready", "dependencies": {}}
    try:
        async with OsirisClient() as client:
            result["dependencies"]["osiris"] = await client.health()
    except Exception as exc:
        result["status"] = "degraded"
        result["dependencies"]["osiris"] = {
            "status": "unreachable",
            "error_type": type(exc).__name__,
        }

    try:
        result["dependencies"]["llm"] = await ModelRouter().health()
    except Exception as exc:
        result["status"] = "degraded"
        result["dependencies"]["llm"] = {"status": "unreachable", "error_type": type(exc).__name__}
    return result


@app.get("/tools")
async def tools(_: str = Depends(require_api_key)) -> dict[str, Any]:
    return {
        "mode": "read-only",
        "tools": sorted(READ_ONLY_TOOLS),
        "excluded": [
            "active_scanning",
            "exploitation",
            "credential_access",
            "intrusive_surveillance",
            "face_recognition_tracking",
        ],
    }


@app.post("/investigate")
async def investigate_route(
    body: InvestigationRequest,
    request: Request,
    _: str = Depends(require_api_key),
):
    request_id = request.headers.get("X-Request-ID") or "generated-by-middleware"
    try:
        result = await investigate(
            body.query,
            requested_tools=body.allowed_tools,
            scope=body.scope.model_dump(exclude_none=True),
        )
        result["request_id"] = request_id
        return result
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
