"""Capture task lifecycle uses synthetic evidence and never contacts ADB/model."""

import io
import json
from pathlib import Path
import threading
import zipfile

from PIL import Image
import pytest

from workbench.app import Workbench
import workbench.services.android_capture_service as capture_module
from workbench.adapters.android_capture_runner import capture_prompt, CAPTURE_TOOLS


@pytest.fixture
def capture(tmp_path, monkeypatch):
    bench = Workbench(data_dir=tmp_path / 'data', runner=lambda _job: '合成文档，不执行外部任务。')
    project = bench.create_project('截图隔离测试', '合成业务资料')
    version = bench.create_product_version(project['id'], {'name': 'V-test'})
    service = bench.android_capture
    monkeypatch.setattr(capture_module.AndroidCaptureService, 'settings', lambda self: {'ready': True, 'adb_path': 'fixture-adb', 'adb_available': True, 'codex_available': True, 'skill_available': True})
    monkeypatch.setattr(capture_module.AndroidCaptureService, 'preflight', lambda self, serial, package: {'serial': serial or 'FIXTURE-DEVICE', 'app_version': {'name': '1.0-fixture', 'code': '1'}})
    yield bench, project, version, service
    bench.close()


def create(capture, serial='FIXTURE-DEVICE'):
    _, project, version, service = capture
    return service.create({'project_id': project['id'], 'version_id': version['id'], 'package': 'test.synthetic.app',
                           'scope': '仅走查合成首页到结果页', 'title': '合成截图任务', 'serial': serial})


def wait(service, session_id):
    thread = service._capture_threads.get(session_id)
    if thread:
        thread.join(timeout=5)
        assert not thread.is_alive()
    return service.get(session_id)


def evidence(directory):
    identifier = 'obs-' + 'a' * 16
    images = directory / 'observations'
    images.mkdir(exist_ok=True)
    png = io.BytesIO()
    Image.new('RGB', (120, 200), '#364168').save(png, 'PNG')
    relative = f'observations/{identifier}.png'
    (directory / relative).write_bytes(png.getvalue())
    (images / f'{identifier}.json').write_text(json.dumps({'id': identifier, 'package': 'test.synthetic.app',
        'serial': 'FIXTURE-DEVICE', 'captured_at': 'fixture-time', 'files': {'screenshot': relative}}), encoding='utf-8')
    (directory / 'research-map.json').write_text(json.dumps({'modules': [{'id': 'M01', 'title': '合成首页', 'status': 'blocked', 'reason': '仅测试部分证据'}], 'states': [], 'transitions': []}), encoding='utf-8')
    return relative


def test_create_does_not_launch_model_or_add_project_evidence(capture):
    bench, project, version, service = capture
    record = create(capture)
    assert record['status'] == 'prepared'
    assert record['version_id'] == version['id']
    assert not bench.rows('SELECT id FROM documents WHERE project_id=?', (project['id'],))
    assert not service._capture_threads
    assert len(service.sessions(project['id'], version['id'])['sessions']) == 1
    assert not service.sessions(project['id'])['sessions']


def test_staged_previews_are_confined_and_confirmation_is_idempotent(capture):
    bench, project, version, service = capture
    record = create(capture)
    directory, _ = service._find(record['id'])
    relative = evidence(directory)
    (directory / 'request.json').write_text('{"adb_path":"private-local-path"}', encoding='utf-8')
    service._update(directory, status='paused', pause_reason='合成系统选择器待处理')
    assert service.file(record['id'], relative).is_file()
    for path in ('../session.json', 'request.json', '/etc/passwd', 'C:/outside.png', 'attempts/prompt.md'):
        with pytest.raises(ValueError):
            service.file(record['id'], path)
    assert not bench.rows('SELECT id FROM documents WHERE project_id=?', (project['id'],))
    result = service.confirm(record['id'])
    assert result['status'] == 'confirmed' and len(result['document_ids']) == 2
    assert service.confirm(record['id'])['document_ids'] == result['document_ids']
    image = bench.document(result['document_ids'][0])
    assert image['category'] == 'images' and image['subcategory'] == 'competitor'
    assert bench.rows('SELECT document_id FROM version_documents WHERE version_id=?', (version['id'],))
    content, _ = service.export(record['id'])
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert relative in archive.namelist()
        assert 'request.json' not in archive.namelist()
        assert b'private-local-path' not in content


