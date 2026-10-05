from __future__ import annotations

import re
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.config import SETTINGS
from app.crypto_core import CryptoConfigurationError, CryptoValidationError, KEYRING, commitment, open_envelope, pqc_backend_available, seal, verify_effect_binding
from app.crypto_models import (
    CommitRequest,
    CommitResponse,
    CryptoStatusResponse,
    HybridRecipientOpenRequest,
    OpenRequest,
    OpenResponse,
    RecipientOpenRequest,
    RecipientOpenResponse,
    SealRequest,
    SealResponse,
)
from app.crypto_recipient import open_hybrid_recipient_envelope, open_recipient_envelope
from app.models import AuditEvent, EngineeringEnvelope, EngineeringRequest, EvidenceSnapshotRequest, EvidenceSnapshotResponse, PilotRunRequest, PilotRunResponse, PlanRequest, PlanResponse, VerifyRequest, VerifyResponse
from app.privacy import active_subject_token, minimised_payload, record_payload, retention_deadline, subject_tokens
from app.privacy_models import BreachCreate, BreachResponse, PrivacyActionResponse, PrivacyInventoryResponse, PrivacyRecordCreate, PrivacyRecordResponse, RectifyRequest, RetentionPurgeResponse, SubjectExportResponse, SubjectRequest
from app.providers import status as provider_status
from app.security import Principal, require_minimum_role, require_principal
from app.services.adaptive import build_plan
from app.services.engineering import build_engineering_envelope
from app.services.evidence import verify
from app.services.pilot import execute_pilot
from app.store import STORE
from app.telemetry import METRICS, OTEL

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")

app = FastAPI(title="ORBYTHRA API", version=__version__, docs_url=None if SETTINGS.environment == "production" else "/docs", redoc_url=None if SETTINGS.environment == "production" else "/redoc", description="Evidence-first verification, engineering intelligence, controlled pilot, cryptographic trust and GDPR-aligned privacy engineering API.")


def _secure_headers(response, request_id: str) -> None:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time.perf_counter()
    started_ns = time.time_ns()
    trace_context = OTEL.begin(request.headers.get("traceparent"))
    request.state.trace_id = trace_context.trace_id
    request.state.span_id = trace_context.span_id
    supplied = request.headers.get("x-request-id", "").strip()
    request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex
    request.state.request_id = request_id
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > SETTINGS.max_body_bytes:
                response = JSONResponse(status_code=413, content={"detail": "request_body_too_large"})
                _secure_headers(response, request_id)
                response.headers["traceparent"] = trace_context.traceparent
                METRICS.observe(request.method, request.url.path, 413, (time.perf_counter() - started) * 1000)
                OTEL.observe_http(
                    trace_context,
                    method=request.method,
                    path=request.url.path,
                    status_code=413,
                    request_id=request_id,
                    start_time_unix_nano=started_ns,
                    end_time_unix_nano=time.time_ns(),
                )
                return response
        except ValueError:
            pass
    response = await call_next(request)
    _secure_headers(response, request_id)
    response.headers["traceparent"] = trace_context.traceparent
    remaining = getattr(request.state, "rate_limit_remaining", None)
    if remaining is not None:
        response.headers["X-RateLimit-Remaining"] = str(remaining)
    METRICS.observe(request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
    OTEL.observe_http(
        trace_context,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        request_id=request_id,
        start_time_unix_nano=started_ns,
        end_time_unix_nano=time.time_ns(),
    )
    return response


def _audit(request: Request, principal: Principal, *, action: str, status_text: str, metadata: dict[str, object] | None = None) -> None:
    STORE.record_audit(request_id=request.state.request_id, principal_id=principal.principal_id, workspace_id=principal.workspace_id, action=action, status=status_text, metadata={"role": principal.role, **(metadata or {})})


def _crypto_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CryptoConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _subject_token_values(workspace_id: str, subject_id: str) -> list[str]:
    try:
        return [token for _, token in subject_tokens(workspace_id, subject_id)]
    except (CryptoConfigurationError, ValueError) as exc:
        raise _crypto_http_error(exc) from exc


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "product": "ORBYTHRA", "version": __version__}


