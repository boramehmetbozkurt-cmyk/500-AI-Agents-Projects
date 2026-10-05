from __future__ import annotations

import hashlib
import math
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.config import SETTINGS
from app.crypto_core import canonical_json
from app.enterprise import evaluate_policy
from app.enterprise_models import EnterprisePolicy, ModelInvocationRequest, ModelMessage, PolicyEvaluationRequest, ProviderProfile, RiskTier
from app.enterprise_store import ENTERPRISE_STORE
from app.failure_memory_v15 import FAILURE_MEMORY_V15, FailureObservation
from app.provider_gateway import ProviderGatewayError, invoke_registered_model
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v15/long-generation", tags=["v15-long-generation"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

SessionStatus = Literal["ACTIVE", "COMPLETE", "ABORTED"]
TokenAccounting = Literal["requested_budget", "utf8_estimate"]
_MAX_TOTAL_TOKENS = 2_000_000
_MAX_CHUNK_TOKENS = 32_768
_MAX_STEPS_PER_CALL = 4


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _estimate_tokens(value: str) -> int:
    # Provider-independent fallback only. The exact tokenizer is model/provider specific.
    # We intentionally expose this as an estimate and never relabel it as exact usage.
    if not value:
        return 0
    return max(1, math.ceil(len(value.encode("utf-8")) / 4))


class LongGenerationSessionRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=160)
    messages: list[ModelMessage] = Field(min_length=1, max_length=198)
    policy_id: str = Field(default="default", min_length=1, max_length=80)
    risk_tier: RiskTier = "moderate"
    data_categories: list[str] = Field(default_factory=list, max_length=100)
    evidence_pass_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    guarded_claims: int = Field(default=0, ge=0, le=1000)
    retention_days: int = Field(default=0, ge=0, le=36500)
    human_approved: bool = False
    target_total_tokens: int = Field(default=32_768, ge=1, le=_MAX_TOTAL_TOKENS)
    chunk_max_tokens: int = Field(default=32_768, ge=256, le=_MAX_CHUNK_TOKENS)
    continuation_overlap_chars: int = Field(default=8_000, ge=0, le=16_000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class LongGenerationBatchRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=_MAX_STEPS_PER_CALL)


class LongGenerationChunk(BaseModel):
    session_id: str
    chunk_index: int
    text: str
    requested_token_budget: int
    estimated_output_tokens: int
    token_accounting: TokenAccounting = "utf8_estimate"
    text_sha256: str
    chain_sha256: str
    request_reference: str
    latency_ms: float
    created_at: int


class LongGenerationSession(BaseModel):
    session_id: str
    status: SessionStatus
    provider_id: str
    model_id: str
    policy_id: str
    target_total_tokens: int
    chunk_max_tokens: int
    allocated_output_token_budget: int
    estimated_output_tokens: int
    generated_characters: int
    next_chunk_index: int
    minimum_planned_chunks: int
    progress: float
    last_chain_sha256: str | None
    created_at: int
    updated_at: int


class LongGenerationBatchResponse(BaseModel):
    session: LongGenerationSession
    chunks: list[LongGenerationChunk]


class LongGenerationManifest(BaseModel):
    session_id: str
    status: SessionStatus
    target_total_tokens: int
    allocated_output_token_budget: int
    estimated_output_tokens: int
    chunk_count: int
    chunk_hashes: list[str]
    final_chain_sha256: str | None
    manifest_sha256: str
    accounting_note: str


