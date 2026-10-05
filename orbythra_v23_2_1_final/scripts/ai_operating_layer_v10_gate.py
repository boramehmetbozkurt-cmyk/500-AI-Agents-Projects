from app.ai_operating_layer_v10 import OperatingRequest,ModelCandidate,orchestrate
from app.verifiable_intelligence_v6 import EvidenceDocument
def main():
 r=orchestrate(OperatingRequest(request_id="v10-frozen",prompt="q",claims=["Water freezes at zero Celsius"],evidence=[EvidenceDocument(source_id="s",text="Water freezes at zero Celsius.")],candidates=[ModelCandidate(model_id="provider-neutral",output="ok",confidence=.9)]),"frozen")
 if r.status!="PASS" or not r.receipt:raise SystemExit("v10 gate failed")
 print('{"schema":"orbythra.v10-ai-operating-layer","passed":1,"total":1}')
if __name__=="__main__":main()
