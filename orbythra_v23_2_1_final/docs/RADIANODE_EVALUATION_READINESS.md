# ORBYTHRA — Evaluation Readiness Baseline

Version: 0.2.0 release candidate

This document defines the controlled technical baseline presented for independent engineering review. It is not an independent validation report and does not claim certification.

## Evaluation-ready capabilities

- Deterministic claim-to-evidence gate with explicit support and authority thresholds.
- Explicit states for supported, contradicted, insufficient, stale and low-authority evidence.
- Adaptive query planning with visible objectives, modes and success criteria.
- Engineering decision envelope with unknowns, assumptions, required evidence, FMEA prompts and verification steps.
- API-key authentication with workspace isolation.
- Per-key/workspace/client rate limiting.
- Request IDs, security headers and auditable API actions.
- Persistent SQLite evidence snapshots and pilot run records.
- Controlled pilot endpoint with explicit acceptance criteria and stored results.
- Containerized Python 3.12 + FastAPI runtime.
- CI quality gate covering compilation, API tests and OpenAPI smoke checks.

## Proposed independent review sequence

1. Freeze a mutually agreed commit/release identifier.
2. Radianode selects or approves evaluation cases.
3. Acceptance criteria are written before execution.
4. Evidence is supplied or collected with traceable identifiers.
5. Cases are executed through `/v1/pilot/run`.
6. Raw run records and audit trail are exported without post-hoc edits.
7. Failures are classified as methodology, evidence, implementation or scope failures.
8. Remediation is performed in a new release.
9. The same frozen cases are re-run.
10. Radianode issues its own independent report and limitations statement.

## Separation of roles

ORBYTHRA engineering/development artifacts can support evaluation, but Radianode must control its independent conclusions, pass/fail interpretation and final report. ORBYTHRA must not self-issue or pre-write an "independent" approval.

## Items requiring external completion

- Radianode approval of the formal scope and test cases.
- Radianode-owned execution/review or witnessed execution as agreed.
- Independent report.
- Any commercial pilot customer's own acceptance/sign-off.
