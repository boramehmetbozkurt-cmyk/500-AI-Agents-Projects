"""Execute assessor-owned JSONL HTTP cases against a controlled deployment.

No bundled synthetic dataset is claimed as independent validation. Requests can
mutate the target: use an isolated assessor deployment and dedicated credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import httpx

CATEGORIES = {
    'claim_evidence', 'engineering_reasoning', 'first_principles',
    'quantitative_traceability', 'temporal_reality', 'distributed_verification',
    'governed_actions', 'security', 'tenant_isolation', 'failure_behaviour',
}


def load_cases(path, minimum=1000):
    raw = Path(path).read_bytes()
    cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    ids = set()
    for case in cases:
        cid = case['case_id']
        if not cid or cid in ids:
            raise ValueError('missing_or_duplicate_case_id')
        ids.add(cid)
        if case['category'] not in CATEGORIES:
            raise ValueError('unknown_category')
        path = case['path']
        if not path.startswith('/') or path.startswith('//') or '\\' in path or urlsplit(path).netloc:
            raise ValueError('case_path_must_be_relative')
        if case.get('method', 'GET') not in {'GET','POST','PUT','PATCH','DELETE'}:
            raise ValueError('invalid_method')
        if case.get('auth', 'valid') not in {'valid','missing','invalid'}:
            raise ValueError('invalid_auth_mode')
        if not 100 <= case['expected_status'] <= 599:
            raise ValueError('invalid_expected_status')
        if case['expected_status'] < 300 and not case.get('expected_json'):
            raise ValueError('successful_cases_require_semantic_assertions')
    counts = Counter(c['category'] for c in cases)
    if len(cases) < minimum or (minimum >= 1000 and set(counts) != CATEGORIES):
        raise ValueError('insufficient_cases_or_categories')
    return cases, hashlib.sha256(raw).hexdigest()


def execute(cases, client, api_key):
    rows = []
    for case in cases:
        headers = {'X-Workspace-ID': case.get('workspace', 'external-validation')}
        auth = case.get('auth', 'valid')
        if auth != 'missing':
            headers['X-API-Key'] = api_key if auth == 'valid' else 'deliberately-invalid'
        try:
            response = client.request(case.get('method', 'GET'), case['path'], headers=headers, json=case.get('body'))
            assertions = case.get('expected_json', {})
            body = response.json() if assertions else {}
            matched = all(body.get(key) == value for key, value in assertions.items())
            passed = response.status_code == case['expected_status'] and matched
            row = {'case_id':case['case_id'], 'category':case['category'], 'passed':passed,
                   'http_status':response.status_code, 'response_sha256':hashlib.sha256(response.content).hexdigest()}
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            row = {'case_id':case['case_id'], 'category':case['category'], 'passed':False, 'error_type':type(exc).__name__}
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases')
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--release-sha', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    cases, fingerprint = load_cases(args.cases)
    key = os.environ['ORBYTHRA_EVALUATOR_API_KEY']
    with httpx.Client(base_url=args.base_url, timeout=30, follow_redirects=False) as client:
        version = client.get('/v1/system/version', headers={'X-API-Key':key}).json()
        if args.release_sha not in {version.get('commit_sha'), version.get('release_sha')}:
            raise SystemExit('target_release_sha_mismatch')
        rows = execute(cases, client, key)
    report = {'protocol':'orbythra-external-harness-v1', 'release_sha':args.release_sha,
              'dataset_sha256':fingerprint, 'total':len(rows), 'passed':sum(r['passed'] for r in rows),
              'independent_validation_claim':False, 'results':rows}
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    Path(args.output).write_bytes(raw)
    Path(args.output + '.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    raise SystemExit(0 if all(r['passed'] for r in rows) else 1)


if __name__ == '__main__':
    main()
