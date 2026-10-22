"""Collection-only host, HTTP surface, portability and local ADB discovery."""
import io
import json
from pathlib import Path
import sqlite3
import zipfile
from http.server import ThreadingHTTPServer
import threading
import urllib.request
import urllib.error

import pytest

from workbench.collection_app import CollectionWorkbench, CollectionHandler, find_local_adb
from scripts.packaging.collection_launcher import dispatch_worker


def test_collection_host_has_only_collection_services_and_exports(tmp_path):
    app = CollectionWorkbench(tmp_path / 'data')
    try:
        project = app.create_project('独立采集', '合成离线资料')
        doc = app.add_document(project['id'], '评论.csv', 'content,score\nSynthetic review,4\n'.encode())
        state = app.state(project['id'])
        assert state['edition'] == 'data-collection'
        assert state['documents'][0]['id'] == doc['id']
        assert not {'jobs', 'workflows', 'packs', 'conditions'} & state.keys()
        assert not hasattr(app, 'prepare')
        assert not hasattr(app, 'job_service')
        content, filename = app.export_project(project['id'])
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            data = json.loads(bundle.read('data.json'))
            assert data['documents'][0]['name'] == '评论.csv'
            assert data['jobs'] == []
            assert not any('preferences' in name or 'token' in name for name in bundle.namelist())
        assert filename.endswith('.zip')
    finally:
        app.close()


@pytest.mark.parametrize('method,path', [
    ('GET', '/api/jobs/abc'), ('POST', '/api/prepare'), ('POST', '/api/assemble'),
    ('POST', '/api/jobs/abc/start'), ('GET', '/api/search'), ('POST', '/api/packs'),
    ('POST', '/api/projects/import'), ('POST', '/api/integrations/lanhu'),
])
def test_non_collection_routes_are_not_available(method, path):
    assert not CollectionHandler.allowed(path, method)


@pytest.mark.parametrize('method,path', [
    ('GET', '/api/state'), ('POST', '/api/competitors/collect'),
    ('GET', '/api/android-capture/devices'),
    ('POST', '/api/android-capture/sessions/' + 'a' * 32 + '/resume'),
    ('GET', '/api/projects/' + 'a' * 32 + '/export'),
])
def test_collection_routes_are_available(method, path):
    assert CollectionHandler.allowed(path, method)


def test_adb_finds_scrcpy_and_reuses_only_valid_local_preference(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Local'))
    monkeypatch.delenv('WORKBENCH_ADB_PATH', raising=False)
    monkeypatch.setattr('workbench.collection_app.shutil.which', lambda _: None)
    adb = tmp_path / 'Desktop/Tools/scrcpy-test/scrcpy-test/adb.exe'
    adb.parent.mkdir(parents=True)
    adb.write_bytes(b'fixture only; never executed')
    assert find_local_adb() == adb.resolve()
    saved = tmp_path / 'another/adb.exe'
    saved.parent.mkdir()
    saved.write_bytes(b'fixture only; never executed')
    prior = tmp_path / 'Local/ProductWorkbenchResearch/data/workbench.sqlite3'
    prior.parent.mkdir(parents=True)
    with sqlite3.connect(prior) as db:
        db.execute('CREATE TABLE preferences(key TEXT PRIMARY KEY,value TEXT)')
        db.execute('INSERT INTO preferences VALUES(?,?)', ('integration:android-capture', json.dumps({'adb_path': str(saved)})))
    assert find_local_adb() == saved.resolve()


def test_collection_worker_only_dispatches_fixed_modules(tmp_path, monkeypatch):
    assert dispatch_worker(['--self-test'], tmp_path) is None
    assert dispatch_worker(['-X', 'utf8', str(tmp_path / 'workbench/capture_mcp.py')], tmp_path) == ('capture-mcp', [])
    with pytest.raises(ValueError, match='内置采集'):
        dispatch_worker([str(tmp_path / 'user.py')], tmp_path)
    monkeypatch.setattr('sys.frozen', True, raising=False)
    assert dispatch_worker([str(tmp_path / 'old/workbench/review_scraper_worker.py')], tmp_path / 'new') == ('collector', [])


def test_staged_store_data_can_be_confirmed_without_generation_services(tmp_path):
    app = CollectionWorkbench(tmp_path / 'data')
    try:
        project = app.create_project('商店采集确认', '')
        scrape_id = 'b' * 32
        with app.db() as db:
            db.execute('INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,review_count,warning_count,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (scrape_id, project['id'], 'google_play', 'test.collection.fixture',
                        json.dumps({'collect_listing': True, 'translate': False}), 'ready', '',
                        '2026-10-22T00:00:00Z', '2026-10-22T00:00:00Z', '', 1, 0, ''))
        directory = app.data / 'scrapes' / project['id'] / scrape_id
        directory.mkdir(parents=True)
        (directory / 'store-listing.md').write_text('# Synthetic store listing\n', encoding='utf-8')
        (directory / 'reviews.csv').write_text('content,score\nSynthetic review,4\n', encoding='utf-8')
        (directory / 'manifest.json').write_text(json.dumps({'listing': {'title': 'Synthetic fixture', 'market': 'US'}, 'review_count': 1}), encoding='utf-8')
        result = app.confirm_competitor_collection(scrape_id)
        assert result['status'] == 'completed'
        assert len(result['document_ids']) == 2
        assert any(item['name'].startswith('竞品评论-') for item in app.state(project['id'])['documents'])
        assert app.rows('SELECT id FROM jobs') == []
    finally:
        app.close()


def test_http_rejected_generation_routes_return_json_without_reset(tmp_path):
    app = CollectionWorkbench(tmp_path / 'data')
    server = ThreadingHTTPServer(('127.0.0.1', 0), CollectionHandler)
    server.app = app
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        origin = f'http://127.0.0.1:{server.server_port}'
        for path in ('/api/prepare', '/api/assemble', '/api/packs', '/api/projects/import', '/api/integrations/lanhu'):
            request = urllib.request.Request(origin + path, data=b'{"fixture":"rejected without side effects"}',
                                             headers={'Content-Type': 'application/json', 'X-Workbench-Token': app.token})
            with pytest.raises(urllib.error.HTTPError) as caught:
                opener.open(request, timeout=5)
            assert caught.value.code == 404
            assert 'error' in json.loads(caught.value.read())
        assert app.state()['projects'] == []
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()
        app.close()
