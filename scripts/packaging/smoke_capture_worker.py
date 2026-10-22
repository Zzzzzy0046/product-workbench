"""Offline handshake with the real frozen capture worker; no ADB/model calls.

Only initialize, tools/list and capture_context are sent over MCP stdio. The
selector path intentionally does not exist: the EXE must use its fixed worker.
All processes belong to a private test-owned Windows Job Object.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import queue
from pathlib import Path
import subprocess
import tempfile
import threading
import time

try:
    from .smoke_workbench_exe import isolated_environment, start_owned_process
except ImportError:
    from smoke_workbench_exe import isolated_environment, start_owned_process


EXPECTED_TOOLS = {
    'capture_context', 'launch_app', 'observe', 'act_observe', 'add_module', 'add_page',
    'attach_observation', 'add_transition', 'set_module_status', 'export_flows', 'finish', 'view_observation',
}
EXPECTED_PROTOCOL_FILES = {
    'SKILL.md', 'references/walkthrough.md', 'references/ads.md',
    'references/delivery.md', 'references/json-contract.md',
}


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class FrozenMcpClient:
    """Small synchronous JSON-RPC client, with exact ownership of its process.

    This avoids relying on an SDK's parent-only termination behavior. It does
    not add an application test entry point or execute a supplied Python file.
    """

    def __init__(self, exe, root, session, environment, timeout=60):
        self.root, self.timeout = Path(root), timeout
        self.sequence, self.responses = 0, queue.Queue()
        self.cleanup = None
        selector = self.root / 'workbench' / 'capture_mcp.py'
        selector.parent.mkdir(parents=True, exist_ok=True)
        _require(not selector.exists(), 'The fixed worker selector must not exist on disk.')
        self.stderr_path = self.root / 'worker-stderr.log'
        self.stderr = self.stderr_path.open('wb')
        try:
            self.process, self.tree = start_owned_process(
                [str(exe), '-X', 'utf8', str(selector), '--session', str(session)],
                cwd=self.root, env=environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.stderr,
            )
        except BaseException:
            self.stderr.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for raw in self.process.stdout:
                if len(raw) > 24 * 1024 * 1024:
                    raise ValueError('MCP response exceeds the offline smoke limit.')
                if raw.strip():
                    self.responses.put(json.loads(raw.decode('utf-8')))
        except Exception as error:
            self.responses.put(error)
        finally:
            self.responses.put(EOFError('The frozen MCP stream closed.'))

    def send(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + '\n').encode('utf-8'))
        self.process.stdin.flush()

    def request(self, method, params=None):
        self.sequence += 1
        identifier = self.sequence
        self.send({'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params or {}})
        until = time.monotonic() + self.timeout
        while True:
            left = until - time.monotonic()
            if left <= 0:
                raise TimeoutError(f'MCP {method} timed out; no request was repeated.')
            try:
                response = self.responses.get(timeout=left)
            except queue.Empty:
                raise TimeoutError(f'MCP {method} timed out; no request was repeated.') from None
            if isinstance(response, BaseException):
                raise response
            if response.get('id') != identifier:
                continue  # Logs/notifications are not replies to this request.
            if 'error' in response:
                raise RuntimeError(f'MCP {method} failed: {response["error"]}')
            return response.get('result', {})

    def initialize(self):
        initialized = self.request('initialize', {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'workbench-frozen-offline-smoke', 'version': '2.0'},
        })
        self.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        return initialized

    def call(self, name, arguments=None):
        result = self.request('tools/call', {'name': name, 'arguments': arguments or {}})
        _require(not result.get('isError'), f'MCP tool {name} returned an error: {result.get("content")}')
        texts = [item['text'] for item in result.get('content', []) if item.get('type') == 'text']
        _require(len(texts) == 1, f'{name} must include one JSON text block.')
        return json.loads(texts[0]), result

    def close(self):
        try:
            try:
                if self.process.stdin and not self.process.stdin.closed:
                    self.process.stdin.close()
                self.process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        finally:
            try:
                self.cleanup = self.tree.stop(self.process)
            finally:
                if self.process.stdout:
                    self.process.stdout.close()
                self.stderr.close()
                self.reader.join(timeout=2)
        return self.cleanup


def _handshake(exe, root, request, report, timeout):
    session = root / 'synthetic-session'
    session.mkdir()
    (session / 'request.json').write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
    environment = isolated_environment(root)
    codex_home = Path(environment['CODEX_HOME'])
    _require(not codex_home.exists(), 'Personal Codex data must not be inherited.')
    report['checks'].update({'worker_selector_file_absent': True, 'empty_codex_home': True,
                             'skill_override_removed': 'WORKBENCH_ANDROID_SKILL' not in environment,
                             'python_source_path_removed': 'PYTHONPATH' not in environment})
    client = FrozenMcpClient(exe, root, session, environment, timeout)
    try:
        initialized = client.initialize()
        report['server'] = initialized.get('serverInfo', {})
        _require(report['server'].get('name') == 'android-capture', 'Unexpected frozen MCP server name.')
        listing = client.request('tools/list')
        names = {tool['name'] for tool in listing.get('tools', [])}
        report['tools'] = sorted(names)
        _require(EXPECTED_TOOLS == names, f'Restricted tools changed: missing={sorted(EXPECTED_TOOLS - names)}, extra={sorted(names - EXPECTED_TOOLS)}')
        action_schema = next(tool for tool in listing['tools'] if tool['name'] == 'act_observe')['inputSchema']['properties']
        _require({'coordinates', 'text', 'submit', 'in_view', 'include_image'} <= set(action_schema), 'New walkthrough action arguments are missing.')
        report['checks']['restricted_tool_contract'] = True
        # The handshake intentionally calls only this one read-only tool.
        context, raw = client.call('capture_context')
        _require([block['type'] for block in raw['content']] == ['text'], 'Context must not return a screenshot.')
        _require(context.get('ok') is True and context.get('skill_source') == 'bundled', 'Bundled Skill not loaded.')
        _require(context.get('backend') == 'android-walkthrough', 'The frozen worker still uses the previous screenshot backend.')
        for key in ('serial', 'package', 'app_version'):
            _require(context['target'][key] == request[key], f'Unexpected target {key}.')
        _require('adb_path' not in context['target'], 'Context must not expose the execution path.')
        _require(context.get('actions_used') == 0 and context['map']['observations'] == [], 'Unexpected device action/observation.')
        protocol = context.get('protocol', {})
        _require(EXPECTED_PROTOCOL_FILES <= set(protocol), 'New android-walkthrough references are incomplete.')
        _require(all(isinstance(protocol[name], str) and protocol[name].strip() for name in EXPECTED_PROTOCOL_FILES),
                 'Bundled protocol text is empty.')
        report['context'] = {'ok': True, 'skill_source': context['skill_source'], 'backend': context['backend'],
                             'backend_version': context.get('backend_version'), 'actions_used': 0,
                             'observations': 0, 'protocol_files': sorted(protocol),
                             'protocol_sha256': {name: hashlib.sha256(protocol[name].encode('utf-8')).hexdigest()
                                                 for name in sorted(EXPECTED_PROTOCOL_FILES)}}
        report['checks']['bundled_walkthrough_skill_and_references_readable'] = True
        for name in ('observations', 'capture-session.json', 'agent-result.json', 'timings.jsonl'):
            _require(not (session / name).exists(), f'Unexpected device/result artifact: {name}')
        progress = [json.loads(line) for line in (session / 'progress.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        _require([item.get('tool') for item in progress] == ['capture_context', 'capture_context']
                 and [item.get('status') for item in progress] == ['started', 'completed'], 'Unexpected context-only progress.')
        _require(all(item.get('actions_used') == 0 for item in progress), 'Progress recorded a device action.')
        report['checks']['context_only_no_device_or_finish_artifacts'] = True
    finally:
        report['process_cleanup'] = client.close()
        report['checks']['owned_process_tree_stopped'] = report['process_cleanup']['verified']
        errors = client.stderr_path.read_text(encoding='utf-8', errors='replace').strip()
        if errors:
            report['worker_stderr_tail'] = errors[-6000:]


def run_smoke(exe, timeout):
    started = time.monotonic()
    report = {'ok': False, 'started_at': _utc_now(), 'checks': {},
              'scope': 'Real frozen MCP initialize/list_tools/capture_context only; no ADB, device, model, or external network calls.'}
    try:
        _require(exe.is_file(), 'The supplied EXE does not exist.')
        with exe.open('rb') as stream:
            report['exe_identity'] = {'bytes': exe.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
        with tempfile.TemporaryDirectory(prefix='workbench-exe-capture-smoke-') as directory:
            root = Path(directory)
            request = {'adb_path': str(root / 'ADB-MUST-NEVER-RUN.exe'), 'serial': 'SYNTHETIC-NO-DEVICE',
                       'package': 'test.handshake.app', 'title': 'EXE 合成握手', 'scope': '只验证新版协议，不读取或操作设备。',
                       'app_version': {'name': 'synthetic', 'code': '0'}, 'attempt_id': 'exe-handshake-only',
                       'max_actions': 1, 'budget_seconds': 30}
            _handshake(exe, root, request, report, timeout)
        report['ok'] = True
    except Exception as error:
        report['errors'] = [f'{type(error).__name__}: {error}']
    report['finished_at'] = _utc_now()
    report['duration_seconds'] = round(time.monotonic() - started, 3)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--timeout', default=60., type=float)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 180:
        parser.error('--timeout must be between 1 and 180 seconds')
    report = run_smoke(args.exe.expanduser().resolve(), args.timeout)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': report['ok'], 'report': str(args.report.resolve()),
                      'duration_seconds': report['duration_seconds'], 'errors': report.get('errors', [])}, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
