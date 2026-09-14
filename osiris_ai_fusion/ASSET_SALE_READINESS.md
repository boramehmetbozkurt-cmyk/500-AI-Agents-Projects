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
- specialist Hunter modules
- SEAL authorization/provenance receipts

Engineering Intelligence adds a first-principles, multi-scale technical decision surface with explicit alternatives, FMEA, unknown/assumption separation and quantitative verification planning. Model output is not represented as a physical test, certification or licensed-engineering approval.

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
- [x] Temporal Globe UI
- [x] Science Genome Graph schema and live adapters
- [x] Science Genome Explorer UI
- [x] Science Genome -> ORBYTHRA World evidence bridge
- [x] Engineering Intelligence v2.0 API + Engineering Lab UI
- [x] canonical engineering prompt retained and versioned
- [x] engineering structural quality gate + bounded repair pass
- [x] hardened production Compose baseline
- [ ] production domain with uptime history
- [ ] buyer-safe public demo tenant
- [ ] repeatable no-secret demo bootstrap package

### Engineering

- [x] CI lint/test/compile/import validation
- [x] dependency audit workflow
- [x] hardened Docker build
- [x] non-root runtime check
- [x] DCO checks
- [x] regression tests for tenant isolation/world/forks/atlas/science/engineering
- [x] SBOM artifact on every asset-readiness run
- [x] buyer file-hash/data-rights manifest
- [x] automated ORBYTHRA carve-out bundle
- [x] integrity-checked backup + restore tooling and regression tests
- [x] reproducible synthetic core benchmark in buyer data-room artifact
- [ ] signed release artifacts/provenance attestations
- [ ] production load/latency benchmark and SLO/error-budget dashboard
- [ ] external validation benchmark for Engineering Intelligence against real engineering cases

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
- [ ] third-party penetration test
- [ ] formal secrets rotation exercise evidence
- [ ] incident response tabletop evidence
- [ ] privacy/DPA templates for enterprise buyers

### IP and licensing

- [x] upstream MIT license identified
- [x] science/data source commercial classifications documented
- [x] provenance/source IDs retained in science graph
- [x] automated ORBYTHRA carve-out bundle
- [x] file hash inventory + legacy source-path Git provenance artifact
- [x] automated dependency/license SBOM
- [x] third-party notices document
- [ ] standalone ORBYTHRA repository if required by transaction structure
- [ ] trademark/domain ownership package
- [ ] contributor assignment register
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
- [ ] cross-source scientist identity resolution benchmark
- [ ] cross-database gene/protein/variant resolution benchmark
- [ ] large production-scale source snapshots actually ingested and measured
- [ ] proprietary derived signals that do not violate source licenses
- [ ] proprietary engineering benchmark/case corpus with rights clearance

### Commercial proof

- [ ] 2-5 design partners/pilots
- [ ] documented buyer/use-case interviews
- [ ] ARR/MRR or signed paid pilots
- [ ] retention/usage metrics
- [ ] case study showing time/cost advantage
- [ ] enterprise pricing and security questionnaire pack

## $1M+ strategic-asset readiness gates

A seven-figure asking price becomes materially easier to defend when several of these are simultaneously true:

1. Standalone IP provenance is clean and buyer-auditable.
2. Production deployment has uptime/security evidence.
3. The live demo visibly combines World + Temporal Globe + Science Genome Graph + Engineering Intelligence.
4. At least one large-scale source importer is operational, resumable and populated with a material real dataset.
5. A unique derived-data/decision layer exists beyond simply proxying public APIs.
6. Enterprise design partners or paid pilots validate willingness to pay.
7. Benchmarks show measurable advantage over a conventional search/RAG stack and, for engineering use, over an unstructured general-model baseline.
8. Data licensing and attribution obligations are automated, not manual.
9. A buyer can reproduce the product from a clean checkout with documented secrets/config.
10. Security/privacy review has no unresolved critical findings.

The repository covers a substantial part of gates 3, 4 (software path), 8 and 9. Gates 1, 2, 5, 6, 7 and 10 still require external/production evidence rather than more source files alone.

## Marketplace versus strategic sale

A generic marketplace typically values pre-revenue software primarily as a small code/domain asset. The path to a seven-figure outcome is therefore not "add more files"; it is to create strategic scarcity through integrated technology, clean IP, operational proof, proprietary derived intelligence and customer validation.

ORBYTHRA should be sold, if sold, as a coherent platform/IP/data/decision-infrastructure acquisition rather than a template SaaS listing.
