import base64,uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.distributed_verification_v9 import TRUST_V9,Validator
from app.persistent_validators_v9 import PERSISTENT_VALIDATORS_V9
from app.model_adapters_v10 import disagreement,GovernedHttpModelAdapter
def b64(x):return base64.urlsafe_b64encode(x).decode().rstrip("=")
def test_validator_persists_and_reloads():
 k=ed25519.Ed25519PrivateKey.generate();i="persist-"+uuid.uuid4().hex;pub=b64(k.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw));TRUST_V9.register(Validator(validator_id=i,public_key_b64=pub,organization="org"));TRUST_V9.validators.pop(i);assert PERSISTENT_VALIDATORS_V9.get(i).organization=="org" and TRUST_V9._lookup(i).validator_id==i
def test_cross_model_disagreement():assert disagreement([{"output":"yes"},{"output":"no"}])["detected"] is True
def test_equivalent_normalized_output_agrees():assert disagreement([{"output":"YES  now"},{"output":" yes now "}])["detected"] is False
def test_unconfigured_provider_fails_closed(monkeypatch):
 monkeypatch.setattr("app.model_adapters_v10.llm_provider",lambda:None)
 try:GovernedHttpModelAdapter().generate(model_id="x",prompt="q");assert False
 except RuntimeError as e:assert str(e)=="llm_provider_not_configured"
