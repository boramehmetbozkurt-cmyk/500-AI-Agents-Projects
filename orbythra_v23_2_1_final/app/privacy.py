from __future__ import annotations

import base64
import hashlib
import hmac
import time
import unicodedata
from typing import Any

from app.config import SETTINGS
from app.crypto_core import CryptoConfigurationError


def _decode_key(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode((value + padding).encode("ascii"))
    if len(raw) != 32:
        raise CryptoConfigurationError("privacy_master_key_invalid")
    return raw


def _normalise_subject_id(subject_id: str) -> str:
    value = unicodedata.normalize("NFKC", subject_id).strip()
    if not value:
        raise ValueError("subject_id_required")
    return value


def subject_tokens(workspace_id: str, subject_id: str) -> list[tuple[str, str]]:
    if not SETTINGS.master_keys:
        raise CryptoConfigurationError("privacy_crypto_not_configured")
    subject = _normalise_subject_id(subject_id)
    message = b"ORBYTHRA-GDPR-SUBJECT-V1\x00" + workspace_id.encode("utf-8") + b"\x00" + subject.encode("utf-8")
    return [(key_id, hmac.new(_decode_key(encoded), message, hashlib.sha256).hexdigest()) for key_id, encoded in SETTINGS.master_keys]


def active_subject_token(workspace_id: str, subject_id: str) -> tuple[str, str]:
    return subject_tokens(workspace_id, subject_id)[0]


def retention_deadline(retention_days: int, now: int | None = None) -> int:
    base = int(time.time()) if now is None else int(now)
    return base + int(retention_days) * 86400


def record_payload(*, data_categories: list[str], declared_fields: list[str], payload: dict[str, Any], consent_reference: str | None, special_category: bool, article9_condition: str | None) -> dict[str, Any]:
    return {
        "data_categories": sorted({item.strip() for item in data_categories if item.strip()}),
        "declared_fields": sorted({item.strip() for item in declared_fields if item.strip()}),
        "payload": payload,
        "consent_reference": consent_reference,
        "special_category": bool(special_category),
        "article9_condition": article9_condition,
    }


def minimised_payload(payload: dict[str, Any], declared_fields: list[str]) -> dict[str, Any]:
    declared = {item.strip() for item in declared_fields if item.strip()}
    unknown = set(payload) - declared
    if unknown:
        raise ValueError("undeclared_payload_fields:" + ",".join(sorted(unknown)))
    return {key: payload[key] for key in payload if key in declared}
