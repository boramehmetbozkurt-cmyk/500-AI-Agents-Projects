import time,uuid
from app.temporal_reality_v8 import TEMPORAL_V8,TemporalFactIn
def w():return "v8-"+uuid.uuid4().hex
def fact(obj,vf=100,vt=None):return TemporalFactIn(subject="service",predicate="status",object=obj,valid_from=vf,valid_to=vt,source_id="src",evidence_sha256="a"*64)
def test_snapshot_respects_valid_time():
 x=w();TEMPORAL_V8.add(x,fact("old",100,200));TEMPORAL_V8.add(x,fact("new",200,None))
 assert [r["object"] for r in TEMPORAL_V8.snapshot(x,150)]==["old"]
 assert [r["object"] for r in TEMPORAL_V8.snapshot(x,250)]==["new"]
def test_conflict_detected_for_overlapping_claims():
 x=w();TEMPORAL_V8.add(x,fact("up"));TEMPORAL_V8.add(x,fact("down"))
 assert TEMPORAL_V8.conflicts(x,150)[0]["predicate"]=="status"
def test_known_at_reconstructs_record_history():
 x=w();a=TEMPORAL_V8.add(x,fact("up"));known=a["recorded_at"]-1
 assert TEMPORAL_V8.snapshot(x,150,known)==[]
def test_stale_detection():
 x=w();a=TEMPORAL_V8.add(x,fact("up"));assert a["fact_id"] in TEMPORAL_V8.stale(x,1,a["recorded_at"]+2)
