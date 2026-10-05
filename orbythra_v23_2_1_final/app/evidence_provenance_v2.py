from __future__ import annotations
import hashlib
from pydantic import BaseModel,Field,model_validator
from app.crypto_core import canonical_json
class EvidenceSpan(BaseModel):
 source_id:str=Field(min_length=1,max_length=200);claim:str=Field(min_length=1,max_length=2000);text:str=Field(min_length=1,max_length=200000);start:int=Field(ge=0);end:int=Field(gt=0)
 @model_validator(mode="after")
 def bounds(self):
  if self.end<=self.start or self.end>len(self.text):raise ValueError("invalid_evidence_span")
  return self
 def quoted(self):return self.text[self.start:self.end]
 def digest(self):return hashlib.sha256(canonical_json({"source_id":self.source_id,"claim":self.claim,"quoted":self.quoted(),"start":self.start,"end":self.end})).hexdigest()
def provenance_manifest(spans:list[EvidenceSpan])->dict:
 entries=[{"source_id":s.source_id,"claim":s.claim,"start":s.start,"end":s.end,"quote_sha256":hashlib.sha256(s.quoted().encode()).hexdigest(),"binding_sha256":s.digest()} for s in spans]
 return {"schema":"orbythra.evidence-provenance.v2","entries":entries,"manifest_sha256":hashlib.sha256(canonical_json(entries)).hexdigest()}
