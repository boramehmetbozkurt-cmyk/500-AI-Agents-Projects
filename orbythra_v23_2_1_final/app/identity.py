from __future__ import annotations

import json
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt

from app.config import Settings

_ALLOWED_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384"}
_ALLOWED_ROLES = {"viewer", "evaluator", "operator", "admin"}
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_LOCK = threading.RLock()


class OIDCValidationError(ValueError):
    pass


@dataclass(frozen=True)
class OIDCIdentity:
    subject: str
    workspace_id: str
    role: str
    issuer: str
    claims: dict[str, Any]


def _fetch_jwks(url: str, ttl_seconds: int = 300) -> dict[str, Any]:
    now = time.monotonic()
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(url)
        if cached and cached[0] > now:
            return cached[1]
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ORBYTHRA-OIDC/1"})
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            raw = response.read(1_000_001)
    except Exception as exc:
        raise OIDCValidationError("oidc_jwks_fetch_failed") from exc
    if len(raw) > 1_000_000:
        raise OIDCValidationError("oidc_jwks_response_too_large")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise OIDCValidationError("oidc_jwks_invalid_json") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("keys"), list):
        raise OIDCValidationError("oidc_jwks_invalid_shape")
    with _JWKS_LOCK:
        _JWKS_CACHE[url] = (now + ttl_seconds, parsed)
    return parsed


def _load_jwks(settings: Settings) -> dict[str, Any]:
    if settings.oidc_jwks_json:
        try:
            parsed = json.loads(settings.oidc_jwks_json)
        except Exception as exc:
            raise OIDCValidationError("oidc_jwks_invalid_json") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("keys"), list):
            raise OIDCValidationError("oidc_jwks_invalid_shape")
        return parsed
    if settings.oidc_jwks_url:
        return _fetch_jwks(settings.oidc_jwks_url)
    raise OIDCValidationError("oidc_jwks_not_configured")


def verify_oidc_token(token: str, settings: Settings, *, jwks_override: dict[str, Any] | None = None) -> OIDCIdentity:
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise OIDCValidationError("oidc_not_configured")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise OIDCValidationError("oidc_invalid_token_header") from exc
    algorithm = str(header.get("alg", ""))
    key_id = str(header.get("kid", ""))
    if algorithm not in _ALLOWED_ALGORITHMS:
        raise OIDCValidationError("oidc_algorithm_not_allowed")
    if not key_id:
        raise OIDCValidationError("oidc_kid_required")
    jwks = jwks_override or _load_jwks(settings)
    selected: dict[str, Any] | None = None
    for candidate in jwks.get("keys", []):
        if isinstance(candidate, dict) and str(candidate.get("kid", "")) == key_id:
            selected = candidate
            break
    if selected is None:
        raise OIDCValidationError("oidc_unknown_kid")
    try:
        pyjwk = jwt.PyJWK.from_dict(selected, algorithm=algorithm)
        claims = jwt.decode(
            token,
            key=pyjwk.key,
            algorithms=[algorithm],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise OIDCValidationError("oidc_token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise OIDCValidationError("oidc_token_invalid") from exc
    subject = str(claims.get("sub", "")).strip()
    workspace_id = str(claims.get(settings.oidc_workspace_claim, "")).strip()
    role = str(claims.get(settings.oidc_role_claim, "viewer")).strip().lower()
    if not subject:
        raise OIDCValidationError("oidc_subject_required")
    if not workspace_id:
        raise OIDCValidationError("oidc_workspace_claim_required")
    if role not in _ALLOWED_ROLES:
        raise OIDCValidationError("oidc_role_invalid")
    return OIDCIdentity(subject=subject, workspace_id=workspace_id, role=role, issuer=settings.oidc_issuer, claims=dict(claims))
