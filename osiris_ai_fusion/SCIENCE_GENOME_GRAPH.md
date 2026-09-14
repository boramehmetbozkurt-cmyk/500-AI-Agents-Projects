# OSIRIS Science Genome Graph

OSIRIS Science Genome Graph extends OSIRIS World with an evidence-bound model of scientists, scholarly work and public reference biology. It is deliberately not a patient-genome database and not a diagnostic engine.

## Goal

Build one traversable graph that can answer questions across:

- scientists and scholars from historical to contemporary periods
- institutions, fields, discoveries, inventions and contributions
- publications, citations, topics, identifiers and funding relationships
- organisms, genome assemblies and chromosomes
- genes, transcripts and proteins
- public variants, phenotypes and pathways
- cross-database identifiers and release provenance

Every imported record must retain source, external stable identifier, observed time, release/version where available, license/commercial classification, checksum/digest and evidence lineage.

## Core entity model

### People and science

- `scientist`
- `institution`
- `field`
- `contribution`
- `work`
- `dataset`
- `funding_award`
- `scientific_event`
- `identifier`

### Biology and genomics

- `organism`
- `assembly`
- `chromosome`
- `gene`
- `transcript`
- `exon`
- `protein`
- `protein_isoform`
- `variant`
- `phenotype`
- `pathway`
- `sequence_reference`
- `database_crossref`

## Core relationships

- scientist `authored` work
- scientist `coauthored_with` scientist
- scientist `affiliated_with` institution
- scientist `contributed_to` contribution
- scientist `discovered` entity/concept
- scientist `developed` method/technology
- work `cites` work
- work `about_topic` field/topic
- gene `located_on` chromosome
- gene `transcribes_to` transcript
- gene `encodes` protein
- transcript `translates_to` protein
- variant `variant_of` sequence/gene
- variant `associated_with` phenotype
- protein/gene `participates_in` pathway
- gene/protein `ortholog_of` gene/protein
- sequence `part_of_assembly` assembly
- entity `cross_references` external identifier
- source `source_asserts` entity or relationship

Relationships are assertions with source provenance and confidence. They are not promoted to universal fact merely because a provider returns them.

## Scientist coverage strategy

### OpenAlex backbone

OpenAlex supplies a large disambiguated author/work/institution/topic graph. It is the modern scholarly backbone. Live API calls are for bounded search and delta lookup; full-scale import uses OpenAlex snapshots/CLI and checkpointed ingestion.

Store at minimum:

- OpenAlex Author ID
- display name and known name variants when available
- ORCID when available
- works count / cited-by count as source-time metrics
- institution relationships
- topics/fields
- works and authorship relationships
- source updated date

Metrics such as citation counts are time-varying observations, not immutable properties.

### Wikidata historical layer

Wikidata complements modern bibliographic identity with historical scientists, life dates, places, occupations, fields, awards and cross-identifiers. Very large imports use Wikidata dumps; WDQS is reserved for bounded queries.

Historical claims can conflict. OSIRIS must retain competing sourced dates/occupations/contributions instead of forcing false certainty.

### Crossref and public researcher identifiers

Crossref provides publication/DOI metadata and can strengthen work-level identity. Public ORCID metadata can be used only under the applicable ORCID API/data terms and must remain source-attributed; OSIRIS does not infer private researcher attributes.

## Genome and biology coverage strategy

### NCBI Datasets / GenBank / Gene

Primary uses:

- gene identifiers and metadata
- genome assemblies and reference sequences
- taxonomic context
- transcript/protein links
- reference sequence packages

Every sequence-bearing object should carry accession, assembly, taxon, source release and checksum when available.

### Ensembl

Primary uses:

- stable Ensembl gene/transcript/protein identifiers
- genomic coordinates
- assembly names
- biotypes
- comparative genomics and homology
- variant and phenotype relationships where sourced

Coordinates without assembly/version are considered incomplete.

### UniProt

Primary uses:

- stable protein accessions
- reviewed/unreviewed status
- protein names/functions
- sequence metadata
- gene and database cross-references
- protein families and pathways where available

Attribution required for copyrightable database content under UniProt terms.

### ClinVar

