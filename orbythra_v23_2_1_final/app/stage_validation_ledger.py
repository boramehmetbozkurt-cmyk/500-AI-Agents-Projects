from __future__ import annotations
import hashlib
from typing import Any
from app.config import SETTINGS
from app.crypto_core import canonical_json
from app.validation_evidence_v45 import VALIDATION_EVIDENCE
def configuration_sha256()->str:
 safe={"environment":SETTINGS.environment,"crypto_algorithm":SETTINGS.crypto_algorithm,"key_management_mode":SETTINGS.key_management_mode,"rate_limit_per_minute":SETTINGS.rate_limit_per_minute,"max_body_bytes":SETTINGS.max_body_bytes,"deployment_id":SETTINGS.deployment_id}
 return hashlib.sha256(canonical_json(safe)).hexdigest()
def record_stage(workspace_id:str,stage:str,status:str,artifact:dict[str,Any])->dict[str,Any]:
 digest=hashlib.sha256(canonical_json(artifact)).hexdigest()
 return VALIDATION_EVIDENCE.append(workspace_id,{"suite":stage,"commit_sha":SETTINGS.release_sha or "unbound-development","configuration_sha256":configuration_sha256(),"result":status,"total":1,"passed":1 if status=="PASS" else 0,"failed":0 if status=="PASS" else 1,"artifact_sha256":digest})
