# ORBYTHRA v1.3 External Validation Protocol

## Status

ORBYTHRA v1.3 is an **External Validation Candidate**, not an independently validated product until a qualified third party executes the protocol and issues attributable evidence.

## Objective

Measure whether ORBYTHRA improves assurance outcomes when wrapped around the same underlying AI/model/agent workflow, without changing the underlying model between comparison arms.

## Required comparison

- Arm A: baseline model or agent without ORBYTHRA assurance controls.
- Arm B: the same model or agent with ORBYTHRA evidence, policy, intent/effect and audit controls enabled.
- Minimum 500 cases total.
- Minimum 100 cases in each of five domains: engineering, enterprise research, finance information, policy/compliance, technical support.
- Case ordering must be randomized.
- Human graders should be blinded to the tested arm where practical.

## Predeclared primary metrics

1. Unsupported-claim rate.
2. Contradiction-detection recall.
3. Correct-abstention rate.
4. Evidence-traceability rate.
5. Critical false-negative rate.

Secondary metrics include false-positive rate, reviewer time, policy-block accuracy, intent/effect binding accuracy, p50/p95 latency overhead and cost overhead per case.

The machine-readable protocol and thresholds are stored in `benchmarks/external_validation_protocol_v1.json` and exposed by `GET /v1/validation/protocol` together with a SHA-256 fingerprint.

## Integrity requirements

The independent report must identify:

- exact ORBYTHRA release SHA;
- deployment identifier;
- underlying model/provider and version where disclosure is permitted;
- dataset/corpus fingerprint;
- case count by domain and label;
- primary metric numerator and denominator or equivalent confusion matrix;
- exclusions, invalid cases and deviations from the protocol;
- evaluator identity and report date.

## Deterministic vs stochastic evidence

ORBYTHRA deterministic CI/benchmark results must be reported separately from stochastic model/agent performance. A 100% deterministic challenge-pack pass does **not** imply a universal hallucination-reduction percentage.

## Security review track

The product-validation track is separate from security review. The v1.3 handoff requests:

- external API/web penetration testing;
- workspace/tenant isolation testing;
- authentication/authorization testing;
- replay/nonce/concurrency testing;
- cryptographic design review scoped to EffectSeal, key derivation/wrapping, signatures, X25519 recipient wrapping and outcome receipts;
- remediation and retest evidence for material findings.

## Recipient-only envelope test

v1.3 adds a recipient-only X25519 open path. The recipient can decrypt a recipient-wrapped EffectSeal envelope using its private key without access to the ORBYTHRA master key. The signer public key must be pinned by the caller; trusting an arbitrary public key embedded in the envelope is not sufficient signer authentication.

## Production deployment evidence

The repository contains a hardened Kubernetes baseline and a CI deployment-manifest gate. These are configuration evidence only. A real production claim additionally requires deployment records, external secret/KMS custody, telemetry, uptime/error/latency history and recovery evidence from the live environment.

## Completion definition

v1.3 independent validation is complete only when all of the following exist:

1. an attributable third-party report;
2. tested release SHA/deployment ID;
3. dataset fingerprint;
4. primary metric results;
5. security findings and remediation status;
6. documented protocol deviations.

Until then the correct status is **External Validation Candidate / External Validation Pending**.
