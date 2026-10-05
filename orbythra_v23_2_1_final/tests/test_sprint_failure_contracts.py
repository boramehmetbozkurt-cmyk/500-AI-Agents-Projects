import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.api import app
from app.security import RATE_LIMITER
from app.web_evidence_v51 import _safe_url, _sentences


@pytest.mark.parametrize('url', ['https://example.com:bad/path', 'https://[broken'])
def test_malformed_source_url_is_client_error(url):
    with pytest.raises(HTTPException) as exc:
        _safe_url(url)
    assert exc.value.status_code == 400


def test_source_sentences_are_scored_individually():
    assert _sentences('First claim. Second claim! Third?') == ['First claim.', 'Second claim!', 'Third?']


@pytest.mark.parametrize('headers', [{}, {'X-API-Key': 'invalid-key'}])
def test_every_protected_operation_rejects_missing_or_invalid_auth(headers):
    from tests.test_all_endpoint_contracts import _operation_request
    document = app.openapi()
    client = TestClient(app, raise_server_exceptions=False)
    checked = 0
    for path, item in document['paths'].items():
        for method, operation in item.items():
            if method not in {'get', 'post', 'put', 'patch', 'delete'}:
                continue
            if not any(p.get('name', '').lower() == 'x-api-key' for p in operation.get('parameters', [])):
                continue
            RATE_LIMITER.reset()
            url, kwargs = _operation_request(path, method, operation, document, checked)
            kwargs['headers'] = headers
            response = client.request(method, url, **kwargs)
            assert response.status_code == 401, (method, path, response.text)
            checked += 1
    assert checked >= 90


def test_registry_outage_has_explicit_503(monkeypatch):
    from app.persistent_validators_v9 import PERSISTENT_VALIDATORS_V9
    def unavailable(*args, **kwargs):
        raise OperationalError('SELECT', {}, Exception('private connection details'))
    monkeypatch.setattr(PERSISTENT_VALIDATORS_V9, 'get', unavailable)
    RATE_LIMITER.reset()
    response = TestClient(app, raise_server_exceptions=False).post('/v9/trust/quorum', headers={'X-API-Key':'test-secret'}, json={
        'payload_sha256':'a'*64, 'nonce':'outage-nonce-123', 'minimum_validators':1,
        'attestations':[dict(validator_id='outage', decision='PASS', payload_sha256='a'*64, nonce='outage-nonce-123', issued_at=1, signature_b64='x')]})
    assert response.status_code == 503
    assert response.json()['detail'] == 'validator_registry_unavailable'
    assert 'private connection' not in response.text
