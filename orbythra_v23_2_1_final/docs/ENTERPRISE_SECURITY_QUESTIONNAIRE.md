# ORBYTHRA Enterprise Security Questionnaire — Evidence Baseline

This document answers common procurement questions using current repository evidence. Items requiring real production operation or independent audit are explicitly marked pending.

## Product and tenancy

- Architecture: FastAPI service with PostgreSQL production option and SQLite evaluation fallback.
- Tenant separation: workspace-scoped data access plus RBAC.
- Authentication: API-key authentication with constant-time comparison; enterprise SSO remains a future deployment/integration item.
- Roles: viewer, evaluator, operator, admin.

## Encryption and keys

- In transit: TLS is required at the production ingress/reverse proxy.
- At rest: application envelope encryption for protected payloads using standard AEAD primitives.
- Algorithms: AES-256-GCM and ChaCha20-Poly1305; HKDF-SHA256; Ed25519 signatures; X25519 optional recipient wrapping.
- Key management: key IDs and rotation-compatible key ring. Production master keys must be injected from a secret manager/KMS and must not be committed to source.
- Production KMS evidence: pending live deployment.

## Application security

- Static scan: Bandit in CI.
- Dependency vulnerability audit: pip-audit in CI.
- Secret scanning: repository secret scanner in CI.
- Regression tests: automated pytest suite.
- OpenAPI route gates: critical APIs must remain present for CI to pass.
- External penetration test: pending independent assessor.

## AI assurance

- Deterministic evidence gate and guarded/abstention behavior.
- Predeclared pilot acceptance criteria.
- Enterprise provider registry.
- Runtime risk policy engine with provider/region/data-category controls.
- Benchmark scorecards with accuracy, traceability, evidence-pass and latency thresholds.
- Human approval gate for configured risk tiers.

## Privacy

- Processing purpose/lawful-basis metadata.
- Data minimisation controls.
- Pseudonymised subject indexing.
- Encrypted protected payloads.
- Retention/purge controls.
- Access/portability, rectification, restriction, erasure and consent-withdrawal support.
- Breach register with 72-hour review clock.
- Legal GDPR certification: not claimed; organisational/legal review remains required.

## Availability and resilience

- Health/readiness checks.
- PostgreSQL production topology.
- Backup/recovery tooling and runbook.
- Docker non-root runtime.
- Formal measured SLA, multi-zone uptime and DR exercise evidence: pending live production.

## Audit and accountability

- Request IDs and audit trail.
- Workspace/provider/policy/benchmark actions are auditable.
- Usage metering supports enterprise unit tracking.
- Independent SOC 2 / ISO 27001 report: pending formal external audit.

## Procurement evidence package

Provide under NDA as appropriate: architecture, current CI run, security scan outputs, dependency inventory, cryptographic design, GDPR technical controls, DPA template, subprocessor register, incident/SLA policy, pilot acceptance protocol, benchmark reports and independent reports once issued.
