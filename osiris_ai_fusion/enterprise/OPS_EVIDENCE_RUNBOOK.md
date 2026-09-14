# ORBYTHRA Operational Evidence Runbook

This runbook creates repeatable evidence for security and production diligence. A runbook is not the same
as evidence that an exercise happened; signed/dated results from a real environment must be retained.

## Secrets rotation exercise

Quarterly or before a transaction:

1. Inventory ORBYTHRA API/admin keys, LLM/provider keys, Stripe keys and SEAL signing material.
2. Create replacement credentials in the upstream provider/secret manager.
3. Deploy replacements to staging and run `/health`, `/ready`, representative investigation and receipt verification checks.
4. Deploy to production using overlap where the provider supports it.
5. Revoke the old secret.
6. Verify old credentials fail and new credentials succeed.
7. Run deterministic secret scanning against the repository and deployment bundle.
8. Record operator, UTC timestamps, credential class (never the secret), affected services and rollback outcome.

Evidence file naming convention: `rotation-YYYYMMDD.json`.

## Incident-response tabletop

Scenario: a tenant reports that an ORBYTHRA output contains data believed to belong to another tenant.

Expected actions:

1. Declare incident severity and freeze affected deployment changes.
2. Preserve logs, request IDs and database backup without exposing secrets in the incident channel.
3. Disable/revoke affected tenant credentials if necessary.
4. Determine whether the issue is UI caching, authentication, query scoping or persistent cross-tenant storage.
5. Test tenant boundaries with known fixtures.
6. Identify affected records/users and legal notification obligations.
7. Patch and validate in an isolated environment.
8. Restore service only after scope/isolation tests pass.
9. Produce root-cause analysis, corrective actions and evidence of verification.

Evidence file naming convention: `tabletop-YYYYMMDD.md`.

## Production SLO evidence

The in-process benchmark is only a regression baseline. Production evidence should include:

- deployment/environment identifier;
- measurement interval of at least seven days for initial diligence and 30+ days for mature evidence;
- total requests and 5xx count;
- p50/p95/p99 latency by major API surface;
- uptime/availability source independent of the application when possible;
- error-budget consumption;
- incident periods annotated rather than deleted;
- exact release Git SHA.

Default starting SLO hypothesis:

- availability: 99.5% monthly;
- API p95 latency for non-LLM control endpoints: <= 1.5 s;
- zero known cross-tenant data leaks;
- zero unauthorized active execution.

Customer contracts may require stricter targets.

## Independent penetration test scope

Provide the assessor with:

- production/staging architecture and data-flow diagram;
- authenticated tenant test accounts;
- API inventory/OpenAPI schema;
- tenant isolation requirements;
- rate limits and explicit excluded active capabilities;
- deployment/container configuration;
- source review access when contractually approved.

Minimum requested coverage:

- authentication/session/API-key handling;
- tenant isolation/IDOR;
- injection and SSRF/provider-boundary testing;
- CORS/CSP/security headers;
- rate-limit abuse;
- secret leakage;
- dependency/container configuration;
- billing/webhook verification;
- science/genome privacy boundary;
- evidence/provenance tampering.

A pentest is complete only when the independent report and remediation evidence exist.

## Release signing

Use `ops_attestation.py` over the exact buyer/release artifacts. In production/release CI, provide
`SEAL_ED25519_PRIVATE_KEY_B64` from an external secret manager. Never commit the private key.
The resulting attestation must contain the release Git SHA, artifact SHA-256 values, public key and Ed25519 signature.
