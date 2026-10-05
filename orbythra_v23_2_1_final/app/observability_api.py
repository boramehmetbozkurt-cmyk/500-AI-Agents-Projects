from __future__ import annotations
import time
from fastapi import APIRouter,Depends
from sqlalchemy import text
from app.security import Principal,require_minimum_role
from app.store import STORE
from app.config import SETTINGS
from app.telemetry import OTEL
router=APIRouter(prefix="/v1/observability",tags=["observability"]);_EV=require_minimum_role("evaluator")
@router.get("/health")
def health():return {"status":"ok","time":int(time.time())}
@router.get("/readiness")
def ready(principal:Principal=Depends(_EV)):
 return {"ready":STORE.ping(),"database":STORE.backend,"release_sha":SETTINGS.release_sha,"deployment_id":SETTINGS.deployment_id}
@router.get("/metrics")
def metrics(principal:Principal=Depends(_EV)):
 with STORE.engine.connect() as c:
  audits=c.execute(text("SELECT COUNT(*) FROM audit_events WHERE workspace_id=:w"),{"w":principal.workspace_id}).scalar_one()
  nonces=c.execute(text("SELECT COUNT(*) FROM crypto_nonces WHERE workspace_id=:w"),{"w":principal.workspace_id}).scalar_one()
 return {"workspace_id":principal.workspace_id,"audit_events":audits,"reserved_nonces":nonces,"otel":OTEL.snapshot()}
