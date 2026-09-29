# ORBYTHRA Claim & Quantitative Trace Schema

Date: 2026-09-29
Purpose: define the minimum audit object for material technical outputs.

## Claim object

Required fields:

- `claim_id`
- `question_id`
- `claim_text`
- `claim_type`: observed | calculated | inferred | model-derived | unsupported
- `decision_context`
- `system_boundary`
- `release_id`
- `snapshot_id`
- `commit_id`
- `created_at`
- `source_refs[]`
- `assumption_refs[]`
- `variable_refs[]`
- `uncertainty_refs[]`
- `confidence_metadata`
- `review_state`: unreviewed | accepted | qualified | rejected | abstained

## Source/evidence object

- `source_id`
- `source_type`
- `publisher_or_authority`
- `title_or_record`
- `retrieved_at`
- `published_or_effective_at` when available
- `uri_or_repository_ref`
- `evidence_excerpt_or_locator`
- `authority_notes`
- `relevance_notes`
- `freshness_notes`
- `integrity_digest` when generated

Memory continuity must not be represented as fresh source evidence unless independently re-retrieved and bound as a current evidence object.

## Assumption object

- `assumption_id`
- `statement`
- `reason_required`
- `source_or_owner`
- `scope`
- `sensitivity_level`
- `validation_status`

## Quantitative variable object

- `variable_id`
- `symbol_or_name`
- `value`
- `unit`
- `unit_system`
- `value_type`: measured | sourced | calculated | assumed | bounded
- `source_ref`
- `uncertainty_ref`
- `validity_conditions`

## Transformation / equation object

- `step_id`
- `input_variable_refs[]`
- `equation_or_transformation`
- `output_variable_refs[]`
- `unit_check`
- `rounding_rule`
- `implementation_or_replay_ref`

## Uncertainty object

- `uncertainty_id`
- `class`: aleatory | epistemic | source-conflict | stale-data | missing-data | model | provider/runtime
- `description`
- `range_or_distribution` when justified
- `effect_on_claim`
- `mitigation`
- `abstention_or_escalation_rule`

## Decision / disposition object

- `disposition_id`
- `claim_refs[]`
- `result`
- `limitations`
- `open_gaps[]`
- `human_review_required`
- `approval_ref` when a side effect exists

## Reconstruction requirement

A material quantitative result should be replayable as:

`problem -> evidence -> assumptions -> variables/units -> equations/transformations -> uncertainty -> result -> claim/disposition`

If this path cannot be reconstructed, the output must be marked non-reproducible rather than described as engineering-grade.
