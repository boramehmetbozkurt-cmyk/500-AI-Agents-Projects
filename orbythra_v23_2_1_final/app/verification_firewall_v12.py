from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.config import SETTINGS
from app.crypto_core import canonical_json
from app.nli_verifier_v51 import NLI
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v12/verification", tags=["v12-verification-firewall"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!])\s+|\n+")
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s*")
_ABSTENTION_MARKERS = (
    "insufficient evidence",
    "cannot verify",
    "can't verify",
    "unable to verify",
    "not enough evidence",
    "human review required",
)


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_claim(value: str) -> str:
    value = _BULLET_PREFIX.sub("", value.strip())
    value = value.strip(" #\t")
    return re.sub(r"\s+", " ", value).strip()


def _is_abstention(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in _ABSTENTION_MARKERS)


def extract_atomic_claims(output: str) -> list[str]:
    """Conservatively bind verification to every assertive output sentence.

    The caller may add required_claims, but cannot remove claims extracted from the
    candidate output. Questions and explicit abstentions are not treated as factual
    claims. This is intentionally deterministic and fail-closed.
    """
    claims: list[str] = []
    seen: set[str] = set()
    in_code = False
    for raw in _SENTENCE_SPLIT.split(output):
        text = raw.strip()
        if not text:
            continue
        if text.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        claim = _clean_claim(text)
        if len(claim) < 4 or claim.endswith("?") or _is_abstention(claim):
            continue
        key = claim.casefold()
        if key not in seen:
            seen.add(key)
            claims.append(claim)
    return claims


class EvidenceArtifact(BaseModel):
    source_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100000)
    url: str | None = Field(default=None, max_length=2000)
    observed_at: int | None = None
    published_at: int | None = None
    independence_key: str | None = Field(default=None, max_length=200)
    declared_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    def digest(self) -> str:
        return _sha(
            {
                "source_id": self.source_id,
                "text": self.text,
                "url": self.url,
                "observed_at": self.observed_at,
                "published_at": self.published_at,
                "independence_key": self.independence_key,
            }
        )

    @property
    def independence_identity(self) -> str:
        return self.independence_key or self.source_id


class VerificationPolicy(BaseModel):
    minimum_claim_coverage: float = Field(default=1.0, ge=0, le=1)
    minimum_entailment: float = Field(default=0.75, ge=0, le=1)
    contradiction_threshold: float = Field(default=0.75, ge=0, le=1)
    minimum_independent_sources: int = Field(default=1, ge=1, le=20)
    maximum_evidence_age_seconds: int = Field(default=2592000, ge=60, le=31536000)
    future_clock_skew_seconds: int = Field(default=300, ge=0, le=3600)

    @model_validator(mode="after")
    def finite_thresholds(self):
        for value in (self.minimum_claim_coverage, self.minimum_entailment, self.contradiction_threshold):
            if not math.isfinite(value):
                raise ValueError("verification_threshold_must_be_finite")
        return self


class VerificationFirewallRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    nonce: str = Field(min_length=16, max_length=256)
    model_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=100000)
    output: str = Field(min_length=1, max_length=200000)
    evidence: list[EvidenceArtifact] = Field(default_factory=list, max_length=200)
    required_claims: list[str] = Field(default_factory=list, max_length=200)
    risk_tier: Literal["low", "moderate", "high", "critical"] = "moderate"
    human_approved: bool = False
    policy: VerificationPolicy = Field(default_factory=VerificationPolicy)
    expected_release_sha: str = Field(min_length=40, max_length=80)
    configuration_sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_uniqueness(self):
        source_ids = [item.source_id for item in self.evidence]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate_evidence_source_id")
        normalized = [item.strip().casefold() for item in self.required_claims if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("duplicate_required_claim")
        return self


class ClaimVerdictV12(BaseModel):
    claim: str
    status: Literal["SUPPORTED", "CONTRADICTED", "UNSUPPORTED"]
    supporting_sources: list[str]
    contradicting_sources: list[str]
    independent_support_count: int
    best_entailment: float
    best_contradiction: float
    verifier: str


class VerificationGate(BaseModel):
    name: str
    passed: bool
    detail: str


class VerificationFirewallResponse(BaseModel):
    request_id: str
    status: Literal["PASS", "REVIEW", "FAIL"]
    release_output: bool
    output: str | None
    safe_output: str
    extracted_claims: list[str]
    claim_verdicts: list[ClaimVerdictV12]
    claim_coverage: float
    invalid_evidence: list[str]
    stale_evidence: list[str]
    gates: list[VerificationGate]
    prompt_sha256: str
    output_sha256: str
    evidence_manifest_sha256: str
    policy_sha256: str
    verification_receipt_sha256: str
    release_sha: str
    configuration_sha256: str
    boundary: str = (
        "V12 binds candidate output to claim-level supplied evidence, deterministic NLI signals, "
        "evidence integrity, source independence and temporal validity. It does not independently "
        "fetch sources or prove factual truth beyond the supplied evidence set."
    )


def _bound_claims(body: VerificationFirewallRequest) -> list[str]:
    claims = extract_atomic_claims(body.output)
    seen = {claim.casefold() for claim in claims}
    for raw in body.required_claims:
        claim = _clean_claim(raw)
        if claim and claim.casefold() not in seen:
            claims.append(claim)
            seen.add(claim.casefold())
    return claims


def _guard_evidence(body: VerificationFirewallRequest, now: int) -> tuple[list[str], list[str]]:
    invalid: list[str] = []
    stale: list[str] = []
    for evidence in body.evidence:
        if evidence.declared_sha256 and evidence.declared_sha256 != evidence.digest():
            invalid.append(evidence.source_id + ":digest_mismatch")
        if evidence.observed_at is not None:
            if evidence.observed_at > now + body.policy.future_clock_skew_seconds:
                invalid.append(evidence.source_id + ":future_observation")
            elif now - evidence.observed_at > body.policy.maximum_evidence_age_seconds:
                stale.append(evidence.source_id)
    return sorted(set(invalid)), sorted(set(stale))


def _verdict_for_claim(claim: str, body: VerificationFirewallRequest) -> ClaimVerdictV12:
    supporting: list[str] = []
    contradicting: list[str] = []
    independent: set[str] = set()
    best_entailment = 0.0
    best_contradiction = 0.0
    verifier = NLI.name

    for evidence in body.evidence:
        score = NLI.score(claim, evidence.text)
        verifier = score.verifier
        best_entailment = max(best_entailment, score.entailment)
        best_contradiction = max(best_contradiction, score.contradiction)
        if score.contradiction >= body.policy.contradiction_threshold:
            contradicting.append(evidence.source_id)
        if score.entailment >= body.policy.minimum_entailment:
            supporting.append(evidence.source_id)
            independent.add(evidence.independence_identity)

    if contradicting:
        status: Literal["SUPPORTED", "CONTRADICTED", "UNSUPPORTED"] = "CONTRADICTED"
    elif len(independent) >= body.policy.minimum_independent_sources:
        status = "SUPPORTED"
    else:
        status = "UNSUPPORTED"

    return ClaimVerdictV12(
        claim=claim,
        status=status,
        supporting_sources=sorted(set(supporting)),
        contradicting_sources=sorted(set(contradicting)),
        independent_support_count=len(independent),
        best_entailment=round(best_entailment, 6),
        best_contradiction=round(best_contradiction, 6),
        verifier=verifier,
    )


def verify_candidate_output(body: VerificationFirewallRequest, *, now: int | None = None) -> VerificationFirewallResponse:
    evaluated_at = int(time.time()) if now is None else int(now)
    claims = _bound_claims(body)
    invalid_evidence, stale_evidence = _guard_evidence(body, evaluated_at)
    verdicts = [_verdict_for_claim(claim, body) for claim in claims]

    supported = sum(item.status == "SUPPORTED" for item in verdicts)
    coverage = supported / len(verdicts) if verdicts else (1.0 if _is_abstention(body.output) else 0.0)
    contradictions = [item.claim for item in verdicts if item.status == "CONTRADICTED"]
    unsupported = [item.claim for item in verdicts if item.status == "UNSUPPORTED"]
    high_risk_approval = body.risk_tier not in {"high", "critical"} or body.human_approved

    gates = [
        VerificationGate(name="candidate_output_bound", passed=True, detail=f"{len(extract_atomic_claims(body.output))} claims extracted from output"),
        VerificationGate(name="evidence_integrity", passed=not invalid_evidence, detail=";".join(invalid_evidence) if invalid_evidence else "all declared digests/timestamps valid"),
        VerificationGate(name="evidence_freshness", passed=not stale_evidence, detail=",".join(stale_evidence) if stale_evidence else "fresh when observed_at supplied"),
        VerificationGate(name="claim_support", passed=not unsupported and not contradictions and (bool(verdicts) or _is_abstention(body.output)), detail=f"supported={supported}/{len(verdicts)} unsupported={len(unsupported)} contradicted={len(contradictions)}"),
        VerificationGate(name="claim_coverage", passed=coverage >= body.policy.minimum_claim_coverage, detail=f"{coverage:.3f} >= {body.policy.minimum_claim_coverage:.3f}"),
        VerificationGate(name="no_contradictions", passed=not contradictions, detail=f"contradicted={len(contradictions)}"),
        VerificationGate(name="source_independence", passed=all(item.status != "SUPPORTED" or item.independent_support_count >= body.policy.minimum_independent_sources for item in verdicts), detail=f"minimum independent sources={body.policy.minimum_independent_sources}"),
        VerificationGate(name="high_risk_human_approval", passed=high_risk_approval, detail="human approval required for high/critical risk"),
    ]
    failed = [gate.name for gate in gates if not gate.passed]
    status: Literal["PASS", "REVIEW", "FAIL"]
    if not failed:
        status = "PASS"
    elif failed == ["high_risk_human_approval"]:
        status = "REVIEW"
    else:
        status = "FAIL"

    evidence_manifest = [
        {
            "source_id": item.source_id,
            "digest": item.digest(),
            "independence_identity": item.independence_identity,
            "observed_at": item.observed_at,
            "published_at": item.published_at,
        }
        for item in body.evidence
    ]
    prompt_sha = _text_sha(body.prompt)
    output_sha = _text_sha(body.output)
    evidence_manifest_sha = _sha(evidence_manifest)
    policy_sha = _sha(body.policy.model_dump(mode="json"))
    receipt = {
        "request_id": body.request_id,
        "nonce_sha256": _text_sha(body.nonce),
        "model_id": body.model_id,
        "prompt_sha256": prompt_sha,
        "output_sha256": output_sha,
        "evidence_manifest_sha256": evidence_manifest_sha,
        "policy_sha256": policy_sha,
        "claim_verdicts": [item.model_dump(mode="json") for item in verdicts],
        "status": status,
        "release_sha": body.expected_release_sha,
        "configuration_sha256": body.configuration_sha256,
    }
    receipt_sha = _sha(receipt)
    safe_output = body.output if status == "PASS" else ("HUMAN_REVIEW_REQUIRED" if status == "REVIEW" else "INSUFFICIENT_EVIDENCE")

    return VerificationFirewallResponse(
        request_id=body.request_id,
        status=status,
        release_output=status == "PASS",
        output=body.output if status == "PASS" else None,
        safe_output=safe_output,
        extracted_claims=claims,
        claim_verdicts=verdicts,
        claim_coverage=round(coverage, 6),
        invalid_evidence=invalid_evidence,
        stale_evidence=stale_evidence,
        gates=gates,
        prompt_sha256=prompt_sha,
        output_sha256=output_sha,
        evidence_manifest_sha256=evidence_manifest_sha,
        policy_sha256=policy_sha,
        verification_receipt_sha256=receipt_sha,
        release_sha=body.expected_release_sha,
        configuration_sha256=body.configuration_sha256,
    )


@router.post("/evaluate", response_model=VerificationFirewallResponse)
def evaluate_v12(body: VerificationFirewallRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> VerificationFirewallResponse:
    if not SETTINGS.release_sha or body.expected_release_sha != SETTINGS.release_sha:
        raise HTTPException(status_code=409, detail="release_sha_mismatch")
    replay_fingerprint = _sha(
        {
            "request_id": body.request_id,
            "nonce": body.nonce,
            "output_sha256": _text_sha(body.output),
            "release_sha": body.expected_release_sha,
        }
    )
    if not STORE.reserve_crypto_nonce(
        workspace_id=principal.workspace_id,
        nonce_fingerprint="verification-v12:" + replay_fingerprint,
        expires_at=int(time.time()) + 86400,
    ):
        raise HTTPException(status_code=409, detail="verification_replay_detected")

    result = verify_candidate_output(body)
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", body.request_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="verification_firewall_v12",
        status=result.status,
        metadata={
            "output_sha256": result.output_sha256,
            "evidence_manifest_sha256": result.evidence_manifest_sha256,
            "policy_sha256": result.policy_sha256,
            "verification_receipt_sha256": result.verification_receipt_sha256,
            "claim_coverage": result.claim_coverage,
            "failed_gates": [gate.name for gate in result.gates if not gate.passed],
        },
    )
    return result


@router.get("/readiness")
def readiness_v12(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "12.0-p0",
        "workspace_id": principal.workspace_id,
        "candidate_output_binding": True,
        "automatic_atomic_claim_extraction": True,
        "caller_cannot_omit_output_claims": True,
        "semantic_nli_gate": True,
        "contradiction_gate": True,
        "evidence_digest_recomputation": True,
        "future_timestamp_rejection": True,
        "freshness_gate": True,
        "source_independence_gate": True,
        "fail_closed_release": True,
        "replay_protection": True,
        "release_binding": True,
        "configuration_binding": True,
        "verification_receipt_hash": True,
        "external_source_fetching": False,
        "factual_truth_claim": False,
    }