class LongGenerationStoreV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS long_generation_sessions_v15(
                    workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    encrypted_request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_total_tokens INTEGER NOT NULL,
                    chunk_max_tokens INTEGER NOT NULL,
                    allocated_output_token_budget INTEGER NOT NULL,
                    estimated_output_tokens INTEGER NOT NULL,
                    generated_characters BIGINT NOT NULL,
                    next_chunk_index INTEGER NOT NULL,
                    last_chain_sha256 TEXT,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    PRIMARY KEY(workspace_id,session_id)
                    )"""
                )
            )
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS long_generation_chunks_v15(
                    workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    encrypted_text TEXT NOT NULL,
                    requested_token_budget INTEGER NOT NULL,
                    estimated_output_tokens INTEGER NOT NULL,
                    text_sha256 TEXT NOT NULL,
                    chain_sha256 TEXT NOT NULL,
                    request_reference TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    created_at BIGINT NOT NULL,
                    PRIMARY KEY(workspace_id,session_id,chunk_index)
                    )"""
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_longgen_v15_status ON long_generation_sessions_v15(workspace_id,status,updated_at)"))

    def create(self, workspace_id: str, principal_id: str, body: LongGenerationSessionRequest, *, now: int | None = None) -> LongGenerationSession:
        created_at = int(time.time()) if now is None else int(now)
        session_id = "lg15_" + uuid.uuid4().hex[:24]
        protected = body.model_dump(mode="json")
        protected["last_tail"] = ""
        encrypted = VAULT.encrypt_json(protected, workspace_id=workspace_id, purpose="long-generation-session-v15")
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO long_generation_sessions_v15(
                    workspace_id,session_id,principal_id,provider_id,model_id,policy_id,encrypted_request_json,status,
                    target_total_tokens,chunk_max_tokens,allocated_output_token_budget,estimated_output_tokens,
                    generated_characters,next_chunk_index,last_chain_sha256,created_at,updated_at
                    ) VALUES(:w,:id,:principal,:provider,:model,:policy,:request,'ACTIVE',:target,:chunk,0,0,0,0,NULL,:created,:updated)"""
                ),
                {
                    "w": workspace_id,
                    "id": session_id,
                    "principal": principal_id,
                    "provider": body.provider_id,
                    "model": body.model_id,
                    "policy": body.policy_id,
                    "request": encrypted,
                    "target": body.target_total_tokens,
                    "chunk": body.chunk_max_tokens,
                    "created": created_at,
                    "updated": created_at,
                },
            )
        result = self.get(workspace_id, session_id)
        if result is None:
            raise RuntimeError("long_generation_session_not_persisted")
        return result

    def _row(self, workspace_id: str, session_id: str) -> dict[str, object] | None:
        with STORE.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM long_generation_sessions_v15 WHERE workspace_id=:w AND session_id=:id"),
                {"w": workspace_id, "id": session_id},
            ).mappings().first()
        return None if row is None else dict(row)

    def protected_request(self, workspace_id: str, session_id: str) -> dict[str, object] | None:
        row = self._row(workspace_id, session_id)
        if row is None:
            return None
        return VAULT.decrypt_json(str(row["encrypted_request_json"]), workspace_id=workspace_id, purpose="long-generation-session-v15")

    def get(self, workspace_id: str, session_id: str) -> LongGenerationSession | None:
        row = self._row(workspace_id, session_id)
        if row is None:
            return None
        target = int(row["target_total_tokens"])
        allocated = int(row["allocated_output_token_budget"])
        return LongGenerationSession(
            session_id=str(row["session_id"]),
            status=str(row["status"]),
            provider_id=str(row["provider_id"]),
            model_id=str(row["model_id"]),
            policy_id=str(row["policy_id"]),
            target_total_tokens=target,
            chunk_max_tokens=int(row["chunk_max_tokens"]),
            allocated_output_token_budget=allocated,
            estimated_output_tokens=int(row["estimated_output_tokens"]),
            generated_characters=int(row["generated_characters"]),
            next_chunk_index=int(row["next_chunk_index"]),
            minimum_planned_chunks=math.ceil(target / int(row["chunk_max_tokens"])),
            progress=round(min(1.0, allocated / target), 6),
            last_chain_sha256=None if row["last_chain_sha256"] is None else str(row["last_chain_sha256"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def append_chunk(
        self,
        workspace_id: str,
        session_id: str,
        *,
        chunk_index: int,
        text_value: str,
        requested_token_budget: int,
        estimated_output_tokens: int,
        text_sha256: str,
        chain_sha256: str,
        request_reference: str,
        latency_ms: float,
        last_tail: str,
        now: int | None = None,
    ) -> LongGenerationChunk:
        created_at = int(time.time()) if now is None else int(now)
        row = self._row(workspace_id, session_id)
        if row is None:
            raise ValueError("long_generation_session_not_found")
        if str(row["status"]) != "ACTIVE":
            raise ValueError("long_generation_session_not_active")
        protected = VAULT.decrypt_json(str(row["encrypted_request_json"]), workspace_id=workspace_id, purpose="long-generation-session-v15")
        protected["last_tail"] = last_tail
        encrypted_request = VAULT.encrypt_json(protected, workspace_id=workspace_id, purpose="long-generation-session-v15")
        encrypted_text = VAULT.encrypt_json({"text": text_value}, workspace_id=workspace_id, purpose="long-generation-chunk-v15")
        new_allocated = int(row["allocated_output_token_budget"]) + requested_token_budget
        new_estimated = int(row["estimated_output_tokens"]) + estimated_output_tokens
        new_characters = int(row["generated_characters"]) + len(text_value)
        target = int(row["target_total_tokens"])
        new_status = "COMPLETE" if new_allocated >= target else "ACTIVE"
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO long_generation_chunks_v15(
                    workspace_id,session_id,chunk_index,encrypted_text,requested_token_budget,estimated_output_tokens,
                    text_sha256,chain_sha256,request_reference,latency_ms,created_at
                    ) VALUES(:w,:id,:idx,:text,:budget,:estimate,:text_sha,:chain_sha,:ref,:latency,:created)"""
                ),
                {
                    "w": workspace_id,
                    "id": session_id,
                    "idx": chunk_index,
                    "text": encrypted_text,
                    "budget": requested_token_budget,
                    "estimate": estimated_output_tokens,
                    "text_sha": text_sha256,
                    "chain_sha": chain_sha256,
                    "ref": request_reference,
                    "latency": latency_ms,
                    "created": created_at,
                },
            )
            connection.execute(
                text(
                    """UPDATE long_generation_sessions_v15 SET encrypted_request_json=:request,status=:status,
                    allocated_output_token_budget=:allocated,estimated_output_tokens=:estimated,
                    generated_characters=:characters,next_chunk_index=:next_index,last_chain_sha256=:chain,updated_at=:updated
                    WHERE workspace_id=:w AND session_id=:id"""
                ),
                {
                    "request": encrypted_request,
                    "status": new_status,
                    "allocated": new_allocated,
                    "estimated": new_estimated,
                    "characters": new_characters,
                    "next_index": chunk_index + 1,
                    "chain": chain_sha256,
                    "updated": created_at,
                    "w": workspace_id,
                    "id": session_id,
                },
            )
        return LongGenerationChunk(
            session_id=session_id,
            chunk_index=chunk_index,
            text=text_value,
            requested_token_budget=requested_token_budget,
            estimated_output_tokens=estimated_output_tokens,
            text_sha256=text_sha256,
            chain_sha256=chain_sha256,
            request_reference=request_reference,
            latency_ms=round(latency_ms, 3),
            created_at=created_at,
        )

    def chunk(self, workspace_id: str, session_id: str, chunk_index: int) -> LongGenerationChunk | None:
        with STORE.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM long_generation_chunks_v15 WHERE workspace_id=:w AND session_id=:id AND chunk_index=:idx"),
                {"w": workspace_id, "id": session_id, "idx": chunk_index},
            ).mappings().first()
        if row is None:
            return None
        protected = VAULT.decrypt_json(str(row["encrypted_text"]), workspace_id=workspace_id, purpose="long-generation-chunk-v15")
        return LongGenerationChunk(
            session_id=session_id,
            chunk_index=int(row["chunk_index"]),
            text=str(protected["text"]),
            requested_token_budget=int(row["requested_token_budget"]),
            estimated_output_tokens=int(row["estimated_output_tokens"]),
            text_sha256=str(row["text_sha256"]),
            chain_sha256=str(row["chain_sha256"]),
            request_reference=str(row["request_reference"]),
            latency_ms=float(row["latency_ms"]),
            created_at=int(row["created_at"]),
        )

    def chunk_hashes(self, workspace_id: str, session_id: str) -> list[str]:
        with STORE.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT text_sha256 FROM long_generation_chunks_v15 WHERE workspace_id=:w AND session_id=:id ORDER BY chunk_index"),
                {"w": workspace_id, "id": session_id},
            ).mappings().all()
        return [str(row["text_sha256"]) for row in rows]

    def abort(self, workspace_id: str, session_id: str, *, now: int | None = None) -> LongGenerationSession:
        updated_at = int(time.time()) if now is None else int(now)
        with STORE.engine.begin() as connection:
            result = connection.execute(
                text("UPDATE long_generation_sessions_v15 SET status='ABORTED',updated_at=:updated WHERE workspace_id=:w AND session_id=:id AND status='ACTIVE'"),
                {"updated": updated_at, "w": workspace_id, "id": session_id},
            )
        if not result.rowcount and self.get(workspace_id, session_id) is None:
            raise ValueError("long_generation_session_not_found")
        session = self.get(workspace_id, session_id)
        if session is None:
            raise RuntimeError("long_generation_abort_not_persisted")
        return session


