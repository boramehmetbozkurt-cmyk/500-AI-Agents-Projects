from app.verifiable_intelligence_v6 import EvidenceDocument,verify_claims
CASES=[
("Water freezes at zero Celsius","Water freezes at zero Celsius.",True),
("Earth has one moon","Earth has one moon.",True),
("Paris is the capital of France","Berlin is in Germany.",False),
("The service is available","The service is not available.",False),
]
def main():
 passed=0
 for claim,text,expected in CASES:
  got=verify_claims([claim],[EvidenceDocument(source_id="frozen",text=text)]).status=="PASS"
  passed+=got==expected
 if passed!=len(CASES):raise SystemExit(f"v6 benchmark failed: {passed}/{len(CASES)}")
 print('{"schema":"orbythra.v6-frozen-benchmark","passed":4,"total":4}')
if __name__=="__main__":main()
