"""Exercise the real frozen server in an isolated profile, without model or ADB calls."""
from __future__ import annotations

import argparse
import base64
import hashlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile


class OwnedProcessTree:
    """A private Windows Job Object containing only this test's launched process.

    Never discovers processes by name, port, or a historical PID. Windows keeps
    descendants in this job even when a PyInstaller bootloader parent exits.
    Closing the handle also kills job members if the test raises unexpectedly.
    """

    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('The frozen EXE process-tree smoke requires Windows.')
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        self.kernel.QueryInformationJobObject.restype = wintypes.BOOL
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.TerminateJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL

        class BasicLimits(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount',
                        'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise error
        self.root_pid = None

    def assign(self, process):
        # This handle came directly from our Popen, not from a PID lookup.
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        self.root_pid = process.pid

    def pids(self):
        if not self.handle:
            return []
        ctypes = self.ctypes
        # ULONG count/count followed by pointer-sized process IDs.
        for capacity in (128, 1024, 8192):
            buffer = ctypes.create_string_buffer(8 + capacity * ctypes.sizeof(ctypes.c_size_t))
            if self.kernel.QueryInformationJobObject(self.handle, 3, buffer, ctypes.sizeof(buffer), None):
                count = ctypes.c_uint32.from_buffer(buffer, 4).value
                values = (ctypes.c_size_t * count).from_buffer(buffer, 8)
                return sorted(int(pid) for pid in values)
            if ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                raise ctypes.WinError(ctypes.get_last_error())
        raise RuntimeError('The private smoke job has too many processes to verify safely.')

    def stop(self, process=None, port=None):
        report = {'root_pid': self.root_pid, 'ownership': 'private Windows Job Object assigned from this test Popen handle',
                  'owned_pids_before_cleanup': self.pids()}
        try:
            if not self.kernel.TerminateJobObject(self.handle, 1):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            until = time.monotonic() + 15
            remaining = self.pids()
            while remaining and time.monotonic() < until:
                time.sleep(.05)
                remaining = self.pids()
            report['remaining_owned_pids'] = remaining
            if process is not None:
                process.wait(timeout=5)
            if remaining:
                raise RuntimeError(f'Test process cleanup did not finish: {remaining}')
        finally:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        if port is not None:
            report['port'] = port
            until = time.monotonic() + 5
            while True:
                with socket.socket() as probe:
                    probe.settimeout(.2)
                    listening = probe.connect_ex(('127.0.0.1', port)) == 0
                if not listening or time.monotonic() >= until:
                    break
                time.sleep(.05)
            report['listener_remaining'] = listening
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1', port))
                    report['port_rebind_succeeded'] = True
                except OSError:
                    report['port_rebind_succeeded'] = False
            if listening:
                raise RuntimeError(f'Port {port} still has a listener after stopping our private job; no other process was killed.')
        report['verified'] = not report['remaining_owned_pids'] and not report.get('listener_remaining', False)
        return report


def start_owned_process(arguments, **kwargs):
    tree = OwnedProcessTree()
    try:
        # Start suspended so even the PyInstaller bootloader cannot create an
        # unowned child in the gap before AssignProcessToJobObject.
        process = subprocess.Popen(arguments, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) | 0x4, **kwargs)
        try:
            tree.assign(process)
            _resume_owned_root(process.pid)
        except BaseException:
            # Assignment failed: stop only the exact root process we launched.
            process.kill()
            process.wait(timeout=10)
            raise
        return process, tree
    except BaseException:
        if tree.handle:
            tree.kernel.CloseHandle(tree.handle)
            tree.handle = None
        raise