LONG_GENERATION_V15 = LongGenerationStoreV15()


def _policy_guard(workspace_id: str, protected: dict[str, object]) -> ProviderProfile:
    policy_id = str(protected["policy_id"])
    provider_id = str(protected["provider_id"])
    stored_policy = ENTERPRISE_STORE.get_policy(workspace_id, policy_id)
    if stored_policy is None:
        raise HTTPException(status_code=404, detail="policy_not_found")
    stored_provider = ENTERPRISE_STORE.get_provider(workspace_id, provider_id)
    if stored_provider is None:
        raise HTTPException(status_code=404, detail="provider_not_found")
    provider = ProviderProfile(**stored_provider)
    decision = evaluate_policy(
        EnterprisePolicy(**stored_policy),
        provider,
        PolicyEvaluationRequest(
            policy_id=policy_id,
            provider_id=provider_id,
            risk_tier=str(protected["risk_tier"]),
            data_categories=list(protected.get("data_categories") or []),
            evidence_pass_rate=float(protected["evidence_pass_rate"]),
            guarded_claims=int(protected["guarded_claims"]),
            retention_days=int(protected["retention_days"]),
            human_approved=bool(protected["human_approved"]),
        ),
    )
    if decision.decision == "BLOCK":
        raise HTTPException(status_code=403, detail={"policy_decision": "BLOCK", "reasons": decision.reasons})
    if decision.decision == "REVIEW":
        raise HTTPException(status_code=409, detail={"policy_decision": "REVIEW", "reasons": decision.reasons})
    return provider


