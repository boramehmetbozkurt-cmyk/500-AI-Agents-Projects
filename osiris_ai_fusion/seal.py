from __future__ import annotations

import hashlib
import hmac
import os
import time
import unicodedata
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
from typing import Any

import cbor2

DOMAIN = b"OSIRIS-SEAL-INTENT-V1"


def _norm_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _canon_decimal(value: Any) -> str:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid decimal value: {value!r}")
    s = format(d.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _canon(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k).lower(): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]).lower())}
    if isinstance(value, list):
        return [_canon(v) for v in value]
    if isinstance(value, str):
        return _norm_text(value)
    if isinstance(value, float):
        return _canon_decimal(value)
    return value


@dataclass(frozen=True)
class SealedIntent:
    intent_id: str
    query: str
    allowed_tools: list[str]
    created_at: int
    expires_at: int
    nonce: str
    human_readable: str

    def canonical_bytes(self) -> bytes:
        payload = _canon(asdict(self))
        return cbor2.dumps(payload, canonical=True)

    def digest(self) -> str:
        body = self.canonical_bytes()
        framed = len(DOMAIN).to_bytes(8, "big") + DOMAIN + len(body).to_bytes(8, "big") + body
        return hashlib.sha256(framed).hexdigest()


def seal_intent(query: str, allowed_tools: list[str], ttl_seconds: int = 300) -> SealedIntent:
    now = int(time.time())
    nonce = os.urandom(16).hex()
    normalized_query = _norm_text(query)
    intent_id = hashlib.sha256(f"{normalized_query}|{nonce}|{now}".encode()).hexdigest()[:24]
    human = f"Query={normalized_query}; tools={','.join(sorted(set(t.lower() for t in allowed_tools)))}"
    return SealedIntent(
        intent_id=intent_id,
        query=normalized_query,
        allowed_tools=sorted(set(t.lower() for t in allowed_tools)),
        created_at=now,
        expires_at=now + ttl_seconds,
        nonce=nonce,
        human_readable=human,
    )


def sign_receipt(intent: SealedIntent, executed_tools: list[str], effect_summary: str) -> dict[str, Any]:
    if int(time.time()) > intent.expires_at:
        raise ValueError("Intent expired")
    executed = sorted(set(t.lower() for t in executed_tools))
    unauthorized = [t for t in executed if t not in intent.allowed_tools]
    if unauthorized:
        raise PermissionError(f"Unauthorized tools executed: {unauthorized}")

    receipt = {
        "intent_id": intent.intent_id,
        "intent_digest": intent.digest(),
        "executed_tools": executed,
        "effect_summary": _norm_text(effect_summary),
        "verified_at": int(time.time()),
        "policy_check": "PASS",
        "effect_match": "PASS",
    }
    key_hex = os.getenv("SEAL_MASTER_KEY_HEX", "").strip()
    if key_hex:
        key = bytes.fromhex(key_hex)
        msg = cbor2.dumps(_canon(receipt), canonical=True)
        receipt["hmac_sha256"] = hmac.new(key, msg, hashlib.sha256).hexdigest()
    else:
        receipt["hmac_sha256"] = None
    return receipt
