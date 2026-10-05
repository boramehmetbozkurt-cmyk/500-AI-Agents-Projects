from app.ai_operating_layer_v10 import OperatingRequest,ModelCandidate,orchestrate
from app.verifiable_intelligence_v6 import EvidenceDocument
from app.governed_agents_v7 import SimulationRequest
def base(**kw):
 x={"request_id":"v10-req-001","prompt":"q","claims":["Paris is the capital of France"],"evidence":[EvidenceDocument(source_id="s",text="Paris is the capital of France.")],"candidates":[ModelCandidate(model_id="m1",output="a",confidence=.8),ModelCandidate(model_id="m2",output="b",confidence=.9)]};x.update(kw);return OperatingRequest(**x)
def test_selects_highest_confidence_and_seals():r=orchestrate(base(),"w");assert r.status=="PASS" and r.selected_model_id=="m2" and r.receipt
def test_unverified_claim_fails_closed():r=orchestrate(base(evidence=[EvidenceDocument(source_id="s",text="Berlin is in Germany.")]),"w");assert r.status=="FAIL" and r.receipt is None
def test_low_confidence_models_fail():r=orchestrate(base(candidates=[ModelCandidate(model_id="m",output="x",confidence=.2)]),"w");assert r.status=="FAIL"
def test_blocked_action_blocks_release():
 a=SimulationRequest(action_id="a",operation="write",intended_effect={"x":1},predicted_effect={"x":2},reversible=True,rollback_plan={"x":0})
 r=orchestrate(base(action=a),"w");assert r.status=="FAIL" and r.action_decision=="BLOCK"
