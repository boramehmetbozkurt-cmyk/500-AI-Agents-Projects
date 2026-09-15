# OSIRIS Threat Model

This threat model covers OSIRIS Fusion, Public SaaS, OSIRIS World, Sensor Mesh, Temporal Reality Atlas/Globe and the Science Genome Graph. It is an engineering control register, not a substitute for an independent penetration test or legal/privacy review.

## Security goals

1. Keep tenant data isolated.
2. Prevent untrusted prompts from turning read-only research into active scanning, exploitation or credential access.
3. Preserve evidence/source lineage so generated analysis cannot silently become fact.
4. Prevent scenario/future data from mutating canonical reality.
5. Keep personal/patient genomic data out of the shared Science Genome Graph.
6. Prevent provider/API compromise from silently poisoning high-confidence canonical state.
7. Make backups, releases and data imports integrity-verifiable.
8. Keep secrets out of source control and logs.

## Trust boundaries

### Browser / public client

Untrusted. Session API keys can be stored only in session-scoped browser storage by the current UIs. The browser cannot choose arbitrary provider execution URLs.

### Public SaaS API

Authenticated and rate-limited. Identity determines tenant/workspace scope. Authorization is not accepted from model output.

### Fusion planner / model

Untrusted decision support. Model output can propose tools/claims but cannot widen caller authorization scope. Unsupported claims are dropped by evidence sanitization.

### Provider federation

External network boundary. Built-in/configured providers are read-only. User prompts do not supply provider URLs. Every provider response is untrusted until normalized, evidence-tagged and policy-checked.

### OSIRIS World

High-integrity state boundary. Facts require evidence IDs. Fork branches cannot assert new canonical facts. Assumptions are fork-only.

### Science Genome Graph

Public-reference scientific data plane. Stable source IDs, release/checksum provenance and licensing classification are retained. Raw personal genomes and identifiable patient genetics are explicitly excluded.

### Persistence / SQLite

Private application state. Production must use encrypted volume/storage at the infrastructure layer, restricted filesystem permissions and audited backups. The current backup tooling produces integrity-checked snapshots and manifests.

## STRIDE-style risks and controls

### Spoofing

Risks:
- stolen API keys
- forged provider identity
- fake scientific identifiers
- counterfeit source URLs

Controls:
- tenant API-key validation
- source registry with fixed/configured provider endpoints
- stable database identifiers retained separately from display names
- no scientist deduplication by name alone
- source IDs and record digests in imported entities

Remaining hardening:
- enterprise SSO/OIDC
- key rotation UX and expiring service credentials
- signed provider snapshots/releases where upstream supports it

### Tampering

Risks:
- modified database files
- altered import snapshots
- modified buyer/release artifacts
- changed evidence payloads

Controls:
- source SHA256 validation in bulk importer
- per-record source digest
- SEAL/provenance receipts for core intelligence
- asset file hash manifests
- SQLite `integrity_check` on backup and restore
- backup manifest SHA256/table counts

Remaining hardening:
- signed release attestations
- immutable/append-only remote backup target
- external transparency log for release hashes

### Repudiation

Risks:
- inability to prove which source/release produced a claim
- unclear buyer provenance

Controls:
- source IDs and observed timestamps
- import release/checkpoint receipts
- World event provenance
- Sensor Mesh receipts
- buyer data-room manifest/SBOM
- DCO on release commits

Remaining hardening:
- centralized audit-log export
- signed administrative actions
- formal contributor/IP assignment register

### Information disclosure

Risks:
- tenant crossover
- secrets in source/logs
- sensitive personal genomic data entering shared graph
- sensitive location data in Atlas

Controls:
- workspace ID on core stores
- tenant-scoped APIs
- personal genome query/content guard for shared Science Graph
- no credential/seed/private-key collection
- Atlas privacy boundary and no intrusive tracking
- browser API key uses session storage rather than persistent local storage

Remaining hardening:
- automated secret scanning in CI
- DLP/classifier for uploaded private data if uploads are introduced
- enterprise privacy/DPA package
- encryption-key management policy

### Denial of service

Risks:
- expensive research fan-out
- graph rebuild abuse
- bulk import exhaustion
- provider latency/outages

Controls:
- API rate limiting
- bounded result limits
- provider timeouts
- resumable bulk imports/checkpoints
- duplicate suppression in Sensor Mesh and World bridge

Remaining hardening:
- separate worker queue for large imports
- per-plan CPU/data quotas
- circuit breakers/provider health scoring
- load-test/SLO evidence

### Elevation of privilege

Risks:
- planner/model broadening user scope
- fork/scenario becoming canonical fact
- action connectors bypassing approval

Controls:
- caller scope authoritative in planner
- read-only autonomous tool policy
- facts need evidence
- forks cannot create canonical facts
- assumptions only on forks
- action connectors remain approval-gated

Remaining hardening:
- formal permission matrix tests for every new connector
- scoped service identities for background workers

## Genomic privacy model

### Shared graph allowed

- public reference assemblies
- public genes/transcripts/proteins
- public scientific publications
- public variant assertions such as ClinVar records
- public researcher metadata
- public cross-database identifiers

### Shared graph prohibited

- identifiable patient data
- personal VCF/BCF
- BAM/CRAM linked to an individual
- personal FASTQ
- private genotype/phenotype pairs
- consent-restricted cohorts
- attempts to re-identify individuals from genomic data

A future personal-genome product must be a separate encrypted private vault with explicit consent, purpose limitation, export/deletion controls, data-retention settings and no automatic shared-world promotion.

## Scientific integrity threats

### Name collision / scientist identity errors

Do not merge people by name. Prefer stable IDs (OpenAlex, ORCID, Wikidata), coauthor network, affiliations and temporal plausibility. Ambiguous matches remain separate.

### Assembly drift

A genomic coordinate without assembly/release is incomplete. Ensembl/NCBI coordinate claims should carry assembly/version.

### Classification drift

ClinVar and other assertions change. Store observation/source dates and do not present classifications as eternal facts.

### Citation-count drift

Citation metrics are time-dependent observations. Do not treat them as immutable person/work properties.

### Source poisoning

A single provider response cannot automatically become verified fact. Imported public reference records enter World as sourced `claim` unless separately promoted under evidence policy.

## Incident priorities

P0:
- cross-tenant data exposure
- credential/secret leak
- unauthorized active action/exploitation
- personal genomic data exposed in shared graph
- canonical World tampering

P1:
- material provenance failure
- corrupt backup with no valid restore
- provider poisoning affecting many entities
- billing/auth bypass

P2:
- single-provider outage
- stale non-critical data
- UI-only degradation

## Pre-sale security evidence still required

- independent penetration test
- remediation report with no unresolved critical/high findings
- production secret rotation exercise
- backup/restore drill against production-like data
- SLO/load report
- privacy/DPA/legal review
- source/dependency license review by counsel for final asset-purchase schedule
