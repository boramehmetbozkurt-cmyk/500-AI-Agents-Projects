import pytest
from pydantic import ValidationError
from app.causal_intelligence_v11 import CausalRequest,CausalEdge,evaluate
from app.verifiable_intelligence_v6 import EvidenceDocument
E=[EvidenceDocument(source_id="s",text="Smoking increases lung cancer risk.")]
def req(**kw):
 x={"request_id":"causal-001","hypothesis":"smoking causes increased lung cancer risk","edges":[CausalEdge(cause="smoking",effect="lung cancer risk",mechanism="carcinogen exposure",evidence_claims=["Smoking increases lung cancer risk"],confidence=.9,confounders=["age"])],"evidence":E,"intervention":"remove smoking exposure","counterfactual":"same population without smoking"};x.update(kw);return CausalRequest(**x)
def test_supported_causal_hypothesis_passes_and_seals():
 r=evaluate(req(),"w");assert r.status=="PASS" and r.receipt and r.intervention_ready and r.counterfactual_ready
def test_missing_confounder_analysis_reviews():
 e=req().edges[0].model_copy(update={"confounders":[]});r=evaluate(req(edges=[e]),"w");assert r.status=="REVIEW" and r.receipt is None
def test_unsupported_evidence_fails():
 r=evaluate(req(evidence=[EvidenceDocument(source_id="x",text="The sky is blue.")]),"w");assert r.status=="FAIL"
def test_low_confidence_reviews():
 e=req().edges[0].model_copy(update={"confidence":.4});assert evaluate(req(edges=[e]),"w").status=="REVIEW"
def test_cycle_rejected():
 with pytest.raises(ValidationError):CausalRequest(request_id="causal-cycle",hypothesis="cycle",edges=[CausalEdge(cause="a",effect="b",mechanism="m",evidence_claims=["a b"],confidence=.9,confounders=["c"]),CausalEdge(cause="b",effect="a",mechanism="m",evidence_claims=["b a"],confidence=.9,confounders=["c"])],evidence=[EvidenceDocument(source_id="s",text="a b")])
