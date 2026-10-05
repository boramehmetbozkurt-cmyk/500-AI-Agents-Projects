import base64,time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.distributed_verification_v9 import TRUST_V9,Validator,Attestation,QuorumRequest
def b64(x):return base64.urlsafe_b64encode(x).decode().rstrip("=")
def main():
 xs=[]
 for i in range(3):
  k=ed25519.Ed25519PrivateKey.generate();vid=f"frozen-{i}";pub=b64(k.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw));TRUST_V9.register(Validator(validator_id=vid,public_key_b64=pub,organization=vid));a=Attestation(validator_id=vid,decision="PASS",payload_sha256="d"*64,nonce="frozen-nonce",issued_at=int(time.time()),signature_b64="x");a.signature_b64=b64(k.sign(TRUST_V9.message(a)));xs.append(a)
 r=TRUST_V9.quorum(QuorumRequest(payload_sha256="d"*64,nonce="frozen-nonce",attestations=xs))
 if r["status"]!="PASS" or r["valid_validators"]!=3:raise SystemExit("v9 gate failed")
 print('{"schema":"orbythra.v9-distributed-verification","passed":1,"total":1}')
if __name__=="__main__":main()
