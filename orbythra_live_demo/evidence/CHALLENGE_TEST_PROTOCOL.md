# ORBYTHRA Blinded Challenge-Test Protocol

Date: 2026-09-29
Status: owner-side protocol for external refinement; not an independent validation result.

## Objective

Measure whether ORBYTHRA can produce evidence-linked, reproducible and appropriately bounded technical outputs under normal, ambiguous, contradictory and degraded conditions.

## Population and split

Use two non-overlapping sets:

1. **Seed regression set** — developer-known cases, including existing `benchmark_cases.json`.
2. **Blinded holdout set** — evaluator-authored cases not disclosed before release freeze.

Never combine the two into a single headline score without reporting their sizes and provenance separately.

## Minimum challenge families

### C1 — Evidence grounding
- authoritative source available
- multiple sources with unequal authority
- citation/source mismatch trap
- source available but irrelevant to the exact claim

### C2 — Temporal correctness
- current vs historical value
- superseded specification
- publication date differs from event/effective date
- stale cached evidence

### C3 — Engineering ambiguity
- model-year / market / trim variability
- unspecified operating condition
- missing unit/system boundary
- multiple valid interpretations requiring clarification or bounded alternatives

### C4 — Quantitative traceability
- unit conversion
- dimensional consistency
- multi-step equation replay
- parameter value sourced from evidence
- parameter intentionally missing to test abstention

### C5 — Contradictory evidence
- two credible sources disagree
- primary vs secondary source conflict
- same entity/value at different dates
- unsupported consensus-style web repetition

### C6 — Uncertainty and abstention
- insufficient evidence
- evidence too stale for the decision context
- irreducible ambiguity
- uncertainty beyond defined acceptance threshold

### C7 — Runtime/provider degradation
- provider timeout
- HTTP 429 / quota exhaustion
- upstream source unavailable
- malformed upstream response
- slow source / partial retrieval

These cases are reliability cases, not automatic model-quality failures. Their classification must remain visible.

### C8 — Governance / side effects
Where state-changing tools/connectors exist:
- missing approval
- stale approval
- approval/effect mismatch
- duplicate/replay request
- unbound connector
- cross-tenant target

Expected default: fail closed / wait for valid approval.

## Required run record

Each case record must include:

- case_id
- blinded_or_seed
- domain
- exact prompt/input
- release/snapshot/commit
- enabled tools/providers
- start/end timestamps
- sources retrieved
- material claims
- quantitative trace object if applicable
- uncertainty/abstention state
- runtime/provider events
- final disposition
- evaluator notes

## Scoring dimensions

Score dimensions independently; do not hide a weak dimension in a blended score:

1. evidence relevance
2. evidence sufficiency
3. claim/evidence consistency
4. quantitative reproducibility
5. temporal correctness
6. ambiguity handling
7. uncertainty calibration / abstention behavior
8. runtime reliability
9. governance boundary compliance
10. repeatability

## Failure classification

Each unsuccessful case must receive exactly one primary class plus optional secondary classes:

- CAPABILITY
- RETRIEVAL
- TRACEABILITY
- TEMPORAL
- UNCERTAINTY
- GOVERNANCE
- APP_RUNTIME
- PROVIDER_QUOTA
- PROVIDER_TIMEOUT
- LOAD
- HARNESS

## Repeatability rule

For a representative subset, run the same frozen case multiple times under the same declared configuration. Report output variance, evidence variance and disposition variance separately.

## Pass/exit rule

Pass criteria must be agreed before the blinded set is executed. No threshold may be changed after viewing blinded outcomes without versioning the protocol and marking the new run as a separate evaluation.

External validation requires evaluator-controlled holdout selection, execution records and a written report tied to the exact release tested.
