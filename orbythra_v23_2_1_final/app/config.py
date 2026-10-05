from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

_ALLOWED_ROLES = {"admin", "operator", "evaluator", "viewer"}
_ALLOWED_CRYPTO_ALGORITHMS = {"aes256-gcm", "chacha20-poly1305"}
_ALLOWED_KEY_MANAGEMENT_MODES = {"environment", "external_secret_manager", "kms_envelope"}
_ALLOWED_PQC_MODES = {"off", "hybrid-preferred", "hybrid-required"}


@dataclass(frozen=True)
class Settings:
    environment: str
    db_path: str
    database_url: str | None
    api_keys: tuple[tuple[str, str], ...]
    api_roles: tuple[tuple[str, str], ...]
    rate_limit_per_minute: int
    max_body_bytes: int
    evidence_provider_url: str | None
    llm_provider_url: str | None
    master_keys: tuple[tuple[str, str], ...]
    signing_keys: tuple[tuple[str, str], ...]
    crypto_algorithm: str
    crypto_default_ttl_seconds: int
    crypto_max_ttl_seconds: int
    oidc_issuer: str | None
    oidc_audience: str | None
    oidc_jwks_url: str | None
    oidc_jwks_json: str | None
    oidc_workspace_claim: str
    oidc_role_claim: str
    deployment_id: str | None
    release_sha: str | None
    key_management_mode: str
    allow_legacy_approvals: bool
    pqc_mode: str

    @property
    def auth_configured(self) -> bool:
        return bool(self.api_keys) or self.oidc_configured

    @property
    def crypto_configured(self) -> bool:
        if not self.master_keys:
            return False
        if self.environment != "production":
            return True
        return self.signing_keys_isolated

    @property
    def signing_keys_isolated(self) -> bool:
        return _key_rings_distinct(self.master_keys, self.signing_keys)

    @property
    def oidc_configured(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_audience and (self.oidc_jwks_url or self.oidc_jwks_json))

    @property
    def external_key_management_declared(self) -> bool:
        return self.key_management_mode in {"external_secret_manager", "kms_envelope"}

    def role_for(self, principal_id: str) -> str:
        mapping = dict(self.api_roles)
        return mapping.get(principal_id, "operator")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _parse_api_keys(raw: str) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item or ":" not in item:
            continue
        principal, secret = item.split(":", 1)
        principal = principal.strip()[:80]
        secret = secret.strip()
        if principal and secret:
            pairs.append((principal, secret))
    return tuple(pairs)


def _parse_roles(raw: str) -> tuple[tuple[str, str], ...]:
    roles: list[tuple[str, str]] = []
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        principal, role = (part.strip() for part in item.split("=", 1))
        if principal and role in _ALLOWED_ROLES:
            roles.append((principal[:80], role))
    return tuple(roles)


def _decode_key_material(encoded: str) -> bytes | None:
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode((encoded + padding).encode("ascii"))
    except Exception:
        return None


def _key_ring_valid(keys: tuple[tuple[str, str], ...]) -> bool:
    if not keys:
        return False
    key_ids = [key_id for key_id, _ in keys]
    if len(set(key_ids)) != len(key_ids):
        return False
    for _, encoded in keys:
        raw = _decode_key_material(encoded)
        if raw is None or len(raw) != 32:
            return False
    return True


def _key_rings_distinct(
    encryption_keys: tuple[tuple[str, str], ...],
    signing_keys: tuple[tuple[str, str], ...],
) -> bool:
    if not _key_ring_valid(encryption_keys) or not _key_ring_valid(signing_keys):
        return False
    encryption_material = {_decode_key_material(encoded) for _, encoded in encryption_keys}
    signing_material = {_decode_key_material(encoded) for _, encoded in signing_keys}
    return encryption_material.isdisjoint(signing_material)


def _parse_master_keys(raw: str, legacy: str) -> tuple[tuple[str, str], ...]:
    source = raw.strip()
    if not source and legacy.strip():
        source = f"v1:{legacy.strip()}"
    keys: list[tuple[str, str]] = []
    for chunk in source.split(","):
        item = chunk.strip()
        if not item or ":" not in item:
            continue
        key_id, encoded = item.split(":", 1)
        key_id = key_id.strip()[:40]
        encoded = encoded.strip()
        if key_id and encoded:
            keys.append((key_id, encoded))
    return tuple(keys)


