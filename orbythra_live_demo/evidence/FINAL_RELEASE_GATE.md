# ORBYTHRA Final Release Gate

A release may be called **Final Owner-Controlled Baseline** only when all owner-controlled checks below are green.

## Automated
- [ ] Python/unit/integration suite green
- [ ] strategic validation harness green or explicitly classified infrastructure-only failure
- [ ] dependency/security audit green
- [ ] Docker/build gate green
- [ ] buyer/evaluation artifact gate green
- [ ] evidence manifest schema valid
- [ ] no committed secrets
- [ ] protected side-effect tests fail closed
- [ ] tenant-isolation negative tests green
- [ ] claim/trace reconstruction tests green

## Release evidence
- [ ] exact commit recorded
- [ ] exact deployment/snapshot recorded
- [ ] enabled providers/tools recorded
- [ ] benchmark population and provenance recorded
- [ ] capability failures separated from runtime/provider/harness failures
- [ ] known limitations recorded
- [ ] rollback/recovery path recorded

## External gates — never self-attest
These may remain OPEN without creating another architecture stage:
- independent engineering evaluation
- authorized security assessment
- evaluator-controlled blinded holdout
- real bounded engineering/digital-twin pilot
- remediation/retest of external findings

External gates upgrade evidence/certification status only.
