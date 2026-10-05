from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.attachments import Attachment, resolve_attachments
from app.config import SETTINGS
from app.model_adapters_v10 import GovernedHttpModelAdapter
from app.model_output_assurance_v51 import EvidenceRef, OutputAssuranceRequest, evaluate as assure_model_output
from app.models import Claim, EngineeringRequest, EvidenceItem, PlanRequest, VerifyRequest
from app.providers import evidence_provider, google_search_provider, keyless_search_provider, status as provider_status
from app.security import Principal, require_minimum_role
from app.services.adaptive import build_plan
from app.services.engineering import build_engineering_envelope
from app.services.evidence import verify as verify_evidence
from app.store import STORE
from app.web_evidence_v51 import WebSource, _fetch as fetch_public_source

router = APIRouter(prefix="/v11/answer", tags=["v11-unified-answer"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


_LANGUAGE_NAMES = {
    "en": "English", "tr": "Turkish", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "ar": "Arabic",
}

def _detect_language(text: str) -> str:
    """Best-effort query language detection for the seven supported UI languages.

    This intentionally avoids an external dependency. It is used only to tell the
    answer generator which language to reply in; it is not treated as evidence.
    """
    raw = text.casefold()
    if re.search(r"[\u0600-\u06ff]", raw):
        return "ar"
    q = " " + re.sub(r"[^\w'’]+", " ", raw, flags=re.UNICODE) + " "
    if re.search(r"[\u0600-\u06ff]", q):
        return "ar"
    markers = {
        "tr": (" nedir ", " kimdir ", " nasıl ", " neden ", " hangi ", " ne zaman ", " için ", " hakkında ", "ş", "ğ", "ı"),
        "de": (" was ist ", " wer ist ", " wie ", " warum ", " welche ", " und ", " der ", " die ", " das ", " für ", "ß"),
        "fr": (" qu'est-ce ", " qu'est ce ", " qui est ", " comment ", " pourquoi ", " quel ", " quelle ", " les ", " des ", " pour ", "ç", "œ"),
        "es": (" qué es ", " quien es ", " quién es ", " cómo ", " por qué ", " cual ", " cuál ", " para ", " los ", " las ", "¿", "ñ"),
        "it": (" che cos'è ", " che cosa ", " chi è ", " come ", " perché ", " quale ", " per ", " gli ", " della ", " è "),
    }
    scores = {lang: sum(2 if len(m.strip()) > 2 else 1 for m in marks if m in q) for lang, marks in markers.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "en"


class UnifiedAnswerRequest(BaseModel):
    query: str = Field(min_length=3, max_length=12000)
    mode: Literal["AUTO", "WEB_RESEARCH", "AI_ANALYSIS"] = "AUTO"
    model_id: str | None = Field(default=None, max_length=200)
    max_sources: int = Field(default=5, ge=1, le=8)
    # Workspace-scoped ids returned by POST /v11/answer/files. Their text becomes
    # direct evidence so the agent can answer questions about uploaded files.
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


class UnifiedSource(BaseModel):
    source_id: str
    title: str
    url: str
    publisher: str | None = None
    published_at: str | None = None
    retrieved_at: int
    snippet: str | None = None
    source_type: str
    direct_fetch: bool = False
    evidence_status: Literal["DIRECT_EVIDENCE", "DISCOVERY_ONLY", "USER_FILE"] = "DISCOVERY_ONLY"


class PipelineStep(BaseModel):
    step: str
    status: Literal["PASS", "REVIEW", "ERROR"]
    detail: str
    endpoint: str | None = None


class UnifiedAnswerResponse(BaseModel):
    query: str
    answer_language: str | None = None
    status: Literal["PASS", "REVIEW", "BLOCKED", "ERROR"]
    answer: str | None = None
    confidence: float | None = None
    sources: list[UnifiedSource] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    pipeline: list[PipelineStep] = Field(default_factory=list)
    receipt: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    effective_mode: str | None = None
    boundary: str = (
        "ORBYTHRA verifies evidence bindings, contradictions, freshness and release controls. "
        "Search and model providers remain external inputs; PASS is a scoped verification result, not omniscience."
    )


def _tokens(text: str) -> set[str]:
    return {x.lower() for x in _WORD.findall(text) if len(x) > 2}


def _overlap(a: str, b: str) -> float:
    left = _tokens(a)
    if not left:
        return 0.0
    right = _tokens(b)
    return len(left & right) / len(left)


def _is_general_factual(query: str) -> bool:
    """Broad factual/definition intent. This alone must not force fail-closed web mode.

    Static questions such as "What is Bitcoin?" / "BTC nedir?" may be answered
    from the configured model while web search is used opportunistically for evidence.
    """
    q = query.lower().strip()
    terms = (
        "nedir", "ne demek", "what is", "what are", "when", "where",
        "ne zaman", "nerede", "kaç", "hangi",
    )
    return any(term in q for term in terms) or q.startswith(("what ", "when ", "where ", "ne ", "hangi "))


def _is_person_lookup(query: str) -> bool:
    """Person/profile/title lookups require direct external evidence in AUTO mode."""
    q = query.lower().strip()
    person_terms = (
        " kimdir", "who is ", "ceo", "president", "başkan", "founder", "kurucusu",
        "linkedin", "profile", "profil",
    )
    return q.startswith(("who ", "kim ")) or any(term in q for term in person_terms)


def _requires_strict_external_evidence(query: str) -> bool:
    """Queries where stale/model-only output should not be released as an answer."""
    q = query.lower().strip()
    market_terms = ("price", "fiyat", "exchange rate", "döviz", "kur ")
    return (
        _is_time_sensitive(query)
        or _is_person_lookup(query)
        or _risk_tier(query) == "high"
        or any(term in q for term in market_terms)
    )


def _is_time_sensitive(query: str) -> bool:
    q = query.lower().strip()
    terms = (
        "today", "latest", "current", "currently", "now", "recent", "this week", "this month",
        "bugün", "güncel", "şu an", "şimdiki", "son durum", "en son", "bu hafta", "bu ay",
        "current ceo", "current president", "mevcut ceo", "mevcut başkan",
    )
    return any(term in q for term in terms)


def _is_engineering(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in ("engineering", "mühendis", "architecture", "mimari", "system design", "teknik", "latency", "throughput", "api", "backend", "frontend"))


def _risk_tier(query: str) -> str:
    q = query.lower()
    high = (
        "diagnosis", "treatment", "dose", "medication", "medical", "health",
        "tanı", "tedavi", "doz", "ilaç", "sağlık",
        "legal advice", "lawsuit", "hukuki tavsiye", "dava",
        "investment advice", "buy stock", "sell stock", "yatırım tavsiyesi", "hisse al", "hisse sat",
    )
    return "high" if any(term in q for term in high) else "moderate"


def _configuration_sha(mode: str, model_id: str, routed: list[str]) -> str:
    raw = json.dumps(
        {"mode": mode, "model_id": model_id, "routed_endpoints": routed, "release": SETTINGS.release_sha},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _authority(url: str) -> float:
    if url.startswith("attachment://"):
        # User-supplied file: authoritative for questions about that file itself.
        return 0.75
    host = (urlparse(url).hostname or "").lower()
    if host.endswith(".gov") or ".gov." in host or host.endswith(".edu") or ".edu." in host:
        return 0.9
    if host:
        return 0.68
    return 0.0


def _best_excerpt(query: str, text: str) -> str:
    sentences = [s.strip() for s in _SENTENCE.split(" ".join(text.split())) if len(s.strip()) >= 20]
    if not sentences:
        return " ".join(text.split())[:700]
    def _quality(sentence: str) -> float:
        words = sentence.split()
        if not words:
            return 0.0
        # Sentence-like text has lower-case words and ends with punctuation; nav/menu text does not.
        lowercase_ratio = sum(1 for w in words if w[:1].islower()) / len(words)
        ends_well = 1.0 if sentence[-1] in ".!?" else 0.6
        length_ok = 1.0 if 40 <= len(sentence) <= 400 else 0.7
        return lowercase_ratio * ends_well * length_ok

    ranked = sorted(sentences[:3000], key=lambda s: (_overlap(query, s) * (0.5 + _quality(s)), min(len(s), 500)), reverse=True)
    return ranked[0][:700]


def _normalize_generic_results(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows = payload.get("results", [])
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:limit], start=1):
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or row.get("link") or "").strip()
        if not url:
            continue
        normalized.append({
            "source_id": str(row.get("source_id") or f"provider-{index}")[:200],
            "title": str(row.get("title") or url)[:500],
            "url": url[:2000],
            "publisher": str(row.get("publisher") or row.get("domain") or "")[:300],
            "snippet": str(row.get("snippet") or row.get("text") or "")[:4000],
            "full_text": str(row.get("full_text") or "")[:100000],
            "published_at": str(row.get("published_at") or "")[:120] or None,
            "source_type": str(row.get("source_type") or "evidence_provider")[:120],
        })
    return normalized


def _search(query: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    """Tool: web discovery. Keyed providers first, keyless DuckDuckGo/Bing last."""
    google = google_search_provider()
    if google is not None:
        return google.search(query, limit=limit), "google"
    generic = evidence_provider()
    if generic is not None:
        payload = generic.post_json("/search", {"query": query, "limit": limit}, timeout=15)
        return _normalize_generic_results(payload, limit), "evidence_provider"
    if getattr(provider_status(), "keyless_search_configured", False):
        keyless = keyless_search_provider()
        if keyless is not None:
            return keyless.search(query, limit=limit), "keyless_web_search"
    raise RuntimeError("search_provider_unavailable")


def _web_search_available(providers: Any) -> bool:
    return bool(
        getattr(providers, "google_search_configured", False)
        or getattr(providers, "evidence_provider_configured", False)
        or getattr(providers, "keyless_search_configured", False)
    )


def _attachment_sources(attachments: list[Attachment]) -> tuple[list[UnifiedSource], dict[str, str]]:
    """Tool: file context. Uploaded files are direct evidence the agent can cite."""
    now = int(time.time())
    sources: list[UnifiedSource] = []
    texts: dict[str, str] = {}
    for item in attachments:
        if not item.text:
            continue
        texts[item.attachment_id] = item.text[:100000]
        sources.append(UnifiedSource(
            source_id=item.attachment_id,
            title=item.filename,
            url=f"attachment://{item.attachment_id}",
            publisher="user_upload",
            published_at=None,
            retrieved_at=now,
            snippet=item.text[:400],
            source_type="attachment",
            direct_fetch=True,
            evidence_status="USER_FILE",
        ))
    return sources, texts


def _mentions_file(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in (
        "file", "document", "attached", "attachment", "upload", "pdf", "csv", "this text", "the text",
        "dosya", "belge", "döküman", "doküman", "ekte", "ekli", "yükle", "bu metin", "metinde", "içerik", "özetle", "summarize",
    ))


def _collect_direct_evidence(
    discovered: list[dict[str, Any]],
) -> tuple[list[UnifiedSource], dict[str, str], list[str]]:
    now = int(time.time())
    sources: list[UnifiedSource] = []
    texts: dict[str, str] = {}
    warnings: list[str] = []
    for item in discovered:
        source_id = str(item.get("source_id") or uuid.uuid4().hex)[:200]
        url = str(item.get("url") or "")[:2000]
        publisher = str(item.get("publisher") or (urlparse(url).hostname or ""))[:300]
        published_at = item.get("published_at") or None
        # Search-provider snippets/full_text are discovery metadata, not evidence.
        # A web result becomes evidence only after ORBYTHRA independently fetches
        # the underlying public HTTPS source through the web-evidence controls.
        direct = False
        text = ""
        if url:
            try:
                # Percent-encode non-ASCII URL characters (e.g. Wikipedia titles) before fetching.
                safe_url = quote(url, safe=":/?&=#%+@;,~!$'()*[]")
                snap, fetched = fetch_public_source(WebSource(source_id=source_id, url=safe_url), 6.0, 1_500_000)
                text = fetched.strip()
                direct = bool(text)
                published_at = snap.published_at or published_at
            except Exception:
                warnings.append(f"direct_source_fetch_failed:{source_id}")
        if direct:
            texts[source_id] = text[:100000]
        sources.append(UnifiedSource(
            source_id=source_id,
            title=str(item.get("title") or url)[:500],
            url=url,
            publisher=publisher or None,
            published_at=str(published_at)[:120] if published_at else None,
            retrieved_at=now,
            # Never expose an unfetched search snippet as if it were evidence.
            snippet=(" ".join(text.split())[:700] or None) if direct else None,
            source_type=str(item.get("source_type") or "web")[:120],
            direct_fetch=direct,
            evidence_status="DIRECT_EVIDENCE" if direct else "DISCOVERY_ONLY",
        ))
    return sources, texts, warnings


def _source_pack(query: str, sources: list[UnifiedSource], texts: dict[str, str]) -> str:
    blocks: list[str] = []
    for source in sources:
        text = texts.get(source.source_id, "")
        if not text:
            # Discovery-only records must never enter the factual generation context.
            continue
        excerpt = _best_excerpt(query, text)
        blocks.append(
            f"SOURCE {source.source_id}\nTITLE: {source.title}\nURL: {source.url}\nEXCERPT: {excerpt}"
        )
    return "\n\n".join(blocks)


def _generate_answer(
    *, query: str, model_id: str, sources: list[UnifiedSource], texts: dict[str, str], response_language: str | None = None
) -> tuple[str, float, str, list[str]]:
    warnings: list[str] = []
    provider_state = provider_status()
    if provider_state.llm_provider_configured:
        source_pack = _source_pack(query, sources, texts)
        language_code = response_language or _detect_language(query)
        language_name = _LANGUAGE_NAMES.get(language_code, "English")
        prompt = (
            "You are the answer-generation component inside ORBYTHRA. Answer the user's question directly and concisely. "
            f"Reply in {language_name}, matching the language of the user's query. Preserve URLs, code, identifiers and quoted source names as-is. "
            "When a SOURCE PACK is present, use only facts supported by that pack; do not invent citations or facts. "
            "If evidence is insufficient, explicitly say what cannot be established. Prefer 1-4 clear declarative sentences.\n\n"
            f"USER QUERY:\n{query}\n\nSOURCE PACK:\n{source_pack or '[no external evidence supplied]'}"
        )
        generated = GovernedHttpModelAdapter(timeout=25).generate(model_id=model_id, prompt=prompt)
        return generated["output"].strip(), float(generated["confidence"]), "governed_llm_provider", warnings

    excerpts = [_best_excerpt(query, texts[s.source_id]) for s in sources if s.source_id in texts]
    excerpts = [x for x in excerpts if x]
    if excerpts:
        warnings.append("llm_provider_not_configured:using_extractive_source_answer")
        answer = " ".join(dict.fromkeys(excerpts[:2]))
        confidence = min(0.72, 0.55 + 0.06 * len(excerpts[:2]))
        return answer, confidence, "extractive_direct_source", warnings
    raise RuntimeError("llm_provider_not_configured")


def _claims(answer: str) -> list[str]:
    parts = [x.strip() for x in _SENTENCE.split(" ".join(answer.split())) if len(x.strip()) >= 8]
    if not parts and answer.strip():
        parts = [answer.strip()]
    return list(dict.fromkeys(parts))[:8]


def _evidence_refs(claims: list[str], sources: list[UnifiedSource], texts: dict[str, str]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for source in sources:
        text = texts.get(source.source_id)
        if not text:
            continue
        supports = [claim for claim in claims if _overlap(claim, text) >= 0.45]
        refs.append(EvidenceRef(
            source_id=source.source_id,
            # attachment:// pseudo-URLs are not web sources; the assurance gate expects HTTP(S) or None.
            url=source.url if source.url.startswith(("http://", "https://")) else None,
            supports=supports,
            contradicts=[],
            observed_at=source.retrieved_at,
            text=text[:100000],
        ))
    return refs


def _v1_verification(query: str, claims: list[str], sources: list[UnifiedSource], texts: dict[str, str]) -> dict[str, Any]:
    evidence_items: list[EvidenceItem] = []
    for source in sources:
        text = texts.get(source.source_id)
        if not text:
            continue
        best_support = max((_overlap(claim, text) for claim in claims), default=0.0)
        evidence_items.append(EvidenceItem(
            id=source.source_id,
            url=source.url if source.url.startswith(("http://", "https://")) else None,
            title=source.title,
            support=min(1.0, best_support * 1.25),
            authority=_authority(source.url),
            retrieved_at=datetime.fromtimestamp(source.retrieved_at, tz=UTC),
            contradicts=False,
        ))
    claim_models: list[Claim] = []
    for index, claim in enumerate(claims, start=1):
        bound = [source.source_id for source in sources if source.source_id in texts and _overlap(claim, texts[source.source_id]) >= 0.25]
        claim_models.append(Claim(
            id=f"claim-{index}",
            text=claim,
            evidence_ids=bound,
            time_sensitive=_is_time_sensitive(query),
        ))
    if not claim_models:
        return {"disposition": "ABSTAIN_OR_QUALIFY", "verdicts": [], "evidence_gate_pass_rate": 0.0}
    result = verify_evidence(VerifyRequest(
        claims=claim_models,
        evidence=evidence_items,
        minimum_support=0.65,
        minimum_authority=0.60,
        max_age_days=30,
    ))
    return result.model_dump(mode="json")


def _error_response(query: str, code: str, pipeline: list[PipelineStep], warnings: list[str], mode: str | None = None) -> UnifiedAnswerResponse:
    return UnifiedAnswerResponse(
        query=query,
        status="ERROR",
        verification={"passed": False, "failed_gates": [], "error_code": code},
        pipeline=pipeline,
        warnings=warnings,
        error_code=code,
        effective_mode=mode,
    )


@router.post("", response_model=UnifiedAnswerResponse)
def answer(body: UnifiedAnswerRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> UnifiedAnswerResponse:
    query = body.query.strip()
    answer_language = _detect_language(query)
    request_id = "answer-" + uuid.uuid4().hex
    nonce = secrets.token_hex(24)
    pipeline: list[PipelineStep] = [PipelineStep(step="understanding_question", status="PASS", detail="query accepted")]
    warnings: list[str] = []
    routed: list[str] = []

    providers = provider_status()
    web_search_ok = _web_search_available(providers)

    # Tool: file context (uploaded attachments become direct evidence).
    attachments, missing_attachments = resolve_attachments(principal.workspace_id, body.attachment_ids)
    if missing_attachments:
        warnings.append("attachments_not_found_or_expired:" + ",".join(missing_attachments)[:500])
    attachment_sources, attachment_texts = _attachment_sources(attachments)
    has_files = bool(attachment_texts)

    if body.mode == "WEB_RESEARCH":
        effective_mode = "WEB_RESEARCH"
    elif body.mode == "AI_ANALYSIS":
        effective_mode = "AI_ANALYSIS"
    elif has_files and (_mentions_file(query) or not _requires_strict_external_evidence(query)):
        # Questions about an uploaded file are answered from the file first.
        effective_mode = "AI_ANALYSIS"
    elif _requires_strict_external_evidence(query) and web_search_ok:
        # Current/person/high-risk/market-data questions must have direct evidence.
        effective_mode = "WEB_RESEARCH"
    elif not providers.llm_provider_configured and web_search_ok:
        effective_mode = "WEB_RESEARCH"
    else:
        effective_mode = "AI_ANALYSIS"

    # Agent tool selection: the agent decides which tools to run for this query.
    use_search = effective_mode == "WEB_RESEARCH" or (
        effective_mode == "AI_ANALYSIS" and web_search_ok and not (has_files and body.mode == "AUTO")
    )
    selected_tools = (["file_context"] if has_files else []) + (["web_search"] if use_search else [])
    if attachments and not has_files:
        warnings.append("attachments_have_no_extractable_text")
    pipeline.append(PipelineStep(
        step="tool_selection",
        status="PASS",
        detail=f"tools={','.join(selected_tools) or 'none'}; attachments={len(attachment_texts)}; mode={effective_mode}",
    ))

    plan = build_plan(PlanRequest(query=query))
    routed.append("/v1/plan")
    pipeline.append(PipelineStep(step="planning", status="PASS", detail=f"complexity={plan.complexity}; modes={','.join(plan.modes)}", endpoint="/v1/plan"))

    engineering: dict[str, Any] | None = None
    if _is_engineering(query):
        env = build_engineering_envelope(EngineeringRequest(problem=query))
        engineering = env.model_dump(mode="json")
        routed.append("/v1/engineering/envelope")
        pipeline.append(PipelineStep(step="engineering_analysis", status="PASS", detail=env.decision_status, endpoint="/v1/engineering/envelope"))

    discovered: list[dict[str, Any]] = []
    sources: list[UnifiedSource] = list(attachment_sources)
    texts: dict[str, str] = dict(attachment_texts)
    if has_files:
        pipeline.append(PipelineStep(
            step="reading_attachments",
            status="PASS",
            detail=f"files={len(attachment_texts)}; chars={sum(len(t) for t in attachment_texts.values())}",
            endpoint="/v11/answer/files",
        ))
    if use_search:
        try:
            discovered, search_provider_name = _search(query, body.max_sources)
            pipeline.append(PipelineStep(step="searching_sources", status="PASS", detail=f"provider={search_provider_name}; results={len(discovered)}"))
            web_sources, web_texts, source_warnings = _collect_direct_evidence(discovered)
            sources.extend(web_sources)
            texts.update(web_texts)
            warnings.extend(source_warnings)
            routed.append("/v5.1/web-evidence/verify")
            pipeline.append(PipelineStep(
                step="collecting_evidence",
                status="PASS" if web_texts else "REVIEW",
                detail=f"direct_web_sources={len(web_texts)}/{len(web_sources)}; discovery_only={len(web_sources)-len(web_texts)}",
                endpoint="/v5.1/web-evidence/verify",
            ))
            if effective_mode == "WEB_RESEARCH" and not web_texts and not attachment_texts:
                warnings.append("verified_evidence_unavailable:discovery_results_not_promoted_to_evidence")
                pipeline.append(PipelineStep(
                    step="evidence_release_gate",
                    status="REVIEW",
                    detail="No directly fetched evidence; answer generation blocked",
                    endpoint="/v5.1/web-evidence/verify",
                ))
                return UnifiedAnswerResponse(
                    query=query,
                    answer_language=answer_language,
                    status="BLOCKED",
                    answer=None,
                    confidence=None,
                    sources=sources,
                    claims=[],
                    verification={
                        "passed": False,
                        "model_assurance_status": "NOT_RUN",
                        "v1_disposition": "ABSTAIN_OR_QUALIFY",
                        "failed_gates": ["direct_source_evidence"],
                        "direct_source_count": 0,
                        "discovery_source_count": len(web_sources),
                        "evidence_gate_pass_rate": 0.0,
                    },
                    pipeline=pipeline,
                    receipt={"request_id": request_id, "selected_tools": selected_tools, "routed_endpoints": routed},
                    warnings=warnings,
                    error_code="verified_evidence_unavailable",
                    effective_mode=effective_mode,
                )
        except Exception as exc:
            if effective_mode == "WEB_RESEARCH" and not has_files:
                pipeline.append(PipelineStep(step="searching_sources", status="ERROR", detail=f"search provider unavailable or failed: {exc.__class__.__name__}"))
                return _error_response(query, "search_provider_unavailable", pipeline, warnings, effective_mode)
            warnings.append("search_provider_failed:continuing_with_ai_only")
            pipeline.append(PipelineStep(step="searching_sources", status="REVIEW", detail="search unavailable; continuing without external evidence"))

    model_id = (body.model_id or os.getenv("ORBYTHRA_DEFAULT_MODEL_ID", "default")).strip() or "default"
    try:
        generated_answer, confidence, generator, generation_warnings = _generate_answer(
            query=query,
            model_id=model_id,
            sources=sources,
            texts=texts,
            response_language=answer_language,
        )
        warnings.extend(generation_warnings)
        routed.append("/v10/providers/invoke")
        pipeline.append(PipelineStep(step="generating_answer", status="PASS", detail=f"generator={generator}", endpoint="/v10/providers/invoke"))
    except RuntimeError as exc:
        pipeline.append(PipelineStep(step="generating_answer", status="ERROR", detail=str(exc), endpoint="/v10/providers/invoke"))
        return _error_response(query, str(exc), pipeline, warnings, effective_mode)

    claim_texts = _claims(generated_answer)
    v1 = _v1_verification(query, claim_texts, sources, texts)
    routed.append("/v1/verify")
    v1_pass = v1.get("disposition") == "ANSWER"
    pipeline.append(PipelineStep(
        step="checking_claims",
        status="PASS" if v1_pass else "REVIEW",
        detail=f"disposition={v1.get('disposition')}; pass_rate={v1.get('evidence_gate_pass_rate', 0)}",
        endpoint="/v1/verify",
    ))

    if not SETTINGS.release_sha:
        pipeline.append(PipelineStep(step="assurance", status="ERROR", detail="release SHA is not configured", endpoint="/v5.1/model-output/evaluate"))
        return _error_response(query, "release_configuration_missing", pipeline, warnings, effective_mode)

    evidence_refs = _evidence_refs(claim_texts, sources, texts)
    config_sha = _configuration_sha(effective_mode, model_id, routed)
    try:
        assurance = assure_model_output(
            OutputAssuranceRequest(
                request_id=request_id,
                nonce=nonce,
                model_id=model_id,
                prompt=query,
                output=generated_answer,
                confidence=confidence,
                risk_tier=_risk_tier(query),
                evidence=evidence_refs,
                required_claims=claim_texts,
                human_approved=False,
                minimum_evidence_coverage=0.8,
                minimum_confidence=0.5,
                expected_release_sha=SETTINGS.release_sha,
                configuration_sha256=config_sha,
            ),
            request,
            principal,
        )
    except HTTPException as exc:
        code = str(exc.detail)
        pipeline.append(PipelineStep(step="assurance", status="ERROR", detail=code, endpoint="/v5.1/model-output/evaluate"))
        return _error_response(query, code, pipeline, warnings, effective_mode)

    routed.append("/v5.1/model-output/evaluate")
    failed_gates = [gate.name for gate in assurance.gates if not gate.passed]
    if assurance.status == "PASS" and v1_pass and texts:
        final_status: Literal["PASS", "REVIEW", "BLOCKED", "ERROR"] = "PASS"
    elif assurance.status == "REVIEW":
        final_status = "REVIEW"
    else:
        final_status = "BLOCKED"
    if not texts and "direct_source_evidence" not in failed_gates:
        failed_gates.append("direct_source_evidence")
    if not v1_pass and "v1_evidence_gate" not in failed_gates:
        failed_gates.append("v1_evidence_gate")

    pipeline.append(PipelineStep(
        step="assurance",
        status="PASS" if final_status == "PASS" else "REVIEW",
        detail=f"model_assurance={assurance.status}; failed_gates={','.join(failed_gates) or 'none'}",
        endpoint="/v5.1/model-output/evaluate",
    ))

    claims = [item.model_dump(mode="json") for item in assurance.claim_verdicts]
    # Strict WEB_RESEARCH remains fail-closed. AI_ANALYSIS is different: web search
    # is only an evidence-enrichment tool, so lack of directly fetchable evidence
    # must not erase an otherwise safe model answer. The console policy below can
    # downgrade evidence-only failures to REVIEW while preserving the answer.
    release_verified_output = final_status == "PASS"
    reviewable_ai_draft = effective_mode == "AI_ANALYSIS"
    release_answer = release_verified_output or reviewable_ai_draft
    visible_answer = generated_answer if release_answer else None
    visible_claims = claims if release_answer else []
    if use_search and not release_verified_output:
        if reviewable_ai_draft:
            warnings.append("answer_unverified:external_evidence_not_sufficient_for_verified_pass")
        else:
            warnings.append("answer_withheld:verification_not_passed")
    receipt = {
        "request_id": request_id,
        "nonce_sha256": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        "release_sha": SETTINGS.release_sha,
        "configuration_sha256": config_sha,
        "output_sha256": assurance.output_sha256,
        "evidence_manifest_sha256": assurance.evidence_manifest_sha256,
        "routed_endpoints": routed,
        "generator": generator,
        "engineering": engineering,
        "selected_tools": selected_tools,
        "attachment_ids": list(attachment_texts.keys()),
    }
    verification = {
        "passed": final_status == "PASS",
        "model_assurance_status": assurance.status,
        "v1_disposition": v1.get("disposition"),
        "failed_gates": failed_gates,
        "direct_source_count": len(texts),
        "discovery_source_count": sum(1 for source in sources if source.evidence_status == "DISCOVERY_ONLY"),
        "evidence_gate_pass_rate": v1.get("evidence_gate_pass_rate", 0.0),
        "answer_released": visible_answer is not None,
    }
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", request_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="unified_answer_console",
        status=final_status,
        metadata={
            "answer_request_id": request_id,
            "effective_mode": effective_mode,
            "source_count": len(sources),
            "direct_source_count": len(texts),
            "attachment_count": len(attachment_texts),
            "selected_tools": selected_tools,
            "claim_count": len(claim_texts),
            "failed_gates": failed_gates,
            "routed_endpoints": routed,
        },
    )
    return UnifiedAnswerResponse(
        query=query,
        answer_language=answer_language,
        status=final_status,
        answer=visible_answer,
        confidence=round(confidence, 4) if visible_answer is not None else None,
        sources=sources,
        claims=visible_claims,
        verification=verification,
        pipeline=pipeline,
        receipt=receipt,
        warnings=warnings,
        effective_mode=effective_mode,
    )


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    state = provider_status()
    return {
        "release": "11-unified-answer",
        "workspace_id": principal.workspace_id,
        "unified_answer_console": True,
        "google_search_configured": state.google_search_configured,
        "keyless_search_configured": getattr(state, "keyless_search_configured", False),
        "web_search_configured": _web_search_available(state),
        "file_attachments_supported": True,
        "evidence_provider_configured": state.evidence_provider_configured,
        "llm_provider_configured": state.llm_provider_configured,
        "release_binding_configured": bool(SETTINGS.release_sha),
        "automatic_request_id": True,
        "automatic_nonce": True,
        "fail_closed_assurance": True,
        "raw_nonce_exposed": False,
        "advanced_api_explorer_preserved": True,
    }