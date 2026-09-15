# ORBYTHRA Clean IP Carve-Out Plan

Goal: move from a product developed inside a public MIT-licensed fork to a transaction-ready ORBYTHRA repository without misrepresenting upstream rights.

## Important legal reality

The current root MIT license permits reuse, modification, distribution, sublicensing and sale subject to preservation of the notice. A clean repository can improve chain-of-title clarity, but it cannot revoke valid third-party rights already granted in previously published MIT-covered material.

## Migration steps

1. Freeze a release commit and generate the existing ORBYTHRA carve-out ZIP/hash/provenance artifacts.
2. Build a file-level provenance list: original ORBYTHRA / modified upstream / third-party / generated / excluded.
3. Create a new dedicated repository owned by the final legal entity. The currently connected GitHub toolset cannot create repositories, so this is an external account action.
4. Import only the ORBYTHRA application subtree and required build/deployment files.
5. Preserve upstream MIT and third-party notices for any retained licensed code.
6. Add a new top-level license for genuinely proprietary future ORBYTHRA code only after counsel confirms which files can be treated that way.
7. Require contributor IP-assignment/DCO policy for new contributors.
8. Keep third-party datasets out of source-control; ingest under a source registry and license metadata.
9. Tag the clean baseline and generate SBOM, file hashes and provenance evidence.
10. Buyer counsel signs off the final IP schedule.

## Do not do

- Do not delete upstream copyright notices from copied/substantial upstream material.
- Do not claim that creating a new private repo makes previously MIT-released code exclusive.
- Do not mix customer data or licensed bulk datasets into the IP source bundle.

## Exit criterion

A buyer should be able to answer, for every material asset: who created it, who owns it, what license applies, whether it can be transferred, and what obligations survive the transaction.
