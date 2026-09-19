from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# README.md and DEPLOYMENT.md both document `cp .env.example .env`, and python-dotenv
# is already a declared runtime dependency, but nothing was reading that file: every
# local `uvicorn app:app` run silently ignored it. Compose was unaffected because it
# passes the file through `env_file:`.
ENV_FILE = Path(__file__).resolve().parent / ".env"


def load_env_file(path: Path = ENV_FILE) -> bool:
    """Read the documented .env file, if one exists.

    The path is anchored to this module rather than the process working directory,
    so the result does not depend on where the server was started from.
    ``override=False`` keeps real environment variables authoritative, which is what
    containers, CI and secret managers rely on.
    """
    return load_dotenv(path, override=False)


load_env_file()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


def _set(name: str) -> frozenset[str]:
    raw = os.getenv(name, "")
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _origins() -> tuple[str, ...]:
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw:
        return ()
    if raw.lstrip().startswith("["):
        return tuple(str(item) for item in json.loads(raw))
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str = field(
        default_factory=lambda: os.getenv("APP_ENV", "development").strip().lower()
    )
    api_key: str = field(
        default_factory=lambda: _first_env(
            "ORBYTHRA_FUSION_API_KEY",
            "OSIRIS_FUSION_API_KEY",
        ),
        repr=False,
    )
    # Internal attribute name is kept for compatibility with the existing client.
    # ORBYTHRA_BASE_URL is the public configuration name; OSIRIS_BASE_URL is legacy.
    osiris_base_url: str = field(
        default_factory=lambda: _first_env(
            "ORBYTHRA_BASE_URL",
            "OSIRIS_BASE_URL",
            default="https://osirisai.live",
        ).rstrip("/")
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        ).rstrip("/")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "qwen3:4b").strip()
    )
    llm_think: bool = field(default_factory=lambda: _bool("LLM_THINK", False))
    fallback_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_FALLBACK_BASE_URL", "").rstrip("/")
    )
    fallback_api_key: str = field(
        default_factory=lambda: os.getenv("LLM_FALLBACK_API_KEY", "").strip(),
        repr=False,
    )
    fallback_model: str = field(
        default_factory=lambda: os.getenv("LLM_FALLBACK_MODEL", "").strip()
    )
    ai_planner_enabled: bool = field(
        default_factory=lambda: _bool("AI_PLANNER_ENABLED", True)
    )
    fast_decision_enabled: bool = field(
        default_factory=lambda: _bool("FAST_DECISION_ENABLED", False)
    )
    fast_decision_base_url: str = field(
        default_factory=lambda: os.getenv("FAST_DECISION_BASE_URL", "").rstrip("/")
    )
    fast_decision_api_key: str = field(
        default_factory=lambda: os.getenv("FAST_DECISION_API_KEY", "").strip(),
        repr=False,
    )
    fast_decision_model: str = field(
        default_factory=lambda: os.getenv("FAST_DECISION_MODEL", "jev").strip()
    )
    fast_decision_path: str = field(
        default_factory=lambda: os.getenv("FAST_DECISION_PATH", "/decision").strip()
    )
    fast_decision_timeout_seconds: float = field(
        default_factory=lambda: _float("FAST_DECISION_TIMEOUT_SECONDS", 1.5)
    )
    fast_decision_min_confidence: float = field(
        default_factory=lambda: _float("FAST_DECISION_MIN_CONFIDENCE", 0.75)
    )
    tool_timeout_seconds: float = field(
        default_factory=lambda: _float("TOOL_TIMEOUT_SECONDS", 20.0)
    )
    llm_timeout_seconds: float = field(
        default_factory=lambda: _float("LLM_TIMEOUT_SECONDS", 120.0)
    )
    max_parallel_tools: int = field(
        default_factory=lambda: _int("MAX_PARALLEL_TOOLS", 5)
    )
    max_evidence_bytes: int = field(
        default_factory=lambda: _int("MAX_EVIDENCE_BYTES", 1_500_000)
    )
    max_prompt_evidence_chars: int = field(
        default_factory=lambda: _int("MAX_PROMPT_EVIDENCE_CHARS", 60_000)
    )
    max_tool_calls: int = field(default_factory=lambda: _int("MAX_TOOL_CALLS", 8))
    # Recursive subquery planning spends only the tool-call budget the root plan
    # leaves unspent, so enabling it redistributes work rather than adding any.
    subquery_planning_enabled: bool = field(
        default_factory=lambda: _bool("SUBQUERY_PLANNING_ENABLED", True)
    )
    subquery_max_count: int = field(
        default_factory=lambda: _int("SUBQUERY_MAX_COUNT", 3)
    )
    subquery_max_depth: int = field(
        default_factory=lambda: _int("SUBQUERY_MAX_DEPTH", 2)
    )
    seal_ttl_seconds: int = field(
        default_factory=lambda: _int("SEAL_TTL_SECONDS", 300)
    )
    seal_replay_db: str = field(
        default_factory=lambda: os.getenv("SEAL_REPLAY_DB", ".seal_replay.sqlite3")
    )
    request_limit_per_minute: int = field(
        default_factory=lambda: _int("REQUEST_LIMIT_PER_MINUTE", 30)
    )
    require_signed_receipts: bool = field(
        default_factory=lambda: _bool("REQUIRE_SIGNED_RECEIPTS", False)
    )
    store_path: str = field(
        default_factory=lambda: os.getenv("FUSION_STORE_PATH", "fusion.sqlite3")
    )
    watcher_enabled: bool = field(
        default_factory=lambda: _bool("WATCHER_ENABLED", False)
    )
    watcher_poll_seconds: int = field(
        default_factory=lambda: _int("WATCHER_POLL_SECONDS", 300)
    )
    commercial_mode: bool = field(
        default_factory=lambda: _bool("COMMERCIAL_MODE", False)
    )
    strict_commercial_sources: bool = field(
        default_factory=lambda: _bool("STRICT_COMMERCIAL_SOURCES", True)
    )
    licensed_providers: frozenset[str] = field(
        default_factory=lambda: _set("LICENSED_PROVIDERS")
    )
    cors_origins: tuple[str, ...] = field(default_factory=_origins)
    ui_enabled: bool = field(default_factory=lambda: _bool("UI_ENABLED", True))

    # Public SaaS layer
    saas_enabled: bool = field(default_factory=lambda: _bool("SAAS_ENABLED", True))
    saas_public_signup_enabled: bool = field(
        default_factory=lambda: _bool("SAAS_PUBLIC_SIGNUP_ENABLED", True)
    )
    saas_session_ttl_seconds: int = field(
        default_factory=lambda: _int("SAAS_SESSION_TTL_SECONDS", 604800)
    )
    saas_base_url: str = field(
        default_factory=lambda: os.getenv("SAAS_BASE_URL", "").rstrip("/")
    )
    stripe_secret_key: str = field(
        default_factory=lambda: os.getenv("STRIPE_SECRET_KEY", "").strip(),
        repr=False,
    )
    stripe_webhook_secret: str = field(
        default_factory=lambda: os.getenv("STRIPE_WEBHOOK_SECRET", "").strip(),
        repr=False,
    )
    stripe_price_pro: str = field(
        default_factory=lambda: os.getenv("STRIPE_PRICE_PRO", "").strip()
    )
    stripe_price_team: str = field(
        default_factory=lambda: os.getenv("STRIPE_PRICE_TEAM", "").strip()
    )

    @property
    def ui_dir(self) -> Path:
        return Path(__file__).resolve().parent / "ui"

    @property
    def saas_ui_dir(self) -> Path:
        return Path(__file__).resolve().parent / "saas_ui"

    def validate(self) -> None:
        if self.app_env == "production":
            missing: list[str] = []
            if not self.saas_enabled and not self.api_key:
                missing.append("ORBYTHRA_FUSION_API_KEY")
            signed_receipt_key = os.getenv("SEAL_ED25519_PRIVATE_KEY_B64", "").strip()
            if self.require_signed_receipts and not signed_receipt_key:
                missing.append("SEAL_ED25519_PRIVATE_KEY_B64")
            if missing:
                raise RuntimeError("Missing required production settings: " + ", ".join(missing))
        if self.max_parallel_tools < 1:
            raise RuntimeError("MAX_PARALLEL_TOOLS must be >= 1")
        if self.fast_decision_enabled and not self.fast_decision_base_url:
            raise RuntimeError(
                "FAST_DECISION_BASE_URL is required when FAST_DECISION_ENABLED=true"
            )
        if not self.fast_decision_path.startswith("/"):
            raise RuntimeError("FAST_DECISION_PATH must start with /")
        if self.fast_decision_timeout_seconds <= 0:
            raise RuntimeError("FAST_DECISION_TIMEOUT_SECONDS must be > 0")
        if not 0.0 <= self.fast_decision_min_confidence <= 1.0:
            raise RuntimeError("FAST_DECISION_MIN_CONFIDENCE must be between 0 and 1")
        if self.subquery_max_count < 0:
            raise RuntimeError("SUBQUERY_MAX_COUNT must be >= 0")
        if self.subquery_max_count > 12:
            raise RuntimeError("SUBQUERY_MAX_COUNT must be <= 12")
        if self.subquery_max_depth < 1:
            raise RuntimeError("SUBQUERY_MAX_DEPTH must be >= 1")
        if self.subquery_max_depth > 4:
            raise RuntimeError("SUBQUERY_MAX_DEPTH must be <= 4")
        if self.max_tool_calls < 1:
            raise RuntimeError("MAX_TOOL_CALLS must be >= 1")
        if self.max_evidence_bytes < 10_000:
            raise RuntimeError("MAX_EVIDENCE_BYTES is too small")
        if self.watcher_poll_seconds < 60:
            raise RuntimeError("WATCHER_POLL_SECONDS must be >= 60")
        if self.saas_session_ttl_seconds < 3600:
            raise RuntimeError("SAAS_SESSION_TTL_SECONDS must be >= 3600")
        stripe_values = [
            self.stripe_secret_key,
            self.stripe_webhook_secret,
            self.stripe_price_pro,
            self.stripe_price_team,
        ]
        if any(stripe_values) and not all(stripe_values):
            raise RuntimeError(
                "Stripe billing requires STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, "
                "STRIPE_PRICE_PRO and STRIPE_PRICE_TEAM together"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate()
    return settings
