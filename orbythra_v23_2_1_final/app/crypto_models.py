from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ApprovalProof(BaseModel):
    approver_id: str = Field(min_length=1, max_length=120)
    intent_digest: str = Field(min_length=64, max_length=64)
    proof_type: Literal["gesture", "passkey", "signature", "hybrid_signature", "two_party", "manual"] = "gesture"
    proof: str = Field(min_length=1, max_length=4096)
    public_key_b64: str | None = Field(default=None, max_length=128)
    pq_public_key_b64: str | None = Field(default=None, max_length=4096)
    pq_proof: str | None = Field(default=None, max_length=8192)


class CommitRequest(BaseModel):
    intent: dict[str, Any]
    effect: dict[str, Any] | None = None


class CommitResponse(BaseModel):
    intent_sha256: str
    intent_sha3_256: str
    effect_sha256: str | None = None
    effect_sha3_256: str | None = None
    effect_binding_ok: bool
    mismatched_fields: list[str]


class SealRequest(BaseModel):
    payload: dict[str, Any]
    intent: dict[str, Any]
    effect: dict[str, Any] | None = None
    approvals: list[ApprovalProof] = Field(default_factory=list, max_length=10)
    min_approvals: int = Field(default=1, ge=0, le=3)
    domain: str = Field(default="transaction", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    ttl_seconds: int | None = Field(default=None, ge=0, le=2_592_000)
    algorithm: Literal["aes256-gcm", "chacha20-poly1305"] | None = None
    recipient_public_key_b64: str | None = Field(default=None, max_length=128)
    recipient_mlkem768_public_key_b64: str | None = Field(default=None, max_length=4096)


class SealResponse(BaseModel):
    envelope: dict[str, Any]
    intent_digest: str
    algorithm: str
    key_id: str
    expires_at: int
    approval_count: int


class OpenRequest(BaseModel):
    envelope: dict[str, Any]
    expected_intent_digest: str | None = Field(default=None, min_length=64, max_length=64)
    enforce_replay_protection: bool = True


class OpenResponse(BaseModel):
    payload: dict[str, Any]
    intent: dict[str, Any]
    effect: dict[str, Any] | None
    intent_digest: str
    signer_verified: bool
    outcome_receipt: dict[str, Any]


class RecipientOpenRequest(BaseModel):
    envelope: dict[str, Any]
    recipient_private_key_b64: str = Field(min_length=40, max_length=128)
    expected_signing_public_key_b64: str = Field(min_length=40, max_length=128)
    expected_pq_signing_public_key_b64: str | None = Field(default=None, max_length=4096)
    expected_intent_digest: str | None = Field(default=None, min_length=64, max_length=64)
    enforce_replay_protection: bool = True


class HybridRecipientOpenRequest(BaseModel):
    envelope: dict[str, Any]
    recipient_x25519_private_key_b64: str = Field(min_length=40, max_length=128)
    recipient_mlkem768_private_key_b64: str = Field(min_length=40, max_length=256)
    expected_signing_public_key_b64: str = Field(min_length=40, max_length=128)
    expected_pq_signing_public_key_b64: str | None = Field(default=None, max_length=4096)
    expected_intent_digest: str | None = Field(default=None, min_length=64, max_length=64)
    enforce_replay_protection: bool = True


class RecipientOpenResponse(BaseModel):
    payload: dict[str, Any]
    intent: dict[str, Any]
    effect: dict[str, Any] | None
    intent_digest: str
    signer_verified: bool
    recipient_verified: bool
    ciphertext_sha256: str
    opened_at: int


class CryptoStatusResponse(BaseModel):
    configured: bool
    active_key_id: str | None
    available_key_ids: list[str]
    active_signing_key_id: str | None = None
    available_signing_key_ids: list[str] = Field(default_factory=list)
    signing_keys_isolated: bool = False
    pqc_mode: str = "off"
    pqc_backend_available: bool = False
    default_algorithm: str
    components: list[str]
