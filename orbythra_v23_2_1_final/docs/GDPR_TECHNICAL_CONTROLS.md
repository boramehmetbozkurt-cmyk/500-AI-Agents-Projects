# ORBYTHRA GDPR Technical Controls

## Scope

ORBYTHRA v0.5.0 implements GDPR-aligned technical privacy controls. This document maps the implemented controls to common GDPR obligations. It is not a legal opinion, certification, supervisory-authority approval, or substitute for controller/processor contracts, privacy notices, DPIAs, international-transfer assessments, DPO obligations, records outside ORBYTHRA, or jurisdiction-specific legal review.

## Implemented controls

### Lawfulness, purpose limitation and transparency support

Every privacy record requires a specific purpose and one Article 6-style lawful-basis category. Consent-based records require a consent reference. Special-category records require an explicit Article 9 condition reference.

### Data minimisation

The API requires `declared_fields`; payload fields not declared are rejected. This provides an enforceable minimisation gate for data entering the dedicated privacy-record subsystem.

### Pseudonymisation and confidentiality

Raw subject identifiers are not stored in the privacy index. Workspace-scoped HMAC subject tokens are stored instead. Privacy payloads are encrypted at rest using ORBYTHRA's envelope-encryption vault. Existing RBAC, workspace isolation, rate limiting, audit logging and cryptographic controls remain active.

### Storage limitation

Every privacy record has an explicit `retention_until` deadline. Expired records can be purged via `POST /v1/privacy/retention/purge` or `scripts/gdpr_retention.py`.

### Data-subject rights

Implemented API operations include:

- access and JSON portability: `POST /v1/privacy/subjects/export`
- rectification: `POST /v1/privacy/records/rectify`
- restriction: `POST /v1/privacy/subjects/restrict`
- consent withdrawal: `POST /v1/privacy/subjects/withdraw-consent`
- erasure: `POST /v1/privacy/subjects/erase`

Erasure is intentionally restricted to admin role because the operation is destructive. Operational/legal exceptions to erasure must be assessed by the controller before invoking it.

### Accountability and processing inventory

`GET /v1/privacy/inventory` returns purpose/lawful-basis counts without exposing raw personal payloads. Privacy operations are written to the encrypted audit trail.

### Breach readiness

`POST /v1/privacy/breaches` creates an encrypted breach record and calculates a 72-hour supervisory-authority review deadline from the reported awareness/detection timestamp. The system does not automatically assert that notification is legally required; risk and controller status must be assessed.

## Controls intentionally not claimed as complete

The codebase alone cannot establish full GDPR compliance. A deployment still needs, as applicable:

- controller/processor role determination
- privacy notices and transparent information under Articles 12-14
- a complete Record of Processing Activities where required
- processor Data Processing Agreements
- international-transfer mechanism and transfer-impact assessment where applicable
- DPIA for processing likely to result in high risk
- DPO appointment where legally required
- subprocessors and retention schedules approved by the organisation
- incident response procedures and supervisory-authority/data-subject notification decisions
- legal validation of lawful bases and Article 9 conditions
- procedures to verify identity before fulfilling data-subject requests

## Security test boundary

Internal automated tests validate implementation behavior such as encryption at rest, pseudonymised lookup, workspace isolation, minimisation rejection, access/export, rectification, restriction, consent withdrawal, erasure, retention purge and breach-deadline calculation. These tests demonstrate code behavior, not external legal certification.