@app.get("/ready", tags=["system"])
def ready() -> dict[str, object]:
    database_ready = STORE.ping()
    providers = provider_status()
    pqc_ready = SETTINGS.pqc_mode != "hybrid-required" or pqc_backend_available()
    production_crypto_ok = (SETTINGS.crypto_configured and pqc_ready) or SETTINGS.environment != "production"
    return {"ready": database_ready and SETTINGS.auth_configured and production_crypto_ok, "auth_configured": SETTINGS.auth_configured, "crypto_configured": SETTINGS.crypto_configured, "pqc_mode": SETTINGS.pqc_mode, "pqc_backend_ready": pqc_ready, "database_ready": database_ready, "database_backend": STORE.backend, "environment": SETTINGS.environment, "providers": {"evidence": providers.evidence_provider_configured, "llm": providers.llm_provider_configured}, "capabilities": ["evidence_gate", "adaptive_planning", "engineering_intelligence", "api_key_authentication", "rbac", "workspace_isolation", "rate_limiting", "audit_trail", "evidence_snapshots", "pilot_acceptance_runs", "postgresql_or_sqlite", "operational_metrics", "provider_adapters", "morseguard_normalization", "gestureguard_intent_binding", "effectseal_intent_effect_binding", "dsel_adunaic_dynamic_representation", "aes256_gcm", "chacha20_poly1305", "hkdf_sha256", "ed25519_signatures", "x25519_recipient_envelope", "nonce_ttl_replay_protection", "encrypted_data_at_rest", "gdpr_lawful_basis_registry", "gdpr_data_minimisation", "gdpr_pseudonymisation", "gdpr_retention_enforcement", "gdpr_access_portability", "gdpr_rectification", "gdpr_restriction", "gdpr_erasure", "gdpr_consent_withdrawal", "gdpr_processing_inventory", "gdpr_breach_register"]}