def _continuation_messages(protected: dict[str, object], session: LongGenerationSession, chunk_index: int) -> list[ModelMessage]:
    base_messages = [ModelMessage(**item) for item in list(protected["messages"])]
    directive = ModelMessage(
        role="system",
        content=(
            "ORBYTHRA V15 long-generation control: produce only the next coherent segment of the requested answer. "
            f"This is segment {chunk_index + 1}; aggregate requested output-token budget is {session.target_total_tokens}. "
            "Preserve the user's objective, terminology and constraints. Do not restart, summarize prior material, or claim the overall task is complete unless this is the final budget segment."
        ),
    )
    messages = [directive, *base_messages]
    last_tail = str(protected.get("last_tail") or "")
    if last_tail:
        messages.append(ModelMessage(role="assistant", content=last_tail))
        messages.append(ModelMessage(role="user", content="Continue directly from the prior output tail without repetition or reset."))
    return messages


def _record_generation_failure(workspace_id: str, session_id: str, error_class: str, detail: str) -> None:
    try:
        FAILURE_MEMORY_V15.record(
            workspace_id,
            FailureObservation(
                component="long-generation-v15",
                error_class=error_class[:200],
                invariant="long-generation chunks must remain policy-governed, resumable and integrity-chained",
                severity="medium",
                evidence_sha256=_hash({"session_id": session_id, "error_class": error_class, "detail": detail}),
                release_sha=SETTINGS.release_sha or "v15-long-generation-candidate",
            ),
        )
    except Exception:
        # Failure-memory telemetry must never mask the original generation failure.
        pass


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "aggregate_output_token_budget_max": _MAX_TOTAL_TOKENS,
        "per_provider_call_token_cap": _MAX_CHUNK_TOKENS,
        "resumable_chunking": True,
        "encrypted_session_and_chunk_storage": True,
        "workspace_isolation": True,
        "policy_revalidation_before_each_chunk": True,
        "sha256_chunk_and_chain_receipts": True,
        "failure_memory_integration": True,
        "token_accounting_boundary": "2,000,000 is an aggregate requested output-token budget; exact emitted tokens remain provider/tokenizer dependent and are exposed only as an estimate in this provider-neutral layer.",
    }


