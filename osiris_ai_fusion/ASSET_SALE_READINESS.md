# ORBYTHRA Asset Sale Readiness

This document is a technical/commercial due-diligence register. It is not a valuation certificate and does not claim that ORBYTHRA is worth any specific amount.

## Sale thesis

ORBYTHRA is positioned as a strategic technology/IP asset rather than a generic pre-revenue SaaS listing:

- evidence-first research/orchestration engine
- multi-tenant Public SaaS
- provider federation
- ORBYTHRA World verified living-world model
- bitemporal Time Machine
- World Fork counterfactual engine
- World Sensor Mesh
- Temporal Reality Atlas
- Temporal Globe
- Science Genome Graph
- historical scientist / scholarly-data ingestion pipelines
- Science Genome -> ORBYTHRA World bridge
- ORBYTHRA Engineering Intelligence
- ORBYTHRA Proprietary World Intelligence Engine
- specialist Hunter modules
- SEAL authorization/provenance receipts

Engineering Intelligence adds a first-principles, multi-scale technical decision surface with explicit alternatives, FMEA, unknown/assumption separation and quantitative verification planning. Model output is not represented as a physical test, certification or licensed-engineering approval.

The Proprietary World Intelligence Engine derives transparent Discovery, Emergence, Decision Confidence and World Change signals from ORBYTHRA World truth state, evidence coverage, freshness, relation density, dispute pressure and World Pulse. World Change Signal is intentionally labeled an uncalibrated decision-support heuristic rather than a statistical probability forecast.

The commercial goal is to make the asset defensible to a strategic buyer through product maturity, demonstrable data integrations, rights clarity, security evidence, deployment evidence and customer/pilot proof.

## Critical IP fact

The parent repository is a fork and its root license is MIT with copyright attribution to the upstream author. MIT permits use, modification, sublicensing and sale, provided the copyright/license notice is preserved.

This means:

- ORBYTHRA can contain and distribute MIT-licensed upstream material.
- A buyer must receive the applicable upstream MIT notice.
- Upstream MIT code is not exclusive proprietary IP.
- Value must be attributed to ORBYTHRA-specific code, architecture, integrations, brand, data pipelines, decision workflows, deployment, customer relationships and any separately owned IP.

### Carve-out status

The Asset Readiness workflow produces an ORBYTHRA-branded carve-out ZIP, file hashes, Git path provenance, dependency SBOM, data-rights registry and upstream MIT notice. The repository path `osiris_ai_fusion` may remain as a legacy implementation path for compatibility; it is not the acquisition-facing product name. This materially improves technical due diligence, but it is not a legal certification of exclusive ownership.

Before a final asset sale, a buyer/counsel should still confirm:

1. The final source/IP schedule.
2. Required third-party/open-source notices.
3. Git history/provenance for material modules.
4. Contributor/IP assignment records for any external contributor.
5. Trademark/domain ownership.

Do not market the upstream open-source repository itself as exclusive property.

## Data rights register

### OpenAlex

- scholarly metadata: CC0/public-domain model
- use API for bounded live access
- use snapshot/CLI for bulk mirror/import
- full-text PDFs retain their original licenses; do not assume OpenAlex metadata licensing grants rights to article content

### Wikidata

- structured data: CC0
- WDQS for bounded queries
- dump for large-scale ingestion

### NCBI molecular data

- NCBI places no restrictions on use/distribution of molecular database data
- some submitters/countries may assert patent/copyright/other rights
- preserve NCBI attribution and source identifiers
- isolate databases/resources that have special copyright terms

### Ensembl

- project-generated data generally unrestricted
- third-party constraints can exist
- retain stable IDs, assemblies/releases and source provenance

### UniProt

- copyrightable database content: CC BY 4.0
- attribution required
- patent/other rights may still apply to portions of records

### ClinVar

- public variant assertion archive
- attribution requested
- classifications are assertions and must not be marketed as diagnostic determinations

## Buyer data-room checklist

### Product

- [x] documented product architecture
- [x] authenticated multi-tenant SaaS boundary
- [x] API keys and quotas
- [x] billing contract integration
- [x] World/Atlas/Sensor APIs
- [x] Proprietary World Intelligence API and transparent score methodology
- [x] Temporal Globe UI
- [x] Science Genome Graph schema and live adapters
- [x] Science Genome Explorer UI
- [x] Science Genome -> ORBYTHRA World evidence bridge
- [x] Engineering Intelligence v2.0 API + Engineering Lab UI
- [x] canonical engineering prompt retained and versioned
- [x] engineering structural quality gate + bounded repair pass
- [x] hardened production Compose baseline
- [x] reproducible buyer-safe local demo seed/package without provider secrets
- [ ] hosted buyer-safe public demo tenant
- [ ] production domain with uptime history

### Engineering

- [x] CI lint/test/compile/import validation
- [x] dependency audit workflow
- [x] hardened Docker build
- [x] non-root runtime check
- [x] DCO checks
- [x] regression tests for tenant isolation/world/forks/atlas/science/engineering/intelligence
- [x] SBOM artifact on every asset-readiness run
- [x] buyer file-hash/data-rights manifest
- [x] automated ORBYTHRA carve-out bundle
- [x] integrity-checked backup + restore tooling and regression tests
- [x] reproducible synthetic core benchmark in buyer data-room artifact
- [x] deterministic science identity/cross-database resolution regression benchmark
- [x] rights-cleared synthetic Engineering Intelligence benchmark corpus and evaluator
- [x] offline deep-research pipeline ablation benchmark (deduplication and per-question
      attribution against the same pipeline with those features off). It is explicitly not
      independent, not a third-party comparison, and does not model recall gains from
      decomposition; gate 7 stays partially satisfied until an external baseline exists.