def _optional_url(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    if not value.startswith(("https://", "http://")):
        raise RuntimeError(f"{name} must use http:// or https://")
    return value.rstrip("/")


def _optional_text(name: str, maximum: int = 4096) -> str | None:
    value = os.getenv(name, "").strip()
    return value[:maximum] if value else None


def load_settings() -> Settings:
    environment = os.getenv("ORBYTHRA_ENV", "development").strip().lower() or "development"
    db_path = os.getenv("ORBYTHRA_DB_PATH", "./data/orbythra.db").strip() or "./data/orbythra.db"
    database_url = os.getenv("ORBYTHRA_DATABASE_URL", "").strip() or None
    if database_url is None:
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    algorithm = os.getenv("ORBYTHRA_CRYPTO_ALGORITHM", "aes256-gcm").strip().lower()
    if algorithm not in _ALLOWED_CRYPTO_ALGORITHMS:
        raise RuntimeError("ORBYTHRA_CRYPTO_ALGORITHM must be aes256-gcm or chacha20-poly1305")
    key_management_mode = os.getenv("ORBYTHRA_KEY_MANAGEMENT_MODE", "environment").strip().lower() or "environment"
    if key_management_mode not in _ALLOWED_KEY_MANAGEMENT_MODES:
        raise RuntimeError("ORBYTHRA_KEY_MANAGEMENT_MODE must be environment, external_secret_manager or kms_envelope")
    pqc_default = "hybrid-required" if environment == "production" else "off"
    pqc_mode = os.getenv("ORBYTHRA_PQC_MODE", pqc_default).strip().lower() or pqc_default
    if pqc_mode not in _ALLOWED_PQC_MODES:
        raise RuntimeError("ORBYTHRA_PQC_MODE must be off, hybrid-preferred or hybrid-required")
    allow_legacy_approvals = _env_bool("ORBYTHRA_ALLOW_LEGACY_APPROVALS", environment != "production")
    if environment == "production":
        allow_legacy_approvals = False
    oidc_jwks_url = _optional_url("ORBYTHRA_OIDC_JWKS_URL")
    if environment == "production" and oidc_jwks_url and not oidc_jwks_url.startswith("https://"):
        raise RuntimeError("ORBYTHRA_OIDC_JWKS_URL must use https:// in production")
    master_keys = _parse_master_keys(os.getenv("ORBYTHRA_MASTER_KEYS", ""), os.getenv("ORBYTHRA_MASTER_KEY_B64", ""))
    signing_keys = _parse_master_keys(os.getenv("ORBYTHRA_SIGNING_KEYS", ""), "")
    if environment == "production" and master_keys and not _key_ring_valid(master_keys):
        raise RuntimeError("ORBYTHRA_MASTER_KEYS must contain unique keys that decode to exactly 32 bytes")
    if environment == "production" and signing_keys and not _key_ring_valid(signing_keys):
        raise RuntimeError("ORBYTHRA_SIGNING_KEYS must contain unique keys that decode to exactly 32 bytes")
    if environment == "production" and signing_keys and not _key_rings_distinct(master_keys, signing_keys):
        raise RuntimeError("ORBYTHRA_SIGNING_KEYS must not reuse ORBYTHRA_MASTER_KEYS key material")
    return Settings(
        environment=environment,
        db_path=db_path,
        database_url=database_url,
        api_keys=_parse_api_keys(os.getenv("ORBYTHRA_API_KEYS", "")),
        api_roles=_parse_roles(os.getenv("ORBYTHRA_API_ROLES", "")),
        rate_limit_per_minute=_bounded_int("ORBYTHRA_RATE_LIMIT_PER_MINUTE", 60, 1, 10000),
        max_body_bytes=_bounded_int("ORBYTHRA_MAX_BODY_BYTES", 2_000_000, 16_384, 20_000_000),
        evidence_provider_url=_optional_url("ORBYTHRA_EVIDENCE_PROVIDER_URL"),
        llm_provider_url=_optional_url("ORBYTHRA_LLM_PROVIDER_URL"),
        master_keys=master_keys,
        signing_keys=signing_keys,
        crypto_algorithm=algorithm,
        crypto_default_ttl_seconds=_bounded_int("ORBYTHRA_CRYPTO_DEFAULT_TTL_SECONDS", 3600, 60, 86400),
        crypto_max_ttl_seconds=_bounded_int("ORBYTHRA_CRYPTO_MAX_TTL_SECONDS", 86400, 300, 2_592_000),
        oidc_issuer=_optional_text("ORBYTHRA_OIDC_ISSUER", 500),
        oidc_audience=_optional_text("ORBYTHRA_OIDC_AUDIENCE", 500),
        oidc_jwks_url=oidc_jwks_url,
        oidc_jwks_json=_optional_text("ORBYTHRA_OIDC_JWKS_JSON", 200_000),
        oidc_workspace_claim=os.getenv("ORBYTHRA_OIDC_WORKSPACE_CLAIM", "orbythra_workspace").strip()[:120] or "orbythra_workspace",
        oidc_role_claim=os.getenv("ORBYTHRA_OIDC_ROLE_CLAIM", "orbythra_role").strip()[:120] or "orbythra_role",
        deployment_id=_optional_text("ORBYTHRA_DEPLOYMENT_ID", 160),
        release_sha=_optional_text("ORBYTHRA_RELEASE_SHA", 80),
        key_management_mode=key_management_mode,
        allow_legacy_approvals=allow_legacy_approvals,
        pqc_mode=pqc_mode,
    )


SETTINGS = load_settings()
