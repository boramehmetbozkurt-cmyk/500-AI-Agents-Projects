# ORBYTHRA Independent Validation Scope

Reference release: AppDeploy `v2`, snapshot `1789502718462`.

## Controlled handoff sequence

1. NDA / confidentiality terms.
2. Provide the public buyer-demo URL and release identifier first.
3. Agree written scope, test window, rate limits, tenant/test accounts and permitted data.
4. Share only the minimum controlled evaluation package required for the agreed scope.
5. Receive a formal written report with methodology, evidence, severity/impact and reproducible findings.
6. Remediate findings against the same release lineage.
7. Request retest and a written closure/delta report.

## Radianode — engineering validation

Requested evidence categories:

- architecture and engineering-method review;
- digital-twin / engineering-intelligence assumptions where applicable;
- reproducibility of outputs and traceability to evidence;
- vendor-neutral review of claimed engineering capabilities;
- identified limitations, unsupported claims and recommended acceptance criteria.

Deliverable requested: independent engineering validation report referencing release `1789502718462` or an explicitly agreed successor release.

## InterClin AI — Search/RAG/deep-research evaluation

Benchmark axes:

- Turkish and English answer completeness;
- retrieval relevance and source diversity;
- factuality / groundedness;
- citation/source consistency;
- no-source fallback quality;
- ambiguity handling;
- current-information behavior;
- domain routing (web/science/world/engineering);
- proprietary-signal calibration if supplied under NDA;
- latency/cost measurements if included in the agreed protocol.

The public seed benchmark is `benchmark_cases.json`. Evaluator should add a blinded holdout set so results are not limited to developer-known prompts.

## Synack — third-party security test

Requested scope categories:

- public web application;
- backend API routes;
- authentication/authorization if enabled in the evaluation environment;
- tenant/workspace isolation where applicable;
- input validation and injection classes;
- SSRF and unsafe outbound-request behavior;
- secrets/token exposure;
- rate-limit / abuse-resistance checks;
- AI/LLM-specific prompt injection, data exfiltration and tool-boundary testing where applicable;
- remediation verification and retest.

No production-destructive testing, credential attacks against unrelated third parties, or out-of-scope active scanning should be performed without explicit written authorization.

## Release-control rule

Every external report must name the exact release/snapshot tested. Findings from one snapshot must not be represented as validation of a later snapshot unless the evaluator performs a retest or explicitly extends coverage in writing.
