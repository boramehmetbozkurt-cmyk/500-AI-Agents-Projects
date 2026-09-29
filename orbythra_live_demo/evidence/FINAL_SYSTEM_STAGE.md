# ORBYTHRA — Final System Stage

Date: 2026-09-29
Status: **FINAL OWNER-CONTROLLED ARCHITECTURE BASELINE**

This document freezes the target architecture of ORBYTHRA. “Final” means there is no additional internal architecture stage after this baseline. Future work is maintenance, evidence refresh, model/provider substitution, domain packs, and externally controlled validation—not a new ORBYTHRA maturity tier.

## System definition

ORBYTHRA is a model-agnostic Engineering Intelligence and Verifiable Temporal Reality platform. It converts a question or engineering decision into an auditable chain:

`intent -> plan -> retrieval -> provenance -> temporal/spatial context -> contradiction analysis -> quantitative trace -> uncertainty -> synthesis -> self-evaluation -> bounded refinement -> disposition -> integrity receipt -> telemetry`

State-changing effects add:

`disposition -> explicit approval -> intent/effect binding -> execution -> effect verification -> immutable action record`

## Final architecture invariants

1. **Evidence first.** Material factual claims require source lineage.
2. **Time aware.** Publication, effective, retrieval, and decision times remain distinct.
3. **Quantitatively replayable.** Engineering calculations expose variables, units, equations, assumptions, and uncertainty.
4. **Contradictions stay visible.** Conflicting evidence is not silently averaged away.
5. **Uncertainty is actionable.** Missing/stale/conflicting evidence can force qualification, abstention, or escalation.
6. **Model agnostic.** No single LLM/provider is a trust root.
7. **Bounded autonomy.** Research/refinement is bounded; external side effects are approval gated.
8. **Tenant isolated.** Persistent memory/goals/actions must preserve tenant boundaries.
9. **Memory is not evidence.** Historical memory cannot become fresh evidence without re-retrieval and provenance.
10. **Fail closed for effects.** Missing/stale/mismatched approval cannot execute.
11. **Provider failures are classified.** Quota/timeout/runtime/load/harness failures remain separate from capability failures.
12. **Integrity is explicit.** Evidence/report artifacts carry deterministic digests/receipts.
13. **Observability is mandatory.** Run IDs, failure classes, provider events, decisions, and action records are traceable.
14. **Validation is release-bound.** No later release inherits external validation without retest.

## Final subsystem map

- Adaptive Core / orchestration
- Evidence retrieval and provenance
- Temporal Reality Engine
- World/spatial context and map output
- Engineering Intelligence
- Claim & Quantitative Trace
- Contradiction engine
- Uncertainty / abstention policy
- Self-evaluation and bounded refinement
- Persistent Goals
- Tenant-isolated episodic/fact memory
- Learned research policy
- Cognitive telemetry
- Scheduler with bounded cadence
- Approval-gated action ledger
- Intent/effect verification boundary
- Integrity receipts
- Hunter/domain modules
- Buyer-safe and evaluation surfaces
- Release/evidence manifests
- Security/threat model and incident/recovery controls

## Definition of Done

The internal architecture baseline is complete when the repository contains:
- executable core and API;
- deterministic tests for trust-boundary logic;
- CI/release gates;
- threat model and security scope;
- claim/trace schema;
- blinded evaluation protocol;
- release manifest and evidence ledger;
- production runbook and recovery procedure;
- explicit external-validation boundary.

External evidence is deliberately **not** fabricated by this repository. Independent security assessment, Radianode/evaluator report, blinded evaluator-controlled holdout results, and a real engineering/digital-twin pilot remain external gates. Completing those gates changes the evidence status of this same architecture; it does not create another system stage.

## Release claim discipline

Allowed: “final owner-controlled architecture baseline”, “validation-ready”, or a narrower claim supported by attached evidence.

Not allowed without external evidence: “independently certified”, “independently validated”, “zero-risk”, “infallible”, or universal engineering-grade claims.

## Change policy

After this baseline, changes are classified only as:
- PATCH — bug/security/reliability fix;
- EVIDENCE — new benchmark/audit/pilot evidence;
- PROVIDER — model/search/tool substitution;
- DOMAIN — bounded Hunter/domain pack;
- OPERATIONS — deployment/observability/scaling;
- BREAKING — invariant/API/schema change requiring a new major release and revalidation.

There is no “next maturity stage” inside the product roadmap after this baseline.
