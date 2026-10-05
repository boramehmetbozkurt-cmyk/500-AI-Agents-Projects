from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

from fastapi import Header, HTTPException, Request, status

from app.config import SETTINGS
from app.identity import OIDCValidationError, verify_oidc_token

_WORKSPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ROLE_ORDER = {"viewer": 0, "evaluator": 1, "operator": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    principal_id: str
    workspace_id: str
    key_fingerprint: str
    role: str


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.RLock()

    def check(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limit_exceeded", headers={"Retry-After": str(retry_after)})
            bucket.append(now)
            return max(0, self.limit - len(bucket))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


RATE_LIMITER = SlidingWindowRateLimiter(SETTINGS.rate_limit_per_minute)


def _fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


def _authenticate(secret: str) -> tuple[str, str] | None:
    for principal_id, candidate in SETTINGS.api_keys:
        if secrets.compare_digest(secret, candidate):
            return principal_id, _fingerprint(candidate)
    return None


def _rate_limit(request: Request, fingerprint: str, workspace_id: str) -> None:
    client_host = request.client.host if request.client else "unknown"
    remaining = RATE_LIMITER.check(f"{fingerprint}:{workspace_id}:{client_host}")
    request.state.rate_limit_remaining = remaining


def _apply_identity_lifecycle(subject: str, workspace_id: str, role: str) -> str:
    # Lazy import avoids making core auth depend on enterprise initialization order.
    from app.enterprise_store import ENTERPRISE_STORE

    entry = ENTERPRISE_STORE.get_identity(workspace_id, subject)
    if entry is None:
        return role
    if not entry.get("active", True):
        raise HTTPException(status_code=401, detail="identity_deactivated")
    override = entry.get("role_override")
    return str(override) if override in _ROLE_ORDER else role


def require_principal(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Principal:
    if not SETTINGS.auth_configured:
        raise HTTPException(status_code=503, detail="api_authentication_not_configured")

    if x_api_key:
        authenticated = _authenticate(x_api_key)
        if authenticated is None:
            raise HTTPException(status_code=401, detail="invalid_api_key")
        workspace_id = x_workspace_id.strip()
        if not _WORKSPACE_RE.fullmatch(workspace_id):
            raise HTTPException(status_code=400, detail="invalid_workspace_id")
        principal_id, fingerprint = authenticated
        _rate_limit(request, fingerprint, workspace_id)
        return Principal(principal_id=principal_id, workspace_id=workspace_id, key_fingerprint=fingerprint, role=SETTINGS.role_for(principal_id))

    if authorization and authorization.startswith("Bearer ") and SETTINGS.oidc_configured:
        token = authorization[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="missing_bearer_token")
        try:
            identity = verify_oidc_token(token, SETTINGS)
        except OIDCValidationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if not _WORKSPACE_RE.fullmatch(identity.workspace_id):
            raise HTTPException(status_code=401, detail="oidc_workspace_claim_invalid")
        principal_id = "oidc:" + identity.subject[:160]
        fingerprint = hashlib.sha256(f"{identity.issuer}|{identity.subject}".encode("utf-8")).hexdigest()[:16]
        role = _apply_identity_lifecycle(identity.subject, identity.workspace_id, identity.role)
        _rate_limit(request, fingerprint, identity.workspace_id)
        return Principal(principal_id=principal_id, workspace_id=identity.workspace_id, key_fingerprint=fingerprint, role=role)

    if authorization and authorization.startswith("Bearer ") and not SETTINGS.oidc_configured:
        raise HTTPException(status_code=503, detail="oidc_authentication_not_configured")
    if SETTINGS.api_keys:
        raise HTTPException(status_code=401, detail="missing_api_key")
    raise HTTPException(status_code=401, detail="missing_authentication")


def require_minimum_role(minimum_role: str) -> Callable[..., Principal]:
    if minimum_role not in _ROLE_ORDER:
        raise ValueError("unknown role")

    def dependency(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        x_workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> Principal:
        principal = require_principal(request, x_api_key, x_workspace_id, authorization)
        if _ROLE_ORDER.get(principal.role, -1) < _ROLE_ORDER[minimum_role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role")
        return principal

    return dependency
