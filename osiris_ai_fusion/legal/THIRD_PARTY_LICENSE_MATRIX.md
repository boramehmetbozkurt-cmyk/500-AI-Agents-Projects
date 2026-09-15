# ORBYTHRA Third-Party License Matrix

Status date: 2026-09-15. Validate again against the exact source/dependency version used in each release.

| Source | Current terms / constraint | ORBYTHRA control |
|---|---|---|
| Root repository | MIT | Preserve root copyright + permission notice; never call upstream code exclusive IP. |
| OpenAlex metadata | CC0/public-domain model | Metadata may be reused; linked PDFs/full text retain their original licenses. Store per-work content license separately. |
| Wikidata structured data | CC0 | Preserve source identifiers/provenance even though attribution is not a CC0 requirement. |
| NCBI molecular data | NCBI states it imposes no reuse/distribution restriction; submitters/countries may still assert rights | Preserve accession/source; do not imply NCBI transfers third-party rights. |
| ClinVar | Public archive; attribution requested; not for direct diagnosis/medical decisions without genetics-professional review | Attribute ClinVar; research/informational use only in ORBYTHRA. |
| Ensembl project-generated data | Generally unrestricted; third-party constraints may apply; Ensembl code Apache 2.0 | Track release/assembly/source and isolate third-party constrained datasets. |
| UniProt copyrightable database content | CC BY 4.0 | Provide attribution; retain patent/other-rights caveat; no medical substitute claims. |
| OpenStreetMap database | ODbL | Display attribution; comply with share-alike obligations for derivative databases where applicable; do not assume tile/API service rights from data license. |
| Pleiades data/content | CC BY 3.0 | Attribute Pleiades/contributors and retain source/release metadata. |
| Three.js / Leaflet / other frontend dependencies | Version-specific open-source licenses | Self-host/pin reviewed versions for production and include notices in SBOM. |

## Distribution rule

ORBYTHRA-derived intelligence must not erase source licensing. Each ingest adapter should retain: source ID, source URL, source release/version, observed time, applicable license label, and attribution text where required.

## Full-text rule

A metadata record being open does not make linked article text/PDF open. Full-text ingestion/export must check the content-level license before commercial redistribution or model-training reuse.
