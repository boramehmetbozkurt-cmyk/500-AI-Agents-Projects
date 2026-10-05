from __future__ import annotations
import os,uuid
from fastapi.testclient import TestClient
from app.api import app
client=TestClient(app); H={"X-API-Key":"test-secret","X-Workspace-ID":"blind-v5"}
COMMIT=os.getenv("ORBYTHRA_RELEASE_SHA","0"*40)
def body():
 cases=[]
 for i in range(30):
  ok=i%10!=0
  cases.append({"case_id":f"blind-{i}","domain":["eng","ops","security"][i%3],"unseen":True,"success":ok,"evidence_coverage":.95,"confidence":.9 if ok else .1,"transferred_skill":i>=20})
 return {"challenge_id":"ch-"+uuid.uuid4().hex[:8],"validator_id":"external-lab-fixture","nonce":"external-secret-nonce-1234","cases":cases,"minimum_domains":3,"expected_commit_sha":COMMIT}
def test_blind_challenge_executes_and_binds_evidence():
 r=client.post("/v5/validation/blind-challenges/execute",json=body(),headers=H); assert r.status_code==200,r.text
 b=r.json(); assert b["status"]=="PASS"; assert len(b["case_set_sha256"])==64; assert len(b["manifest_sha256"])==64; assert len(b["validation_evidence_sha256"])==64
def test_blind_challenge_rejects_wrong_release():
 b=body(); b["expected_commit_sha"]="f"*40 if COMMIT!="f"*40 else "e"*40
 r=client.post("/v5/validation/blind-challenges/execute",json=b,headers=H); assert r.status_code==409; assert r.json()["detail"]["reason"]=="stale_or_wrong_release"
def test_blind_challenge_rejects_duplicate_case_ids():
 b=body(); b["cases"][1]["case_id"]=b["cases"][0]["case_id"]
 r=client.post("/v5/validation/blind-challenges/execute",json=b,headers=H); assert r.status_code==409; assert r.json()["detail"]["reason"]=="duplicate_case_id"
def test_release_readiness_does_not_claim_independence():
 client.post("/v5/validation/blind-challenges/execute",json=body(),headers=H)
 r=client.get("/v5/validation/release-readiness",headers=H); assert r.status_code==200
 assert r.json()["release_validated"] is True; assert r.json()["independent_validation_claim"] is False
