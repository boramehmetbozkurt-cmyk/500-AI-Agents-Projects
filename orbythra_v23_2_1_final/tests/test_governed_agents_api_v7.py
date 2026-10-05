from fastapi.testclient import TestClient
from app.api import app
from app.config import SETTINGS
C=TestClient(app);H={"X-API-Key":SETTINGS.api_keys[0][1],"X-Workspace-ID":"v7-test"}
def test_v7_simulation_api_fail_closed():
 b={"action_id":"a1","operation":"write","intended_effect":{"x":1},"predicted_effect":{"x":2},"risk_tier":"high","reversible":True,"rollback_plan":{"x":0},"blast_radius":10}
 r=C.post("/v7/agents/simulate",headers=H,json=b);assert r.status_code==200 and r.json()["decision"]=="BLOCK"
def test_v7_readiness_boundaries():
 x=C.get("/v7/agents/readiness",headers=H).json();assert x["release"]=="7.0" and x["live_tool_sandbox_execution"] is False and x["independent_agentic_security_validation"] is False
