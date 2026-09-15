from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from config import get_settings


PLAN_LIMITS: dict[str, dict[str, int | float | str]] = {
    "free": {
        "investigations_per_month": 50,
        "watchlists": 3,
        "api_keys": 2,
        "price_usd_month": 0,
        "label": "Free",
    },
    "pro": {
        "investigations_per_month": 2000,
        "watchlists": 50,
        "api_keys": 10,
        "price_usd_month": 29,
        "label": "Pro",
    },
    "team": {
        "investigations_per_month": 20000,
        "watchlists": 250,
        "api_keys": 50,
        "price_usd_month": 99,
        "label": "Team",
    },
    "admin": {
        "investigations_per_month": 1_000_000_000,
        "watchlists": 1_000_000,
        "api_keys": 1_000_000,
        "price_usd_month": 0,
        "label": "Admin",
    },
}

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class AuthContext:
    tenant_id: str
    user_id: str
    email: str
    plan: str
    auth_kind: str
    is_admin: bool = False


class SignupRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(default="", max_length=120)
    organization: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="Default", min_length=1, max_length=80)


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "team"]


class SaaSManager:
    def __init__(self, path: str | None = None) -> None:
        self.settings = get_settings()
        self.path = path or self.settings.store_path
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
                CREATE TABLE IF NOT EXISTS saas_tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    subscription_status TEXT NOT NULL DEFAULT 'free',
                    stripe_customer_id TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS saas_users (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL DEFAULT '',
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(tenant_id) REFERENCES saas_tenants(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS saas_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES saas_users(id) ON DELETE CASCADE,
                    FOREIGN KEY(tenant_id) REFERENCES saas_tenants(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS saas_api_keys (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    last4 TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    revoked_at INTEGER,
                    FOREIGN KEY(user_id) REFERENCES saas_users(id) ON DELETE CASCADE,
                    FOREIGN KEY(tenant_id) REFERENCES saas_tenants(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS saas_usage (
                    tenant_id TEXT NOT NULL,
                    period TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(tenant_id, period, metric),
                    FOREIGN KEY(tenant_id) REFERENCES saas_tenants(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_saas_session_token
                    ON saas_sessions(token_hash, expires_at);
                CREATE INDEX IF NOT EXISTS idx_saas_api_key_hash
                    ON saas_api_keys(key_hash, revoked_at);
                """
            )
            conn.commit()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:20]}"

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not _EMAIL_RE.fullmatch(normalized):
            raise ValueError("Geçerli bir e-posta adresi girin")
        return normalized

    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> str:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        ).hex()

    def _make_session(self, conn: sqlite3.Connection, user_id: str, tenant_id: str) -> str:
        raw = secrets.token_urlsafe(32)
        now = int(time.time())
        conn.execute(
            "INSERT INTO saas_sessions VALUES (?, ?, ?, ?, ?, ?)",
            (
                self._id("sess"),
                user_id,
                tenant_id,
                self._hash_token(raw),
                now + self.settings.saas_session_ttl_seconds,
                now,
            ),
        )
        return raw

    def signup(self, email: str, password: str, name: str, organization: str) -> dict[str, Any]:
        if not self.settings.saas_public_signup_enabled:
            raise PermissionError("Public signup is disabled")
        normalized = self._normalize_email(email)
        if len(password) < 12:
            raise ValueError("Şifre en az 12 karakter olmalı")
        now = int(time.time())
        tenant_id = self._id("tenant")
        user_id = self._id("user")
        tenant_name = (organization or name or normalized.split("@", 1)[0]).strip()[:120]
        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(password, salt)
        try:
            with self._lock, self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO saas_tenants VALUES (?, ?, 'free', 'free', NULL, ?, ?)",
                    (tenant_id, tenant_name, now, now),
                )
                conn.execute(
                    "INSERT INTO saas_users VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, tenant_id, normalized, name.strip()[:120], salt.hex(), password_hash, now),
                )
                session = self._make_session(conn, user_id, tenant_id)
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("Bu e-posta zaten kayıtlı") from exc
        return {
            "token": session,
            "token_type": "bearer",
            "user": {"id": user_id, "email": normalized, "name": name.strip()[:120]},
            "tenant": {"id": tenant_id, "name": tenant_name, "plan": "free"},
        }

    def login(self, email: str, password: str) -> dict[str, Any]:
        normalized = self._normalize_email(email)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.*, t.name AS tenant_name, t.plan, t.subscription_status
                FROM saas_users u JOIN saas_tenants t ON t.id=u.tenant_id
                WHERE u.email=?
                """,
                (normalized,),
            ).fetchone()
            if row is None:
                raise PermissionError("E-posta veya şifre hatalı")
            salt = bytes.fromhex(row["password_salt"])
            candidate = self._password_hash(password, salt)
            if not hmac.compare_digest(candidate, row["password_hash"]):
                raise PermissionError("E-posta veya şifre hatalı")
            session = self._make_session(conn, row["id"], row["tenant_id"])
            conn.commit()
        return {
            "token": session,
            "token_type": "bearer",
            "user": {"id": row["id"], "email": row["email"], "name": row["name"]},
            "tenant": {
                "id": row["tenant_id"],
                "name": row["tenant_name"],
                "plan": row["plan"],
                "subscription_status": row["subscription_status"],
            },
        }

    def authenticate(self, authorization: str | None, api_key: str | None) -> AuthContext:
        if self.settings.api_key and api_key and hmac.compare_digest(api_key, self.settings.api_key):
            return AuthContext("default", "system", "admin@local", "admin", "admin-key", True)

        if api_key:
            digest = self._hash_token(api_key)
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT k.tenant_id, k.user_id, u.email, t.plan
                    FROM saas_api_keys k
                    JOIN saas_users u ON u.id=k.user_id
                    JOIN saas_tenants t ON t.id=k.tenant_id
                    WHERE k.key_hash=? AND k.revoked_at IS NULL
                    """,
                    (digest,),
                ).fetchone()
            if row:
                return AuthContext(row["tenant_id"], row["user_id"], row["email"], row["plan"], "api-key")

        if authorization and authorization.lower().startswith("bearer "):
            raw = authorization[7:].strip()
            digest = self._hash_token(raw)
            now = int(time.time())
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT s.tenant_id, s.user_id, u.email, t.plan
                    FROM saas_sessions s
                    JOIN saas_users u ON u.id=s.user_id
                    JOIN saas_tenants t ON t.id=s.tenant_id
                    WHERE s.token_hash=? AND s.expires_at>?
                    """,
                    (digest, now),
                ).fetchone()
            if row:
                return AuthContext(row["tenant_id"], row["user_id"], row["email"], row["plan"], "session")

        if (
            self.settings.app_env != "production"
            and not self.settings.api_key
            and not api_key
            and not authorization
        ):
            return AuthContext("default", "development", "dev@local", "admin", "development", True)
        raise PermissionError("Authentication required")

    def logout(self, bearer: str | None) -> bool:
        if not bearer or not bearer.lower().startswith("bearer "):
            return False
        digest = self._hash_token(bearer[7:].strip())
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM saas_sessions WHERE token_hash=?", (digest,))
            conn.commit()
            return cursor.rowcount > 0

    def account(self, auth: AuthContext) -> dict[str, Any]:
        if auth.is_admin:
            return {
                "user": {"id": auth.user_id, "email": auth.email},
                "tenant": {"id": auth.tenant_id, "name": "Administrator", "plan": "admin"},
                "limits": PLAN_LIMITS["admin"],
            }
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id AS user_id, u.email, u.name AS user_name,
                       t.id AS tenant_id, t.name AS tenant_name, t.plan,
                       t.subscription_status, t.stripe_customer_id
                FROM saas_users u JOIN saas_tenants t ON t.id=u.tenant_id
                WHERE u.id=? AND t.id=?
                """,
                (auth.user_id, auth.tenant_id),
            ).fetchone()
        if row is None:
            raise KeyError(auth.user_id)
        plan = row["plan"] if row["plan"] in PLAN_LIMITS else "free"
        return {
            "user": {"id": row["user_id"], "email": row["email"], "name": row["user_name"]},
            "tenant": {
                "id": row["tenant_id"],
                "name": row["tenant_name"],
                "plan": plan,
                "subscription_status": row["subscription_status"],
            },
            "limits": PLAN_LIMITS[plan],
        }

    @staticmethod
    def _period() -> str:
        return time.strftime("%Y-%m", time.gmtime())

    def usage(self, auth: AuthContext) -> dict[str, Any]:
        plan = auth.plan if auth.plan in PLAN_LIMITS else "free"
        period = self._period()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT metric, count FROM saas_usage WHERE tenant_id=? AND period=?",
                (auth.tenant_id, period),
            ).fetchall()
            try:
                watchlists = conn.execute(
                    "SELECT COUNT(*) AS n FROM watchlists WHERE workspace_id=? AND enabled=1",
                    (auth.tenant_id,),
                ).fetchone()["n"]
            except sqlite3.OperationalError:
                watchlists = 0
            api_keys = conn.execute(
                "SELECT COUNT(*) AS n FROM saas_api_keys WHERE tenant_id=? AND revoked_at IS NULL",
                (auth.tenant_id,),
            ).fetchone()["n"]
        usage = {row["metric"]: row["count"] for row in rows}
        usage.setdefault("investigations", 0)
        usage["watchlists"] = watchlists
        usage["api_keys"] = api_keys
        return {"period": period, "plan": plan, "usage": usage, "limits": PLAN_LIMITS[plan]}

    def reserve_investigation(self, auth: AuthContext) -> None:
        if auth.is_admin:
            return
        plan = auth.plan if auth.plan in PLAN_LIMITS else "free"
        limit = int(PLAN_LIMITS[plan]["investigations_per_month"])
        period = self._period()
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT count FROM saas_usage WHERE tenant_id=? AND period=? AND metric='investigations'",
                (auth.tenant_id, period),
            ).fetchone()
            current = int(row["count"]) if row else 0
            if current >= limit:
                conn.rollback()
                raise PermissionError("Monthly investigation quota exceeded")
            conn.execute(
                """
                INSERT INTO saas_usage(tenant_id, period, metric, count, updated_at)
                VALUES (?, ?, 'investigations', 1, ?)
                ON CONFLICT(tenant_id, period, metric)
                DO UPDATE SET count=count+1, updated_at=excluded.updated_at
                """,
                (auth.tenant_id, period, now),
            )
            conn.commit()

    def ensure_watchlist_capacity(self, auth: AuthContext) -> None:
        if auth.is_admin:
            return
        plan = auth.plan if auth.plan in PLAN_LIMITS else "free"
        limit = int(PLAN_LIMITS[plan]["watchlists"])
        with self._connect() as conn:
            try:
                count = conn.execute(
                    "SELECT COUNT(*) AS n FROM watchlists WHERE workspace_id=? AND enabled=1",
                    (auth.tenant_id,),
                ).fetchone()["n"]
            except sqlite3.OperationalError:
                count = 0
        if count >= limit:
            raise PermissionError("Watchlist limit reached for your plan")

    def create_api_key(self, auth: AuthContext, name: str) -> dict[str, Any]:
        if auth.is_admin:
            raise PermissionError("Admin bootstrap identity does not create tenant API keys")
        plan = auth.plan if auth.plan in PLAN_LIMITS else "free"
        limit = int(PLAN_LIMITS[plan]["api_keys"])
        with self._lock, self._connect() as conn:
            active = conn.execute(
                "SELECT COUNT(*) AS n FROM saas_api_keys WHERE tenant_id=? AND revoked_at IS NULL",
                (auth.tenant_id,),
            ).fetchone()["n"]
            if active >= limit:
                raise PermissionError("API key limit reached for your plan")
            raw = "orb_live_" + secrets.token_urlsafe(30)
            now = int(time.time())
            key_id = self._id("key")
            conn.execute(
                "INSERT INTO saas_api_keys VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (key_id, auth.tenant_id, auth.user_id, name.strip()[:80], self._hash_token(raw), raw[-4:], now),
            )
            conn.commit()
        return {"id": key_id, "name": name.strip()[:80], "api_key": raw, "last4": raw[-4:], "created_at": now}

    def list_api_keys(self, auth: AuthContext) -> list[dict[str, Any]]:
        if auth.is_admin:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, last4, created_at
                FROM saas_api_keys
                WHERE tenant_id=? AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
            (auth.tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_api_key(self, auth: AuthContext, key_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE saas_api_keys SET revoked_at=? WHERE id=? AND tenant_id=? AND revoked_at IS NULL",
                (int(time.time()), key_id, auth.tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def create_checkout(self, auth: AuthContext, plan: str) -> dict[str, Any]:
        if plan not in {"pro", "team"}:
            raise ValueError("Unsupported plan")
        secret = self.settings.stripe_secret_key
        price_id = self.settings.stripe_price_pro if plan == "pro" else self.settings.stripe_price_team
        if not secret or not price_id or not self.settings.saas_base_url:
            raise RuntimeError("Stripe billing is not configured")
        base = self.settings.saas_base_url.rstrip("/")
        form = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": f"{base}/?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{base}/?billing=cancelled",
            "client_reference_id": auth.tenant_id,
            "customer_email": auth.email,
            "metadata[tenant_id]": auth.tenant_id,
            "metadata[plan]": plan,
            "subscription_data[metadata][tenant_id]": auth.tenant_id,
            "subscription_data[metadata][plan]": plan,
            "allow_promotion_codes": "true",
        }
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=form,
                headers={"Authorization": f"Bearer {secret}"},
            )
        if response.status_code >= 400:
            raise RuntimeError("Stripe checkout creation failed")
        payload = response.json()
        return {"checkout_url": payload.get("url"), "session_id": payload.get("id"), "plan": plan}

    def _verify_stripe_signature(self, payload: bytes, signature: str) -> None:
        secret = self.settings.stripe_webhook_secret
        if not secret:
            raise PermissionError("Stripe webhook secret is not configured")
        parts: dict[str, list[str]] = {}
        for item in signature.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            parts.setdefault(key.strip(), []).append(value.strip())
        try:
            timestamp = int(parts["t"][0])
        except (KeyError, ValueError, IndexError) as exc:
            raise PermissionError("Invalid Stripe signature") from exc
        if abs(int(time.time()) - timestamp) > 300:
            raise PermissionError("Expired Stripe signature")
        signed = str(timestamp).encode("ascii") + b"." + payload
        expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", [])):
            raise PermissionError("Invalid Stripe signature")

    def process_stripe_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        self._verify_stripe_signature(payload, signature)
        event = json.loads(payload)
        event_type = str(event.get("type", ""))
        obj = ((event.get("data") or {}).get("object") or {})
        metadata = obj.get("metadata") or {}
        tenant_id = str(obj.get("client_reference_id") or metadata.get("tenant_id") or "")
        plan = str(metadata.get("plan") or "free")
        if plan not in {"free", "pro", "team"}:
            plan = "free"
        if not tenant_id:
            return {"received": True, "updated": False, "type": event_type}
        status = str(obj.get("status") or "active")
        if event_type == "customer.subscription.deleted":
            plan, status = "free", "canceled"
        if event_type in {
            "checkout.session.completed",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            customer = obj.get("customer")
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    UPDATE saas_tenants
                    SET plan=?, subscription_status=?, stripe_customer_id=COALESCE(?, stripe_customer_id), updated_at=?
                    WHERE id=?
                    """,
                    (plan, status, customer, int(time.time()), tenant_id),
                )
                conn.commit()
            return {"received": True, "updated": True, "type": event_type, "plan": plan}
        return {"received": True, "updated": False, "type": event_type}


settings = get_settings()
saas_manager = SaaSManager(settings.store_path)
router = APIRouter(prefix="/saas", tags=["saas"])


async def require_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthContext:
    try:
        return saas_manager.authenticate(authorization, x_api_key)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/plans")
async def plans() -> dict[str, Any]:
    public = {key: value for key, value in PLAN_LIMITS.items() if key != "admin"}
    return {
        "plans": public,
        "billing_configured": bool(settings.stripe_secret_key and settings.stripe_price_pro),
    }


@router.post("/signup")
async def signup(body: SignupRequest) -> dict[str, Any]:
    try:
        return saas_manager.signup(body.email, body.password, body.name, body.organization)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login")
async def login(body: LoginRequest) -> dict[str, Any]:
    try:
        return saas_manager.login(body.email, body.password)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout")
async def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
    _: AuthContext = Depends(require_identity),
) -> dict[str, bool]:
    return {"logged_out": saas_manager.logout(authorization)}


@router.get("/me")
async def me(auth: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    return saas_manager.account(auth)


@router.get("/usage")
async def usage(auth: AuthContext = Depends(require_identity)) -> dict[str, Any]:
    return saas_manager.usage(auth)


@router.get("/api-keys")
async def api_keys(auth: AuthContext = Depends(require_identity)) -> list[dict[str, Any]]:
    return saas_manager.list_api_keys(auth)


@router.post("/api-keys")
async def create_api_key(
    body: ApiKeyCreateRequest,
    auth: AuthContext = Depends(require_identity),
) -> dict[str, Any]:
    try:
        return saas_manager.create_api_key(auth, body.name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, auth: AuthContext = Depends(require_identity)) -> dict[str, bool]:
    return {"revoked": saas_manager.revoke_api_key(auth, key_id)}


@router.post("/billing/checkout")
async def billing_checkout(
    body: CheckoutRequest,
    auth: AuthContext = Depends(require_identity),
) -> dict[str, Any]:
    try:
        return await saas_manager.create_checkout(auth, body.plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/billing/webhook")
async def billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature")
    payload = await request.body()
    try:
        return saas_manager.process_stripe_webhook(payload, stripe_signature)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
