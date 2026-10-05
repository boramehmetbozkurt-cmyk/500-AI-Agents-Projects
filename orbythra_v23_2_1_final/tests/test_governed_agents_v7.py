from app.governed_agents_v7 import SimulationRequest,simulate,recovery_plan
def req(**kw):
 x={"action_id":"a1","operation":"transfer","intended_effect":{"amount":10},"predicted_effect":{"amount":10},"risk_tier":"moderate","reversible":True,"rollback_plan":{"action":"reverse"},"blast_radius":1};x.update(kw);return SimulationRequest(**x)
def test_matching_bounded_action_allowed():assert simulate(req()).decision=="ALLOW"
def test_effect_mismatch_blocks():assert simulate(req(predicted_effect={"amount":11})).decision=="BLOCK"
def test_missing_rollback_requires_review():assert simulate(req(rollback_plan=None)).decision=="REVIEW"
def test_large_blast_radius_escalates():assert simulate(req(blast_radius=2000)).decision=="REVIEW" and simulate(req(blast_radius=2000)).effective_risk=="critical"
def test_recovery_is_hash_bound():
 r=recovery_plan(action_id="a1",reason="effect_mismatch",rollback_plan={"action":"reverse"});assert r["state"]=="CONTAINED" and len(r["recovery_sha256"])==64
