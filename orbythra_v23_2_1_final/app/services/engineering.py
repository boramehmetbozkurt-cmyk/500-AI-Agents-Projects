from __future__ import annotations

from app.models import EngineeringEnvelope, EngineeringRequest


def build_engineering_envelope(request: EngineeringRequest) -> EngineeringEnvelope:
    unknowns: list[str] = []
    assumptions: list[str] = []

    if not request.target:
        unknowns.append("target_or_acceptance_criteria")
    if not request.constraints:
        unknowns.append("constraints")
    if not request.standards:
        assumptions.append("No governing standard was supplied; standards must be confirmed before release.")

    required_evidence = [
        "Measured or authoritative input data for all decision-driving parameters",
        "Traceable source or test record for each factual engineering claim",
        "Applicable standards, limits and operating envelope",
        "Baseline or alternative design data for comparison",
    ]

    verification_plan = [
        "Define measurable acceptance criteria before selecting a solution.",
        "Bind each decision-driving claim to evidence and run the ORBYTHRA evidence gate.",
        "Quantify uncertainty and identify assumptions that materially change the decision.",
        "Run a reproducible benchmark or experiment against a baseline.",
        "Record result, evidence IDs, timestamp and release decision in an auditable artifact.",
    ]

    fmea_prompts = [
        "What can fail and what is the effect?",
        "What is the severity, occurrence likelihood and detectability?",
        "Which single failure mode dominates residual risk?",
        "What verification or control reduces that risk measurably?",
    ]

    return EngineeringEnvelope(
        decision_status="NEEDS_MORE_INPUT" if unknowns else "READY_FOR_EVIDENCE",
        problem=request.problem,
        target=request.target,
        assumptions=assumptions,
        unknowns=unknowns,
        required_evidence=required_evidence,
        verification_plan=verification_plan,
        fmea_prompts=fmea_prompts,
    )
