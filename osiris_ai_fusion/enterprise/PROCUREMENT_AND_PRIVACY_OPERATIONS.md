# ORBYTHRA Procurement, Privacy and Customer Lifecycle Operations

This document is an operational readiness pack, not legal certification. It defines the evidence ORBYTHRA must retain for enterprise onboarding, privacy operations, customer offboarding and procurement diligence.

## Customer onboarding

Before activation, retain: customer legal name, billing contact, security contact, tenant ID, plan, approved data classes, allowed integrations, data residency requirements if any, DPA/terms status, subprocessors disclosed, pilot or contract dates, and named account owner.

Provisioning checklist:

1. Create tenant and primary administrator.
2. Issue least-privilege API credentials.
3. Confirm quotas and rate limits.
4. Record enabled providers/integrations.
5. Run tenant isolation smoke tests using known fixtures.
6. Record the release Git SHA and deployment environment.
7. Provide security/privacy contact path.
8. Record acceptance of terms/DPA where applicable.

## Customer offboarding

Offboarding must be authorized and auditable. The default process is:

1. Stop new billing and record the effective termination date.
2. Revoke API keys and sessions.
3. Disable scheduled/watchlist activity.
4. Export customer data only when contractually requested and legally permitted.
5. Apply retention/legal-hold policy before deletion.
6. Delete tenant-scoped active data in documented order.
7. Verify zero active rows remain for the tenant in tenant-scoped tables.
8. Record backup-retention implications separately; backups are not silently rewritten.
9. Produce a dated completion receipt naming the operator and affected tenant ID.

`ops_tenant_assurance.py` inventories tenant-scoped rows and creates a fail-safe offboarding plan. It intentionally does not delete production data automatically.

## Privacy operations

Maintain a live register for:

- data categories processed;
- purpose/legal basis where required;
- storage locations;
- retention periods;
- subprocessors and processing purpose;
- international transfer mechanism where relevant;
- data-subject request contact and verification procedure;
- security incident/privacy escalation owner.

Operational requests should have timestamps for receipt, identity verification, scope, systems searched, action taken, exceptions/legal holds and completion.

## Subprocessor register

The production subprocessor list must reflect only providers actually enabled in production. Never list optional development providers as active subprocessors without checking the deployed configuration.

Each entry should record: legal entity, service, data categories, processing purpose, region, transfer mechanism, contract/DPA status, security review date and owner.

## Procurement evidence packet

A buyer or enterprise customer should be able to receive:

- architecture/data-flow diagram;
- current security questionnaire;
- threat model;
- SBOM/dependency audit evidence;
- uptime/SLO evidence;
- backup/restore and disaster-recovery evidence;
- penetration-test report when completed;
- privacy policy and DPA;
- subprocessor register;
- incident-response process;
- tenant isolation evidence;
- release provenance/attestation;
- data-source/license register;
- onboarding/offboarding procedure;
- case study/pilot evidence when real customer evidence exists.

## Evidence boundary

A template or automated test is not equivalent to a completed legal, security or customer event. ORBYTHRA should only mark a diligence gate complete when the required dated real-world artifact exists.
