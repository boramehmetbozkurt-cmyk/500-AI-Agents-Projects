from unittest.mock import patch
from fastapi.testclient import TestClient
from app.api import app
from app.config import SETTINGS
from app.web_evidence_v51 import SourceSnapshot

def h():return {"X-API-Key":SETTINGS.api_keys[0][1],"X-Workspace-ID":"default"}
def fake(src,timeout,max_bytes):return SourceSnapshot(source_id=src.source_id,url=src.url,status="FETCHED",content_sha256="a"*64,fetched_at=1,bytes_read=50),"ORBYTHRA evidence supports claim alpha with verified material"
def test_web_evidence_found():
 with patch("app.web_evidence_v51._fetch",side_effect=fake):
  r=TestClient(app).post("/v5.1/web-evidence/verify",headers=h(),json={"request_id":"webtest-001","claims":["claim alpha verified material"],"sources":[{"source_id":"s1","url":"https://example.com"}],"minimum_token_overlap":.5})
 assert r.status_code==200 and r.json()["status"]=="PASS" and r.json()["snapshot_id"]
def test_web_evidence_not_established():
 with patch("app.web_evidence_v51._fetch",side_effect=fake):
  d=TestClient(app).post("/v5.1/web-evidence/verify",headers=h(),json={"request_id":"webtest-002","claims":["unrelated quantum banana statement"],"sources":[{"source_id":"s1","url":"https://example.com"}],"minimum_token_overlap":.8}).json()
 assert d["status"]=="REVIEW" and d["claim_verdicts"][0]["status"]=="NOT_ESTABLISHED"
def test_private_host_rejected():
 from app.web_evidence_v51 import _safe_url
 import pytest
 from fastapi import HTTPException
 with pytest.raises(HTTPException):_safe_url("https://127.0.0.1/private")

def test_semantic_contradiction_signal():
 from app.web_evidence_v51 import _semantic_signal
 score,contra,_=_semantic_signal("ORBYTHRA is secure","ORBYTHRA is not secure according to this test.")
 assert score>=.55 and contra is True

def test_semantic_support_signal():
 from app.web_evidence_v51 import _semantic_signal
 score,contra,excerpt=_semantic_signal("ORBYTHRA evidence supports claim","The report says ORBYTHRA evidence supports claim with material.")
 assert score>=.55 and contra is False and excerpt
