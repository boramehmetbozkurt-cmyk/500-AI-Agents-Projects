# ORBYTHRA EU AI Act Compliance Baseline

Status date: 2026-09-15.

## Intended-purpose baseline

ORBYTHRA is positioned as research, world-intelligence, scientific knowledge, scenario and engineering decision-support software. It is not positioned as an autonomous medical diagnosis system, conformity-assessment body, or sole safety component of regulated machinery/products.

## Article 50 transparency

EU AI Act Article 50 transparency obligations apply from 2 August 2026 for covered systems. ORBYTHRA product surfaces should therefore:

- disclose that the user is interacting with an AI-enabled system where this is not otherwise obvious;
- label AI-generated analysis in the UI/API metadata;
- preserve provenance/evidence metadata for factual claims;
- avoid presenting simulated/scenario content as verified fact.

Recommended UI label: `AI-generated analysis — verify critical decisions with qualified professionals.`

## High-risk classification gate

Before any deployment in a regulated product or safety function, perform a use-case classification review. Under Article 6, high-risk treatment can apply where the AI is intended as a safety component/product covered by Annex I harmonisation legislation and the relevant product requires third-party conformity assessment. 2026 EU amendments/guidance also emphasise that non-safety assistance/performance optimisation does not automatically become a safety component, while failure that endangers health/safety can.

## Engineering Intelligence controls

- Output is advisory/decision-support, not certification.
- Unknowns and assumptions must be explicit.
- FMEA/verification recommendations do not replace physical testing.
- Safety-critical use requires authorised engineering review and applicable conformity procedures.
- Keep versioned prompts/models and audit records for material enterprise decisions.

## Medical/science controls

- Public-reference genetics only.
- No patient-specific diagnosis/treatment recommendation positioning.
- Source assertions remain source assertions; ORBYTHRA must not silently promote them to clinical truth.

## Reassessment triggers

Run a new AI Act classification assessment when ORBYTHRA is used for employment, education admissions, essential services/credit, law enforcement, migration/border control, justice/democratic processes, biometrics, medical devices, industrial safety components, or any other Annex III/Annex I context.
