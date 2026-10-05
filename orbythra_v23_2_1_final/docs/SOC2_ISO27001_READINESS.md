# ORBYTHRA SOC 2 / ISO 27001 Readiness Matrix

Status: internal readiness mapping only. **Not a SOC 2 report, ISO 27001 certification, or auditor opinion.**

| Control area | Current technical evidence | Remaining organisational / external gate |
|---|---|---|
| Access control | API authentication, RBAC, workspace isolation, least-role endpoints | Joiner/mover/leaver process, SSO lifecycle, periodic access review evidence |
| Cryptography | AES-256-GCM / ChaCha20-Poly1305, HKDF, Ed25519, X25519, key IDs/rotation | Production KMS/HSM configuration, key-owner process, rotation evidence |
| Secure SDLC | CI compile/test, Bandit, dependency audit, secret scan, OpenAPI gates | Formal change policy, reviewer approvals, release sign-off evidence |
| Vulnerability management | Dependency audit and static security scan | External penetration test, remediation SLAs, recurring scan cadence evidence |
| Logging / monitoring | Audit trail, request IDs, operational metrics | Central SIEM, alert routing, on-call evidence, retention policy |
| Incident response | Breach/incident register and review clock, production runbook | Named incident commander/on-call roster, tabletop exercise, postmortem evidence |
| Availability | Health/readiness checks, Docker, PostgreSQL option, backup/recovery tooling | Live multi-zone architecture, measured uptime, tested RTO/RPO |
| Privacy | GDPR-aligned technical controls, retention, DSAR support, encryption | Executed DPA, privacy notices, DPIA where required, counsel review |
| Vendor risk | Provider registry and risk policy engine | Executed subprocessor contracts, vendor reviews, transfer assessments |
| AI governance | Provider allowlists, risk tiers, evidence thresholds, human approval gates | Governance committee/accountability, approved risk taxonomy, recurring reviews |
| Evaluation | Predeclared benchmark thresholds and persisted scorecards | Independent benchmark witness/validation, customer acceptance data |
| Business continuity | Backup/recovery scripts and documented rollback | Live disaster-recovery exercise and evidence of recovery objectives |

## Internal evidence package expected for an auditor

1. Architecture and data-flow diagrams.
2. Asset and provider inventory.
3. Access-role matrix and access-review exports.
4. CI/security scan records tied to release SHAs.
5. Change/release approvals.
6. Incident response plan and exercise evidence.
7. Vulnerability/pentest findings with remediation trail.
8. Backup/restore test results and measured RTO/RPO.
9. Subprocessor and transfer register.
10. Privacy/DPA/DPIA records where applicable.
11. Benchmark and AI-governance policy outputs.
12. Customer contract/SLA and support evidence.

## Certification boundary

The repository can supply technical controls and reproducible evidence. SOC 2 Type I/II and ISO 27001 require organisational scope definition and independent audit/certification. Those outputs must remain marked `PENDING_EXTERNAL_PARTY` until issued.