Primary uses:

- public variant assertions
- associated conditions/traits
- submitters and assertion histories
- review/classification status
- citations and accessions

ClinVar records are submitted assertions. OSIRIS must not convert them into patient-specific diagnosis or treatment recommendations.

## DNA model

OSIRIS does not model "DNA" as one undifferentiated blob. The reference model is:

`organism -> assembly -> chromosome/contig -> gene -> transcript -> exon -> protein`

with parallel relationships for:

`variant -> reference location -> gene/transcript/protein consequence -> phenotype/assertion -> evidence/source`

The graph stores reference biology and public scientific assertions. Raw individual genomes remain outside the shared graph.

## Personal-genome privacy boundary

The shared Science Genome Graph must reject or segregate:

- raw personal VCF/BCF
- BAM/CRAM alignment files
- FASTQ from identifiable individuals
- patient identifiers
- case-level genotype linked to identity
- consent-restricted genomic datasets

A future Personal Genome Vault, if implemented, must be a separate encrypted tenant/private data plane with explicit consent, purpose limitation, deletion/export controls and no automatic promotion into shared OSIRIS World.

## Database architecture

### `science_entities`

Tenant-scoped normalized entity cache:

- `workspace_id`
- `canonical_key`
- `entity_type`
- `source_id`
- `external_id`
- `name`
- `payload_json`
- `payload_digest`
- `observed_at`
- `updated_at`

### `science_edges`

Evidence/provenance-aware relationships:

- `workspace_id`
- `edge_key`
- `source_key`
- `relation`
- `target_key`
- `source_id`
- `evidence_json`
- `confidence`
- `observed_at`

### `science_ingest_runs`

Checkpoint/import receipts:

- source/import query digest
- status
- entity count
- timestamps

Bulk production import should extend this with shard/cursor/checkpoint/release/checksum/error counters so jobs are resumable and auditable.

## Entity resolution

Never deduplicate scientists by name alone.

Priority signals:

1. exact stable source identifiers
2. ORCID/ROR/DOI/NCBI/Ensembl/UniProt cross-identifiers
3. authorship/coauthor graph
4. institution history
5. field/topic similarity
6. temporal plausibility
7. name variants/transliteration

Ambiguous merges remain separate with a `possible_same_as` relationship until evidence crosses a configured threshold.

## Time model

Scientists and scientific knowledge also use OSIRIS bitemporal rules:

- when did the real-world event/publication/discovery occur?
- when did OSIRIS observe/import the assertion?
- which source release was current?

A claim that became accepted in 2026 must not rewrite what a 1920 historical branch knew.

## Bulk ingestion path

1. source manifest + rights check
2. download/snapshot receipt
3. checksum and release ID
4. parse into source-native staging records
5. normalize into canonical entities
6. cross-ID resolution
7. edge generation
8. provenance validation
9. dedup
10. publish to tenant/global reference graph
11. index for search/graph traversal
12. emit ingest receipt and metrics

APIs should not be abused to mirror full public datasets when official snapshots/dumps are offered.

## Quality gates

- stable identifier retained
- source retained
- license/commercial-use classification retained
- assembly/release required for genomic coordinates
- no source-free fact promotion
- no name-only person merge
- no private/patient genome in shared graph
- no medical diagnosis generation
- deterministic digests for imported records
- tenant isolation for user-curated/imported graph state
- rollback by source release

## Current v1.3 implementation

Implemented:

- live OpenAlex scientist and work search
- bounded Wikidata candidate search for historical identity discovery
- NCBI Datasets + Ensembl human/reference gene lookup
- UniProt protein lookup
- ClinVar bounded variant search
- tenant-scoped normalized entity persistence
- provenance/source registry
- personal-genome shared-graph guard
- import-plan endpoint for snapshot-scale expansion
- regression tests for normalization, provenance and tenant isolation

Not claimed:

- all scientists have already been bulk-imported
- all genomes/proteomes/variants have already been mirrored
- every historical attribution is resolved
- private/patient genomic data is supported
- genomic data is diagnostic advice

Those are explicit data-import, identity-resolution, rights and privacy workstreams rather than hidden assumptions.