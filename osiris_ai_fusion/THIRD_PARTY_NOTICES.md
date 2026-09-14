# OSIRIS Third-Party Notices

This notice is a buyer/deployment aid and is not a legal opinion. Final distribution/acquisition packages should be reviewed against the exact dependency and data versions used in that release.

## Upstream repository license

OSIRIS currently lives inside a repository whose root license is MIT and carries upstream copyright notice:

`Copyright (c) 2025 ashishpatel26`

The MIT copyright and permission notice must be preserved in copies/substantial portions of applicable upstream Software. MIT permits use, modification, distribution, sublicensing and sale subject to that notice.

The OSIRIS carve-out process therefore includes a copy of the root license and does not describe upstream MIT material as exclusive proprietary IP.

## Python/runtime dependencies

Runtime/test dependency licenses are not hard-coded here because versions can change. The `OSIRIS Asset Readiness` workflow generates a resolved SPDX-style package inventory and package/license metadata for each candidate commit.

Primary direct runtime dependencies currently include:

- FastAPI
- Uvicorn
- HTTPX
- Pydantic
- LangGraph
- cryptography
- cbor2
- python-dotenv

Transitive dependencies must also be reviewed from the generated SBOM.

## Front-end libraries

### Three.js

Temporal Globe uses Three.js through an external pinned CDN module reference. Preserve/apply the library's license requirements for the exact distributed version. For production supply-chain hardening, self-host and integrity-pin reviewed frontend dependencies instead of depending indefinitely on a mutable external CDN path.

### Leaflet

The Command Center uses Leaflet through a pinned CDN reference. Preserve/apply the license requirements for the exact distributed version. A production acquisition can self-host the reviewed artifact.

## External data sources

### OpenAlex

OSIRIS uses OpenAlex for scholarly metadata. OpenAlex metadata is made available under CC0/public-domain terms. Full-text content linked or distributed through OpenAlex can have separate licenses; OSIRIS does not treat metadata licensing as a grant of article/PDF rights.

### Wikidata

Wikidata structured data is CC0. Large-scale ingestion should use official dumps rather than treating the public query service as a bulk-mirroring endpoint.

### NCBI

NCBI states that it places no restrictions on the use/distribution of molecular database data, while noting that submitters/countries may assert patent, copyright or other rights in portions of submitted material. Resource-specific notices must be respected.

### Ensembl

Ensembl project-generated data is generally available without restriction, but third-party datasets can carry separate constraints. Preserve stable IDs, assembly/release and source information.

### UniProt

Copyrightable UniProt database portions are provided under CC BY 4.0. Attribution is required and other patent/rights considerations can apply.

### ClinVar

ClinVar is a public archive of variant/clinical assertions. Source attribution should be preserved. ClinVar assertions are not represented by OSIRIS as patient-specific diagnosis or treatment advice.

### OpenStreetMap / historical / geospatial providers

OSIRIS Atlas source records retain source/license metadata because geospatial datasets have provider-specific attribution/share-alike/commercial requirements. Do not bulk distribute derived map data without checking the exact source license.

## User/customer data

Third-party notices do not grant rights to customer data. Tenant/customer data remains governed by customer contracts, privacy terms and applicable law. Personal raw-genome/patient data is not permitted in the shared Science Genome Graph.
