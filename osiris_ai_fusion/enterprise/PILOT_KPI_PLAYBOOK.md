# ORBYTHRA Pilot KPI Playbook

The pilot KPI ledger exists to turn product claims into measured customer evidence. A pilot is not considered successful because a demo looks good; it is successful only when the agreed task sample produces measurable outcomes.

## Core pilot metrics

- **Task success rate:** completed tasks accepted as correct/useful divided by evaluated tasks. Target for a strong enterprise pilot: >= 0.90.
- **Grounded claim rate:** factual claims with traceable supporting evidence divided by factual claims sampled. Target: >= 0.95.
- **Human acceptance rate:** outputs accepted without material correction divided by evaluated outputs. Target: >= 0.85.
- **Median latency:** end-to-end time for the agreed task class. The target is use-case specific and must be recorded, not invented.
- **Cost per task:** actual inference/provider/runtime cost per evaluated task. The target is use-case specific.

## Minimum evidence sample

Use at least 25 representative tasks for an initial pilot score and expand the sample before making broad performance claims. Preserve failed tasks; do not remove them from the denominator. Record changes in task definitions or model/provider configuration as a new evaluation cohort.

## Acceptance bands

| Band | Task success | Grounded claims | Human acceptance |
|---|---:|---:|---:|
| Strong pilot | >=90% | >=95% | >=85% |
| Promising / iterate | 80-89% | 85-94% | 75-84% |
| Not ready for claim | <80% | <85% | <75% |

These thresholds are ORBYTHRA operating targets, not industry standards.

## Evidence discipline

1. Pilot metrics are tenant-scoped.
2. A metric is shown as `awaiting-real-pilot-data` until actual measurements are entered.
3. No synthetic value may be presented as customer evidence.
4. Benchmark results, production SLO history, pentest findings, and commercial revenue are separate evidence classes.
5. Any public sales claim should identify the sample, date window, product version, and whether the result was independently validated.
