import hashlib
from fastapi.testclient import TestClient
from app.api import app
from app.config import SETTINGS
def headers():return {"X-API-Key":SETTINGS.api_keys[0][1],"X-Workspace-ID":"default"}
def body(nonce="1234567890abcdef",**kw):
    x={"request_id":"assurance-001","nonce":nonce,"model_id":"test","prompt":"q","output":"supported answer","confidence":.9,"risk_tier":"moderate","required_claims":["c1"],"evidence":[{"source_id":"s1","url":"https://example.com","supports":["c1"],"text":"c1"}],"expected_release_sha":SETTINGS.release_sha,"configuration_sha256":"a"*64};x.update(kw);return x
def test_pass_releases_with_manifest():
    d=TestClient(app).post("/v5.1/model-output/evaluate",json=body(),headers=headers()).json()
    assert d["status"]=="PASS" and d["release_output"] is True and len(d["evidence_manifest_sha256"])==64
    assert d["claim_verdicts"][0]["status"]=="SUPPORTED"
def test_missing_evidence_fails_closed():
    d=TestClient(app).post("/v5.1/model-output/evaluate",json=body(nonce="1234567890abcdea",evidence=[]),headers=headers()).json()
    assert d["status"]=="FAIL" and d["output"] is None
def test_contradiction_fails_closed():
    e=[{"source_id":"s1","supports":["c1"],"text":"c1"},{"source_id":"s2","contradicts":["c1"],"text":"not c1"}]
    d=TestClient(app).post("/v5.1/model-output/evaluate",json=body(nonce="1234567890abcdeb",evidence=e),headers=headers()).json()
    assert d["status"]=="FAIL" and d["claim_verdicts"][0]["status"]=="CONTRADICTED"
def test_high_risk_requires_human():
    d=TestClient(app).post("/v5.1/model-output/evaluate",json=body(nonce="1234567890abcdec",risk_tier="high"),headers=headers()).json()
    assert d["status"]=="REVIEW" and d["output"] is None
def test_wrong_release_rejected():
    r=TestClient(app).post("/v5.1/model-output/evaluate",json=body(nonce="1234567890abcded",expected_release_sha="0"*40),headers=headers())
    assert r.status_code==409
def test_replay_rejected():
    c=TestClient(app);b=body(nonce="1234567890abcdee",request_id="replay-001")
    assert c.post("/v5.1/model-output/evaluate",json=b,headers=headers()).status_code==200
    assert c.post("/v5.1/model-output/evaluate",json=b,headers=headers()).status_code==409

def test_nli_neutral_blocks_release():
    b=body(nonce="1234567890abcdef0",request_id="nli-neutral",evidence=[{"source_id":"s1","supports":["c1"],"text":"unrelated material"}])
    d=TestClient(app).post("/v5.1/model-output/evaluate",json=b,headers=headers()).json()
    assert d["status"]=="FAIL" and d["output"] is None and d["claim_verdicts"][0]["nli_label"]=="NEUTRAL"
