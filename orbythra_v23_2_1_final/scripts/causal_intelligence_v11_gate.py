from app.causal_intelligence_v11 import CausalRequest,CausalEdge,evaluate
from app.verifiable_intelligence_v6 import EvidenceDocument
def main():
 r=evaluate(CausalRequest(request_id="v11-frozen",hypothesis="heat raises temperature",edges=[CausalEdge(cause="heat",effect="temperature",mechanism="energy transfer",evidence_claims=["Heat raises temperature"],confidence=.9,confounders=["ambient conditions"])],evidence=[EvidenceDocument(source_id="s",text="Heat raises temperature.")],intervention="apply heat",counterfactual="do not apply heat"),"frozen")
 if r.status!="PASS" or not r.receipt:raise SystemExit("v11 gate failed")
 print('{"schema":"orbythra.v11-causal-intelligence","passed":1,"total":1}')
if __name__=="__main__":main()
