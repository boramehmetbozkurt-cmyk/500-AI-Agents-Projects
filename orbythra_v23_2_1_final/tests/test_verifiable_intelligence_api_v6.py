from fastapi.testclient import TestClient
from app.api import app
from app.config import SETTINGS
from app.crypto_core import open_envelope
C=TestClient(app);H={"X-API-Key":SETTINGS.api_keys[0][1],"X-Workspace-ID":"v6-test"}
def body(text="Paris is the capital of France."):
 return {"request_id":"v6-request-001","claims":["Paris is the capital of France"],"evidence":[{"source_id":"s1","text":text,"url":"https://example.com","authority":.8}]}
def test_v6_api_pass_and_signed_receipt():
 r=C.post("/v6/verifiable-intelligence/verify",headers=H,json=body());assert r.status_code==200
 x=r.json();assert x["verification"]["status"]=="PASS" and x["receipt_sha256"]
 opened=open_envelope(x["receipt"],expected_workspace_id="v6-test");assert opened["content"]["payload"]["release"]=="6.0"
def test_v6_api_fails_closed_on_unrelated_evidence():
 r=C.post("/v6/verifiable-intelligence/verify",headers=H,json=body("Berlin is in Germany."));assert r.status_code==200 and r.json()["verification"]["status"]=="FAIL"
def test_v6_readiness_is_truthful_about_baseline():
 r=C.get("/v6/verifiable-intelligence/readiness",headers=H);assert r.status_code==200
 x=r.json();assert x["deterministic_nli_baseline"] is True and x["external_llm_nli_adapter"] is False and x["factual_truth_claim"] is False
