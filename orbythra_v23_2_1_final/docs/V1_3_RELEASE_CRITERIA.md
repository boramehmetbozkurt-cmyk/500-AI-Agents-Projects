# ORBYTHRA v1.3 Release Criteria

## Release identity

Target: `1.3.0` — **External Validation Candidate**.

The version indicates that ORBYTHRA has completed repository-controlled production/security/validation-readiness work. It does not indicate that an independent evaluator has approved the product.

## v1.1 — Production hardening criteria

Repository-controlled criteria:

- PostgreSQL-capable production configuration;
- immutable release SHA and deployment ID support;
- external secret-manager/KMS deployment modes;
- hardened Kubernetes deployment baseline;
- at least two replicas in the baseline;
- HPA and PodDisruptionBudget;
- NetworkPolicy;
- non-root/read-only/drop-capabilities security context;
- startup/readiness/liveness probes;
- backup/restore integrity drill;
- retry/circuit-breaker provider resilience.

External production evidence still required:

- actual production deployment record;
- actual KMS/HSM or secret-manager custody evidence;
- production telemetry;
- measured uptime/error/latency history;
- measured RPO/RTO and rollback rehearsal.

## v1.2 — Security hardening criteria

Repository-controlled criteria:

- AES-256-GCM / ChaCha20-Poly1305 EffectSeal paths;
- Ed25519 envelope signing;
- X25519 recipient wrapping;
- recipient-only decryption with pinned signer public key;
- exact intent/effect binding;
- signed Ed25519 approval proof verification;
- approval signer identity derived from public-key fingerprint;
- key rotation regression coverage;
- TTL/expiry regression coverage;
- ciphertext/recipient-wrap mutation fail-closed tests;
- replay concurrency regression coverage;
- Bandit, dependency audit, SBOM and repository secret scan.

External security evidence still required:

- independent penetration test;
- independent cryptographic design review;
- material finding remediation and retest.

## v1.3 — External validation candidate criteria

Repository-controlled criteria:

- frozen deterministic benchmark v2;
- expanded deterministic benchmark v3;
- fingerprinted machine-readable external validation protocol;
- minimum 500-case A/B protocol design across five domains;
- predeclared primary and secondary metrics;
- external validation readiness API;
- validation protocol API with SHA-256 fingerprint;
- independent evaluator report template;
- reproducible validation handoff bundle;
- SHA-256 release-evidence manifest;
- all mandatory CI gates green on the exact release commit.

## Completion of independent validation

Independent validation is not complete at repository release time. Completion additionally requires an external party to provide:

1. evaluator identity and dated report;
2. tested release SHA and deployment ID;
3. dataset fingerprint and case counts;
4. results for every primary metric;
5. exclusions and protocol deviations;
6. penetration-test/crypto-review references where in scope;
7. remediation/retest status for material security findings.

## Approved claim

> ORBYTHRA v1.3.0 is an external-validation candidate with reproducible internal release evidence, production-deployment hardening, cryptographic approval/recipient controls, and a fingerprinted third-party evaluation protocol. Independent validation remains pending until attributable external evidence is issued.
