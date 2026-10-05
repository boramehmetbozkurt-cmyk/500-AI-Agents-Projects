import json
import httpx
import pytest
from scripts.external_validation_harness import CATEGORIES, load_cases, execute


def test_harness_supports_1000_cases_without_claiming_external_results(tmp_path):
    path = tmp_path / 'cases.jsonl'
    cases = [dict(case_id=str(i), category=sorted(CATEGORIES)[i % 10], path='/health', expected_status=200, expected_json={'status':'ok'}) for i in range(1000)]
    path.write_text('\n'.join(map(json.dumps, cases)))
    loaded, digest = load_cases(path)
    assert len(loaded) == 1000 and len(digest) == 64
    with httpx.Client(base_url='https://assessor.invalid', transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'ok'}))) as client:
        rows = execute(loaded, client, 'test-only')
    assert len(rows) == 1000 and all(r['passed'] for r in rows)
    cases[1]['case_id'] = '0'
    path.write_text('\n'.join(map(json.dumps, cases)))
    with pytest.raises(ValueError, match='duplicate'):
        load_cases(path)


def test_harness_rejects_semantic_failure_and_transport_failure():
    cases = [dict(case_id='one', category='failure_behaviour', path='/health', expected_status=200, expected_json={'status':'ok'})]
    with httpx.Client(base_url='https://assessor.invalid', transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'wrong'}))) as client:
        assert execute(cases, client, 'test-only')[0]['passed'] is False
    def timeout(request):
        raise httpx.ConnectTimeout('timeout')
    with httpx.Client(base_url='https://assessor.invalid', transport=httpx.MockTransport(timeout)) as client:
        assert execute(cases, client, 'test-only')[0]['passed'] is False
