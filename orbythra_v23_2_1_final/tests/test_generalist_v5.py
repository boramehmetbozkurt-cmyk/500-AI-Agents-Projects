from __future__ import annotations
import uuid
from fastapi.testclient import TestClient
from app.api import app
client=TestClient(app)
H={"X-API-Key":"test-secret","X-Workspace-ID":"v5-generalist"}

def _case(i,domain,success=True,unseen=True,evidence=.95,confidence=.9,transfer=False):
 return {"case_id":f"c{i}","domain":domain,"unseen":unseen,"success":success,"evidence_coverage":evidence,"confidence":confidence if success else 1-confidence,"transferred_skill":transfer}

def _body(eid=None):
 cases=[]
 for i in range(12):
  cases.append(_case(i,["engineering","finance","operations"][i%3],transfer=i>=9))
 return {"evaluation_id":eid or "eval-"+uuid.uuid4().hex[:10],"cases":cases}

def test_v5_passes_diverse_unseen_evidence_grounded_cases_and_binds_validation():
 r=client.post("/v5/generalist/evaluate",json=_body(),headers=H); assert r.status_code==200,r.text
 b=r.json(); assert b["status"]=="PASS" and b["generalist_ready"] is True
 assert len(b["evaluation_sha256"])==64 and len(b["validation_evidence_sha256"])==64
 v=client.get("/v5/generalist/ledger/verify",headers=H); assert v.status_code==200 and v.json()["valid"] is True

def test_v5_fails_closed_on_single_domain_overfit():
 body=_body(); body["cases"]=[_case(i,"engineering") for i in range(12)]
 r=client.post("/v5/generalist/evaluate",json=body,headers=H); assert r.status_code==200
 assert r.json()["status"]=="FAIL"; assert r.json()["gates"]["domain_diversity"] is False

def test_v5_fails_closed_on_seen_only_cases():
 body=_body(); body["cases"]=[_case(i,["engineering","finance","operations"][i%3],unseen=False) for i in range(12)]
 r=client.post("/v5/generalist/evaluate",json=body,headers=H); assert r.status_code==200
 assert r.json()["gates"]["unseen_success"] is False

def test_v5_fails_low_evidence_even_with_perfect_task_success():
 body=_body(); body["cases"]=[_case(i,["engineering","finance","operations"][i%3],evidence=.2) for i in range(12)]
 r=client.post("/v5/generalist/evaluate",json=body,headers=H); assert r.status_code==200
 assert r.json()["generalist_ready"] is False and r.json()["gates"]["evidence_coverage"] is False

def test_v5_fails_miscalibrated_confidence():
 body=_body(); body["cases"]=[_case(i,["engineering","finance","operations"][i%3],confidence=.1) for i in range(12)]
 r=client.post("/v5/generalist/evaluate",json=body,headers=H); assert r.status_code==200
 assert r.json()["gates"]["calibration"] is False

def test_v5_duplicate_evaluation_id_is_rejected():
 body=_body(); assert client.post("/v5/generalist/evaluate",json=body,headers=H).status_code==200
 assert client.post("/v5/generalist/evaluate",json=body,headers=H).status_code==409

def test_v5_workspace_isolation():
 body=_body(); r=client.post("/v5/generalist/evaluate",json=body,headers=H); assert r.status_code==200
 other={"X-API-Key":"test-secret","X-Workspace-ID":"v5-other"}
 assert client.get("/v5/generalist/evaluations/"+body["evaluation_id"],headers=other).status_code==404

def test_v5_readiness_never_claims_agi():
 r=client.get("/v5/generalist/readiness",headers=H); assert r.status_code==200
 b=r.json(); assert b["agi_claim"] is False and b["human_level_general_intelligence_claim"] is False and b["model_weight_self_training"] is False
