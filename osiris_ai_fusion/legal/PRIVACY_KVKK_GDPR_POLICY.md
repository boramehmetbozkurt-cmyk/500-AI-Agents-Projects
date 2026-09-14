# ORBYTHRA Privacy / KVKK / GDPR Policy

Status: product policy baseline. A public privacy notice must be finalized with the operating legal entity, hosting locations, subprocessors and retention periods.

## Data minimisation baseline

ORBYTHRA should process only data necessary for the stated product purpose. Public scientific/reference records are kept separate from customer personal data. Tenant data must remain tenant-scoped.

## Prohibited shared-graph inputs

The shared Science Genome Graph must reject patient/person-specific raw genomic or clinical files, including at minimum: VCF, VCF.GZ, BCF, BAM, CRAM, FASTQ and FASTQ.GZ, and equivalent uploads containing identifiable personal genetic/health data.

## Special-category rule

Under KVKK Article 6, genetic, biometric and health data are special-category personal data. Under GDPR Article 9, genetic data, biometric data used for unique identification and health data are special categories whose processing is prohibited by default unless a listed exception applies.

Accordingly, ORBYTHRA v1.3 does not rely on a generic Terms-of-Use acceptance as a legal basis to ingest personal genomic/health records into the shared graph.

## If personal/special-category processing is added later

Do not enable it until all of the following exist:

- documented controller/processor roles and lawful basis;
- explicit-purpose data map and retention schedule;
- required KVKK/GDPR notices and, where applicable, valid explicit consent or another lawful exception;
- DPIA/impact assessment for high-risk processing where required;
- encryption, access control, tenant isolation, audit logs, deletion/export workflows and breach procedures;
- subprocessor and international-transfer assessment;
- separate medical/regulatory review if outputs affect health decisions.

## User rights operations

Before public paid launch, implement an operational process for access, correction, deletion where applicable, objection/restriction where applicable, portability where applicable, and complaint/contact handling. The public notice must identify the actual legal entity/controller and contact channel.

## Logging

Security and product logs should avoid raw prompts/data where not necessary. Never log secrets, raw personal genome files, or patient identifiers into shared analytics.
