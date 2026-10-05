from __future__ import annotations
import hashlib, ipaddress, re, socket, time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest
from pydantic import BaseModel, Field
from app.security import Principal, require_minimum_role
from app.store import STORE

router=APIRouter(prefix="/v5.1/web-evidence",tags=["web-evidence-verification"])
_REQUIRE_OPERATOR=require_minimum_role("operator")
_TOKEN=re.compile(r"[^\W_]+",re.UNICODE)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
class TextExtractor(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in {"script","style","noscript"}:self.skip+=1
    def handle_endtag(self,tag):
        if tag in {"script","style","noscript"} and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)
class WebSource(BaseModel):
    source_id:str=Field(min_length=1,max_length=200);url:str=Field(min_length=8,max_length=2000)
class WebVerifyRequest(BaseModel):
    request_id:str=Field(min_length=8,max_length=128);claims:list[str]=Field(min_length=1,max_length=50);sources:list[WebSource]=Field(min_length=1,max_length=20)
    timeout_seconds:float=Field(default=5,ge=1,le=10);max_bytes:int=Field(default=500000,ge=10000,le=2000000);minimum_token_overlap:float=Field(default=.55,ge=.1,le=1)
class SourceSnapshot(BaseModel):
    source_id:str;url:str;status:str;content_sha256:str|None=None;fetched_at:int|None=None;published_at:str|None=None;bytes_read:int=0
class ClaimWebVerdict(BaseModel):
    claim:str;status:str;supporting_sources:list[str];contradicting_sources:list[str]=[];score:float;consensus:float=0.0;best_excerpt:str|None=None
class WebVerifyResponse(BaseModel):
    request_id:str;status:str;claim_verdicts:list[ClaimWebVerdict];sources:list[SourceSnapshot];snapshot_id:str|None=None
    boundary:str="Network retrieval and lexical entailment signals are evidence discovery, not proof of factual truth. Retrieved text remains untrusted input."

def _public_host(host:str)->None:
    if not host or host.lower() in {"localhost","localhost.localdomain"}:raise HTTPException(400,"private_or_invalid_source_host")
    try:addrs=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
    except socket.gaierror as e:raise HTTPException(400,"source_dns_resolution_failed") from e
    for a in addrs:
        ip=ipaddress.ip_address(a[4][0])
        if not ip.is_global:raise HTTPException(400,"private_or_reserved_source_address")
def _safe_url(url:str)->None:
    try:
        p=urlparse(url)
        port=p.port
    except ValueError as exc:raise HTTPException(400,"source_url_must_be_public_https") from exc
    if p.scheme!="https" or not p.hostname or p.username or p.password or port not in (None,443):raise HTTPException(400,"source_url_must_be_public_https")
    _public_host(p.hostname)
def _fetch(src:WebSource,timeout:float,max_bytes:int)->tuple[SourceSnapshot,str]:
    _safe_url(src.url);req=Request(src.url,headers={"User-Agent":"ORBYTHRA-WebEvidence/5.1","Accept":"text/html,text/plain;q=0.9"})
    try:
        with build_opener(NoRedirect).open(req,timeout=timeout) as r:
            ctype=(r.headers.get("Content-Type") or "").lower()
            if "text/html" not in ctype and "text/plain" not in ctype:raise HTTPException(415,"unsupported_source_content_type")
            raw=r.read(max_bytes+1)
            if len(raw)>max_bytes:raise HTTPException(413,"source_too_large")
            charset=r.headers.get_content_charset() or "utf-8";txt=raw.decode(charset if charset.lower() in {"utf-8","utf8","ascii","iso-8859-1","latin-1","windows-1252"} else "utf-8",errors="replace")
            if "text/html" in ctype:
                x=TextExtractor();x.feed(txt);txt=" ".join(x.parts)
            txt=" ".join(txt.split());published=r.headers.get("Last-Modified")
            return SourceSnapshot(source_id=src.source_id,url=src.url,status="FETCHED",content_sha256=hashlib.sha256(raw).hexdigest(),fetched_at=int(time.time()),published_at=published,bytes_read=len(raw)),txt[:500000]
    except HTTPException:raise
    except (HTTPError,URLError,TimeoutError,OSError) as e:raise HTTPException(502,f"source_fetch_failed:{src.source_id}") from e
def _tokens(s:str)->set[str]:return {x.lower() for x in _TOKEN.findall(s) if len(x)>2}
def _score(claim:str,text:str)->float:
    c=_tokens(claim)
    if not c:return 0.0
    t=_tokens(text);return len(c&t)/len(c)
def _sentences(text:str)->list[str]:
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+',text) if x.strip()][:4000]
_NEG={'not','no','never','without','false','incorrect',"isn't","wasn't","doesn't","didn't",'değil','yok','hayır','yanlış'}
def _semantic_signal(claim:str,text:str)->tuple[float,bool,str]:
    ct=_tokens(claim);best=0.0;best_sentence='';contradiction=False;claim_neg=bool(ct&_NEG)
    for sent in _sentences(text):
        st=_tokens(sent)
        if not st:continue
        overlap=len(ct&st)/max(1,len(ct));precision=len(ct&st)/max(1,len(st));score=.75*overlap+.25*min(1.0,precision*3)
        if score>best:best,best_sentence=score,sent[:500]
        if score>=.55 and bool(st&_NEG)!=claim_neg:contradiction=True
    return round(best,4),contradiction,best_sentence

@router.post("/verify",response_model=WebVerifyResponse)
def verify(body:WebVerifyRequest,request:FastAPIRequest,principal:Principal=Depends(_REQUIRE_OPERATOR)):
    snaps=[];texts={}
    for src in body.sources:
        snap,txt=_fetch(src,body.timeout_seconds,body.max_bytes);snaps.append(snap);texts[src.source_id]=txt
    verdicts=[]
    for claim in body.claims:
        signals=[]
        for sid,txt in texts.items():
            score,contra,excerpt=_semantic_signal(claim,txt);signals.append((sid,score,contra,excerpt))
        signals.sort(key=lambda x:x[1],reverse=True)
        support=[sid for sid,score,contra,_ in signals if score>=body.minimum_token_overlap and not contra]
        contradict=[sid for sid,score,contra,_ in signals if score>=body.minimum_token_overlap and contra]
        best=signals[0][1] if signals else 0.0;consensus=len(support)/max(1,len(signals))
        status='CONTRADICTED' if contradict else ('EVIDENCE_FOUND' if support else 'NOT_ESTABLISHED')
        verdicts.append(ClaimWebVerdict(claim=claim,status=status,supporting_sources=support,contradicting_sources=contradict,score=best,consensus=round(consensus,4),best_excerpt=signals[0][3] if signals else None))
    evidence=[s.model_dump(mode="json") for s in snaps]
    snap=STORE.create_evidence_snapshot(workspace_id=principal.workspace_id,principal_id=principal.principal_id,label="web-evidence:"+body.request_id,evidence=evidence)
    status="PASS" if all(v.status=="EVIDENCE_FOUND" and v.consensus>0 for v in verdicts) else ("FAIL" if any(v.status=="CONTRADICTED" for v in verdicts) else "REVIEW")
    STORE.record_audit(request_id=getattr(request.state,"request_id",body.request_id),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="web_evidence_verification",status=status,metadata={"snapshot_id":snap["snapshot_id"],"claims":len(body.claims),"sources":len(snaps)})
    return WebVerifyResponse(request_id=body.request_id,status=status,claim_verdicts=verdicts,sources=snaps,snapshot_id=snap["snapshot_id"])
