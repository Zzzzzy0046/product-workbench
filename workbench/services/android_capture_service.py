"""Project-scoped automatic Android screenshot skill sessions."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import zipfile

from workbench.core.runtime import now, uid, ROOT, MAX_FILE, ID_PATTERN
from workbench.core.codex_config import codex_command, configured_model
from workbench.services.base import BoundService
from workbench.adapters.android_capture_runner import run_capture_agent


CONFIG_KEY = 'integration:android-capture'
ACTIVE = {'queued', 'running'}
RESUMABLE = {'paused', 'blocked', 'failed', 'cancelled', 'interrupted', 'ready'}
PACKAGE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$')
SERIAL = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,199}$')


class AndroidCaptureService(BoundService):
    def __init__(self, workbench):
        super().__init__(workbench)
        object.__setattr__(self, '_capture_lock', threading.RLock())
        object.__setattr__(self, '_capture_processes', {})
        object.__setattr__(self, '_capture_threads', {})
        object.__setattr__(self, '_closed', threading.Event())

    @staticmethod
    def skill_root():
        from workbench.adapters.walkthrough_backend import resolve_skill_root
        return resolve_skill_root()

    def settings(self):
        saved = self.rows('SELECT value FROM preferences WHERE key=?', (CONFIG_KEY,))
        try:
            value = json.loads(saved[0]['value']) if saved else {}
        except (ValueError, TypeError):
            value = {}
        requested = str(value.get('adb_path') or os.environ.get('WORKBENCH_ADB_PATH', '')).strip()
        candidates = [requested] if requested else [
            shutil.which('adb.exe' if os.name == 'nt' else 'adb') or '',
            str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Android/Sdk/platform-tools/adb.exe'),
            str(Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'),
            'C:/Android/platform-tools/adb.exe',
        ]
        adb = next((Path(candidate).expanduser().resolve() for candidate in candidates if candidate and Path(candidate).expanduser().is_file()), None)
        error = ''
        try:
            available = bool(codex_command())
        except ValueError as exc:
            available, error = False, str(exc)
        skill = self.skill_root()
        ready = bool(adb and available and skill)
        return {'adb_path': str(adb or requested), 'adb_available': bool(adb),
                'codex_available': available, 'skill_available': bool(skill),
                'ready': ready, 'message': error or ('可以指定 App 和范围开始实机走查。' if ready else '请检查 ADB、Codex CLI 与截图 skill。')}

    def save_settings(self, payload):
        candidate = Path(str(payload.get('adb_path', '')).strip()).expanduser()
        if not candidate.is_file() or (os.name == 'nt' and candidate.suffix.lower() != '.exe'):
            raise ValueError('请选择存在的 adb 可执行文件，不要填写命令或参数。')
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)',
                       (CONFIG_KEY, json.dumps({'adb_path': str(candidate.resolve())})))
        return self.settings()

    def _adb(self, arguments, serial='', timeout=20):
        settings = self.settings()
        if not settings['adb_available']:
            raise ValueError('未找到 ADB，请先配置 adb.exe 路径。')
        if serial and not SERIAL.fullmatch(serial):
            raise ValueError('设备 serial 无效。')
        command = [settings['adb_path']] + (['-s', serial] if serial else []) + list(arguments)
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError('ADB 未能在限定时间内完成，请检查设备连接。') from None
        text = result.stdout.decode('utf-8', errors='replace')
        if result.returncode:
            raise ValueError('ADB 读取失败，请检查 USB 调试授权和设备连接。')
        if len(text) > 2_000_000:
            raise ValueError('设备返回数据过大。')
        return text

    def devices(self):
        text = self._adb(['devices', '-l'])
        devices = []
        for line in text.splitlines():
            parts = line.split()
            if len(parts) < 2 or not SERIAL.fullmatch(parts[0]) or parts[1] not in {'device', 'offline', 'unauthorized', 'recovery', 'sideload'}:
                continue
            model = next((part[6:].replace('_', ' ') for part in parts[2:] if part.startswith('model:')), '')
            devices.append({'serial': parts[0], 'state': parts[1], 'model': model})
        return {'devices': devices, 'message': '' if devices else '未发现设备，请连接 Android 设备并开启 USB 调试。'}

    def preflight(self, serial, package):
        devices = [item for item in self.devices()['devices'] if item['state'] == 'device']
        if not serial and len(devices) == 1:
            serial = devices[0]['serial']
        if not serial or not any(item['serial'] == serial for item in devices):
            raise ValueError('请明确选择一台已授权且在线的 Android 设备。')
        if not PACKAGE.fullmatch(package):
            raise ValueError('请输入有效 Android 包名，例如 com.example.app。')
        installed = self._adb(['shell', 'pm', 'path', package], serial)
        if not any(line.startswith('package:') for line in installed.splitlines()):
            raise ValueError('所选设备未安装这个 App，请核对包名。')
        details = self._adb(['shell', 'dumpsys', 'package', package], serial)
        name = re.search(r'\bversionName=([^\r\n]+)', details)
        code = re.search(r'\bversionCode=(\d+)', details)
        return {'serial': serial, 'app_version': {'name': name.group(1).strip() if name else '', 'code': code.group(1) if code else ''}}

    def _project_root(self, project_id):
        self.project(project_id)
        root = (self.data / 'scrapes' / project_id).resolve()
        if not root.is_relative_to(self.data.resolve()):
            raise ValueError('项目目录无效。')
        return root

    @staticmethod
    def _read(directory):
        try:
            result = json.loads((directory / 'session.json').read_text(encoding='utf-8'))
            if not isinstance(result, dict):
                raise ValueError
            return result
        except (OSError, ValueError):
            raise ValueError('实机走查记录不存在或无法读取。') from None

    @staticmethod
    def _write(directory, record):
        record['updated'] = now()
        temporary = directory / 'session.json.tmp'
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(directory / 'session.json')

    def _find(self, session_id):
        if not isinstance(session_id, str) or not ID_PATTERN.fullmatch(session_id):
            raise ValueError('走查编号无效。')
        for project in self.rows('SELECT id FROM projects'):
            directory = self._project_root(project['id']) / ('android-' + session_id)
            if not directory.resolve().is_relative_to(self._project_root(project['id'])):
                raise ValueError('走查目录不能位于项目之外。')
            if (directory / 'session.json').is_file():
                record = self._read(directory)
                if record.get('id') != session_id or record.get('project_id') != project['id']:
                    raise ValueError('走查记录的项目归属不一致，请重新导入。')
                return directory, record
        raise ValueError('走查任务不存在。')

    def _update(self, directory, **changes):
        with self._capture_lock:
            record = self._read(directory)
            record.update(changes)
            self._write(directory, record)
            return record

    def _records(self, project_id):
        root = self._project_root(project_id)
        for path in sorted(root.glob('android-*/session.json')):
            try:
                record = self._read(path.parent)
                if record.get('project_id') == project_id:
                    yield path.parent, record
            except ValueError:
                continue

    def has_active(self, project_id):
        return any(record.get('status') in ACTIVE or self._process_alive(record.get('id'))
                   or bool(self._capture_threads.get(record.get('id')) and self._capture_threads[record['id']].is_alive())
                   for _, record in self._records(project_id))

    def _process_alive(self, session_id):
        process = self._capture_processes.get(session_id)
        return process is not None and process.poll() is None

    def recover(self):
        for project in self.rows('SELECT id FROM projects'):
            for directory, record in self._records(project['id']):
                if record.get('status') in ACTIVE:
                    self._update(directory, status='interrupted', error='工作台已重启，走查证据已保留；重新检测设备后可续跑。')

    def sessions(self, project_id, version_id=''):
        self.version_service.resolve(project_id, version_id)
        records = [self._public(directory, record, details=False) for directory, record in self._records(project_id)
                   if str(record.get('version_id') or '') == version_id]
        return {'sessions': sorted(records, key=lambda item: item.get('created', ''), reverse=True)}

    @staticmethod
    def _json(path, default):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return default

    def _public(self, directory, record, details=True):
        result = dict(record)
        result['progress'] = []
        result['observations'] = []
        backend = self._json(directory / 'capture-tool-state.json', {})
        result['backend'] = backend.get('backend', record.get('backend', 'legacy'))
        result['backend_version'] = backend.get('backend_version', '')
        result['composites'] = []
        flow_manifest = self._json(directory / 'flow-manifest.json', {})
        result['composite_count'] = len(flow_manifest.get('composites', []))
        mapping = self._json(directory / 'research-map.json', {})
        result['modules'] = mapping.get('modules', []) if isinstance(mapping, dict) else []
        if not details:
            return result
        progress = directory / 'progress.jsonl'
        if progress.is_file():
            for line in progress.read_text(encoding='utf-8', errors='replace')[-64000:].splitlines()[-80:]:
                try:
                    event = json.loads(line)
                    names = {'capture_context': '读取走查范围与断点', 'launch_app': '启动目标 App', 'observe': '观察当前页面', 'act_observe': '操作并核对下一页', 'add_module': '记录模块', 'add_page': '记录页面', 'attach_observation': '保存页面状态与截图', 'add_transition': '记录真实跳转', 'set_module_status': '更新模块覆盖', 'export_flows': '生成模块流程拼图', 'finish': '整理本轮交付'}
                    states = {'started': '进行中', 'completed': '已完成', 'paused': '需要处理'}
                    message = event.get('message') or (names.get(event.get('tool'), event.get('tool', '走查')) + ' · ' + states.get(event.get('status'), event.get('status', '')))
                    result['progress'].append({'time': event.get('time', event.get('at', '')), 'message': str(message)[:700]})
                except (ValueError, AttributeError):
                    continue
        for path in sorted((directory / 'observations').glob('*.json'), key=lambda item: item.stat().st_mtime_ns)[-100:]:
            observation = self._json(path, {})
            relative = observation.get('files', {}).get('screenshot') if isinstance(observation, dict) else ''
            if relative and self._allowed_file(directory, relative, require=False):
                result['observations'].append({'id': observation.get('id', path.stem), 'path': relative, 'captured_at': observation.get('captured_at', '')})
        report = self._json(directory / 'agent-result.json', {})
        for item in report.get('composites', []) if isinstance(report, dict) else []:
            relative = item.get('path') if isinstance(item, dict) else item
            if relative and self._allowed_file(directory, relative, require=False):
                result['composites'].append({**(item if isinstance(item, dict) else {}), 'path': relative})
        return result

    def get(self, session_id):
        directory, record = self._find(session_id)
        return self._public(directory, record)

    def create(self, payload):
        with self.lock:
            return self._create(payload)

    def _create(self, payload):
        project_id = str(payload.get('project_id') or '')
        self.project(project_id)
        version_id = str(payload.get('version_id') or '')
        self.version_service.resolve(project_id, version_id)
        package = str(payload.get('package') or '').strip()
        competitor_id = str(payload.get('competitor_id') or '').strip()
        if competitor_id:
            competitor = self.competitor_service.get(project_id, competitor_id)
            if competitor['platform'] != 'google_play' or competitor['app_id'] != package:
                raise ValueError('实机走查包名必须与所选 Android 竞品一致。')
        scope = str(payload.get('scope') or '').strip()
        title = str(payload.get('title') or package).strip()
        if not 2 <= len(scope) <= 5000 or not 1 <= len(title) <= 120:
            raise ValueError('请填写 2–5000 字走查范围，标题不超过 120 字。')
        serial = str(payload.get('serial') or '').strip()
        checked = self.preflight(serial, package)
        if hasattr(self._workbench, 'competitor_service'):
            competitor_id = self.competitor_service.upsert(project_id, {'platform': 'google_play', 'app_id': package, 'title': title})['id']
        session_id = uid()
        directory = self._project_root(project_id) / ('android-' + session_id)
        directory.mkdir(parents=True)
        record = {'id': session_id, 'project_id': project_id, 'version_id': version_id,
                  'package': package, 'title': title, 'scope': scope, 'competitor_id': competitor_id, **checked,
                  'status': 'prepared', 'created': now(), 'summary': '', 'error': '', 'pause_reason': '', 'document_ids': []}
        self._write(directory, record)
        return self._public(directory, record)

    def start(self, session_id, resume=False):
        with self.lock, self._capture_lock:
            directory, record = self._find(session_id)
            if record.get('status') not in (RESUMABLE if resume else {'prepared'}):
                raise ValueError('当前状态不能开始走查，请刷新后重试。')
            if self._closed.is_set():
                raise ValueError('工作台正在停止。')
            previous_thread = self._capture_threads.get(session_id)
            if self._process_alive(session_id) or previous_thread is not None and previous_thread.is_alive():
                raise ValueError('上一轮进程尚未停止，请稍后再续跑。')
            self._capture_threads.pop(session_id, None)
            self._capture_processes.pop(session_id, None)
            for project in self.rows('SELECT id FROM projects'):
                if any(item.get('serial') == record['serial'] and (
                    item.get('status') in ACTIVE or self._process_alive(item.get('id'))
                    or bool(self._capture_threads.get(item.get('id')) and self._capture_threads[item['id']].is_alive())
                ) for _, item in self._records(project['id'])):
                    raise ValueError('这台设备已有走查任务运行，请先停止或等待完成。')
            settings = self.settings()
            if not settings['ready']:
                raise ValueError(settings['message'])
            checked = self.preflight(record['serial'], record['package'])
            if checked['app_version'] != record.get('app_version'):
                raise ValueError('App 版本已变化，请新建走查任务，避免混入旧版本证据。')
            request = {key: record[key] for key in ('id', 'project_id', 'version_id', 'package', 'serial', 'title', 'scope', 'app_version')}
            request.update({'adb_path': settings['adb_path'], 'python_path': sys.executable,
                            'skill_root': str(self.skill_root()), 'session_dir': str(directory),
                            'model': configured_model(), 'budget_seconds': 600, 'max_actions': 60, 'attempt_id': uid()})
            (directory / 'request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
            (directory / 'agent-result.json').unlink(missing_ok=True)
            (directory / 'cancel.requested').unlink(missing_ok=True)
            self._update(directory, status='queued', error='', pause_reason='', backend='android-walkthrough')
            worker = threading.Thread(target=self._execute, args=(session_id, directory, request), daemon=True)
            self._capture_threads[session_id] = worker
            worker.start()
            return self.get(session_id)

    def _execute(self, session_id, directory, request):
        try:
            with self._capture_lock:
                if self._read(directory)['status'] == 'cancelled':
                    return
                record = self._update(directory, status='running')
            report = run_capture_agent(self, record, directory, request)
            with self._capture_lock:
                if self._read(directory)['status'] == 'cancelled':
                    return
                outcome = report.get('outcome')
                if outcome not in {'completed', 'paused', 'blocked'}:
                    raise ValueError('截图 skill 返回了无法识别的结果，证据已保留。')
                if outcome == 'completed':
                    from workbench.capture_tools import review_session
                    checked = review_session(directory)
                    if not checked.get('ok'):
                        raise ValueError('流程交付检查未通过，请查看缺口后续跑。')
                self._update(directory, status={'completed': 'ready', 'paused': 'paused', 'blocked': 'blocked'}[outcome],
                             summary=str(report.get('summary', ''))[:6000], pause_reason=str(report.get('reason', ''))[:2000], error='')
        except Exception as exc:
            with self._capture_lock:
                if directory.is_dir() and self._read(directory).get('status') != 'cancelled':
                    self._update(directory, status='failed', error=str(exc)[:2000])
        finally:
            with self._capture_lock:
                if not self._process_alive(session_id):
                    self._capture_processes.pop(session_id, None)
                    self._capture_threads.pop(session_id, None)

    def cancel(self, session_id):
        with self._capture_lock:
            directory, record = self._find(session_id)
            if record.get('status') not in ACTIVE | {'prepared', 'paused', 'blocked', 'interrupted'} and not self._process_alive(session_id):
                raise ValueError('当前走查没有运行。')
            self._update(directory, status='cancelled', error='', pause_reason='已停止，已采集证据保留，可继续。')
            (directory / 'cancel.requested').write_text(now(), encoding='utf-8')
            process = self._capture_processes.get(session_id)
        if process is not None and not self.stop_process(process):
            raise ValueError('停止进程未完成，请稍后再续跑。')
        return self.get(session_id)

    def close(self):
        self._closed.set()
        for session_id in list(self._capture_threads):
            try:
                self.cancel(session_id)
            except ValueError:
                pass
        for session_id, process in list(self._capture_processes.items()):
            if self.stop_process(process):
                self._capture_processes.pop(session_id, None)
            else:
                try:
                    directory, _ = self._find(session_id)
                    self._update(directory, error='工作台停止时子进程未完全结束，请核对该设备进程后再续跑。')
                except ValueError:
                    pass

    @staticmethod
    def _allowed_file(directory, relative, require=True):
        relative = str(relative).replace('\\', '/')
        if not relative or relative.startswith('/') or ':' in relative or '..' in Path(relative).parts:
            if require:
                raise ValueError('走查文件路径无效。')
            return None
        allowed = relative.startswith(('observations/', 'flow_export/')) or relative in {'research-map.json', 'app-map.md', 'capture-session.json', 'timings.jsonl', 'flow-manifest.json', 'delivery_review.md'}
        path = (directory / relative).resolve()
        if not allowed or not path.is_relative_to(directory.resolve()) or not path.is_file() or path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.xml', '.json', '.jsonl', '.md'}:
            if require:
                raise ValueError('走查文件不存在或不允许访问。')
            return None
        return path

    def file(self, session_id, relative):
        directory, _ = self._find(session_id)
        return self._allowed_file(directory, relative)

    def export(self, session_id):
        directory, record = self._find(session_id)
        if record['status'] in ACTIVE:
            raise ValueError('请等待本轮结束或停止后再下载证据包。')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('走查记录.json', json.dumps(record, ensure_ascii=False, indent=2))
            for path in sorted(directory.rglob('*')):
                if path.is_file():
                    relative = path.relative_to(directory).as_posix()
                    if self._allowed_file(directory, relative, require=False):
                        archive.writestr(relative, path.read_bytes())
        return output.getvalue(), f"Android实机走查-{record['package']}-{session_id[:8]}.zip"

    def confirm(self, session_id):
        with self.lock, self._capture_lock:
            directory, record = self._find(session_id)
            if record['status'] == 'confirmed':
                return self.get(session_id)
            if record['status'] not in {'ready', 'paused', 'blocked'}:
                raise ValueError('请在走查产生可预览成果后确认；失败任务可先续跑。')
            public = self._public(directory, record)
            images = public['observations'] + public['composites']
            if not images:
                raise ValueError('尚无实际截图，不能确认入库。')
            for item in images:
                path = self._allowed_file(directory, item['path'])
                if path.stat().st_size > MAX_FILE:
                    raise ValueError('有流程拼图超过 12 MB，请先拆成较小模块再入库。')
            self.version_service.resolve(record['project_id'], record.get('version_id', ''))
            competitor_id = ''
            if hasattr(self._workbench, 'competitor_service'):
                competitor_id = self.competitor_service.upsert(record['project_id'], {'platform': 'google_play', 'app_id': record['package'], 'title': record.get('title') or record['package']})['id']
            document_ids = []
            assets = {}
            for item in images:
                relative = item['path']
                if relative in assets:
                    continue
                content = self._allowed_file(directory, relative).read_bytes()
                label = '模块流程' if relative.startswith('flow_export/') else '实机截图'
                name = f"{label}-{record['package']}-{Path(relative).name}"[:180]
                document = self.add_document(record['project_id'], name, content, record.get('version_id', ''),
                                             'evidence', 'images', 'competitor')
                if competitor_id:
                    self.competitor_service.attach_documents(record['project_id'], competitor_id, [document['id']],
                        'module_flow' if relative.startswith('flow_export/') else 'device_screenshot', 'android_capture', session_id, record.get('created'))
                assets[relative] = document['id']
                document_ids.append(document['id'])
            lines = ['# Android 实机截图走查', '', f"- App：`{record['package']}`",
                     f"- 版本：{json.dumps(record.get('app_version', {}), ensure_ascii=False)}",
                     f"- 设备 serial：`{record['serial']}`", f"- 走查时间：{record['created']}",
                     f"- 范围：{record['scope']}", f"- 本轮结果：{record['status']}",
                     '', '这是已安装 App 的真实设备证据，区别于商店宣传图；只覆盖本轮实际观察范围。',
                     '', record.get('summary', ''), '', record.get('pause_reason', ''), '', '## 模块与覆盖', '']
            for module in public['modules']:
                lines.append(f"- {module.get('title', '')}（{module.get('status', '')}）：{module.get('reason', '')}")
            mapping = self._json(directory / 'research-map.json', {})
            lines.extend(['', '## 页面状态与证据', ''])
            for state in mapping.get('states', []):
                lines.append(f"- {state.get('id', '')} · {state.get('title', '')} · 观察 {state.get('observation_id', '')}")
            lines.extend(['', '## 已记录跳转', ''])
            for transition in mapping.get('transitions', []):
                lines.append(f"- {transition.get('id', '')}：{transition.get('from_state', '')} → {transition.get('to_state', '')}；动作 {json.dumps(transition.get('action', {}), ensure_ascii=False)}")
            lines.extend(['', '## 流程拼图与原始截图', ''])
            for relative, document_id in assets.items():
                lines.extend([f"![{Path(relative).stem}](asset://{document_id})", ''])
            document = self.add_document(record['project_id'], f"实机走查索引-{record['package']}-{session_id[:8]}.md",
                                         '\n'.join(lines).encode('utf-8'), record.get('version_id', ''), 'evidence', 'competitor')
            document_ids.append(document['id'])
            if competitor_id:
                self.competitor_service.attach_documents(record['project_id'], competitor_id, [document['id']], 'note', 'android_capture', session_id, record.get('created'))
            self._update(directory, status='confirmed', competitor_id=competitor_id, document_ids=list(dict.fromkeys(document_ids)), confirmed_at=now())
            return self.get(session_id)
