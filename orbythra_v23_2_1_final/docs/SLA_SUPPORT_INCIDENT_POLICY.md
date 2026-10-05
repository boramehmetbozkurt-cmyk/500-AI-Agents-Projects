# ORBYTHRA Enterprise SLA, Support and Incident Policy — Draft Baseline

Status: commercial baseline for negotiation; it becomes binding only when incorporated into an executed agreement.

## Service objectives

Production targets should be activated only after live monitoring can measure them. Proposed enterprise target: 99.9% monthly API availability excluding agreed maintenance, force majeure and customer/provider-caused failures. Do not publish an achieved uptime percentage until measured in production.

## Severity model

- SEV-1 Critical: widespread production outage, confirmed material security compromise, or critical integrity failure. Target acknowledgement: 30 minutes for contracted 24x7 support.
- SEV-2 High: major degradation or high-impact function unavailable with no acceptable workaround. Target acknowledgement: 2 hours.
- SEV-3 Medium: partial degradation with workaround. Target acknowledgement: 1 business day.
- SEV-4 Low: questions, documentation and non-urgent defects. Target acknowledgement: 2 business days.

## Incident lifecycle

Detect -> classify -> assign incident commander -> contain -> preserve evidence -> communicate -> eradicate -> recover -> verify -> postmortem -> corrective actions. Security/privacy incidents must also enter the incident/breach register. Regulatory notification decisions remain a legal/controller assessment.

## Customer communications

For SEV-1 incidents, contracted customers should receive an initial status message after triage and material updates at an agreed cadence until recovery. Final post-incident summaries should identify impact, timeline, root cause where established, corrective actions and prevention work without exposing sensitive security information.

## Recovery objectives

Initial commercial targets to validate through disaster-recovery exercises:
- RPO target: <= 15 minutes for production transactional data where infrastructure supports continuous database backup.
- RTO target: <= 4 hours for regional service recovery.

These are design targets, not achieved metrics, until tested in the chosen production environment.

## Maintenance and changes

Planned material maintenance should use advance customer notice where practical. Emergency security changes may bypass normal notice with retrospective documentation. Releases must be traceable to a commit SHA and pass CI/security gates.

## Support evidence required before enterprise launch

Named support owner, escalation aliases, on-call rota, incident bridge procedure, status communication mechanism, customer security contact path, DR exercise evidence, backup restore evidence and monitored availability dashboard.
