"""Standard-library client for the running EXE's local HTTP API; no keys needed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    parser.add_argument('--collect', metavar='APP_LINK_OR_ID', help='Create a research project and collect this explicitly selected App')
    parser.add_argument('--country', default='us')
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--confirm', action='store_true', help='Confirm a ready collection into that project')
    parser.add_argument('--export', type=Path, help='Save the resulting project ZIP; use with --collect')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    parsed = urlparse(base)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.path:
        parser.error('--base-url must be the EXE console localhost HTTP address')
    token = ''
    opener = build_opener(ProxyHandler({}))

    def api(path, payload=None):
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Origin': base, 'X-Workbench-Token': token}
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        with opener.open(Request(base + path, data=raw, headers=headers), timeout=90) as response:
            body = response.read()
            return json.loads(body) if 'application/json' in response.headers.get('Content-Type', '') else body

    state = api('/api/state')
    token = state['token']
    print('Local API connected; project count:', len(state['projects']))
    if not args.collect:
        print('No collection requested. Use --collect APP_LINK_OR_ID to create a separate research project.')
        return 0
    project = api('/api/projects', {'name': 'API collection example', 'brief': 'Explicitly selected App; collection only.'})
    pid = project['id']
    batch = api('/api/competitors/collect', {'project_id': pid, 'entries': [args.collect],
        'countries': [args.country], 'count_per_country': args.count, 'translate': False})
    sid = batch['items'][0]['id']
    deadline = time.monotonic() + 180
    while True:
        item = api('/api/reviews/scrape/' + sid)
        print('Collection status:', item['status'])
        if item['status'] not in {'queued', 'running'}:
            break
        if time.monotonic() > deadline:
            print('Client wait ended; task is retained on the server. Project:', pid)
            return 2
        time.sleep(2)
    if item['status'] == 'ready' and args.confirm:
        item = api(f'/api/reviews/scrape/{sid}/confirm', {})
    print('Project:', pid, '| collection:', sid, '| status:', item['status'])
    if args.export:
        content = api(f'/api/projects/{pid}/export')
        with args.export.open('xb') as handle:
            handle.write(content)
        print('Saved ZIP:', args.export)
    if item.get('error'):
        print('Message:', item['error'])
    return 0 if item['status'] in {'ready', 'completed'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
