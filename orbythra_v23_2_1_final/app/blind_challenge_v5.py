from __future__ import annotations
import hashlib,json
from typing import Any
from pydantic import BaseModel,Field
from app.generalist_v5 import GeneralistCase,GeneralistEvaluationRequest,evaluate_generalist

def _sha(v:Any)->str:
 return hashlib.sha256(json.dumps(v,ensure_ascii=False,separators=(",",":"),sort_keys=True,allow_nan=False).encode()).hexdigest()

class BlindChallengeRequest(BaseModel):
 challenge_id:str=Field(min_length=1,max_length=120,pattern=r"^[A-Za-z0-9._-]+$")
 validator_id:str=Field(min_length=1,max_length=200)
 nonce:str=Field(min_length=16,max_length=256)
 cases:list[GeneralistCase]=Field(min_length=20,max_length=10000)
 minimum_domains:int=Field(default=3,ge=3,le=100)
 expected_commit_sha:str=Field(pattern=r"^[0-9a-f]{40}$")

def execute_blind_challenge(body:BlindChallengeRequest,current_commit_sha:str)->dict[str,Any]:
 if current_commit_sha!=body.expected_commit_sha:
  return {"status":"REJECTED","reason":"stale_or_wrong_release","challenge_id":body.challenge_id,"current_commit_sha":current_commit_sha}
 if len({c.case_id for c in body.cases})!=len(body.cases):
  return {"status":"REJECTED","reason":"duplicate_case_id","challenge_id":body.challenge_id}
 req=GeneralistEvaluationRequest(evaluation_id="blind-"+body.challenge_id,cases=body.cases,minimum_domains=body.minimum_domains)
 result=evaluate_generalist(req)
 manifest={"schema":"orbythra.blind-challenge.v5","challenge_id":body.challenge_id,"validator_id":body.validator_id,"nonce_sha256":_sha(body.nonce),"commit_sha":current_commit_sha,"case_set_sha256":_sha([c.model_dump(mode="json") for c in body.cases]),"result":result}
 return {**manifest,"status":result["status"],"manifest_sha256":_sha(manifest)}
