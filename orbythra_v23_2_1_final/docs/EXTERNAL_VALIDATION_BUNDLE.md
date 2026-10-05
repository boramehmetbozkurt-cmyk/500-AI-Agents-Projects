# ORBYTHRA External Validation Bundle

Status: evaluator handoff specification. This document intentionally separates internal evidence from independent conclusions.

## Objective

Enable Radianode, a penetration-testing vendor, an enterprise evaluator or another qualified third party to reproduce material ORBYTHRA claims without relying on developer assertions.

## Immutable evaluation inputs

Evaluator should record before testing:

- repository/release commit SHA;
- ORBYTHRA version;
- Python/runtime versions;
- dependency lock/resolution output;
- `scripts/release_evidence.py` output;
- SHA-256 of `benchmarks/assurance_challenge_v2.json`;
- configured environment and database backend;
- exact test start/end timestamps;
- evaluator identity/organization and test methodology.

## Track 1 — Build/release reproducibility

Acceptance evidence:

1. clean checkout of supplied commit;
2. dependencies install successfully;
3. application compiles;
4. unit/integration tests pass;
5. Bandit security gate passes under repository threshold;
6. dependency vulnerability audit returns no known vulnerabilities at test time or findings are explicitly documented;
7. repository secret scan passes;
8. release-evidence manifest is generated and critical-file hashes match the tested checkout;
9. OpenAPI composition contains required protected surfaces.

Independent conclusion must include any environmental deviations.

## Track 2 — Evidence/abstention challenge

Run:

`python scripts/benchmark_gate.py`

Record the complete JSON result. Acceptance target for the frozen v2 deterministic challenge pack: 100% exact scenario match. This target validates deterministic implementation behavior only. It must **not** be reported as “100% hallucination elimination.”

Evaluator should additionally create held-out cases for:

- contradictory evidence;
- stale/undated evidence;
- low-authority evidence;
- partial/mixed claims;
- ambiguous evidence bindings;
- threshold boundary conditions;
- adversarial attempts to force an answer despite a guarded claim.

Held-out cases must not be disclosed to the ORBYTHRA development team before execution when blind evaluation is desired.

## Track 3 — Enterprise policy enforcement

Verify fail-closed behavior for:

- non-allowlisted/disabled providers;
- disallowed deployment/data-residency regions;
- prohibited data categories;
- retention beyond tenant policy;
- missing zero-retention capability at elevated risk;
- missing private endpoint at critical risk;
- missing human approval at configured risk tiers;
- insufficient evidence pass rate or excessive guarded claims;
- cross-workspace access attempts.

Evaluator should demonstrate that a BLOCK/REVIEW decision prevents provider invocation where the API contract says it must.

## Track 4 — Identity and tenant isolation

Test API-key and OIDC/JWT authentication paths including:

- invalid/missing credentials;
- issuer mismatch;
- audience mismatch;
- expired assertion;
- unknown signing key/kid;
- invalid signature;
- invalid workspace claim;
- role escalation attempt;
- cross-workspace object reads;
- rate-limit isolation.

OIDC testing should record identity-provider configuration and key rotation behavior.

## Track 5 — Cryptographic trust layer

Challenge MorseGuard / GestureGuard / EffectSeal / DSEL pipeline:

- normalization ambiguity/wrappers;
- bidirectional/zero-width Unicode controls;
- intent digest substitution;
- effect recipient/amount/action substitution;
- duplicate approver manipulation;
- approval bound to a different intent;
- ciphertext/header/signature tamper;
- wrong workspace;
- wrong key id;
- expired envelope;
- replay of a previously accepted envelope;
- key-rotation decrypt behavior;
- AES-256-GCM and ChaCha20-Poly1305 paths.

Acceptance requirement: semantic or cryptographic mismatch fails closed.

## Track 6 — Privacy/GDPR engineering controls

Technical tests only; no legal-compliance conclusion is requested from a security evaluator unless separately qualified.

Exercise:

- declared-field data minimisation;
- lawful-basis/special-category metadata gates;
- pseudonymised subject indexing;
- encrypted protected records;
- access/export and portability;
- rectification;
- restriction;
- consent withdrawal;
- erasure;
- retention purge;
- processing inventory;
- breach-register authorization and 72-hour review-deadline calculation;
- workspace isolation for privacy records.

## Track 7 — Security assessment

Minimum penetration-test scope should include the controls in `docs/PENTEST_SCOPE_AND_ACCEPTANCE.md`, plus OWASP web/API testing and GenAI-specific attack classes relevant to the deployed gateway (prompt injection, sensitive information disclosure, improper output handling, excessive agency and system-prompt/secret exposure).

Required report fields:

- severity methodology;
- reproducible finding steps;
- affected endpoint/component;
- evidence;
- impact;
- remediation recommendation;
- remediation commit/reference;
- retest disposition.

Do not mark the gate complete until the external assessor issues the report and, for material findings, a retest result.

## Track 8 — Production reliability

On the actual deployment, not CI/TestClient, collect:

- release SHA served by deployment;
- KMS/secret-manager key configuration evidence without exposing secrets;
- request success/error rate;
- p50/p95/p99 latency;
- concurrency/load results;
- uptime over a meaningful window;
- alert delivery test;
- backup timestamp and restore drill;
- measured RPO/RTO;
- rollback drill;
- database fail/reconnect behavior.

Internal synthetic load tests are not a substitute for this track.

## Independent report requested from evaluator

Report should clearly separate:

- **PASS** — directly reproduced/verified;
- **PASS WITH LIMITATION** — reproduced under stated constraints;
- **FAIL** — acceptance criteria not met;
- **NOT TESTED** — outside scope;
- **OBSERVATION** — non-blocking improvement.

The report should not copy ORBYTHRA's self-description as its conclusion. It should state the evaluator's own test setup, evidence and findings.

## Commercial/customer evidence boundary

Independent technical validation does not establish product-market fit, paid adoption, ARR, retention or valuation. Customer and revenue gates require contracts, invoices/payment evidence, usage and renewals/expansion records.