@app.get("/v1/metrics", tags=["operations"])
def metrics(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {"workspace_id": principal.workspace_id, **METRICS.snapshot()}


@app.get("/v1/crypto/status", response_model=CryptoStatusResponse, tags=["crypto"])
def crypto_status(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> CryptoStatusResponse:
    signing_ids = [key_id for key_id, _ in SETTINGS.signing_keys]
    if not signing_ids and SETTINGS.environment != "production":
        signing_ids = KEYRING.key_ids
    pq_available = pqc_backend_available()
    components = [
        "MorseGuard normalization firewall",
        "GestureGuard cryptographic intent-bound approvals",
        "EffectSeal intent/effect binding",
        "DSEL/Project Adunaic dynamic representation",
        "HKDF-SHA256 key separation",
        "AES-256-GCM",
        "ChaCha20-Poly1305",
        "Ed25519 signed envelopes",
        "isolated Ed25519 signing root",
        "X25519 recipient key wrapping",
        "nonce + TTL mandatory production replay protection",
        "envelope encryption for data at rest",
    ]
    if pq_available:
        components.extend(["ML-DSA-65 hybrid signatures", "ML-KEM-768 + X25519 hybrid recipient wrapping"])
    return CryptoStatusResponse(
        configured=SETTINGS.crypto_configured,
        active_key_id=KEYRING.active.key_id if KEYRING.configured else None,
        available_key_ids=KEYRING.key_ids,
        active_signing_key_id=signing_ids[0] if signing_ids else None,
        available_signing_key_ids=signing_ids,
        signing_keys_isolated=SETTINGS.signing_keys_isolated,
        pqc_mode=SETTINGS.pqc_mode,
        pqc_backend_available=pq_available,
        default_algorithm=SETTINGS.crypto_algorithm,
        components=components,
    )


@app.post("/v1/crypto/commit", response_model=CommitResponse, tags=["crypto"])
def crypto_commit(body: CommitRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> CommitResponse:
    intent = commitment(body.intent, domain="intent")
    effect = commitment(body.effect, domain="effect") if body.effect is not None else None
    mismatches = verify_effect_binding(body.intent, body.effect)
    _audit(request, principal, action="crypto_commit", status_text="OK" if not mismatches else "MISMATCH", metadata={"mismatched_fields": mismatches})
    return CommitResponse(intent_sha256=intent["sha256"], intent_sha3_256=intent["sha3_256"], effect_sha256=effect["sha256"] if effect else None, effect_sha3_256=effect["sha3_256"] if effect else None, effect_binding_ok=not mismatches, mismatched_fields=mismatches)


@app.post("/v1/crypto/seal", response_model=SealResponse, tags=["crypto"])
def crypto_seal(body: SealRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> SealResponse:
    if SETTINGS.environment == "production" and body.min_approvals < 1:
        raise HTTPException(status_code=400, detail="approval_required_in_production")
    if SETTINGS.environment == "production" and body.ttl_seconds == 0:
        raise HTTPException(status_code=400, detail="positive_ttl_required_in_production")
    try:
        envelope = seal(payload=body.payload, intent=body.intent, effect=body.effect, approvals=[item.model_dump(mode="json") for item in body.approvals], min_approvals=body.min_approvals, workspace_id=principal.workspace_id, domain=body.domain, ttl_seconds=SETTINGS.crypto_default_ttl_seconds if body.ttl_seconds is None else body.ttl_seconds, algorithm=body.algorithm, recipient_public_key_b64=body.recipient_public_key_b64, recipient_mlkem768_public_key_b64=body.recipient_mlkem768_public_key_b64)
    except (CryptoConfigurationError, CryptoValidationError) as exc:
        raise _crypto_http_error(exc) from exc
    header = envelope["header"]
    _audit(request, principal, action="crypto_seal", status_text="SEALED", metadata={"key_id": header["key_id"], "algorithm": header["algorithm"], "domain": header["domain"], "approval_count": header["approval_count"], "intent_sha256": header["intent_sha256"]})
    return SealResponse(envelope=envelope, intent_digest=header["intent_sha256"], algorithm=header["algorithm"], key_id=header["key_id"], expires_at=header["expires_at"], approval_count=header["approval_count"])


@app.post("/v1/crypto/open", response_model=OpenResponse, tags=["crypto"])
def crypto_open(body: OpenRequest, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> OpenResponse:
    if SETTINGS.environment == "production" and not body.enforce_replay_protection:
        raise HTTPException(status_code=400, detail="replay_protection_required")
    try:
        opened = open_envelope(body.envelope, expected_workspace_id=principal.workspace_id, expected_intent_digest=body.expected_intent_digest)
    except (CryptoConfigurationError, CryptoValidationError) as exc:
        raise _crypto_http_error(exc) from exc
    header = opened["header"]
    if body.enforce_replay_protection:
        reserved = STORE.reserve_crypto_nonce(workspace_id=principal.workspace_id, nonce_fingerprint=opened["nonce_fingerprint"], expires_at=int(header.get("expires_at") or 0))
        if not reserved:
            raise HTTPException(status_code=409, detail="replay_detected")
    content = opened["content"]
    _audit(request, principal, action="crypto_open", status_text="VERIFIED", metadata={"key_id": header["key_id"], "algorithm": header["algorithm"], "domain": header["domain"], "intent_sha256": header["intent_sha256"], "replay_protection": body.enforce_replay_protection})
    return OpenResponse(payload=content["payload"], intent=content["intent"], effect=content.get("effect"), intent_digest=header["intent_sha256"], signer_verified=bool(opened["signer_verified"]), outcome_receipt=opened["outcome_receipt"])


@app.post("/v1/crypto/open-recipient", response_model=RecipientOpenResponse, tags=["crypto"])
def crypto_open_recipient(body: RecipientOpenRequest, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> RecipientOpenResponse:
    if SETTINGS.environment == "production" and not body.enforce_replay_protection:
        raise HTTPException(status_code=400, detail="replay_protection_required")
    try:
        opened = open_recipient_envelope(
            body.envelope,
            expected_workspace_id=principal.workspace_id,
            recipient_private_key_b64=body.recipient_private_key_b64,
            expected_signing_public_key_b64=body.expected_signing_public_key_b64,
            expected_pq_signing_public_key_b64=body.expected_pq_signing_public_key_b64,
            expected_intent_digest=body.expected_intent_digest,
        )
    except (CryptoConfigurationError, CryptoValidationError) as exc:
        raise _crypto_http_error(exc) from exc
    header = opened["header"]
    if body.enforce_replay_protection:
        reserved = STORE.reserve_crypto_nonce(workspace_id=principal.workspace_id, nonce_fingerprint=opened["nonce_fingerprint"], expires_at=int(header.get("expires_at") or 0))
        if not reserved:
            raise HTTPException(status_code=409, detail="replay_detected")
    content = opened["content"]
    _audit(request, principal, action="crypto_open_recipient", status_text="VERIFIED", metadata={"key_id": header["key_id"], "domain": header["domain"], "hybrid": False})
    return RecipientOpenResponse(payload=content["payload"], intent=content["intent"], effect=content.get("effect"), intent_digest=header["intent_sha256"], signer_verified=True, recipient_verified=True, ciphertext_sha256=str(opened["ciphertext_sha256"]), opened_at=int(opened["opened_at"]))


@app.post("/v1/crypto/open-hybrid-recipient", response_model=RecipientOpenResponse, tags=["crypto"])
def crypto_open_hybrid_recipient(body: HybridRecipientOpenRequest, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> RecipientOpenResponse:
    if SETTINGS.environment == "production" and not body.enforce_replay_protection:
        raise HTTPException(status_code=400, detail="replay_protection_required")
    try:
        opened = open_hybrid_recipient_envelope(
            body.envelope,
            expected_workspace_id=principal.workspace_id,
            recipient_x25519_private_key_b64=body.recipient_x25519_private_key_b64,
            recipient_mlkem768_private_key_b64=body.recipient_mlkem768_private_key_b64,
            expected_signing_public_key_b64=body.expected_signing_public_key_b64,
            expected_pq_signing_public_key_b64=body.expected_pq_signing_public_key_b64,
            expected_intent_digest=body.expected_intent_digest,
        )
    except (CryptoConfigurationError, CryptoValidationError) as exc:
        raise _crypto_http_error(exc) from exc
    header = opened["header"]
    if body.enforce_replay_protection:
        reserved = STORE.reserve_crypto_nonce(workspace_id=principal.workspace_id, nonce_fingerprint=opened["nonce_fingerprint"], expires_at=int(header.get("expires_at") or 0))
        if not reserved:
            raise HTTPException(status_code=409, detail="replay_detected")
    content = opened["content"]
    _audit(request, principal, action="crypto_open_hybrid_recipient", status_text="VERIFIED", metadata={"key_id": header["key_id"], "domain": header["domain"], "hybrid": True})
    return RecipientOpenResponse(payload=content["payload"], intent=content["intent"], effect=content.get("effect"), intent_digest=header["intent_sha256"], signer_verified=True, recipient_verified=True, ciphertext_sha256=str(opened["ciphertext_sha256"]), opened_at=int(opened["opened_at"]))


@app.post("/v1/privacy/records", response_model=PrivacyRecordResponse, tags=["privacy"])
def create_privacy_record(body: PrivacyRecordCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PrivacyRecordResponse:
    try:
        key_id, token = active_subject_token(principal.workspace_id, body.subject_id)
        protected = record_payload(data_categories=body.data_categories, declared_fields=body.declared_fields, payload=minimised_payload(body.payload, body.declared_fields), consent_reference=body.consent_reference, special_category=body.special_category, article9_condition=body.article9_condition)
        deadline = retention_deadline(body.retention_days)
        created = STORE.create_privacy_record(workspace_id=principal.workspace_id, subject_token=token, subject_key_id=key_id, purpose=body.purpose, lawful_basis=body.lawful_basis, record_data=protected, retention_until=deadline)
    except (CryptoConfigurationError, ValueError) as exc:
        raise _crypto_http_error(exc) from exc
    _audit(request, principal, action="privacy_record_create", status_text="CREATED", metadata={"record_id": created["record_id"], "purpose": body.purpose, "lawful_basis": body.lawful_basis, "retention_until": deadline, "special_category": body.special_category})
    return PrivacyRecordResponse(record_id=created["record_id"], purpose=body.purpose, lawful_basis=body.lawful_basis, data_categories=protected["data_categories"], declared_fields=protected["declared_fields"], payload=protected["payload"], retention_until=deadline, restricted=False, consent_withdrawn=False, special_category=body.special_category, article9_condition=body.article9_condition, created_at=created["created_at"], updated_at=created["updated_at"])


@app.post("/v1/privacy/subjects/export", response_model=SubjectExportResponse, tags=["privacy"])
def export_subject_data(body: SubjectRequest, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> SubjectExportResponse:
    tokens = _subject_token_values(principal.workspace_id, body.subject_id)
    rows = STORE.export_privacy_records(principal.workspace_id, tokens)
    records = [PrivacyRecordResponse(**row) for row in rows]
    _audit(request, principal, action="privacy_subject_export", status_text="OK", metadata={"record_count": len(records), "format": "application/json"})
    return SubjectExportResponse(generated_at=int(time.time()), subject_id=body.subject_id, records=records)


@app.post("/v1/privacy/records/rectify", response_model=PrivacyActionResponse, tags=["privacy"])
def rectify_subject_data(body: RectifyRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PrivacyActionResponse:
    try:
        payload = minimised_payload(body.payload, body.declared_fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tokens = _subject_token_values(principal.workspace_id, body.subject_id)
    updated = STORE.rectify_privacy_record(workspace_id=principal.workspace_id, tokens=tokens, record_id=body.record_id, payload=payload, declared_fields=body.declared_fields)
    if not updated:
        raise HTTPException(status_code=404, detail="privacy_record_not_found")
    _audit(request, principal, action="privacy_rectification", status_text="UPDATED", metadata={"record_id": body.record_id})
    return PrivacyActionResponse(subject_id=body.subject_id, affected_records=1, action="rectified")


@app.post("/v1/privacy/subjects/restrict", response_model=PrivacyActionResponse, tags=["privacy"])
def restrict_subject_data(body: SubjectRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PrivacyActionResponse:
    affected = STORE.set_subject_restriction(workspace_id=principal.workspace_id, tokens=_subject_token_values(principal.workspace_id, body.subject_id), restricted=True)
    _audit(request, principal, action="privacy_restrict", status_text="RESTRICTED", metadata={"affected_records": affected})
    return PrivacyActionResponse(subject_id=body.subject_id, affected_records=affected, action="restricted")


@app.post("/v1/privacy/subjects/withdraw-consent", response_model=PrivacyActionResponse, tags=["privacy"])
def withdraw_subject_consent(body: SubjectRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PrivacyActionResponse:
    affected = STORE.withdraw_subject_consent(workspace_id=principal.workspace_id, tokens=_subject_token_values(principal.workspace_id, body.subject_id))
    _audit(request, principal, action="privacy_withdraw_consent", status_text="WITHDRAWN", metadata={"affected_records": affected})
    return PrivacyActionResponse(subject_id=body.subject_id, affected_records=affected, action="consent_withdrawn_and_restricted")


@app.post("/v1/privacy/subjects/erase", response_model=PrivacyActionResponse, tags=["privacy"])
def erase_subject_data(body: SubjectRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> PrivacyActionResponse:
    affected = STORE.erase_subject_privacy_records(workspace_id=principal.workspace_id, tokens=_subject_token_values(principal.workspace_id, body.subject_id))
    _audit(request, principal, action="privacy_erasure", status_text="ERASED", metadata={"affected_records": affected})
    return PrivacyActionResponse(subject_id=body.subject_id, affected_records=affected, action="erased")


@app.post("/v1/privacy/retention/purge", response_model=RetentionPurgeResponse, tags=["privacy"])
def purge_expired_privacy_data(request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> RetentionPurgeResponse:
    now = int(time.time())
    purged = STORE.purge_expired_privacy_records(workspace_id=principal.workspace_id, now=now)
    _audit(request, principal, action="privacy_retention_purge", status_text="PURGED", metadata={"purged_records": purged})
    return RetentionPurgeResponse(purged_records=purged, purged_at=now)


@app.get("/v1/privacy/inventory", response_model=PrivacyInventoryResponse, tags=["privacy"])
def privacy_inventory(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> PrivacyInventoryResponse:
    inventory = STORE.privacy_inventory(principal.workspace_id)
    return PrivacyInventoryResponse(**inventory, encryption_at_rest=SETTINGS.crypto_configured)


@app.get("/v1/privacy/status", tags=["privacy"])
def privacy_status(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {"workspace_id": principal.workspace_id, "technical_controls": ["lawful_basis_registry", "purpose_limitation_metadata", "declared_field_minimisation", "encrypted_data_at_rest", "pseudonymised_subject_index", "retention_deadlines_and_purge", "access_and_json_portability", "rectification", "restriction", "erasure", "consent_withdrawal", "processing_inventory", "breach_register_72h_review_clock", "rbac", "audit_trail"], "legal_review_required": True, "claim": "GDPR-aligned technical controls; not a legal certification"}


@app.post("/v1/privacy/breaches", response_model=BreachResponse, tags=["privacy"])
def create_privacy_breach(body: BreachCreate, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> BreachResponse:
    result = STORE.record_privacy_breach(workspace_id=principal.workspace_id, incident_reference=body.incident_reference, details={"summary": body.summary, "personal_data_categories": body.personal_data_categories, "estimated_subjects": body.estimated_subjects}, detected_at=body.detected_at, risk_assessment=body.risk_assessment)
    _audit(request, principal, action="privacy_breach_register", status_text=result["status"], metadata={"breach_id": result["breach_id"], "incident_reference": body.incident_reference, "notification_deadline_at": result["notification_deadline_at"], "risk_assessment": body.risk_assessment})
    return BreachResponse(**result)


@app.get("/v1/privacy/breaches/open", response_model=list[BreachResponse], tags=["privacy"])
def list_open_privacy_breaches(principal: Principal = Depends(_REQUIRE_ADMIN)) -> list[BreachResponse]:
    return [BreachResponse(**row) for row in STORE.open_privacy_breaches(principal.workspace_id)]


@app.post("/v1/verify", response_model=VerifyResponse, tags=["verification"])
def verify_claims(body: VerifyRequest, request: Request, principal: Principal = Depends(require_principal)) -> VerifyResponse:
    result = verify(body)
    _audit(request, principal, action="verify", status_text=result.disposition, metadata={"total_claims": result.total_claims, "guarded_claims": result.guarded_claims, "pass_rate": result.evidence_gate_pass_rate})
    return result


@app.post("/v1/plan", response_model=PlanResponse, tags=["adaptive-core"])
def plan(body: PlanRequest, request: Request, principal: Principal = Depends(require_principal)) -> PlanResponse:
    result = build_plan(body)
    _audit(request, principal, action="plan", status_text="OK", metadata={"complexity": result.complexity, "modes": result.modes})
    return result


@app.post("/v1/engineering/envelope", response_model=EngineeringEnvelope, tags=["engineering-intelligence"])
def engineering_envelope(body: EngineeringRequest, request: Request, principal: Principal = Depends(require_principal)) -> EngineeringEnvelope:
    result = build_engineering_envelope(body)
    _audit(request, principal, action="engineering_envelope", status_text=result.decision_status, metadata={"unknown_count": len(result.unknowns)})
    return result


@app.post("/v1/evidence/snapshots", response_model=EvidenceSnapshotResponse, tags=["evidence"])
def create_evidence_snapshot(body: EvidenceSnapshotRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> EvidenceSnapshotResponse:
    result = STORE.create_evidence_snapshot(workspace_id=principal.workspace_id, principal_id=principal.principal_id, label=body.label, evidence=[item.model_dump(mode="json") for item in body.evidence])
    _audit(request, principal, action="evidence_snapshot_create", status_text="CREATED", metadata={"snapshot_id": result["snapshot_id"], "evidence_count": result["evidence_count"]})
    return EvidenceSnapshotResponse(**result)


@app.get("/v1/evidence/snapshots/{snapshot_id}", tags=["evidence"])
def get_evidence_snapshot(snapshot_id: str, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    result = STORE.get_evidence_snapshot(principal.workspace_id, snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="evidence_snapshot_not_found")
    _audit(request, principal, action="evidence_snapshot_read", status_text="OK", metadata={"snapshot_id": snapshot_id})
    return result


@app.post("/v1/pilot/run", response_model=PilotRunResponse, tags=["pilot"])
def pilot_run(body: PilotRunRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PilotRunResponse:
    result = execute_pilot(body)
    STORE.save_pilot_run(run_id=result.run_id, scenario_id=result.scenario_id, workspace_id=principal.workspace_id, principal_id=principal.principal_id, request_payload=body.model_dump(mode="json"), result_payload=result.model_dump(mode="json"))
    _audit(request, principal, action="pilot_run", status_text="PASS" if result.acceptance_passed else "FAIL", metadata={"run_id": result.run_id, "scenario_id": result.scenario_id, "acceptance_failures": result.acceptance_failures})
    return result


@app.get("/v1/pilot/runs/{run_id}", tags=["pilot"])
def get_pilot_run(run_id: str, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    result = STORE.get_pilot_run(principal.workspace_id, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="pilot_run_not_found")
    _audit(request, principal, action="pilot_run_read", status_text="OK", metadata={"run_id": run_id})
    return result


@app.get("/v1/audit/recent", response_model=list[AuditEvent], tags=["audit"])
def recent_audit(principal: Principal = Depends(_REQUIRE_EVALUATOR), limit: int = Query(default=50, ge=1, le=200)) -> list[AuditEvent]:
    return [AuditEvent(**row) for row in STORE.recent_audit(principal.workspace_id, limit)]
