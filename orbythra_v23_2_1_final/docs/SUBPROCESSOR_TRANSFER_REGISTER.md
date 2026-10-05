# ORBYTHRA Subprocessor and International Transfer Register

Status: controlled template. Production vendors must be entered only after actual contracting and security/privacy review.

| Vendor / legal entity | Service | Data categories | Processing region(s) | Subprocessor role | Transfer mechanism | Security review | DPA executed | Status |
|---|---|---|---|---|---|---|---|---|
| TBD | Cloud hosting | TBD | TBD | Infrastructure | TBD | Pending | Pending | Not approved |
| TBD | Managed database | TBD | TBD | Infrastructure | TBD | Pending | Pending | Not approved |
| TBD | AI/model provider | Customer-configured | TBD | AI processing | TBD | Pending | Pending | Not approved |
| TBD | Monitoring/security | Operational metadata | TBD | Observability/security | TBD | Pending | Pending | Not approved |

## Approval gate

A vendor moves to `Approved` only when all applicable items are documented: legal entity; purpose; minimum data set; processing locations; retention; security controls; incident obligations; confidentiality; DPA/subprocessor terms; international-transfer mechanism; transfer impact assessment where required; deletion/return terms; change notification; exit plan.

## Change process

1. Product/security owner proposes the vendor and intended data flow.
2. Privacy/security review determines data minimisation and region requirements.
3. Contractual terms and transfer mechanism are reviewed.
4. Provider is registered in ORBYTHRA enterprise provider registry and constrained by tenant policy.
5. Customer notification/objection process is applied if contractually required.
6. Evidence is retained with approval date and owner.

## Technical enforcement link

The enterprise policy engine can enforce provider allowlists, permitted regions, prohibited data categories, maximum retention, zero-retention requirements, private-endpoint requirements, evidence thresholds and human-approval gates. Registry approval is not a substitute for legal/vendor review; it converts an approved decision into runtime enforcement.
