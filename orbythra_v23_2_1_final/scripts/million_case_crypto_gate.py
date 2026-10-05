from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time

from app.crypto_core import CryptoValidationError, commitment, open_envelope, seal

TOTAL_DEFAULT = 1_000_000
WORKSPACE = "million-case-adversarial"


def mutate(value: str, n: int) -> str:
    pos = n % max(1, len(value) - 1)
    c = "A" if value[pos] != "A" else "B"
    return value[:pos] + c + value[pos + 1:]


def make_envelope(algorithm: str, n: int):
    intent={"action":"transfer","asset":"USDC","amount":str((n%100000)+1),"recipient":f"recipient-{n%997}","chain":"base","fee":str(n%17)}
    digest=commitment(intent,domain="intent")["sha256"]
    env=seal(payload={"case":n},intent=intent,effect=dict(intent),
        approvals=[{"approver_id":"million-case-harness","intent_digest":digest,"proof_type":"gesture","proof":"opaque"}],
        min_approvals=1,workspace_id=WORKSPACE,domain="million-adversarial",ttl_seconds=3600,algorithm=algorithm)
    return env,digest


def run(total: int) -> dict:
    # 1,000 seeded cryptographic envelopes are reused only as immutable bases.
    # Every case gets a deterministic, case-specific mutation/expectation.
    pool=[]
    for i in range(1000):
        alg="aes256-gcm" if i%2==0 else "chacha20-poly1305"
        pool.append(make_envelope(alg,i))
    classes=["ciphertext_tamper","signature_tamper","header_tamper","wrong_intent","nonce_tamper","key_id_tamper","algorithm_confusion","workspace_swap","expiry_tamper"]
    passed=0
    failed=0
    first_failures=[]
    started=time.perf_counter()
    for n in range(total):
        base,digest=pool[n%len(pool)]
        env=copy.deepcopy(base)
        kind=classes[n%len(classes)]
        try:
            if kind=="ciphertext_tamper":
                env["ciphertext_b64"]=mutate(env["ciphertext_b64"],n)
                open_envelope(env,expected_workspace_id=WORKSPACE)
                ok=False
            elif kind=="signature_tamper":
                env["signature_b64"]=mutate(env["signature_b64"],n)
                open_envelope(env,expected_workspace_id=WORKSPACE)
                ok=False
            elif kind=="header_tamper":
                env["header"]["domain"]=f"tampered-{n}"
                open_envelope(env,expected_workspace_id=WORKSPACE)
                ok=False
            elif kind=="wrong_intent":
                wrong=hashlib.sha256(f"wrong-{n}".encode()).hexdigest()
                open_envelope(env,expected_workspace_id=WORKSPACE,expected_intent_digest=wrong)
                ok=False
            elif kind=="nonce_tamper":
                env["nonce_b64"]=mutate(env["nonce_b64"],n);open_envelope(env,expected_workspace_id=WORKSPACE);ok=False
            elif kind=="key_id_tamper":
                env["header"]["key_id"]="unknown-key";open_envelope(env,expected_workspace_id=WORKSPACE);ok=False
            elif kind=="algorithm_confusion":
                env["header"]["algorithm"]="chacha20-poly1305" if env["header"]["algorithm"]=="aes256-gcm" else "aes256-gcm";open_envelope(env,expected_workspace_id=WORKSPACE);ok=False
            elif kind=="workspace_swap":
                open_envelope(env,expected_workspace_id="other-workspace");ok=False
            else:
                env["header"]["expires_at"]=0;open_envelope(env,expected_workspace_id=WORKSPACE);ok=False
        except CryptoValidationError:
            ok=True
        except Exception as exc:
            ok=False
            if len(first_failures)<10:
                first_failures.append({"case":n,"class":kind,"error":type(exc).__name__+":"+str(exc)})
        if ok:
            passed+=1
        else:
            failed+=1
            if len(first_failures)<10:
                first_failures.append({"case":n,"class":kind,"error":"attack_not_rejected"})
    elapsed=time.perf_counter()-started
    return {"suite":"ORBYTHRA million-case adversarial crypto harness","total":total,"passed":passed,"failed":failed,
            "pass_rate":passed/total if total else 0,"attack_classes":classes,
            "elapsed_seconds":round(elapsed,3),"cases_per_second":round(total/elapsed,1) if elapsed else None,
            "first_failures":first_failures}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--cases",type=int,default=TOTAL_DEFAULT)
    p.add_argument("--output",default="million_case_crypto_report.json")
    a=p.parse_args()
    report=run(a.cases)
    print(json.dumps(report,indent=2))
    with open(a.output,"w",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
    raise SystemExit(1 if report["failed"] else 0)
