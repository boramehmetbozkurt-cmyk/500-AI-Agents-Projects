from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.action_chain_v12 import ACTION_CHAIN_V12
from app.crypto_core import CryptoConfigurationError, CryptoValidationError, canonical_json, commitment, open_envelope, seal
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v15/action-chain", tags=["v15-action-chain-finalization"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class FinalizedActionChain(BaseModel):
    finalization_id: str
    chain_id: str
    chain_head_sha256: str
    chain_receipt_sha256: str
    signed_envelope: dict[str, Any]
    envelope_sha256: str
    created_at: int


class VerifyFinalizationRequest(BaseModel):
    chain_id: str = Field(min_length=1, max_length=200)
    signed_envelope: dict[str, Any]


class VerifyFinalizationResponse(BaseModel):
    chain_id: str
    valid: bool
    signer_verified: bool
    chain_integrity_verified: bool
    chain_head_matches: bool
    chain_receipt_matches: bool
    envelope_sha256: str


class ActionChainFinalizationStoreV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS action_chain_finalizations_v15(
                    finalization_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    chain_id TEXT NOT NULL,
                    chain_head_sha256 TEXT NOT NULL,
                    chain_receipt_sha256 TEXT NOT NULL,
                    envelope_sha256 TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    UNIQUE(workspace_id,chain_id,chain_receipt_sha256)
                    )"""
                )
            )

    def persist(self, workspace_id: str, result: FinalizedActionChain) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO action_chain_finalizations_v15(
                    finalization_id,workspace_id,chain_id,chain_head_sha256,chain_receipt_sha256,envelope_sha256,created_at
                    ) VALUES(:id,:w,:c,:h,:r,:e,:t)"""
                ),
                {
                    "id": result.finalization_id,
                    "w": workspace_id,
                    "c": result.chain_id,
                    "h": result.chain_head_sha256,
                    "r": result.chain_receipt_sha256,
                    "e": result.envelope_sha256,
                    "t": result.created_at,
                },
            )


ACTION_CHAIN_FINALIZATION_V15 = ActionChainFinalizationStoreV15()


def _intent(workspace_id: str, chain_id: str, head_sha256: str, receipt_sha256: str) -> dict[str, str]:
    return {
        "workspace_id": workspace_id,
        "chain_id": chain_id,
        "chain_head_sha256": head_sha256,
        "chain_receipt_sha256": receipt_sha256,
    }


def finalize_chain(workspace_id: str, chain_id: str, *, now: int | None = None) -> FinalizedActionChain:
    chain = ACTION_CHAIN_V12.get(workspace_id, chain_id)
    if chain.status != "COMPLETE":
        raise ValueError("action_chain_not_complete")
    if not chain.integrity_verified:
        raise ValueError("action_chain_integrity_failed")
    created_at = int(time.time()) if now is None else int(now)
    intent = _intent(workspace_id, chain_id, chain.head_sha256, chain.chain_receipt_sha256)
    try:
        envelope = seal(
            payload={
                "kind": "orbythra-v15-action-chain-finalization",
                "chain_id": chain_id,
                "chain_head_sha256": chain.head_sha256,
                "chain_receipt_sha256": chain.chain_receipt_sha256,
            },
            intent=intent,
            effect=None,
            approvals=[],
            min_approvals=0,
            workspace_id=workspace_id,
            domain="action-chain-v15-finalization",
            ttl_seconds=0,
        )
    except CryptoConfigurationError as exc:
        raise RuntimeError("crypto_master_key_not_configured") from exc
    envelope_sha = _hash(envelope)
    result = FinalizedActionChain(
        finalization_id="acf15_" + uuid.uuid4().hex[:24],
        chain_id=chain_id,
        chain_head_sha256=chain.head_sha256,
        chain_receipt_sha256=chain.chain_receipt_sha256,
        signed_envelope=envelope,
        envelope_sha256=envelope_sha,
        created_at=created_at,
    )
    ACTION_CHAIN_FINALIZATION_V15.persist(workspace_id, result)
    return result


def verify_finalization(workspace_id: str, chain_id: str, envelope: dict[str, Any]) -> VerifyFinalizationResponse:
    chain = ACTION_CHAIN_V12.get(workspace_id, chain_id)
    intent = _intent(workspace_id, chain_id, chain.head_sha256, chain.chain_receipt_sha256)
    intent_digest = commitment(intent, domain="intent")["sha256"]
    try:
        opened = open_envelope(envelope, expected_workspace_id=workspace_id, expected_intent_digest=intent_digest)
    except (CryptoConfigurationError, CryptoValidationError):
        return VerifyFinalizationResponse(
            chain_id=chain_id,
            valid=False,
            signer_verified=False,
            chain_integrity_verified=chain.integrity_verified,
            chain_head_matches=False,
            chain_receipt_matches=False,
            envelope_sha256=_hash(envelope),
        )
    payload = opened["content"].get("payload") or {}
    head_matches = payload.get("chain_head_sha256") == chain.head_sha256
    receipt_matches = payload.get("chain_receipt_sha256") == chain.chain_receipt_sha256
    signer_verified = bool(opened.get("signer_verified"))
    return VerifyFinalizationResponse(
        chain_id=chain_id,
        valid=bool(chain.integrity_verified and signer_verified and head_matches and receipt_matches),
        signer_verified=signer_verified,
        chain_integrity_verified=chain.integrity_verified,
        chain_head_matches=head_matches,
        chain_receipt_matches=receipt_matches,
        envelope_sha256=_hash(envelope),
    )


@router.post("/chains/{chain_id}/finalize", response_model=FinalizedActionChain)
def finalize(chain_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> FinalizedActionChain:
    try:
        result = finalize_chain(principal.workspace_id, chain_id)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail == "action_chain_not_found" else 409, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.finalization_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="action_chain_v15_finalize",
        status="SIGNED",
        metadata={
            "finalization_id": result.finalization_id,
            "chain_id": chain_id,
            "chain_head_sha256": result.chain_head_sha256,
            "chain_receipt_sha256": result.chain_receipt_sha256,
            "envelope_sha256": result.envelope_sha256,
        },
    )
    return result


@router.post("/verify", response_model=VerifyFinalizationResponse)
def verify(body: VerifyFinalizationRequest, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> VerifyFinalizationResponse:
    try:
        return verify_finalization(principal.workspace_id, body.chain_id, body.signed_envelope)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "complete_chain_required": True,
        "chain_integrity_required": True,
        "ed25519_signed_encrypted_finalization_envelope": True,
        "workspace_binding": True,
        "intent_commitment_binding": True,
        "head_and_receipt_reverification": True,
        "tampered_envelope_rejection": True,
    }
