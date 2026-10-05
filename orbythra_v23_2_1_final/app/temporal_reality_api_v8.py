from __future__ import annotations
from typing import Any
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel,Field
from app.security import Principal,require_minimum_role
from app.store import STORE
from app.temporal_reality_v8 import TEMPORAL_V8,TemporalFactIn
router=APIRouter(prefix="/v8/temporal",tags=["v8-temporal-reality"]);_OP=require_minimum_role("operator");_EV=require_minimum_role("evaluator")
class SnapshotRequest(BaseModel):valid_at:int;known_at:int|None=None
class StaleRequest(BaseModel):max_age_seconds:int=Field(gt=0);now:int|None=None
@router.post("/facts")
def add_fact(body:TemporalFactIn,request:Request,principal:Principal=Depends(_OP))->dict[str,Any]:
 r=TEMPORAL_V8.add(principal.workspace_id,body);STORE.record_audit(request_id=getattr(request.state,"request_id",r["fact_id"]),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="v8_temporal_fact",status="RECORDED",metadata=r);return r
@router.post("/snapshot")
def snapshot(body:SnapshotRequest,principal:Principal=Depends(_EV))->dict[str,Any]:
 rows=TEMPORAL_V8.snapshot(principal.workspace_id,body.valid_at,body.known_at);return {"valid_at":body.valid_at,"known_at":body.known_at,"facts":rows,"conflicts":TEMPORAL_V8.conflicts(principal.workspace_id,body.valid_at,body.known_at)}
@router.post("/stale")
def stale(body:StaleRequest,principal:Principal=Depends(_EV))->dict[str,Any]:return {"stale_fact_ids":TEMPORAL_V8.stale(principal.workspace_id,body.max_age_seconds,body.now)}
@router.get("/readiness")
def readiness(principal:Principal=Depends(_EV))->dict[str,Any]:
 return {"release":"8.0","workspace_id":principal.workspace_id,"valid_time":True,"transaction_time":True,"historical_state_reconstruction":True,"conflict_detection":True,"stale_fact_detection":True,"evidence_digest_binding":True,"automatic_external_source_change_detection":False,"causal_inference":False,"claim":"Bitemporal evidence-backed reality state; no claim that stored facts are independently true."}
