# ORBYTHRA External Validation Report Template

> This template is intentionally blank. It must be completed and attributable to the independent evaluator. ORBYTHRA maintainers must not self-fill independent conclusions.

## Evaluator

- Organisation:
- Lead evaluator:
- Report date:
- Engagement reference:
- Independence/conflict statement:

## Tested build

- ORBYTHRA version:
- Release SHA:
- Deployment ID:
- Environment:
- Underlying model/provider:
- Model/version/date:
- Dataset fingerprint:
- Protocol fingerprint:
- Total valid cases:
- Excluded/inconclusive cases:

## Protocol deviations

Describe every deviation from `benchmarks/external_validation_protocol_v1.json`. If none, state `NONE`.

## Primary metrics

| Metric | Baseline numerator/denominator | Baseline rate | ORBYTHRA numerator/denominator | ORBYTHRA rate | Confidence interval | Threshold | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| Unsupported-claim rate | | | | | | lower is better | |
| Contradiction-detection recall | | | | | | >= 0.90 | |
| Correct-abstention rate | | | | | | >= 0.90 | |
| Evidence-traceability rate | | | | | | >= 0.95 | |
| Critical false-negative rate | | | | | | <= 0.05 | |

## Secondary metrics

Report false-positive rate, reviewer time, policy-block accuracy, intent/effect binding accuracy, p50/p95 latency overhead and cost overhead per case.

## Security assessment linkage

- Penetration-test report reference:
- Crypto-review report reference:
- Critical findings open:
- High findings open:
- Remediation/retest status:

## Findings

List supported findings with evidence references. Separate deterministic ORBYTHRA controls from stochastic model/agent behaviour.

## Limitations

Describe sampling, domain, model/provider, evaluator, dataset and environment limitations. Do not generalise results beyond the tested population without supporting evidence.

## Independent conclusion

To be written by the independent evaluator.

## Attestation

- Evaluator name/signature or verifiable approval:
- Date:
- Report artifact hash/signature:
