# ORBYTHRA IP Ownership Schedule

Purpose: transaction due diligence. This schedule distinguishes candidate proprietary ORBYTHRA assets from licensed/open/public inputs. It deliberately does not claim ownership that has not been independently verified.

| Asset category | Current classification | Transfer treatment |
|---|---|---|
| Root parent-repository code covered by the root MIT license | Third-party/open-source licensed material | Transfer only subject to MIT notice; not exclusive. |
| ORBYTHRA-specific application modules created on the release branch | Candidate proprietary implementation | Verify authorship/commit history and any employer/contractor assignment before representing as exclusive. |
| ORBYTHRA architecture, schemas, workflows, prompts and product documentation | Candidate proprietary expression/know-how | Include in carve-out; verify contributors and any third-party copied material. |
| Python/JS dependencies | Third-party software | Governed by each dependency license; ship SBOM/notices. |
| OpenAlex/Wikidata public metadata | Open/public data | Do not represent underlying data as proprietary; proprietary value may lie in derived models/relationships. |
| UniProt/Pleiades/OSM and other attribution/share-alike sources | Licensed data | Preserve attribution and source-specific obligations. |
| NCBI/Ensembl/ClinVar records | Public/reference data with source-specific caveats | Preserve provenance; do not imply transfer of third-party patent/copyright/privacy rights. |
| ORBYTHRA name/logo/domain | Brand asset | Transfer only after ownership and trademark/domain records are documented. |
| Customer/tenant data | Customer-controlled/contractual | Not part of IP sale unless contracts and privacy law expressly permit transfer. |

## File-level provenance rule

For final sale, every material source file should be placed into one of four buckets:

1. `ORBYTHRA-owned candidate` — original code/documentation with verified contributor assignment.
2. `Upstream/open-source` — retained under its license.
3. `Generated/derived artifact` — reproducible from owned/licensed inputs.
4. `Third-party restricted` — excluded from the transfer bundle unless separately licensed.

## Required closing evidence

- Git path provenance export.
- Contributor list and assignment/waiver status.
- Root MIT notice and all material dependency notices.
- Final SBOM.
- Data source/license register.
- Trademark/domain ownership evidence.
- Asset purchase agreement schedule naming exactly what is transferred and what is licensed.

## Important limitation

Git authorship alone is not a complete legal chain-of-title opinion. Employment, contractor, university, employer-resource or prior-agreement rights must be checked by transaction counsel where applicable.
