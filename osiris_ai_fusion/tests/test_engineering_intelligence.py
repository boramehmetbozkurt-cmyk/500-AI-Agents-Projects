from pathlib import Path

import pytest

import engineering_intelligence as engineering
from engineering_intelligence import EngineeringProblem, audit_engineering_answer
from llm import ModelResult


def test_canonical_engineering_prompt_is_present():
    prompt = engineering.load_engineering_system_prompt()
    assert "ÇOK KATMANLI ÜRETİM, TASARIM VE ANALİZ ZEKÂSI" in prompt
    assert "TOPRAK" in prompt
    assert "FMEA" in prompt
    assert "BİLİNMEYENLER" in prompt
    assert Path(engineering.PROMPT_PATH).exists()


def test_engineering_audit_requires_core_sections_and_modes():
    answer = """
    1. KARAR
    karar
    2. GEREKÇE
    gerekçe
    TOPRAK SU ATEŞ HAVA
    FMEA
    DOĞRULAMA
    9. BİLİNMEYENLER
    yok
    """
    audit = audit_engineering_answer(answer)
    assert audit["required_sections_complete"] is True
    assert audit["four_modes_complete"] is True
    assert audit["verification_complete"] is True


@pytest.mark.asyncio
async def test_engineering_analysis_repairs_missing_structure(monkeypatch):
    calls = []

    async def fake_generate(self, system, prompt, json_schema=None):
        calls.append(prompt)
        if len(calls) == 1:
            return ModelResult(text="eksik çıktı", provider="test", model="test-model")
        return ModelResult(
            text=(
                "1. KARAR\nX\n2. GEREKÇE\nY\nTOPRAK\nSU\nATEŞ\nHAVA\n"
                "FMEA\nZ\nDOĞRULAMA\nT\n9. BİLİNMEYENLER\nU"
            ),
            provider="test",
            model="test-model",
        )

    monkeypatch.setattr(engineering.ModelRouter, "generate", fake_generate)
    result = await engineering.analyze_engineering_problem(
        EngineeringProblem(problem="Bir bileşeni tasarla", target="10 yıl ömür")
    )
    assert len(calls) == 2
    assert result.product == "ORBYTHRA"
    assert result.audit["required_sections_complete"] is True
    assert result.audit["four_modes_complete"] is True
    assert result.audit["verification_complete"] is True
