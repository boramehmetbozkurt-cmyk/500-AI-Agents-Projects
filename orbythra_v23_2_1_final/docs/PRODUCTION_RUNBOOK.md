# ORBYTHRA Production Runbook

## Release baseline

Current baseline: `v0.6.0`.

Production application entrypoint: `app.api:app`.

Production requirements:

- Python 3.12 runtime
- PostgreSQL 17 recommended; SQLite retained for local/evaluation use
- API keys injected only through environment/secrets manager
- production `ORBYTHRA_MASTER_KEYS` supplied through KMS/secret-management process; never source control
- RBAC roles: `admin`, `operator`, `evaluator`, `viewer`
- TLS terminated by the hosting platform or reverse proxy
- `/health` for liveness and `/ready` for readiness
- provider credentials supplied as backend-only secrets
- production logs/metrics retained according to approved security/privacy policy

## Startup checks

A deployment is considered technically ready only when:

1. `/health` returns `status=ok`.
2. `/ready` returns `ready=true`.
3. database connectivity is healthy.
4. authentication is configured.
5. cryptographic production keys are configured.
6. CI has passed tests, static security scan, dependency audit, secret scan, release-manifest generation and production OpenAPI smoke test.
7. enterprise provider/policy configuration has been reviewed for the target workspace.

## Production secrets

Required secret material must be generated outside the repository. At minimum: database password, API credentials and ORBYTHRA master-key ring. Model/evidence provider credentials are added only when the corresponding provider is enabled. Rotate keys by installing a new active key ID while preserving required older decrypt-capable keys until controlled re-encryption/retirement is complete.

## Backup and recovery

SQLite evaluation environments may use:

```bash
python scripts/backup.py ./backups/orbythra.db
```

PostgreSQL uses `pg_dump` through the same script when `ORBYTHRA_DATABASE_URL` is set.

Production recovery must be exercised, not assumed. Measure actual RPO/RTO and preserve evidence of the restore test. Backups must be encrypted and access controlled.

## Rollback

1. Stop or drain traffic to the failing release.
2. Restore the previous known-good image/version tied to its release SHA.
3. Verify `/health` and `/ready`.
4. Run critical OpenAPI/policy/evidence smoke checks.
5. If data corruption is involved, restore the last verified backup using the approved recovery procedure.
6. Record the incident, impact, timeline and remediation in the audit/change record.

## Observability

`GET /v1/metrics` exposes controlled operational counters and average latency to evaluator-or-higher roles. Hosting-level CPU, memory, network, container restart, database saturation, backup status and TLS/ingress metrics should be collected by the deployment platform. Enterprise launch additionally requires alert routing and named on-call ownership.

## Enterprise governance

Before a high-consequence AI workflow is enabled:

1. Register the model/provider under `/v1/enterprise/providers`.
2. Define a workspace policy under `/v1/enterprise/policies/{policy_id}`.
3. Validate region, data category, retention, zero-retention/private-endpoint and human-approval requirements.
4. Run a predeclared benchmark/pilot and preserve the result.
5. Record usage units and operational evidence after launch.

## Independent validation boundary

This runbook establishes internal production and enterprise-readiness controls only. It does not represent Radianode approval, SOC 2/ISO certification, independent penetration-test approval, legal GDPR certification, customer acceptance, revenue or achieved uptime. Those require the responsible external evidence.
