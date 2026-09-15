# ORBYTHRA Legal Due-Diligence Register

Status: buyer-ready technical draft, external counsel review still required.

## Executive conclusion

No single legal rule identified in this review makes the ORBYTHRA product concept inherently unlawful or unsellable. The principal transaction risk is IP/provenance clarity because the product is currently developed inside a fork whose root license is MIT. The principal operating risks are special-category personal data, source-license compliance, AI transparency, and avoiding regulated medical/safety claims.

## Risk register

| Area | Status | Required control |
|---|---|---|
| Root repository / upstream code | AMBER-HIGH | Preserve MIT notice; do not market upstream material as exclusive IP; complete clean carve-out and contributor review. |
| ORBYTHRA-specific code | AMBER | Establish file-level authorship/provenance and assignment chain before sale. |
| Scientific/open data | AMBER | Enforce source-specific licensing and attribution; separate metadata rights from linked full-text rights. |
| Personal/genetic/health data | RED if enabled; GREEN if excluded | Shared graph must reject patient/raw personal genome data. Any future processing needs separate legal basis, DPIA/impact review and security program. |
| Medical use | AMBER-HIGH | Informational/research only unless separately regulated and validated. |
| Engineering safety use | AMBER-HIGH | Decision support only; no claim that AI output is certification or substitutes for licensed engineering/conformity assessment. |
| EU AI Act transparency | AMBER | Clearly disclose AI interaction/output; preserve provenance/logging and intended-purpose documentation. |
| Trademark ORBYTHRA | AMBER | Preliminary exact-name web/official-domain search found no exact hit; this is not legal clearance. File after professional similarity/class search. |
| Customer/privacy contracts | AMBER | Finalize operator legal entity, governing law, privacy notice, Terms and DPA before public paid launch. |

## Current legal boundaries

1. Keep Science Genome Graph limited to public-reference scientific/genomic information.
2. Reject VCF, BCF, BAM, CRAM, FASTQ and equivalent personal/patient genomic uploads from shared graphs.
3. Do not present ClinVar/UniProt/public genetics as patient-specific diagnosis or treatment.
4. Do not use ORBYTHRA Engineering Intelligence as the sole safety component or certification authority for regulated products.
5. Preserve source identifiers, release/version metadata, license/attribution metadata and evidence receipts.
6. Keep third-party content separable from ORBYTHRA-derived intelligence so the proprietary layer is identifiable.
7. Before acquisition, produce an attorney-reviewed IP schedule and contributor assignment register.

## Key authorities reviewed

- Turkey Law No. 6698 / KVKK Article 6: genetic, biometric and health data are special categories; processing is restricted and subject to listed legal conditions and safeguards.
- GDPR Article 9: genetic, biometric-for-identification and health data are special categories, prohibited by default unless an exception applies.
- EU AI Act Article 50 transparency obligations apply from 2 August 2026 for covered systems.
- EU AI Act Article 6 high-risk classification can apply where AI is a safety component/product under listed harmonisation law and third-party conformity assessment is required.
- Root repository `LICENSE`: MIT permits use/modification/distribution/sublicensing/sale subject to preserving the copyright and permission notice.

## Transaction recommendation

Do not sell the whole parent fork as "exclusive ORBYTHRA IP." Sell a clean ORBYTHRA carve-out with: source-file provenance, open-source notices, dependency SBOM, data-rights matrix, brand/trademark assets, deployment materials, customer/pilot contracts, and an IP assignment schedule.
