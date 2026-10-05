# ORBYTHRA v1.0 Release Criteria

ORBYTHRA v1.0 is the first stable internal product/API baseline. The release number does not imply independent certification, customer acceptance, production uptime history or revenue.

## Mandatory internal gates

A v1.0 release commit must pass all repository-controlled gates:

1. complete pytest suite;
2. frozen assurance challenge v2;
3. expanded assurance challenge v3 at 100% exact-match acceptance;
4. deterministic verification performance smoke;
5. backup/restore integrity drill;
6. Bandit static-security gate;
7. dependency vulnerability audit with no known vulnerabilities;
8. CycloneDX SBOM generation;
9. repository secret scan;
10. SHA-256 release-evidence manifest;
11. production composition and mandatory OpenAPI route smoke;
12. policy revision/rollback tests;
13. identity lifecycle tests;
14. provider retry/circuit-breaker tests.

## Stable v1 surfaces

The `/v1` API major version is the compatibility boundary. Backward-incompatible changes require a new API major version or a documented migration/deprecation period.

Stable capability families:

- evidence verification and guarded disposition;
- Engineering Intelligence / adaptive planning;
- evidence snapshots and pilot acceptance;
- audit and operational metrics;
- cryptographic trust layer;
- GDPR-aligned privacy technical controls;
- enterprise provider registry and model gateway;
- enterprise risk policy enforcement;
- immutable policy revision history and rollback;
- enterprise identity lifecycle controls;
- benchmark scorecards and usage metering;
- system version and assurance-manifest endpoints.

## Production configuration gate

`/v1/enterprise/production/readiness` is a configuration check, not operational proof. A real production environment should additionally provide:

- PostgreSQL;
- OIDC identity provider configuration;
- externally managed production secrets/keys;
- immutable release SHA and deployment ID;
- HTTPS provider endpoints;
- central logging/alerts;
- measured backup/restore RPO/RTO;
- measured uptime, latency and error rate;
- rollback rehearsal.

## External gates intentionally not self-certified

The following remain external evidence even after v1.0:

- independent penetration test and remediation/retest report;
- independent cryptographic/security review;
- Radianode or equivalent independent product validation;
- GDPR legal opinion/certification claim;
- SOC 2 / ISO 27001 formal certification;
- signed enterprise customer contracts;
- invoices/payments/ARR;
- renewal/expansion evidence;
- patentability or freedom-to-operate opinion.

## Release claim

Approved wording:

> ORBYTHRA v1.0 is a stable enterprise AI assurance technical baseline with reproducible internal validation, governance, privacy and cryptographic trust controls. Independent validation, live production history and commercial traction are reported separately when external evidence exists.
