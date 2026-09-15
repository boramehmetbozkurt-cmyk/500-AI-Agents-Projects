# ORBYTHRA Enterprise Readiness Pack

This pack is a sales/security starting point for pilots and buyer diligence. Customer-specific legal,
security and commercial terms must be completed for the actual counterparty.

## Packaging and pricing hypothesis

Pricing below is a commercial hypothesis for validation, not a representation of current ARR.

| Package | Intended use | Indicative price |
| --- | --- | ---: |
| Evaluation | 30-day buyer-safe technical evaluation, local or isolated tenant | $0-$2,500 |
| Design Partner | 6-10 week scoped pilot, defined success metrics and weekly review | $7,500-$25,000 |
| Team SaaS | Shared ORBYTHRA research/world-intelligence workspace | $99/month baseline plus enterprise usage |
| Enterprise Platform | SSO/private deployment/data controls/SLA/support | $30,000-$120,000/year starting hypothesis |
| Strategic License | OEM/embedded/world-model or engineering-intelligence license | negotiated |
| Asset / IP transaction | Technology acquisition or exclusive strategic transaction | negotiated separately |

Do not quote the enterprise or transaction ranges as proven willingness-to-pay until customer interviews
or signed pilots exist.

## Pilot playbook

Every pilot must have one narrow business problem and a written baseline. Recommended sequence:

1. Define one decision workflow with an executive owner and one technical owner.
2. Record the current baseline: analyst hours, search steps, data sources, error/rework rate and decision latency.
3. Select no more than three ORBYTHRA surfaces: World/Temporal Globe, Science Genome, Engineering Intelligence,
   or Proprietary World Intelligence.
4. Agree on data rights before ingestion. Personal raw genomes and patient-level genetics stay outside the shared graph.
5. Pre-register success metrics before the pilot starts.
6. Run a two-week shadow phase where ORBYTHRA does not control production actions.
7. Review evidence/provenance, failure cases and user corrections weekly.
8. End with a written go/no-go and quantified delta against the baseline.

### Default pilot success metrics

- at least 30% reduction in research/triage time;
- 95%+ provenance/source attachment for decision-critical claims;
- zero unauthorized active actions;
- zero cross-tenant data leakage;
- documented human review for high-risk engineering or medical contexts;
- customer-confirmed usefulness score of at least 4/5 for the selected workflow.

## Enterprise security questionnaire baseline

### Architecture and tenancy

- Multi-tenant SaaS boundaries are enforced with tenant/workspace IDs.
- API keys and sessions are tenant-scoped.
- Provider execution is read-only by default.
- Active scanning, exploitation, credential access, transaction signing/broadcast and intrusive face tracking are excluded.

### Authentication and authorization

- Passwords use salted scrypt hashes.
- Session/API tokens are stored as SHA-256 digests rather than plaintext.
- Administrative bootstrap identity is distinct from tenant API keys.
- Rate limiting applies to investigation and high-value knowledge routes.

### Application security

- CI performs lint, tests, Python compile/import checks and browser JavaScript syntax validation.
- Security CI performs dependency audit, deterministic secret scanning and hardened container checks.
- Production Compose runs non-root, read-only, drops Linux capabilities and applies no-new-privileges.

### Data protection

- Shared Science Genome Graph is public-reference science only.
- Personal/patient VCF, BCF, BAM, CRAM and FASTQ material is outside the shared graph boundary.
- Source IDs, evidence IDs and data-rights metadata are preserved where supported.
- Customer retention/deletion periods must be set in the signed DPA/order form before enterprise production use.

### AI governance

- Facts, claims, beliefs and scenarios are separated in ORBYTHRA World.
- Engineering output is decision support, not physical certification or licensed-engineer approval.
- Medical/genomic context is informational/research context, not diagnosis or treatment.
- World Change Signal is explicitly uncalibrated unless a future validated calibration study says otherwise.

### Current external evidence gaps

The following must not be represented as complete until independently obtained:

- third-party penetration test;
- SOC 2 / ISO 27001 certification;
- long-running production SLO evidence;
- customer security review approval;
- external Engineering Intelligence validation;
- legal opinion on a specific acquisition transaction.

## Buyer / customer interview guide

Ask each prospect the same questions so evidence is comparable:

1. What decision currently consumes the most analyst/engineering time?
2. Which sources must be trusted or excluded?
3. What would make an AI-produced answer unusable even if it looks correct?
4. Is temporal history, counterfactual analysis, spatial context or provenance the biggest gap today?
5. What data is prohibited from leaving your environment?
6. What accuracy, latency and uptime threshold would justify a paid pilot?
7. Who owns budget and who can stop deployment on security/legal grounds?
8. What measurable result would justify annual procurement?

## Case-study template

For each validated customer case record:

- Customer / industry (or anonymized descriptor)
- Problem and baseline
- Data sources and rights basis
- ORBYTHRA modules used
- Human-review boundary
- Evaluation period and sample size
- Time saved
- Accuracy/quality delta
- Failure cases
- Security/privacy findings
- Customer quote approved for publication
- Commercial outcome

Never convert an internal synthetic benchmark into a customer case study.
