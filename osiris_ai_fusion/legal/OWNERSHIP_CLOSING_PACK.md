# ORBYTHRA Ownership Closing Pack

This pack is a due-diligence evidence structure, not legal advice and not a substitute for counsel or official registry records.

## Trademark evidence register

Create one row per filing/registration:

| Field | Required evidence |
| --- | --- |
| Mark | Exact word/device mark, e.g. ORBYTHRA |
| Owner | Legal owner name and entity/individual identifier |
| Jurisdiction | TÜRKPATENT, EUIPO, USPTO, WIPO/Madrid, other |
| Nice classes | Classes actually filed; do not infer from a plan |
| Application number | Official filing/application identifier |
| Filing date | Official registry date |
| Status | Filed / published / opposed / registered / refused / abandoned |
| Registry URL/document | Reviewable official evidence |
| Counsel/search memo | Optional but recommended clearance record |

Rules:

- A web search is not a trademark clearance opinion.
- A planned filing is not a filed application.
- Do not use ® before registration in the relevant jurisdiction.
- Keep acquisition-facing branding consistent with the actual owner of the mark.

## Domain ownership register

Create one row per acquisition-facing domain:

| Field | Required evidence |
| --- | --- |
| Domain | Exact domain name |
| Registrant/legal owner | Account/legal owner where available |
| Registrar | Registrar name |
| Registration/acquisition date | Registrar or registry evidence |
| Renewal/expiry | Current renewal/expiry evidence |
| DNS control | Dated DNS TXT challenge or equivalent control test |
| Account evidence | Redacted registrar screenshot/export or registry record |
| Transfer lock/status | Record before a transaction |

WHOIS privacy may hide registrant details. In that case retain registrar-account evidence and a dated DNS control challenge. Never infer ownership from the website merely resolving.

## Contributor/IP assignment register

For every person or entity that materially contributed ORBYTHRA-specific code, architecture, design, documentation, datasets or proprietary benchmark material, record:

- legal name;
- contribution scope and Git identity where applicable;
- employment/contract relationship at contribution time;
- applicable agreement;
- whether IP assignment/work-made-for-hire language applies;
- assignment document identifier and signature date where required;
- exceptions, retained rights or third-party material introduced;
- reviewer and review date.

A Git commit proves contribution history; it does not by itself prove exclusive chain of title.

## Third-party/open-source schedule

The final transaction schedule should reconcile:

1. upstream MIT material and preserved notice;
2. Python/JavaScript dependencies and SBOM;
3. public data-source licences/attribution;
4. externally supplied datasets or benchmarks;
5. model/provider contractual restrictions;
6. fonts/media/UI assets, if any;
7. customer/pilot data and confidentiality obligations.

Upstream MIT material may be sold/distributed subject to its licence, but must not be described as exclusive ORBYTHRA IP.

## Counsel closing checklist

Counsel should review and date at least:

- final asset list and excluded assets;
- ORBYTHRA-specific source/IP schedule;
- upstream/open-source schedule and notices;
- contributor assignments and exceptions;
- trademark/domain evidence;
- material data licences;
- privacy/DPA terms and actual subprocessors;
- material customer/pilot contracts;
- warranties/indemnities proposed in the asset purchase agreement;
- governing law, venue, liability cap and unresolved placeholders in customer-facing terms.

## Definition of done

The ownership/IP gate is complete only when the evidence register is populated with real records and the final transaction IP schedule has been reviewed by qualified counsel. This template alone never closes the gate.
