from app.semantic_verifier_adapter import SEMANTIC_NLI
from app.verifiable_intelligence_v6 import EvidenceDocument,verify_claims
def test_semantic_adapter_fallback_is_explicit():
 v=SEMANTIC_NLI.score("alpha beta","alpha beta");assert v.verifier in {"orbythra-nli-baseline-v1","orbythra-semantic-provider-v1"}
def test_v6_accepts_injected_verifier():
 class V:
  def score(self,c,e):
   from app.nli_verifier_v51 import NLIVerdict
   return NLIVerdict(label="ENTAILMENT",entailment=.99,contradiction=.005,neutral=.005,verifier="test-semantic")
 r=verify_claims(["claim"],[EvidenceDocument(source_id="s",text="evidence")],verifier=V());assert r.status=="PASS" and r.checks[0].verifier=="test-semantic"
