from engineering_benchmark import evaluate_answer, load_cases


def test_engineering_corpus_is_rights_cleared_and_multi_domain():
    payload = load_cases()
    assert payload["external_validation"] is False
    assert "Original synthetic cases" in payload["rights"]
    assert len(payload["cases"]) >= 5
    assert len({case["domain"] for case in payload["cases"]}) >= 4


def test_engineering_evaluator_rewards_required_structure_and_unknowns():
    case = load_cases()["cases"][0]
    answer = """
1. KARAR
Passive thermal path kullan.
2. GEREKÇE
Thermal resistance, conduction, convection, radiation ve interface etkilerini hesapla.
TOPRAK: enclosure dimensions ve material mekanik yolunu incele.
SU: nem/sıvı etkisini kontrol et.
ATEŞ: surface emissivity ve sıcaklık sınırını kontrol et.
HAVA: doğal convection yolunu hesapla.
FMEA
Aşırı sıcaklık ve contact area belirsizliği arıza modudur.
DOĞRULAMA / verification
Termal test ve model korelasyonu yap.
9. BİLİNMEYENLER
Enclosure dimensions, material, surface emissivity, component contact area.
"""
    result = evaluate_answer(case, answer)
    assert result["scores"]["structure"] == 1.0
    assert result["scores"]["required_topics"] == 1.0
    assert result["scores"]["unknown_handling"] == 1.0
