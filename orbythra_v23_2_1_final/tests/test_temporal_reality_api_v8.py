from fastapi.testclient import TestClient
from app.api import app
from app.config import SETTINGS
C=TestClient(app);H={"X-API-Key":SETTINGS.api_keys[0][1],"X-Workspace-ID":"v8-api"}
def test_v8_readiness_boundaries():
 r=C.get("/v8/temporal/readiness",headers=H);assert r.status_code==200
 x=r.json();assert x["release"]=="8.0" and x["historical_state_reconstruction"] and x["automatic_external_source_change_detection"] is False
def test_v8_fact_and_snapshot():
 b={"subject":"policy","predicate":"version","object":"v1","valid_from":100,"source_id":"s","evidence_sha256":"b"*64}
 assert C.post("/v8/temporal/facts",headers=H,json=b).status_code==200
 x=C.post("/v8/temporal/snapshot",headers=H,json={"valid_at":150}).json();assert any(f["object"]=="v1" for f in x["facts"])
