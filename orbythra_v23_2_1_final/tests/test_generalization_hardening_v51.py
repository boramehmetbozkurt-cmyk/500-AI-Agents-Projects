from __future__ import annotations
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.generalization_hardening_v51 import HardeningCase,HardeningRequest,evaluate_hardening
from app.validator_registry_v51 import ValidatorRegistry,canonical
def cases():
 out=[]
 for i in range(60):
  mission=f"m{i//5}" if i<20 else None
  out.append(HardeningCase(case_id=f"c{i}",domain=["a","b","c","d","e"][i%5],success=True,baseline_success=True,confidence=.95,evidence_coverage=.95,ood=i<30,transferred_skill=20<=i<40,negative_control=30<=i<40,regression_anchor=40<=i<60,mission_id=mission,step_index=i%5 if mission else None,total_steps=5 if mission else None))
 return out
def req(cs=None):return HardeningRequest(evaluation_id="hard",cases=cs or cases(),minimum_domains=5,minimum_ood_success=.9,minimum_transfer_success=.9,maximum_negative_transfer_harm=.05,maximum_forgetting=.05,minimum_long_horizon_completion=.9,minimum_evidence=.9,maximum_calibration_error=.1)
def test_v51_hardening_passes_complete_fixture():assert evaluate_hardening(req())["status"]=="PASS"
def test_v51_ood_failure_fails_closed():
 cs=cases()
 for c in cs:
  if c.ood:c.success=False;c.confidence=.05
 r=evaluate_hardening(req(cs));assert not r["gates"]["ood_success"];assert r["status"]=="FAIL"
def test_v51_negative_transfer_is_detected():
 cs=cases()
 for c in cs:
  if c.negative_control:c.success=False;c.confidence=.05
 r=evaluate_hardening(req(cs));assert not r["gates"]["negative_transfer_harm"]
def test_v51_forgetting_is_detected():
 cs=cases()
 for c in cs:
  if c.regression_anchor:c.success=False;c.confidence=.05
 assert not evaluate_hardening(req(cs))["gates"]["catastrophic_forgetting"]
def test_v51_incomplete_long_horizon_fails():
 cs=cases();cs=[c for c in cs if c.case_id!="c4"]
 assert not evaluate_hardening(req(cs))["gates"]["long_horizon_completion"]
def test_validator_signature_registry():
 r=ValidatorRegistry();priv=ed25519.Ed25519PrivateKey.generate();pub=priv.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw);b64=base64.urlsafe_b64encode(pub).decode().rstrip("=");r.register("lab",b64);payload=req().model_dump(mode="json");sig=base64.urlsafe_b64encode(priv.sign(b"ORBYTHRA-VALIDATOR-V5.1\x00"+canonical(payload))).decode().rstrip("=");assert len(r.verify("lab",payload,sig))==64
def test_validator_signature_tamper_rejected():
 r=ValidatorRegistry();priv=ed25519.Ed25519PrivateKey.generate();pub=priv.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw);b64=base64.urlsafe_b64encode(pub).decode().rstrip("=");r.register("lab",b64);payload=req().model_dump(mode="json");sig=base64.urlsafe_b64encode(priv.sign(b"ORBYTHRA-VALIDATOR-V5.1\x00"+canonical(payload))).decode().rstrip("=");payload["minimum_domains"]=4
 try:r.verify("lab",payload,sig);assert False
 except ValueError as e:assert str(e)=="invalid_validator_signature"
