"""Frozen android-walkthrough end-to-end smoke using a local synthetic FakeAdb.

No real ADB, phone, model, or external network is used. A tiny C# fixture accepts
only fixed commands and returns generated PNG/XML. The actual EXE worker runs
observe/action/map/build/finish; the actual EXE HTTP server reads and confirms
the results. Only the model-runner's final session-status handoff is simulated,
explicitly recorded in the report. Test binaries stay inside --output.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    from .smoke_capture_worker import FrozenMcpClient, EXPECTED_PROTOCOL_FILES
    from .smoke_workbench_exe import isolated_environment, start_owned_process
except ImportError:
    from smoke_capture_worker import FrozenMcpClient, EXPECTED_PROTOCOL_FILES
    from smoke_workbench_exe import isolated_environment, start_owned_process


PACKAGE = 'test.frozen.walkthrough'
SERIAL = 'SYNTHETIC-FAKE-ADB-ONLY'


def create_fake_adb(root, environment):
    """Compile a fixture executable; it never invokes a shell or another program."""
    from PIL import Image, ImageDraw

    directory = root / 'fake-adb'
    directory.mkdir()
    for number in range(2):
        image = Image.new('RGB', (240, 400), '#eff2e8')
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                pixels[x, y] = (180 + ((x * 17 + y * 7 + number * 31) % 60),
                                180 + ((x * 5 + y * 13) % 60), 180 + ((x * 11 + y * 3) % 60))
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 20, 228, 115), fill='#244c3e')
        draw.text((24, 42), 'SYNTHETIC FIXTURE', fill='white')
        draw.text((24, 70), f'Screen {number + 1}', fill='white')
        draw.rectangle((18, 180, 222, 235), fill='#fffefb')
        draw.text((35, 200), 'Continue' if not number else 'Back', fill='#244c3e')
        image.save(directory / f'screen-{number}.png')
    source = r'''using System;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
public static class FakeAdb {
  public static int Main(string[] args) {
    string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
    string joined = String.Join(" ", args);
    using(Mutex logMutex=new Mutex(false,"Local\\ProductWorkbenchSyntheticFakeAdbLog")) {
      logMutex.WaitOne();
      try { File.AppendAllText(Path.Combine(root,"commands.log"),joined+"\n",new UTF8Encoding(false)); }
      finally { logMutex.ReleaseMutex(); }
    }
    string serial="SYNTHETIC-FAKE-ADB-ONLY", package="test.frozen.walkthrough";
    if(joined=="devices -l") { Console.WriteLine("List of devices attached\n"+serial+" device product:synthetic model:Fake_Android transport_id:1"); return 0; }
    if(args.Length<3 || args[0]!="-s" || args[1]!=serial) return 21;
    string command=String.Join(" ",args,2,args.Length-2);
    string state=Path.Combine(root,"state.txt");
    int screen=File.Exists(state)?Int32.Parse(File.ReadAllText(state)):0;
    if(command=="shell pm path "+package) { Console.WriteLine("package:/synthetic/base.apk"); return 0; }
    if(command=="shell dumpsys package "+package) { Console.WriteLine("versionName=synthetic-1\nversionCode=1"); return 0; }
    if(command.StartsWith("shell dumpsys window ")) { Console.WriteLine("mCurrentFocus=Window{1 u0 "+package+"/.MainActivity}"); return 0; }
    if(command.StartsWith("shell monkey -p "+package+" ")) { File.WriteAllText(state,"0"); return 0; }
    if(command.StartsWith("shell input tap ")) { File.WriteAllText(state,"1"); return 0; }
    if(command=="shell input keyevent 4") { File.WriteAllText(state,"0"); return 0; }
    if(command.StartsWith("shell uiautomator dump ")) {
      string title=screen==0?"Synthetic Home":"Synthetic Details";
      string label=screen==0?"Continue":"Back";
      Console.Write("<hierarchy rotation=\"0\"><node text=\""+title+"\" package=\""+package+"\" class=\"android.widget.FrameLayout\" bounds=\"[0,0][240,400]\"><node text=\""+label+"\" content-desc=\""+label+"\" package=\""+package+"\" resource-id=\""+package+":id/next\" class=\"android.widget.Button\" clickable=\"true\" enabled=\"true\" bounds=\"[18,180][222,235]\" /></node></hierarchy>"); return 0;
    }
    if(command=="exec-out screencap -p") { byte[] png=File.ReadAllBytes(Path.Combine(root,"screen-"+screen+".png")); Console.OpenStandardOutput().Write(png,0,png.Length); return 0; }
    Console.Error.WriteLine("FakeAdb rejected an unexpected command: "+command); return 22;
  }
}'''
    code = directory / 'FakeAdb.cs'
    code.write_text(source, encoding='utf-8')
    windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
    compiler = next((path for path in [windows / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe',
                                      windows / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'] if path.is_file()), None)
    if compiler is None:
        raise RuntimeError('Windows .NET Framework csc.exe is required to compile the test-only FakeAdb fixture.')
    target = directory / 'FakeAdb.exe'
    process, tree = start_owned_process([str(compiler), '/nologo', '/target:exe', '/optimize+',
                                         '/out:' + str(target), str(code)],
                                        cwd=directory, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = process.communicate(timeout=30)
        if process.returncode or not target.is_file():
            raise RuntimeError('FakeAdb compilation failed: ' + (stdout + stderr).decode('utf-8', 'replace')[-2000:])
    finally:
        cleanup = tree.stop(process)
    return target, cleanup


def run(exe_path, root, timeout=90):
    checks = []
    report = {'ok': False, 'created': datetime.now(timezone.utc).isoformat(), 'checks': checks,
              'scope': 'Real frozen worker and HTTP API with synthetic FakeAdb only; no real device/ADB, model, or external network.',
              'model_runner_status_handoff': 'Not invoked. After frozen finish, this test copies its completed outcome into only its synthetic session.json.'}
    root.mkdir(parents=True, exist_ok=False)
    standalone = root / 'standalone'
    standalone.mkdir()
    exe = standalone / 'ProductWorkbench.exe'
    shutil.copy2(exe_path, exe)
    with exe.open('rb') as stream:
        report['exe_identity'] = {'bytes': exe.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    environment = isolated_environment(root)
    fake_adb, report['fixture_compiler_cleanup'] = create_fake_adb(root, environment)
    data = root / 'data'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin, token = f'http://127.0.0.1:{port}', ''
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def check(name, condition, detail=''):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            raise AssertionError(name + ': ' + detail)

    def request(path, payload=None, expected=200):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Origin': origin, 'X-Workbench-Token': token}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with opener.open(urllib.request.Request(origin + path, data=body, headers=headers), timeout=timeout) as response:
                status, content, mime = response.status, response.read(), response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as error:
            status, content, mime = error.code, error.read(), error.headers.get('Content-Type', '')
        if status != expected:
            raise AssertionError(f'{path}: HTTP {status}, expected {expected}: {content[:500]!r}')
        return json.loads(content) if 'application/json' in mime else content

    log = (root / 'server.log').open('wb')
    server, tree = start_owned_process([str(exe), '--no-browser', '--port', str(port), '--data-dir', str(data)],
                                       cwd=standalone, env=environment, stdout=log, stderr=subprocess.STDOUT)
    try:
        until = time.monotonic() + timeout
        while True:
            try:
                snapshot = request('/api/state')
                token = snapshot['token']
                break
            except (OSError, AssertionError):
                if server.poll() is not None or time.monotonic() >= until:
                    raise RuntimeError('Frozen server did not start; inspect this test server.log.')
                time.sleep(.25)
        check('fresh_isolated_project_space', snapshot['projects'] == [])
        project = request('/api/projects', {'name': '新版截图冻结合成验证', 'brief': 'Synthetic fixture only. No phone or model.'}, 201)
        project_id = project['id']
        settings = request('/api/android-capture/settings', {'adb_path': str(fake_adb)})
        check('only_synthetic_adb_configured', Path(settings['adb_path']).resolve() == fake_adb.resolve())
        devices = request('/api/android-capture/devices')['devices']
        check('synthetic_device_inventory', len(devices) == 1 and devices[0]['serial'] == SERIAL)
        record = request('/api/android-capture/sessions', {'project_id': project_id, 'package': PACKAGE,
                         'serial': SERIAL, 'title': '合成首页到详情；非真实手机证据', 'scope': '仅验证合成首页到详情，记录模块和真实测试动作。'}, 201)
        check('frozen_session_preflight', record['status'] == 'prepared' and record['app_version']['name'] == 'synthetic-1')
        session = data / 'scrapes' / project_id / ('android-' + record['id'])
        fixed_request = {key: record[key] for key in ('id', 'project_id', 'package', 'serial', 'title', 'scope', 'app_version')}
        fixed_request.update(adb_path=str(fake_adb), max_actions=8, budget_seconds=600, attempt_id='frozen-fake-only')
        (session / 'request.json').write_text(json.dumps(fixed_request, ensure_ascii=False, indent=2), encoding='utf-8')
        client_root = root / 'mcp'
        client_root.mkdir()
        client = FrozenMcpClient(exe, client_root, session, environment, timeout)
        try:
            client.initialize()
            context, _ = client.call('capture_context')
            check('new_bundled_backend', context['backend'] == 'android-walkthrough' and context['skill_source'] == 'bundled')
            check('new_skill_reference_contract', EXPECTED_PROTOCOL_FILES <= set(context['protocol']))
            client.call('add_module', {'module_id': 'M01', 'title': '合成导航'})
            client.call('add_page', {'page_id': 'P01', 'module_id': 'M01', 'title': '合成首页'})
            client.call('add_page', {'page_id': 'P02', 'module_id': 'M01', 'title': '合成详情'})
            first, first_raw = client.call('launch_app')
            check('frozen_launch_observes_synthetic_home', first.get('ok') and first['observation']['controls'], str(first.get('error', '')))
            check('default_observation_is_compact_json', [block.get('type') for block in first_raw['content']] == ['text'])
            first_id = first['observation']['id']
            commands_before_view = (fake_adb.parent / 'commands.log').read_bytes()
            viewed, view_raw = client.call('view_observation', {'observation_id': first_id})
            check('explicit_cached_thumbnail_without_adb', viewed.get('ok') and
                  any(block.get('type') == 'image' and block.get('mimeType') == 'image/jpeg' for block in view_raw['content'])
                  and (fake_adb.parent / 'commands.log').read_bytes() == commands_before_view)
            client.call('attach_observation', {'observation_id': first_id, 'module_id': 'M01', 'page_id': 'P01', 'state_id': 'S01', 'title': '合成首页'})
            second, _ = client.call('act_observe', {'observation_id': first_id, 'action': 'tap', 'index': 0})
            check('frozen_action_observes_next_screen', second.get('ok') and second['observation']['id'] != first_id, str(second.get('error', '')))
            client.call('attach_observation', {'observation_id': second['observation']['id'], 'module_id': 'M01', 'page_id': 'P02', 'state_id': 'S02', 'title': '合成详情'})
            edge, _ = client.call('add_transition', {'transition_id': 'T01', 'from_state': 'S01', 'to_state': 'S02'})
            check('automatic_real_action_edge_is_idempotent', edge.get('ok') and edge.get('already_recorded') is True)
            client.call('set_module_status', {'module_id': 'M01', 'status': 'complete', 'reason': '已观察本测试唯一指定路径：合成首页点击后到详情；不代表真实 App。'})
            built, _ = client.call('export_flows')
            check('frozen_build_and_review', built.get('ok') and built.get('composites') and built['review']['ok'])
            finished, _ = client.call('finish', {'outcome': 'completed', 'summary': '仅合成 FakeAdb 首页到详情验证；未连接真实设备、未调用模型。'})
            check('frozen_finish_contract', finished.get('ok') and finished['outcome'] == 'completed' and finished['review']['ok'], str(finished.get('reason', '')))
            report['frozen_result'] = {key: finished[key] for key in ('outcome', 'observation_count', 'actions_used', 'composites')}
        finally:
            report['worker_process_cleanup'] = client.close()
        # Only the model runner's status handoff is represented by a fixture.
        # No map, observation, PNG, build, review, or finish result is fabricated.
        final_result = json.loads((session / 'agent-result.json').read_text(encoding='utf-8'))
        record.update(status='ready', summary=final_result['summary'], pause_reason='', error='')
        (session / 'session.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        public = request('/api/android-capture/sessions/' + record['id'])
        check('workbench_reads_frozen_evidence', public['status'] == 'ready' and len(public['observations']) == 2 and public['composites'] and public['modules'])
        composite = public['composites'][0]['path']
        raw_png = request('/api/android-capture/sessions/' + record['id'] + '/file?path=' + urllib.parse.quote(composite))
        check('workbench_serves_module_png', raw_png.startswith(b'\x89PNG\r\n\x1a\n'))
        evidence_zip = request('/api/android-capture/sessions/' + record['id'] + '/export')
        with zipfile.ZipFile(io.BytesIO(evidence_zip)) as archive:
            check('workbench_exports_current_evidence_zip', archive.testzip() is None and composite in archive.namelist())
        confirmed = request('/api/android-capture/sessions/' + record['id'] + '/confirm', {})
        check('workbench_confirms_evidence_to_library', confirmed['status'] == 'confirmed' and len(confirmed['document_ids']) >= 4)
        again = request('/api/android-capture/sessions/' + record['id'] + '/confirm', {})
        check('confirmation_is_idempotent', again['document_ids'] == confirmed['document_ids'])
        library = request('/api/state?project=' + project_id)['documents']
        found = [item for item in library if item['id'] in confirmed['document_ids']]
        check('confirmed_documents_visible_in_project', len(found) == len(confirmed['document_ids']))
        commands = (fake_adb.parent / 'commands.log').read_text(encoding='utf-8').splitlines()
        check('exactly_one_synthetic_tap', len([line for line in commands if 'shell input tap ' in line]) == 1)
        report['fake_adb'] = {'commands': commands, 'real_adb_called': False, 'serial': SERIAL}
        report['ok'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        try:
            report['server_process_cleanup'] = tree.stop(server, port)
            check('owned_server_tree_and_listener_stopped', report['server_process_cleanup']['verified'])
        except Exception as error:
            report['ok'] = False
            report['cleanup_error'] = f'{type(error).__name__}: {error}'
        finally:
            log.close()
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (root / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Must not exist; contains synthetic fixtures only.')
    parser.add_argument('--timeout', default=90., type=float)
    args = parser.parse_args()
    report = run(args.exe.resolve(), args.output.resolve(), args.timeout)
    print(json.dumps({'ok': report['ok'], 'passed': sum(item['passed'] for item in report['checks']),
                      'report': str(args.output.resolve() / 'verification.json'), 'error': report.get('error'),
                      'cleanup_error': report.get('cleanup_error')}, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
