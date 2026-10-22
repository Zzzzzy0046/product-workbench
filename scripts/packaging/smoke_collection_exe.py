"""Verify the real collector EXE in an empty, test-owned user profile."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import zipfile

try:
    from .smoke_workbench_exe import isolated_environment, start_owned_process
except ImportError:
    from smoke_workbench_exe import isolated_environment, start_owned_process


def run(exe, output, live_store=False, preview_seconds=0):
    output.mkdir(parents=True, exist_ok=False)
    standalone = output / 'standalone'
    standalone.mkdir()
    copied = standalone / 'DataCollector.exe'
    shutil.copy2(exe, copied)
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()
    env = isolated_environment(output)
    checks = []
    report = {'ok': False, 'edition': 'data-collection', 'exe_identity': {'sha256': digest, 'bytes': copied.stat().st_size},
              'checks': checks, 'started_at': datetime.now(timezone.utc).isoformat(),
              'live_store': {'requested': live_store, 'status': 'not_run'},
              'scope': 'Real frozen launcher and HTTP. Synthetic uploaded data; optional public Google Play sample. No real phone or model calls.'}

    def check(name, condition, detail=''):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            raise AssertionError(name + ': ' + detail)

    for flag in ('--version', '--self-test'):
        process, tree = start_owned_process([str(copied), flag], cwd=standalone, env=env,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=60)
            check(flag, process.returncode == 0, stderr.decode('utf-8', errors='replace')[-1200:])
            if flag == '--self-test':
                info = json.loads(stdout)
                check('frozen_dependencies_assets_and_no_generation_service', info['ok'] and info['frozen'] and not info['document_generation_service'])
                report['self_test'] = info
            else:
                report['version'] = stdout.decode('utf-8').strip()
        finally:
            tree.stop(process)

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin, token = f'http://127.0.0.1:{port}', ''
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, payload=None, expected=200, authenticated=True):
        content = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Origin': origin}
        if authenticated:
            headers['X-Workbench-Token'] = token
        if content is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with opener.open(urllib.request.Request(origin + path, data=content, headers=headers), timeout=70) as response:
                status, data, mime = response.status, response.read(), response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as error:
            status, data, mime = error.code, error.read(), error.headers.get('Content-Type', '')
        except OSError as error:
            raise ConnectionError(f'{path}: {error}') from error
        if status != expected:
            raise AssertionError(f'{path}: HTTP {status}, expected {expected}: {data[:350]!r}')
        return json.loads(data) if 'application/json' in mime else data

    log = (output / 'server.log').open('wb')
    process, tree = start_owned_process([str(copied), '--no-browser', '--port', str(port), '--data-dir', str(output / 'data')],
                                       cwd=standalone, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        until = time.monotonic() + 60
        while True:
            try:
                state = request('/api/state')
                token = state['token']
                break
            except OSError:
                if process.poll() is not None or time.monotonic() > until:
                    raise RuntimeError('The frozen collector server failed to start; see server.log.')
                time.sleep(.25)
        check('isolated_collection_edition', state['edition'] == 'data-collection' and not state['projects'])
        check('no_workflow_jobs_or_knowledge_in_state', not {'jobs', 'packs', 'workflows', 'runtime'} & state.keys())
        check('builtin_collector_ready', state['integrations']['review_scraper']['backend'] == 'builtin' and state['integrations']['review_scraper']['ready'])
        page = request('/').decode('utf-8')
        check('utf8_collection_entry', '<title>数据采集工作台</title>' in page)
        for resource in re.findall(r'(?:src|href)="(/[^"]+)"', page):
            check('asset:' + resource, bool(request(resource)))
        for path in ('/features/tasks.js', '/features/outputs.js', '/api/jobs/' + 'a' * 32, '/api/search'):
            request(path, expected=404)
        for path in ('/api/prepare', '/api/assemble', '/api/packs', '/api/projects/import', '/api/integrations/lanhu'):
            request(path, {}, expected=404)
        check('generation_api_and_assets_unavailable', True)
        request('/api/projects', {'name': 'must not be created'}, expected=403, authenticated=False)
        check('mutation_requires_local_csrf_token', not request('/api/state')['projects'])
        project = request('/api/projects', {'name': '采集专用版验证', 'brief': 'Test-owned synthetic data. No real device.'}, expected=201)
        project_id = project['id']
        body = 'content,score\nSynthetic collection sample,4\n'.encode('utf-8')
        doc = request('/api/documents', {'project_id': project_id, 'name': '合成评论.csv', 'content': base64.b64encode(body).decode()}, expected=201)
        check('document_saved_and_download_exact', request('/api/documents/' + doc['id'] + '/download') == body)
        state = request('/api/state?project=' + project_id)
        check('only_current_project_data_visible', len(state['documents']) == 1 and state['documents'][0]['id'] == doc['id'])
        settings = request('/api/android-capture/settings')
        check('bundled_screenshot_skill_without_personal_adb', settings['skill_available'] and not settings['adb_available'])
        if live_store:
            result = request('/api/competitors/collect', {'project_id': project_id, 'entries': ['com.google.android.keep'],
                             'countries': ['us'], 'count_per_country': 3, 'sort': 'newest', 'translate': False}, expected=202)
            scrape_id = result['items'][0]['id']
            until = time.monotonic() + 120
            while True:
                item = request('/api/reviews/scrape/' + scrape_id)
                if item['status'] not in {'queued', 'running'}:
                    break
                if time.monotonic() >= until:
                    request('/api/reviews/scrape/' + scrape_id + '/cancel', {})
                    raise RuntimeError('Google Play sample timed out.')
                time.sleep(.3)
            report['live_store'] = {'requested': True, 'status': item['status'], 'app_id': item['app_id'],
                                    'reviews': item['review_count'], 'screenshots': item.get('screenshot_count', 0),
                                    'warning': item.get('error', '')}
            check('real_google_play_small_sample', item['status'] == 'ready' and item['review_count'] > 0, item.get('error', ''))
            confirmed = request('/api/reviews/scrape/' + scrape_id + '/confirm', {})
            check('real_sample_confirmation_saved', confirmed['status'] == 'completed' and bool(confirmed.get('document_ids')))
        raw_zip = request('/api/projects/' + project_id + '/export')
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as bundle:
            manifest = json.loads(bundle.read('manifest.json'))
            snapshot = json.loads(bundle.read('data.json'))
            check('collection_package_manifest_and_no_generated_jobs', bundle.testzip() is None and snapshot['jobs'] == [] and manifest['package'] == 'workbench-project-v1')
            check('export_file_hashes', all(hashlib.sha256(bundle.read(file['path'])).hexdigest() == file['sha256'] for file in manifest['files']))
            check('no_execution_settings_or_credentials_in_export', not any(name.endswith(('preferences.json', 'config.toml', 'auth.json')) for name in bundle.namelist()))
        (output / '合成采集数据包.zip').write_bytes(raw_zip)
        if preview_seconds:
            report['preview_url'] = origin
            print(json.dumps({'preview_url': origin, 'pid': process.pid, 'seconds': preview_seconds}), flush=True)
            deadline = time.monotonic() + min(preview_seconds, 600)
            while time.monotonic() < deadline:
                if (output / 'preview-done').exists():
                    break
                time.sleep(.3)
        report['ok'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        try:
            report['process_cleanup'] = tree.stop(process, port)
            check('owned_processes_and_test_port_stopped', report['process_cleanup']['verified'])
        except Exception as error:
            report['ok'] = False
            report['cleanup_error'] = str(error)
        log.close()
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live-store', action='store_true')
    parser.add_argument('--preview-seconds', type=int, default=0)
    args = parser.parse_args()
    result = run(args.exe.resolve(), args.output.resolve(), args.live_store, args.preview_seconds)
    print(json.dumps({'ok': result['ok'], 'checks': len(result['checks']), 'error': result.get('error'),
                      'report': str(args.output.resolve() / 'verification.json')}, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