def _resume_owned_root(pid):
    """Resume the only thread of the still-suspended process just created here."""
    import ctypes
    from ctypes import wintypes

    class ThreadEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ThreadID', wintypes.DWORD), ('th32OwnerProcessID', wintypes.DWORD),
                    ('tpBasePri', wintypes.LONG), ('tpDeltaPri', wintypes.LONG), ('dwFlags', wintypes.DWORD)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Thread32First', 'Thread32Next'):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        function.restype = wintypes.BOOL
    kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenThread.restype = wintypes.HANDLE
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(0x4, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    threads = []
    try:
        entry = ThreadEntry()
        entry.dwSize = ctypes.sizeof(entry)
        valid = kernel.Thread32First(snapshot, ctypes.byref(entry))
        while valid:
            if entry.th32OwnerProcessID == pid:
                threads.append(entry.th32ThreadID)
            valid = kernel.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    if len(threads) != 1:
        raise RuntimeError('Cannot prove the newly created root has one suspended primary thread.')
    thread = kernel.OpenThread(0x2, False, threads[0])  # THREAD_SUSPEND_RESUME
    if not thread:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if kernel.ResumeThread(thread) != 1:
            raise RuntimeError('Unexpected primary-thread suspension state; smoke process not started.')
    finally:
        kernel.CloseHandle(thread)


def isolated_environment(root):
    """Empty, test-owned user profile; no personal model/ADB/Skill configuration."""
    env = dict(os.environ)
    for key in list(env):
        upper = key.upper()
        if upper.startswith(('WORKBENCH_', 'COMPETITOR_COLLECTOR_', '_PYI_')) or upper in {
                'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'VIRTUAL_ENV', 'CODEX_HOME'}:
            env.pop(key, None)
    profile = Path(root) / 'empty-profile'
    profile.mkdir(parents=True, exist_ok=True)
    env.update(USERPROFILE=str(profile), HOME=str(profile), LOCALAPPDATA=str(profile / 'Local'),
               APPDATA=str(profile / 'Roaming'), CODEX_HOME=str(profile / '.codex'),
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8', WORKBENCH_RETRIEVAL_MODE='keyword',
               PATH=str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'))
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-store', action='store_true', help='Read one public Google Play sample, with translation off')
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    standalone = root / 'standalone'
    standalone.mkdir()
    exe = standalone / 'ProductWorkbench.exe'
    shutil.copy2(args.exe.resolve(), exe)
    exe_identity = {'bytes': exe.stat().st_size, 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
    data_dir = root / 'data'
    env = isolated_environment(root)
    checks = []

    def check(name, condition, detail=''):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            raise AssertionError(name + ': ' + detail)

    self_test, self_tree = start_owned_process([str(exe), '--self-test'], cwd=standalone, env=env,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = self_test.communicate(timeout=45)
    finally:
        self_cleanup = self_tree.stop(self_test)
    diagnostic = json.loads(stdout.decode('utf-8'))
    check('frozen_dependencies_and_assets', self_test.returncode == 0 and diagnostic['ok'] and diagnostic['frozen'])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    token = ''
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, payload=None, expected=200, authenticated=True):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Origin': origin}
        if authenticated and token:
            headers['X-Workbench-Token'] = token
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(origin + path, data=body, headers=headers)
        try:
            with opener.open(req, timeout=90) as response:
                status, content = response.status, response.read()
                mime = response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as exc:
            status, content, mime = exc.code, exc.read(), exc.headers.get('Content-Type', '')
        if status != expected:
            raise AssertionError(f'{path}: HTTP {status}, expected {expected}: {content[:400]!r}')
        return json.loads(content) if 'application/json' in mime else content

    log = (root / 'server.log').open('wb')
    process, process_tree = start_owned_process([str(exe), '--no-browser', '--port', str(port), '--data-dir', str(data_dir)],
        cwd=standalone, env=env, stdout=log, stderr=subprocess.STDOUT)
    live = {'requested': args.live_store, 'status': 'not_run'}
    try:
        deadline = time.monotonic() + 45
        while True:
            try:
                state = request('/api/state')
                break
            except (OSError, AssertionError):
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('EXE startup failed; inspect isolated server.log')
                time.sleep(.25)
        token = state['token']
        check('starts_without_python_on_PATH_or_original_cwd', process.poll() is None)
        check('fresh_database', state['projects'] == [])
        settings = state['integrations']['review_scraper']
        check('builtin_collector_ready', settings.get('backend') == 'builtin' and settings['ready'])
        check('html_and_static_assets', b'<!' in request('/') and b'reviewScrapeForm' in request('/features/integrations.js'))
        request('/api/projects', {'name': 'must reject'}, expected=403, authenticated=False)
        check('POST_requires_runtime_token', True)
        project = request('/api/projects', {'name': 'EXE isolated synthetic verification', 'brief': 'Synthetic data only; no model/device actions.'}, 201)
        pid = project['id']
        roundtrip = request('/api/integrations/review-scraper', {'root': settings['root'], 'enabled': True})
        check('UI_settings_roundtrip_keeps_builtin', roundtrip['backend'] == 'builtin')
        raw = '# 合成采集材料\n\n仅验证导入导出，不是真实研究。'.encode('utf-8')
        doc = request('/api/documents', {'project_id': pid, 'name': 'synthetic.md', 'content': base64.b64encode(raw).decode()}, 201)
        check('upload_download_roundtrip', request(f"/api/documents/{doc['id']}/download") == raw)
        job = request('/api/prepare', {'project_id': pid, 'task': 'fast/product-baseline', 'instruction': 'Synthetic import/export test only.', 'document_ids': [doc['id']]}, 201)
        request(f"/api/jobs/{job['id']}/import", {'output': '# 合成验证文档\n\n仅测试冻结后的导出依赖。\n\n| 项目 | 内容 |\n|---|---|\n| 状态 | 待验证 |'})
        for fmt in ['docx', 'pdf', 'xlsx', 'csv']:
            content = request(f"/api/jobs/{job['id']}/export?format={fmt}")
            (root / f'export-fixture.{fmt}').write_bytes(content)
            expected = b'%PDF' if fmt == 'pdf' else b'PK' if fmt in {'docx', 'xlsx'} else b'\xef\xbb\xbf'
            check(f'export_{fmt}', content.startswith(expected) and len(content) > 20)
        sid = 'a' * 32
        capture = data_dir / 'scrapes' / pid / ('android-' + sid)
        capture.mkdir(parents=True)
        (capture / 'session.json').write_text(json.dumps({'id': sid, 'project_id': pid, 'package': 'test.synthetic.app', 'status': 'paused'}), encoding='utf-8')
        mapping = {'synthetic': True, '说明': 'No ADB was invoked'}
        (capture / 'research-map.json').write_text(json.dumps(mapping, ensure_ascii=False), encoding='utf-8')
        check('json_capture_file_download', request(f'/api/android-capture/sessions/{sid}/file?path=research-map.json') == mapping)
        if args.live_store:
            queued = request('/api/competitors/collect', {'project_id': pid, 'entries': ['com.google.android.calculator'], 'countries': ['us'], 'count_per_country': 1, 'translate': False}, 202)
            scrape_id = queued['items'][0]['id']
            until = time.monotonic() + 150
            while True:
                item = request('/api/reviews/scrape/' + scrape_id)
                if item['status'] not in {'queued', 'running'} or time.monotonic() > until:
                    break
                time.sleep(1)
            live = {'requested': True, 'platform': 'google_play', 'app_id': 'com.google.android.calculator', 'status': item['status'], 'review_count': item.get('review_count', 0),
                    'screenshot_count': item.get('screenshot_count', 0), 'translation': False}
            if item['status'] == 'ready':
                confirmed = request(f'/api/reviews/scrape/{scrape_id}/confirm', {})
                live['confirmed_status'] = confirmed['status']
                check('live_public_store_native_worker', confirmed['status'] == 'completed')
            else:
                live['reason'] = str(item.get('error', ''))[:300]
                if item['status'] in {'queued', 'running'}:
                    request(f'/api/reviews/scrape/{scrape_id}/cancel', {})
        package = request(f'/api/projects/{pid}/export')
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            check('project_zip_export', archive.testzip() is None and len(archive.namelist()) > 1)
        imported = request('/api/projects/import', {'content': base64.b64encode(package).decode()}, expected=201)
        check('project_import_creates_new_copy', imported['id'] != pid and imported['name'] == project['name'])
    finally:
        failure = sys.exc_info()[1]
        cleanup = None
        cleanup_error = None
        try:
            cleanup = process_tree.stop(process, port=port)
            check('owned_process_tree_and_listener_stopped', cleanup['verified'])
        except Exception as exc:
            cleanup_error = f'{type(exc).__name__}: {exc}'
        finally:
            log.close()
        report = {'ok': failure is None and cleanup_error is None, 'created': datetime.now().isoformat(timespec='seconds'),
                  'exe_identity': exe_identity,
                  'checks': checks, 'live_store': live, 'process_cleanup': cleanup, 'self_test_cleanup': self_cleanup,
                  'error': str(failure) if failure else cleanup_error,
                  'scope': 'Windows same-host isolated profile and directory; no model calls, device operations, or clean-VM claim.'}
        (root / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if cleanup_error:
            raise RuntimeError(cleanup_error)
    print(json.dumps({'passed': len(checks), 'report': str(root / 'verification.json'), 'live_store': live}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
