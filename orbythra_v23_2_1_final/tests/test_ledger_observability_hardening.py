from app.stage_validation_ledger import configuration_sha256,record_stage
from app.validation_evidence_v45 import VALIDATION_EVIDENCE
from app.api import app
def test_configuration_digest_stable():assert configuration_sha256()==configuration_sha256() and len(configuration_sha256())==64
def test_stage_result_is_hash_chained():
 w="ledger-hardening";x=record_stage(w,"v11-test","PASS",{"x":1});assert x["commit_sha"] and x["configuration_sha256"] and VALIDATION_EVIDENCE.verify(w)["valid"]
def test_observability_openapi():p=app.openapi()["paths"];assert "/v1/observability/health" in p and "/v1/observability/readiness" in p and "/v1/observability/metrics" in p