def test_completed_without_verified_evidence_cannot_become_ready(capture, monkeypatch):
    _, _, _, service = capture
    record = create(capture)
    monkeypatch.setattr(capture_module, 'run_capture_agent', lambda *_: {'outcome': 'completed', 'summary': '不能凭一句话通过'})
    service.start(record['id'])
    result = wait(service, record['id'])
    assert result['status'] == 'failed'
    assert '检查未通过' in result['error']


def test_cancellation_drops_late_completion_and_resume_keeps_evidence(capture, monkeypatch):
    _, _, _, service = capture
    record = create(capture)
    entered, release = threading.Event(), threading.Event()
    requests = []

    def run(_service, _record, directory, request):
        requests.append(request.copy())
        entered.set()
        assert release.wait(timeout=4)
        evidence(directory)
        return {'outcome': 'paused', 'summary': '保留部分证据', 'reason': '测试接管'}

    monkeypatch.setattr(capture_module, 'run_capture_agent', run)
    service.start(record['id'])
    assert entered.wait(timeout=3)
    assert service.cancel(record['id'])['status'] == 'cancelled'
    release.set()
    assert wait(service, record['id'])['status'] == 'cancelled'
    directory, _ = service._find(record['id'])
    assert list((directory / 'observations').glob('*.png'))
    assert (directory / 'cancel.requested').is_file()
    service.start(record['id'], resume=True)
    assert wait(service, record['id'])['status'] == 'paused'
    assert not (directory / 'cancel.requested').exists()
    assert requests[0]['attempt_id'] != requests[1]['attempt_id']
    assert len(list((directory / 'observations').glob('*.png'))) == 1


def test_same_device_cannot_run_two_capture_agents(capture, monkeypatch):
    _, _, _, service = capture
    first, second = create(capture), create(capture)
    entered, release = threading.Event(), threading.Event()

    def run(*_):
        entered.set()
        assert release.wait(timeout=4)
        return {'outcome': 'paused', 'summary': '', 'reason': 'fixture'}

    monkeypatch.setattr(capture_module, 'run_capture_agent', run)
    service.start(first['id'])
    assert entered.wait(timeout=3)
    with pytest.raises(ValueError, match='已有走查任务'):
        service.start(second['id'])
    release.set()
    wait(service, first['id'])


def test_service_restart_marks_running_interrupted_without_launching(capture):
    bench, project, version, service = capture
    record = create(capture)
    directory, _ = service._find(record['id'])
    service._update(directory, status='running')
    recovered = Workbench(data_dir=bench.data, runner=lambda _: '')
    assert recovered.android_capture.get(record['id'])['status'] == 'interrupted'
    assert not recovered.android_capture._capture_threads
    recovered.close()


def test_cancelled_but_live_process_keeps_device_and_delete_reservation(capture):
    bench, project, _, service = capture
    first, second = create(capture), create(capture)

    class UnstoppedProcess:
        def poll(self):
            return None

    directory, _ = service._find(first['id'])
    service._update(directory, status='cancelled')
    service._capture_processes[first['id']] = UnstoppedProcess()
    assert service.has_active(project['id'])
    with pytest.raises(ValueError, match='已有走查任务'):
        service.start(second['id'])
    with pytest.raises(ValueError, match='截图|走查'):
        bench.delete_project(project['id'], project['name'])
    service._capture_processes.clear()


def test_scope_data_and_skill_preserve_user_workflow(capture):
    *_, service = capture
    prompt = capture_prompt({'package': 'test.synthetic.app', 'scope': '仅看导入与返回，不做订阅',
                             'serial': 'FIXTURE-DEVICE'}, service.skill_root())
    assert '仅看导入与返回，不做订阅' in prompt
    assert 'capture_context' in prompt and 'finish' in prompt
    assert '不需要 shell' in prompt
    assert set(CAPTURE_TOOLS) == {'capture_context', 'launch_app', 'observe', 'act_observe', 'view_observation', 'add_module', 'add_page',
                                  'attach_observation', 'add_transition', 'set_module_status', 'export_flows', 'finish'}
