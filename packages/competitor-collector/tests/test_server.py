"""Real loopback HTTP permission tests; collection is a deterministic local fake."""
import base64
import http.cookiejar
import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request
import zipfile

import pytest

from competitor_collector.server import CollectorApp, CollectorHTTPServer

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ''

    def call(self, path, method='GET', payload=None, csrf=True, origin=True, extra=None):
        headers = dict(extra or {})
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
            if origin:
                headers.setdefault('Origin', self.base)
            if csrf:
                headers['X-CSRF-Token'] = self.csrf
        request = Request(self.base + path, data=data, method=method, headers=headers)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as response:
            return response.code, response.headers, response.read()
        with response:
            return response.status, response.headers, response.read()

    def login(self, username, password):
        status, headers, data = self.call('/api/login', 'POST', {'username': username, 'password': password})
        assert status == 200, data
        result = json.loads(data)
        self.csrf = result['csrf_token']
        return headers, result


def fake_runner(payload):
    screenshots = Path(payload['output_dir'])
    screenshots.mkdir(parents=True)
    (screenshots / '01.png').write_bytes(PNG)
    return {'listing': {'title': '合成竞品', 'platform': payload['platform'], 'app_id': payload['app_id'],
                        'market': 'US', 'short_description': '原文短描述', 'long_description': '原文长描述',
                        'screenshot_files': ['01.png']},
            'reviews': [{'review_id': 'r1', 'content': '=literal 👎', 'original_content': '=literal 👎',
                         'translated_content': '', 'score': 1, 'platform': payload['platform'], 'app_id': payload['app_id']}],
            'warnings': [], 'filter_stats': {'active': False, 'fetched': 1, 'kept': 1}}


@pytest.fixture
def service(tmp_path):
    app = CollectorApp(tmp_path / 'data', runner=fake_runner)
    admin = app.auth.bootstrap_admin('owner_admin', 'Admin-test-password-394!')
    member = app.auth.create_user(admin, 'member_one', 'Member-test-password-394!')
    other = app.auth.create_user(admin, 'member_two', 'Other-test-password-394!')
    server = CollectorHTTPServer(('127.0.0.1', 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    yield app, base, admin, member, other
    server.shutdown()
    server.server_close()
    app.close()
    thread.join(timeout=5)


def test_http_authentication_owner_isolation_downloads_and_admin(service, tmp_path):
    app, base, admin, member, other = service
    anonymous = Client(base)
    assert anonymous.call('/')[0] == 200
    assert anonymous.call('/api/session')[0] == 200
    for path in ('/api/jobs', '/api/meta', '/api/users'):
        assert anonymous.call(path)[0] == 401
    first, second, manager = Client(base), Client(base), Client(base)
    headers, _ = first.login('member_one', 'Member-test-password-394!')
    assert 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Strict' in headers['Set-Cookie']
    second.login('member_two', 'Other-test-password-394!')
    manager.login('owner_admin', 'Admin-test-password-394!')
    request = {'entries': 'com.synthetic.fixture', 'countries': ['us'], 'count_per_country': 1,
               'root': '/untrusted/legacy', 'owner_id': other['id'], 'role': 'admin', 'api_key': 'not-to-export'}
    assert first.call('/api/jobs', 'POST', request, csrf=False)[0] == 403
    assert first.call('/api/jobs', 'POST', request, origin=False)[0] == 403
    status, _, raw = first.call('/api/jobs', 'POST', request)
    assert status == 202, raw
    job = json.loads(raw)['job']
    identifier = job['id']
    assert job['owner_id'] == member['id']
    assert 'root' not in job['request'] and 'api_key' not in job['request']
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        _, _, raw = first.call('/api/jobs/' + identifier)
        job = json.loads(raw)['job']
        if job['status'] not in {'running', 'queued'}:
            break
        time.sleep(.01)
    assert job['status'] == 'completed', job
    assert json.loads(second.call('/api/jobs')[2])['jobs'] == []
    assert len(json.loads(manager.call('/api/jobs')[2])['jobs']) == 1
    assert second.call('/api/jobs/' + identifier)[0] == 404
    assert second.call('/api/jobs/' + identifier + '/archive')[0] == 404
    item = job['items'][0]
    csv_path = item['files']['reviews_csv']
    assert anonymous.call(csv_path)[0] == 401
    assert second.call(csv_path)[0] == 404
    status, _, csv = first.call(csv_path)
    assert status == 200 and csv.startswith(b'\xef\xbb\xbf')
    status, _, archive = first.call('/api/jobs/' + identifier + '/archive')
    assert status == 200
    archive_path = tmp_path / 'download.zip'
    archive_path.write_bytes(archive)
    with zipfile.ZipFile(archive_path) as packed:
        assert any(name.endswith('reviews.csv') for name in packed.namelist())
        assert not any('sqlite' in name or 'auth' in name for name in packed.namelist())
        assert all('not-to-export' not in packed.read(name).decode('utf-8', 'ignore') for name in packed.namelist())
    traversal = f"/files/{identifier}/{item['id']}/%2e%2e/%2e%2e/auth.sqlite3"
    assert first.call(traversal)[0] == 404
    assert first.call('/api/users')[0] == 403
    assert first.call('/api/users', 'POST', {'username': 'evil_admin', 'password': 'Long-password394!', 'role': 'admin'})[0] == 403
    assert manager.call('/api/users')[0] == 200
    status, _, _ = manager.call('/api/users/' + member['id'], 'PATCH', {'disabled': True})
    assert status == 200
    assert first.call('/api/jobs')[0] == 401
    assert first.call(csv_path)[0] == 401
    assert manager.call('/api/users/' + admin['id'], 'PATCH', {'disabled': True})[0] == 409
    assert second.call('/api/logout', 'POST', {})[0] == 200
    assert second.call('/api/jobs')[0] == 401


def test_request_host_and_session_first_setup_guard(tmp_path):
    app = CollectorApp(tmp_path / 'empty')
    server = CollectorHTTPServer(('127.0.0.1', 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_address[1]}')
    try:
        status, _, raw = client.call('/api/session')
        assert status == 200 and json.loads(raw)['setup_required'] is True
        assert client.call('/health', extra={'Host': 'attacker.example'})[0] == 403
        assert client.call('/api/register', 'POST', {'username': 'hijack', 'password': 'hijack'} )[0] == 401
        assert client.call('/data/auth.sqlite3')[0] == 401
        assert client.call('/api/login', 'POST', {'username': 'admin', 'password': 'admin'}, extra={'Origin': 'http://attacker.example'})[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        app.close()
        thread.join(timeout=5)


def test_persisted_job_retains_owner_and_restart_does_not_retry(tmp_path):
    app = CollectorApp(tmp_path / 'data', runner=lambda payload: pytest.fail('must not call on reload'))
    job_id, owner_id = 'a' * 32, 'owner-id'
    directory = app.runs / job_id
    directory.mkdir()
    (directory / 'job.json').write_text(json.dumps({'id': job_id, 'owner_id': owner_id, 'status': 'running',
        'items': [{'id': 'b' * 32, 'status': 'running'}], 'created_at': '2026-10-21T00:00:00Z'}), encoding='utf-8')
    app.close()
    resumed = CollectorApp(tmp_path / 'data', runner=lambda payload: pytest.fail('must not retry'))
    try:
        assert resumed.jobs[job_id]['status'] == 'failed'
        assert resumed.jobs_for({'id': 'different', 'role': 'member'}) == []
        assert resumed.jobs_for({'id': owner_id, 'role': 'member'})[0]['items'][0]['status'] == 'failed'
    finally:
        resumed.close()
