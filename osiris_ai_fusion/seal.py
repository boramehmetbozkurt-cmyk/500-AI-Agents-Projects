from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import time
import unicodedata
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from config import get_settings
from provenance import sha256_hex

INTENT_DOMAIN = b"OSIRIS-SEAL-INTENT-V2"
RECEIPT_DOMAIN = b"OSIRIS-SEAL-RECEIPT-V2"


def _norm_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _canon_decimal(value: Any) -> str:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc
    s = format(d.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _canon(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k).lower(): _canon(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]).lower())
        }
    if isinstance(value, list):
        return [_canon(v) for v in value]
    if isinstance(value, str):
        return _norm_text(value)
    if isinstance(value, float):
        return _canon_decimal(value)
    return value


def _domain_hash(domain: bytes, payload: bytes) -> str:
    framed = len(domain).to_bytes(8, "big") + domain + len(payload).to_bytes(8, "big") + payload
    return hashlib.sha256(framed).hexdigest()


@dataclass(frozen=True)
class SealedIntent:
    schema_version: int
    intent_id: str
    query: str
    allowed_tools: list[str]
    scope: dict[str, Any]
    expected_effect: dict[str, Any]
    created_at: int
    expires_at: int
    nonce: str
    human_readable: str

    def canonical_bytes(self) -> bytes:
        return cbor2.dumps(_canon(asdict(self)), canonical=True)

    def digest(self) -> str:
        return _domain_hash(INTENT_DOMAIN, self.canonical_bytes())


class ReplayGuard:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_settings().seal_replay_db
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS seal_nonces ("
                "nonce TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)"
            )
            conn.commit()

    def consume(self, nonce: str, expires_at: int) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("DELETE FROM seal_nonces WHERE expires_at < ?", (now,))
            try:
                conn.execute(
                    "INSERT INTO seal_nonces(nonce, expires_at) VALUES (?, ?)",
                    (nonce, expires_at),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise PermissionError("Replay detected: nonce already consumed") from exc


def seal_intent(
    query: str,
    allowed_tools: list[str],
    scope: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> SealedIntent:
    settings = get_settings()
    ttl = ttl_seconds or settings.seal_ttl_seconds
    now = int(time.time())
    nonce = os.urandom(16).hex()
    normalized_query = _norm_text(query)
    tools = sorted(set(t.lower() for t in allowed_tools))
    normalized_scope = _canon(scope or {})
    expected_effect = {
        "read_only": True,
        "max_tool_calls": min(settings.max_tool_calls, len(tools)),
        "allowed_tools": tools,
    }
    intent_id = hashlib.sha256(
        f"{normalized_query}|{nonce}|{now}".encode("utf-8")
    ).hexdigest()[:24]
    human = (
        f"Query={normalized_query}; tools={','.join(tools)}; "
        f"read_only=true; max_tool_calls={expected_effect['max_tool_calls']}"
    )
    return SealedIntent(
        schema_version=2,
        intent_id=intent_id,
        query=normalized_query,
        allowed_tools=tools,
        scope=normalized_scope,
        expected_effect=expected_effect,
        created_at=now,
        expires_at=now + ttl,
        nonce=nonce,
        human_readable=human,
    )


def authorize_execution(
    intent: SealedIntent,
    requested_tools: list[str],
    replay_guard: ReplayGuard | None = None,
) -> None:
    now = int(time.time())
    if now > intent.expires_at:
        raise PermissionError("Intent expired")
    tools = sorted(set(t.lower() for t in requested_tools))
    unauthorized = [tool for tool in tools if tool not in intent.allowed_tools]
    if unauthorized:
        raise PermissionError(f"Unauthorized tools requested: {unauthorized}")
    if len(tools) > int(intent.expected_effect["max_tool_calls"]):
        raise PermissionError("Requested tool count exceeds sealed intent budget")
    (replay_guard or ReplayGuard()).consume(intent.nonce, intent.expires_at)


def _load_private_key() -> Ed25519PrivateKey | None:
    raw_b64 = os.getenv("SEAL_ED25519_PRIVATE_KEY_B64", "").strip()
    if not raw_b64:
        return None
    raw = base64.b64decode(raw_b64)
    if len(raw) != 32:
        raise ValueError("SEAL_ED25519_PRIVATE_KEY_B64 must decode to 32 raw bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def _receipt_signing_bytes(receipt: dict[str, Any]) -> bytes:
    payload = cbor2.dumps(_canon(receipt), canonical=True)
    return (
        len(RECEIPT_DOMAIN).to_bytes(8, "big")
        + RECEIPT_DOMAIN
        + len(payload).to_bytes(8, "big")
        + payload
    )


def sign_receipt(
    intent: SealedIntent,
    executed_tools: list[str],
    effect_summary: str,
    evidence_digest: str,
) -> dict[str, Any]:
    if int(time.time()) > intent.expires_at:
        raise PermissionError("Intent expired")
    executed = sorted(set(t.lower() for t in executed_tools))
    unauthorized = [tool for tool in executed if tool not in intent.allowed_tools]
    if unauthorized:
        raise PermissionError(f"Unauthorized tools executed: {unauthorized}")

    actual_effect = {
        "read_only": True,
        "executed_tools": executed,
        "tool_call_count": len(executed),
        "evidence_digest": evidence_digest,
        "analysis_digest": sha256_hex(_norm_text(effect_summary)),
    }
    bounded_match = (
        actual_effect["read_only"] is True
        and len(executed) <= int(intent.expected_effect["max_tool_calls"])
        and not unauthorized
    )
    receipt: dict[str, Any] = {
        "schema_version": 2,
        "intent_id": intent.intent_id,
        "intent_digest": intent.digest(),
        "scope": intent.scope,
        "executed_tools": executed,
        "expected_effect": intent.expected_effect,
        "actual_effect": actual_effect,
        "verified_at": int(time.time()),
        "policy_check": "PASS" if bounded_match else "FAIL",
        "effect_match": "BOUNDED_PASS" if bounded_match else "FAIL",
        "verification_model": "tool-scope + read-only effect + evidence binding",
        "signature_alg": None,
        "public_key_b64": None,
        "signature_b64": None,
    }

    private_key = _load_private_key()
    if private_key is not None:
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        receipt["signature_alg"] = "Ed25519"
        receipt["public_key_b64"] = base64.b64encode(public_key).decode("ascii")
        unsigned = {k: v for k, v in receipt.items() if k != "signature_b64"}
        receipt["signature_b64"] = base64.b64encode(
            private_key.sign(_receipt_signing_bytes(unsigned))
        ).decode("ascii")
    elif get_settings().require_signed_receipts:
        raise RuntimeError("Signed receipts are required but no SEAL Ed25519 key is configured")

    return receipt


def verify_receipt(receipt: dict[str, Any]) -> bool:
    signature_b64 = receipt.get("signature_b64")
    public_key_b64 = receipt.get("public_key_b64")
    if not signature_b64 or not public_key_b64:
        return False
    unsigned = {k: v for k, v in receipt.items() if k != "signature_b64"}
    public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            _receipt_signing_bytes(unsigned),
        )
        return True
    except Exception:
        return False
