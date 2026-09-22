from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from llm import ModelRouter
from saas import AuthContext, require_identity

PROMPT_VERSION = "2.0"
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "engineering_system_v2_tr.md"
REQUIRED_MARKERS = (
    "1. KARAR",
    "2. GEREKÇE",
    "9. BİLİNMEYENLER",
)
AUDIT_MARKERS = (
    "TOPRAK",
    "SU",
    "ATEŞ",
    "HAVA",
    "FMEA",
    "DOĞRULAMA",
)


class EngineeringProblem(BaseModel):
    problem: str = Field(min_length=3, max_length=12000)
    target: str | None = Field(default=None, max_length=2000)
    budget: str | None = Field(default=None, max_length=1000)
    quantity: str | None = Field(default=None, max_length=1000)
    operating_conditions: str | None = Field(default=None, max_length=2500)
    lifetime: str | None = Field(default=None, max_length=1000)
    standards: list[str] = Field(default_factory=list, max_length=32)
    manufacturing_capability: str | None = Field(default=None, max_length=2500)
    constraints: list[str] = Field(default_factory=list, max_length=64)
    language: str = Field(default="tr", pattern=r"^[a-zA-Z-]{2,12}$")


class EngineeringResult(BaseModel):
    product: str
    mode: str
    prompt_version: str
    provider: str
    model: str
    answer: str
    audit: dict[str, bool]


def load_engineering_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _system_prompt() -> str:
    canonical = load_engineering_system_prompt()
    wrapper = """
ORBYTHRA Engineering Intelligence is an engineering decision mode.
The canonical engineering system prompt below is authoritative for engineering structure.
Do not reveal private chain-of-thought. Provide concise, auditable justifications,
calculations, assumptions, alternatives, risks and verification criteria instead.
Never invent measurements, standards, certifications or test results.
For high-risk engineering, clearly mark where licensed/authorized engineering approval is required.
If a requested datum is missing, label it as unknown/assumption instead of silently filling it in.

--- CANONICAL ENGINEERING SYSTEM PROMPT ---
""".strip()
    return wrapper + "\n\n" + canonical


def _user_prompt(body: EngineeringProblem) -> str:
    rows = [f"PROBLEM:\n{body.problem}"]
    optional = [
        ("HEDEF", body.target),
        ("BÜTÇE", body.budget),
        ("ADET", body.quantity),
        ("ÇALIŞMA KOŞULLARI", body.operating_conditions),
        ("ÖMÜR", body.lifetime),
        ("ÜRETİM İMKÂNI", body.manufacturing_capability),
    ]
    for label, value in optional:
        if value:
            rows.append(f"{label}:\n{value}")
    if body.standards:
        rows.append("İLGİLİ STANDARTLAR / ADAY STANDARTLAR:\n- " + "\n- ".join(body.standards))
    if body.constraints:
        rows.append("EK KISITLAR:\n- " + "\n- ".join(body.constraints))
    rows.append(
        "ÇIKTI DİLİ: " + body.language + "\n"
        "Canonical formatı uygula. Kısa problem olsa bile KARAR, GEREKÇE ve BİLİNMEYENLER "
        "bölümlerini atlama. Dört çalışma modunu tara ve FMEA/doğrulama kriterlerini açıkça ver."
    )
    return "\n\n".join(rows)


def audit_engineering_answer(answer: str) -> dict[str, bool]:
    # A mention in a paragraph (or the user's question echoed back) is not a section.
    headings = []
    for line in answer.splitlines():
        normalized = re.sub(r"^[\s#*_-]+", "", line).strip().upper()
        normalized = re.sub(r"\*", "", normalized).rstrip(": ")
        headings.append(normalized)
    audit = {
        marker: any(
            heading == marker or heading.startswith(marker + " — ")
            or heading.startswith(marker + " - ") or heading.startswith(marker + ":")
            or heading.startswith(marker + " /")
            for heading in headings
        )
        for marker in REQUIRED_MARKERS + AUDIT_MARKERS
    }
    audit["required_sections_complete"] = all(audit[m] for m in REQUIRED_MARKERS)
    audit["four_modes_complete"] = all(audit[m] for m in ("TOPRAK", "SU", "ATEŞ", "HAVA"))
    audit["verification_complete"] = audit["FMEA"] and audit["DOĞRULAMA"]
    audit["structure_valid"] = (
        audit["required_sections_complete"]
        and audit["four_modes_complete"]
        and audit["verification_complete"]
    )
    return audit


async def analyze_engineering_problem(body: EngineeringProblem) -> EngineeringResult:
    router = ModelRouter()
    system = _system_prompt()
    prompt = _user_prompt(body)
    result = await router.generate(system, prompt)
    audit = audit_engineering_answer(result.text)

    if not audit["structure_valid"]:
        repair = (
            prompt
            + "\n\nQUALITY-GATE REPAIR: Önceki çıktı zorunlu denetimi geçmedi. "
            "Yanıtı baştan üret; 1. KARAR, 2. GEREKÇE, TOPRAK/SU/ATEŞ/HAVA, FMEA, "
            "DOĞRULAMA ve 9. BİLİNMEYENLER ifadeleri görünür başlık/alt başlık olarak bulunsun. "
            "Eksik veriyi uydurma."
        )
        result = await router.generate(system, repair)
        audit = audit_engineering_answer(result.text)

    # Keep the answer visible for diagnosis, but never label a failed repair as valid.

    return EngineeringResult(
        product="ORBYTHRA",
        mode="engineering_intelligence",
        prompt_version=PROMPT_VERSION,
        provider=result.provider,
        model=result.model,
        answer=result.text,
        audit=audit,
    )


router = APIRouter(prefix="/engineering", tags=["engineering-intelligence"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def engineering_info(_: Identity) -> dict[str, Any]:
    return {
        "product": "ORBYTHRA",
        "mode": "engineering_intelligence",
        "prompt_version": PROMPT_VERSION,
        "principles": [
            "first_principles",
            "multi_scale_reasoning",
            "cross_discipline_analysis",
            "toprak_su_ates_hava_scan",
            "triz_contradiction",
            "alternative_comparison",
            "fmea",
            "quantitative_verification",
            "unknowns_and_assumptions_separation",
        ],
        "shared_world_integration": "planned: engineering outputs can be bridged into ORBYTHRA World as sourced claims after evidence validation",
    }


@router.get("/prompt/meta")
async def engineering_prompt_meta(_: Identity) -> dict[str, Any]:
    prompt = load_engineering_system_prompt()
    return {
        "product": "ORBYTHRA",
        "version": PROMPT_VERSION,
        "path": "prompts/engineering_system_v2_tr.md",
        "characters": len(prompt),
        "required_sections": list(REQUIRED_MARKERS),
        "audit_markers": list(AUDIT_MARKERS),
    }


@router.post("/analyze", response_model=EngineeringResult)
async def engineering_analyze(body: EngineeringProblem, _: Identity) -> EngineeringResult:
    try:
        return await analyze_engineering_problem(body)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
