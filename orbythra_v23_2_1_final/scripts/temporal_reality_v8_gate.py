import tempfile
from app.temporal_reality_v8 import TEMPORAL_V8,TemporalFactIn
W="v8-frozen"
def f(o,vf,vt=None):return TemporalFactIn(subject="asset",predicate="state",object=o,valid_from=vf,valid_to=vt,source_id="frozen",evidence_sha256="c"*64)
def main():
 TEMPORAL_V8.add(W,f("A",100,200));TEMPORAL_V8.add(W,f("B",200,None))
 checks=[TEMPORAL_V8.snapshot(W,150)[0]["object"]=="A",TEMPORAL_V8.snapshot(W,250)[0]["object"]=="B",not TEMPORAL_V8.conflicts(W,150)]
 if not all(checks):raise SystemExit("v8 temporal gate failed")
 print('{"schema":"orbythra.v8-temporal-reality","passed":3,"total":3}')
if __name__=="__main__":main()