- [x] in-process ASGI load/latency regression baseline
- [x] runtime SLO/latency metrics and admin SLO report surface
- [x] release provenance attestation tooling with SHA-256 and optional Ed25519 signing
- [ ] signed release attestation produced with an owner-controlled release signing key
- [ ] production load/latency history and externally observed SLO/error-budget evidence
- [ ] independent engineering validation against real physical cases

### Security

- [x] read-only provider posture
- [x] no autonomous active scanning/exploitation routes
- [x] no seed/private-key collection
- [x] no intrusive face-tracking functionality
- [x] tenant scoping in core stores
- [x] API rate limiting
- [x] personal-genome shared-graph rejection policy
- [x] threat model / STRIDE-style register
- [x] deterministic credential leakage scan in security CI
- [x] read-only/no-new-privileges/cap-drop Compose validation
- [x] engineering mode forbids fabricated measurements/certifications and marks high-risk approval boundary
- [x] privacy/DPA technical/legal templates for enterprise diligence
- [x] secrets-rotation and incident-tabletop evidence runbooks
- [x] independent pentest scope prepared
- [ ] third-party penetration test report and remediation evidence
- [ ] formal secrets rotation exercise evidence from a real environment
- [ ] incident response tabletop evidence from a real exercise

### IP and licensing

- [x] upstream MIT license identified
- [x] science/data source commercial classifications documented
- [x] provenance/source IDs retained in science graph
- [x] automated ORBYTHRA carve-out bundle
- [x] file hash inventory + legacy source-path Git provenance artifact
- [x] automated dependency/license SBOM
- [x] third-party notices document
- [x] clean-IP carve-out plan and legal due-diligence pack
- [ ] standalone ORBYTHRA repository if required by transaction structure
- [ ] completed trademark/domain ownership filings/package
- [ ] contributor assignment register signed by every applicable contributor
- [ ] counsel review of final asset-purchase IP schedule

### Data / decision moat

- [x] source-independent world/reality schema
- [x] historical/present/future temporal semantics in Temporal Reality Atlas
- [x] physical/digital/metaverse coordinate spaces
- [x] Science Genome Graph schema
- [x] source-release/provenance strategy
- [x] checkpointed OpenAlex snapshot/JSONL importer path
- [x] Wikidata dump historical scientist taxonomy/extractor
- [x] normalized NCBI/Ensembl/UniProt release JSONL import paths
- [x] Science Graph relationship derivation
- [x] digest-deduplicated Science -> World bridge
- [x] multi-layer engineering decision protocol integrated as a product capability
- [x] deterministic cross-source scientist identity resolver + curated benchmark
- [x] deterministic gene/protein/variant cross-database resolver + curated benchmark
- [x] proprietary ORBYTHRA-derived Discovery/Emergence/Decision Confidence/World Change signals
- [x] original synthetic engineering benchmark/case corpus with explicit rights statement
- [ ] large production-scale source snapshots actually ingested and measured
- [ ] externally calibrated/validated proprietary signals with documented predictive or operational lift

### Commercial proof

- [x] enterprise pricing hypothesis, pilot playbook, security questionnaire and case-study template
- [ ] 2-5 design partners/pilots
- [ ] documented buyer/use-case interviews from real counterparties
- [ ] ARR/MRR or signed paid pilots
- [ ] retention/usage metrics from real users
- [ ] validated customer case study showing time/cost advantage
- [ ] validated enterprise willingness-to-pay / procurement evidence

## $1M+ strategic-asset readiness gates

A seven-figure asking price becomes materially easier to defend when several of these are simultaneously true:

1. Standalone IP provenance is clean and buyer-auditable.
2. Production deployment has uptime/security evidence.
3. The live demo visibly combines World + Temporal Globe + Science Genome Graph + Engineering Intelligence + Proprietary World Intelligence.
4. At least one large-scale source importer is operational, resumable and populated with a material real dataset.
5. A unique derived-data/decision layer exists beyond simply proxying public APIs.
6. Enterprise design partners or paid pilots validate willingness to pay.
7. Benchmarks show measurable advantage over a conventional search/RAG stack and, for engineering use, over an unstructured general-model baseline.
8. Data licensing and attribution obligations are automated, not manual.
9. A buyer can reproduce the product from a clean checkout with documented secrets/config.
10. Security/privacy review has no unresolved critical findings.

The repository now materially covers gates 3, 5, 8 and 9 and contains software paths/internal regression evidence toward gates 4 and 7. Gates 1, 2, 6 and 10 still require transaction, production, customer or independent external evidence. Gate 7 remains only partially satisfied until benchmarks demonstrate advantage against external baselines on independently reviewed cases.

## Marketplace versus strategic sale

A generic marketplace typically values pre-revenue software primarily as a small code/domain asset. The path to a seven-figure outcome is therefore not "add more files"; it is to create strategic scarcity through integrated technology, clean IP, operational proof, proprietary derived intelligence and customer validation.

ORBYTHRA should be sold, if sold, as a coherent platform/IP/data/decision-infrastructure acquisition rather than a template SaaS listing.
