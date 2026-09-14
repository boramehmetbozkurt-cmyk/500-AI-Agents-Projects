# OSIRIS Asset Sale Readiness

This document is a technical/commercial due-diligence register. It is not a valuation certificate and does not claim that OSIRIS is worth any specific amount.

## Sale thesis

OSIRIS is positioned as a strategic technology/IP asset rather than a generic pre-revenue SaaS listing:

- evidence-first research/orchestration engine
- multi-tenant Public SaaS
- provider federation
- OSIRIS World verified living-world model
- bitemporal Time Machine
- World Fork counterfactual engine
- World Sensor Mesh
- Temporal Reality Atlas
- Temporal Globe
- Science Genome Graph
- specialist Hunter modules
- SEAL authorization/provenance receipts

The commercial goal is to make the asset defensible to a strategic buyer through product maturity, demonstrable data integrations, rights clarity, security evidence, deployment evidence and customer/pilot proof.

## Critical IP fact

The parent repository is a fork and its root license is MIT with copyright attribution to the upstream author. MIT permits use, modification, sublicensing and sale, provided the copyright/license notice is preserved.

This means:

- OSIRIS can contain and distribute MIT-licensed upstream material.
- A buyer must receive the applicable upstream MIT notice.
- Upstream MIT code is not exclusive proprietary IP.
- Value must be attributed to OSIRIS-specific code, architecture, integrations, brand, data pipelines, deployment, customer relationships and any separately owned IP.

### Required carve-out before a serious asset sale

Create a standalone OSIRIS repository/data room containing only:

1. OSIRIS-owned source files and assets.
2. Clearly inventoried third-party/open-source components.
3. Required notices/licenses.
4. Git history or provenance report showing origin of major modules.
5. A signed contributor/IP assignment record for every external contributor, if any.

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
- [ ] production domain with uptime history
- [ ] buyer-safe public demo tenant
- [ ] repeatable one-command demo bootstrap

### Engineering

- [x] CI lint/test/compile/import validation
- [x] dependency audit workflow
- [x] hardened Docker build
- [x] non-root runtime check
- [x] DCO checks
- [x] regression tests for tenant isolation/world/forks/atlas
- [ ] SBOM artifact on every release
- [ ] signed release artifacts/provenance attestations
- [ ] restore-tested backup runbook
- [ ] load/latency benchmark report
- [ ] SLO/error-budget dashboard

### Security

- [x] read-only provider posture
- [x] no autonomous active scanning/exploitation routes
- [x] no seed/private-key collection
- [x] no intrusive face-tracking functionality
- [x] tenant scoping in core stores
- [x] API rate limiting
- [x] personal-genome shared-graph rejection policy
- [ ] third-party penetration test
- [ ] threat model / STRIDE register
- [ ] secrets rotation runbook
- [ ] incident response tabletop evidence
- [ ] privacy/DPA templates for enterprise buyers

### IP and licensing

- [x] upstream MIT license identified
- [x] science/data source commercial classifications documented
- [x] provenance/source IDs retained in science graph
- [ ] standalone OSIRIS carve-out repository
- [ ] file-by-file origin inventory
- [ ] automated dependency/license SBOM
- [ ] trademark/domain ownership package
- [ ] contributor assignment register
- [ ] counsel review of final asset-purchase IP schedule

### Data moat

- [x] source-independent world/reality schema
- [x] historical/present/future temporal semantics
- [x] physical/digital/metaverse coordinate spaces
- [x] Science Genome Graph schema
- [x] source-release/provenance strategy
- [ ] checkpointed OpenAlex snapshot importer
- [ ] Wikidata dump historical scientist importer
- [ ] NCBI/Ensembl/UniProt release importers
- [ ] cross-source scientist identity resolution benchmark
- [ ] cross-database gene/protein/variant resolution benchmark
- [ ] proprietary derived signals that do not violate source licenses

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
3. The live demo visibly combines World + Temporal Globe + Science Genome Graph.
4. At least one large-scale source importer is operational and resumable.
5. A unique derived-data/decision layer exists beyond simply proxying public APIs.
6. Enterprise design partners or paid pilots validate willingness to pay.
7. Benchmarks show measurable advantage over a conventional search/RAG stack.
8. Data licensing and attribution obligations are automated, not manual.
9. A buyer can reproduce the product from a clean checkout with documented secrets/config.
10. Security/privacy review has no unresolved critical findings.

## Marketplace versus strategic sale

A generic marketplace typically values pre-revenue software primarily as a small code/domain asset. The path to a seven-figure outcome is therefore not "add more files"; it is to create strategic scarcity through integrated technology, clean IP, operational proof, proprietary derived intelligence and customer validation.

OSIRIS should be sold, if sold, as a coherent platform/IP/data-infrastructure acquisition rather than a template SaaS listing.
