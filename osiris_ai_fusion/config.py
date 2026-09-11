from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


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


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    api_key: str = os.getenv("OSIRIS_FUSION_API_KEY", "").strip()
    osiris_base_url: str = os.getenv("OSIRIS_BASE_URL", "https://osirisai.live").rstrip("/")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5:7b").strip()
    fallback_base_url: str = os.getenv("LLM_FALLBACK_BASE_URL", "").rstrip("/")
    fallback_api_key: str = os.getenv("LLM_FALLBACK_API_KEY", "").strip()
    fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "").strip()
    tool_timeout_seconds: float = _float("TOOL_TIMEOUT_SECONDS", 20.0)
    llm_timeout_seconds: float = _float("LLM_TIMEOUT_SECONDS", 120.0)
    max_parallel_tools: int = _int("MAX_PARALLEL_TOOLS", 5)
    max_evidence_bytes: int = _int("MAX_EVIDENCE_BYTES", 1_500_000)
    max_prompt_evidence_chars: int = _int("MAX_PROMPT_EVIDENCE_CHARS", 50_000)
    max_tool_calls: int = _int("MAX_TOOL_CALLS", 8)
    seal_ttl_seconds: int = _int("SEAL_TTL_SECONDS", 300)
    seal_replay_db: str = os.getenv("SEAL_REPLAY_DB", ".seal_replay.sqlite3")
    request_limit_per_minute: int = _int("REQUEST_LIMIT_PER_MINUTE", 30)
    require_signed_receipts: bool = _bool("REQUIRE_SIGNED_RECEIPTS", False)

    def validate(self) -> None:
        if self.app_env == "production":
            missing: list[str] = []
            if not self.api_key:
                missing.append("OSIRIS_FUSION_API_KEY")
            signed_receipt_key = os.getenv("SEAL_ED25519_PRIVATE_KEY_B64", "").strip()
            if self.require_signed_receipts and not signed_receipt_key:
                missing.append("SEAL_ED25519_PRIVATE_KEY_B64")
            if missing:
                raise RuntimeError("Missing required production settings: " + ", ".join(missing))
        if self.max_parallel_tools < 1:
            raise RuntimeError("MAX_PARALLEL_TOOLS must be >= 1")
        if self.max_tool_calls < 1:
            raise RuntimeError("MAX_TOOL_CALLS must be >= 1")
        if self.max_evidence_bytes < 10_000:
            raise RuntimeError("MAX_EVIDENCE_BYTES is too small")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate()
    return settings