@router.post("/sessions", response_model=LongGenerationSession)
def create_session(body: LongGenerationSessionRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> LongGenerationSession:
    protected = body.model_dump(mode="json")
    _policy_guard(principal.workspace_id, protected)
    result = LONG_GENERATION_V15.create(principal.workspace_id, principal.principal_id, body)
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.session_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="long_generation_v15_create",
        status="ACTIVE",
        metadata={
            "session_id": result.session_id,
            "provider_id": result.provider_id,
            "model_id": result.model_id,
            "target_total_tokens": result.target_total_tokens,
            "chunk_max_tokens": result.chunk_max_tokens,
        },
    )
    return result


@router.get("/sessions/{session_id}", response_model=LongGenerationSession)
def get_session(session_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> LongGenerationSession:
    result = LONG_GENERATION_V15.get(principal.workspace_id, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="long_generation_session_not_found")
    return result


@router.post("/sessions/{session_id}/generate", response_model=LongGenerationBatchResponse)
def generate(session_id: str, body: LongGenerationBatchRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> LongGenerationBatchResponse:
    session = LONG_GENERATION_V15.get(principal.workspace_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="long_generation_session_not_found")
    if session.status != "ACTIVE":
        return LongGenerationBatchResponse(session=session, chunks=[])
    protected = LONG_GENERATION_V15.protected_request(principal.workspace_id, session_id)
    if protected is None:
        raise HTTPException(status_code=404, detail="long_generation_session_not_found")
    provider = _policy_guard(principal.workspace_id, protected)
    chunks: list[LongGenerationChunk] = []

    for _ in range(body.steps):
        session = LONG_GENERATION_V15.get(principal.workspace_id, session_id)
        if session is None or session.status != "ACTIVE":
            break
        remaining = session.target_total_tokens - session.allocated_output_token_budget
        if remaining <= 0:
            break
        budget = min(session.chunk_max_tokens, remaining)
        chunk_index = session.next_chunk_index
        messages = _continuation_messages(protected, session, chunk_index)
        invocation = ModelInvocationRequest(
            provider_id=session.provider_id,
            model_id=session.model_id,
            messages=messages,
            policy_id=session.policy_id,
            risk_tier=str(protected["risk_tier"]),
            data_categories=list(protected.get("data_categories") or []),
            evidence_pass_rate=float(protected["evidence_pass_rate"]),
            guarded_claims=int(protected["guarded_claims"]),
            retention_days=int(protected["retention_days"]),
            human_approved=bool(protected["human_approved"]),
            max_tokens=budget,
            temperature=float(protected["temperature"]),
        )
        try:
            text_value, reference, latency_ms = invoke_registered_model(provider, invocation)
        except ProviderGatewayError as exc:
            _record_generation_failure(principal.workspace_id, session_id, "provider_gateway_error", str(exc))
            status_code = 503 if str(exc) in {"provider_secret_not_configured", "provider_transport_error", "provider_dns_resolution_failed", "provider_circuit_open"} else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        if not text_value.strip():
            _record_generation_failure(principal.workspace_id, session_id, "empty_provider_output", "provider returned empty text")
            raise HTTPException(status_code=502, detail="provider_response_empty")

        text_digest = _text_sha256(text_value)
        chain_digest = _hash(
            {
                "domain": "ORBYTHRA-V15-LONG-GENERATION-CHAIN",
                "session_id": session_id,
                "chunk_index": chunk_index,
                "previous_chain_sha256": session.last_chain_sha256,
                "text_sha256": text_digest,
                "requested_token_budget": budget,
                "request_reference": reference,
            }
        )
        overlap = int(protected["continuation_overlap_chars"])
        last_tail = text_value[-overlap:] if overlap else ""
        chunk = LONG_GENERATION_V15.append_chunk(
            principal.workspace_id,
            session_id,
            chunk_index=chunk_index,
            text_value=text_value,
            requested_token_budget=budget,
            estimated_output_tokens=_estimate_tokens(text_value),
            text_sha256=text_digest,
            chain_sha256=chain_digest,
            request_reference=reference,
            latency_ms=latency_ms,
            last_tail=last_tail,
        )
        ENTERPRISE_STORE.record_usage(principal.workspace_id, "model_inference", 1, reference)
        STORE.record_audit(
            request_id=getattr(request.state, "request_id", reference),
            principal_id=principal.principal_id,
            workspace_id=principal.workspace_id,
            action="long_generation_v15_chunk",
            status="OK",
            metadata={
                "session_id": session_id,
                "chunk_index": chunk_index,
                "requested_token_budget": budget,
                "estimated_output_tokens": chunk.estimated_output_tokens,
                "text_sha256": text_digest,
                "chain_sha256": chain_digest,
                "request_reference": reference,
            },
        )
        chunks.append(chunk)
        protected["last_tail"] = last_tail

    final_session = LONG_GENERATION_V15.get(principal.workspace_id, session_id)
    if final_session is None:
        raise RuntimeError("long_generation_session_missing_after_generation")
    return LongGenerationBatchResponse(session=final_session, chunks=chunks)


@router.get("/sessions/{session_id}/chunks/{chunk_index}", response_model=LongGenerationChunk)
def get_chunk(session_id: str, chunk_index: int, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> LongGenerationChunk:
    if chunk_index < 0:
        raise HTTPException(status_code=400, detail="chunk_index_invalid")
    if LONG_GENERATION_V15.get(principal.workspace_id, session_id) is None:
        raise HTTPException(status_code=404, detail="long_generation_session_not_found")
    chunk = LONG_GENERATION_V15.chunk(principal.workspace_id, session_id, chunk_index)
    if chunk is None:
        raise HTTPException(status_code=404, detail="long_generation_chunk_not_found")
    return chunk


@router.post("/sessions/{session_id}/abort", response_model=LongGenerationSession)
def abort(session_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> LongGenerationSession:
    try:
        result = LONG_GENERATION_V15.abort(principal.workspace_id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", session_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="long_generation_v15_abort",
        status=result.status,
        metadata={"session_id": session_id},
    )
    return result


@router.get("/sessions/{session_id}/manifest", response_model=LongGenerationManifest)
def manifest(session_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> LongGenerationManifest:
    session = LONG_GENERATION_V15.get(principal.workspace_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="long_generation_session_not_found")
    hashes = LONG_GENERATION_V15.chunk_hashes(principal.workspace_id, session_id)
    payload = {
        "domain": "ORBYTHRA-V15-LONG-GENERATION-MANIFEST",
        "session_id": session_id,
        "status": session.status,
        "target_total_tokens": session.target_total_tokens,
        "allocated_output_token_budget": session.allocated_output_token_budget,
        "estimated_output_tokens": session.estimated_output_tokens,
        "chunk_hashes": hashes,
        "final_chain_sha256": session.last_chain_sha256,
    }
    return LongGenerationManifest(
        session_id=session_id,
        status=session.status,
        target_total_tokens=session.target_total_tokens,
        allocated_output_token_budget=session.allocated_output_token_budget,
        estimated_output_tokens=session.estimated_output_tokens,
        chunk_count=len(hashes),
        chunk_hashes=hashes,
        final_chain_sha256=session.last_chain_sha256,
        manifest_sha256=_hash(payload),
        accounting_note="Target/allocated values are requested output-token budgets. estimated_output_tokens is provider-neutral UTF-8/4 estimation, not an exact tokenizer count.",
    )
