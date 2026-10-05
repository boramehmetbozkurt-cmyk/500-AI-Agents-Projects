from __future__ import annotations

import uuid

from app.models import (
    EngineeringEnvelope,
    PilotRunRequest,
    PilotRunResponse,
    PlanRequest,
)
from app.services.adaptive import build_plan
from app.services.engineering import build_engineering_envelope
from app.services.evidence import verify


def execute_pilot(request: PilotRunRequest) -> PilotRunResponse:
    run_id = "run_" + uuid.uuid4().hex[:20]
    plan = build_plan(PlanRequest(query=request.query))
    verification = verify(request.verification)
    engineering: EngineeringEnvelope | None = None
    if request.engineering is not None:
        engineering = build_engineering_envelope(request.engineering)

    criteria = request.acceptance
    reasons: list[str] = []

    if verification.disposition != criteria.expected_disposition:
        reasons.append(
            f"disposition_mismatch:{verification.disposition}!={criteria.expected_disposition}"
        )
    if verification.evidence_gate_pass_rate < criteria.minimum_evidence_gate_pass_rate:
        reasons.append("evidence_gate_pass_rate_below_acceptance_threshold")
    if verification.guarded_claims > criteria.maximum_guarded_claims:
        reasons.append("guarded_claim_count_above_acceptance_threshold")
    if criteria.require_engineering_ready:
        if engineering is None:
            reasons.append("engineering_envelope_required_but_missing")
        elif engineering.decision_status != "READY_FOR_EVIDENCE":
            reasons.append("engineering_envelope_not_ready")

    return PilotRunResponse(
        run_id=run_id,
        scenario_id=request.scenario_id,
        acceptance_passed=not reasons,
        acceptance_failures=reasons,
        plan=plan,
        verification=verification,
        engineering=engineering,
    )
