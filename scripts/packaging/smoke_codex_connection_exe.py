"""Verify frozen Codex onboarding offline, using only a compiled synthetic CLI.

The real workbench EXE serves its actual APIs. A fixed .NET fixture named
codex.exe replaces every CLI invocation; it never opens a browser, accesses
personal auth, invokes a model, launches another program, or uses a network.
Only loopback HTTP connects to this smoke's private server process tree.
"""
from __future__ import annotations

import argparse
import base64
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
import urllib.request
import zipfile

try:
    from .smoke_workbench_exe import isolated_environment, start_owned_process
except ImportError:
    from smoke_workbench_exe import isolated_environment, start_owned_process


SECRET_MARKER = 'SYNTHETIC-CODEX-PRIVATE-OUTPUT-DO-NOT-ECHO-01923456789'
PROJECT_MARKER = 'SYNTHETIC-PROJECT-EVIDENCE-NOT-FOR-CONNECTION-8675309'


def create_fake_codex(root, environment):
    """Compile fixed local fixture code, never a user-supplied command."""
    directory = root / 'synthetic-cli'
    directory.mkdir()
    source = r'''using System;
using System.IO;
using System.Reflection;
using System.Text;
public static class SyntheticCodex {
  static readonly Encoding Utf8 = new UTF8Encoding(false);
  const string Secret = "SYNTHETIC-CODEX-PRIVATE-OUTPUT-DO-NOT-ECHO-01923456789";
  public static int Main(string[] args) {
    Console.OutputEncoding = Utf8;
    Console.InputEncoding = Utf8;
    string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
    string[] encoded = Array.ConvertAll(args, item => Convert.ToBase64String(Utf8.GetBytes(item)));
    File.AppendAllText(Path.Combine(root,"calls.log"),String.Join("\t",encoded)+"\n",Utf8);
    string marker = Path.Combine(root,"synthetic-login.marker");
    if(args.Length==1 && args[0]=="--version") {
      Console.WriteLine("codex-cli 0.0.0-fixture");
      Console.Error.WriteLine(Secret);
      return 0;
    }
    if(args.Length==2 && args[0]=="login" && args[1]=="status") {
      Console.Error.WriteLine(Secret);
      if(File.Exists(marker)) { Console.WriteLine("Logged in using ChatGPT"); return 0; }
      Console.WriteLine("Not logged in"); return 1;
    }
    if(args.Length==1 && args[0]=="login") {
      File.WriteAllText(marker,Secret,Utf8);
      Console.WriteLine("SYNTHETIC ONLY https://auth.invalid/oauth?code="+Secret+"&state=synthetic-state");
      return 0;
    }
    if(args.Length>0 && args[0]=="exec") {
      string output=null, cwd=null;
      for(int index=1;index+1<args.Length;index++) {
        if(args[index]=="-o") output=args[index+1];
        if(args[index]=="-C") cwd=args[index+1];
      }
      string prompt=Console.In.ReadToEnd();
      File.AppendAllText(Path.Combine(root,"prompts.log"),Convert.ToBase64String(Utf8.GetBytes(prompt))+"\n",Utf8);
      if(output==null || cwd==null || !Directory.Exists(cwd)) return 31;
      string parent=Path.GetFullPath(Path.GetDirectoryName(output));
      if(!String.Equals(parent,Path.GetFullPath(cwd),StringComparison.OrdinalIgnoreCase)) return 32;
      File.WriteAllText(Path.Combine(root,"test-cwd.txt"),Path.GetFullPath(cwd),Utf8);
      File.WriteAllText(Path.Combine(root,"test-cwd-count.txt"),Directory.GetFileSystemEntries(cwd).Length.ToString(),Utf8);
      File.WriteAllText(output,"连接成功",Utf8);
      Console.Error.WriteLine(Secret);
      return 0;
    }
    Console.Error.WriteLine("Synthetic fixture rejected unexpected arguments.");
    return 30;
  }
}'''
    code = directory / 'SyntheticCodex.cs'
    code.write_text(source, encoding='utf-8')
    windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
    compiler = next((item for item in (
        windows / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe',
        windows / 'Microsoft.NET/Framework/v4.0.30319/csc.exe',
    ) if item.is_file()), None)
    if compiler is None:
        raise RuntimeError('Windows .NET Framework csc.exe is required for the synthetic CLI fixture.')
    target = directory / 'codex.exe'
    process, tree = start_owned_process(
        [str(compiler), '/nologo', '/codepage:65001', '/target:exe', '/optimize+', '/out:' + str(target), str(code)],
        cwd=directory, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=30)
        if process.returncode or not target.is_file():
            raise RuntimeError('Synthetic CLI compilation failed: ' + (stdout + stderr).decode('utf-8', 'replace')[-2000:])
    finally:
        cleanup = tree.stop(process)
    if target.read_bytes()[:2] != b'MZ':
        raise RuntimeError('Synthetic CLI fixture is not a Windows executable.')
    return target, cleanup


def fixture_calls(fake):
    path = fake.parent / 'calls.log'
    if not path.exists():
        return []
    return [[base64.b64decode(value).decode('utf-8') for value in line.split('\t')]
            for line in path.read_text(encoding='utf-8').splitlines()]


def run(exe_path, root, timeout=60.):
    """Run only against a new output directory; never stop existing services."""
    root.mkdir(parents=True, exist_ok=False)
    checks = []
    report = {
        'ok': False, 'created': datetime.now(timezone.utc).isoformat(), 'checks': checks,
        'scope': 'Real frozen HTTP server with a synthetic native Codex fixture in an empty profile. No real CLI login, browser, model, ADB, external network, or clean-VM claim.',
        'real_cli_called': False, 'real_auth_accessed': False, 'real_model_called': False,
    }
    servers = []
    responses = []
    token = ''
    origin = ''
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
        req = urllib.request.Request(origin + path, data=body, headers=headers)
        try:
            with opener.open(req, timeout=timeout) as response:
                status, content, mime = response.status, response.read(), response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as error:
            status, content, mime = error.code, error.read(), error.headers.get('Content-Type', '')
        if SECRET_MARKER.encode() in content or b'auth.invalid/oauth' in content:
            raise AssertionError('HTTP exposed the synthetic private CLI output.')
        responses.append(content)
        if status != expected:
            raise AssertionError(f'{path}: HTTP {status}, expected {expected}: {content[:400]!r}')
        return json.loads(content) if 'application/json' in mime else content

    def start_server(exe, standalone, data, environment, phase):
        nonlocal token, origin
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        token, origin = '', f'http://127.0.0.1:{port}'
        log = (root / ('server-' + phase + '.log')).open('wb')
        try:
            server, tree = start_owned_process(
                [str(exe), '--no-browser', '--port', str(port), '--data-dir', str(data)],
                cwd=standalone, env=environment, stdout=log, stderr=subprocess.STDOUT,
            )
        except BaseException:
            log.close()
            raise
        owned = {'server': server, 'tree': tree, 'port': port, 'log': log, 'phase': phase}
        servers.append(owned)
        until = time.monotonic() + timeout
        while True:
            try:
                snapshot = request('/api/state')
                token = snapshot['token']
                return snapshot, owned
            except (OSError, AssertionError):
                if server.poll() is not None or time.monotonic() >= until:
                    raise RuntimeError('Frozen server did not start; inspect the isolated server log.')
                time.sleep(.2)

    def stop_server(owned):
        if 'cleanup' in owned:
            return
        try:
            owned['cleanup'] = owned['tree'].stop(owned['server'], port=owned['port'])
            check('owned_' + owned['phase'] + '_tree_and_listener_stopped', owned['cleanup']['verified'])
        finally:
            owned['log'].close()

    def operation(kind, body):
        queued = request('/api/integrations/codex/' + kind, body, expected=202)
        identifier = queued.get('operation', {}).get('id')
        check(kind + '_returns_async_operation', bool(identifier))
        until = time.monotonic() + timeout
        while True:
            snapshot = request('/api/integrations/codex')
            item = snapshot.get('operation') or {}
            if item.get('id') != identifier:
                raise AssertionError('Connection operation identity changed unexpectedly.')
            if item.get('status') != 'running':
                check(kind + '_operation_succeeds', item.get('status') == 'succeeded', str(item.get('message', '')))
                return snapshot
            if time.monotonic() >= until:
                request('/api/integrations/codex/cancel', {'operation_id': identifier})
                raise TimeoutError('Synthetic connection operation did not finish in time.')
            time.sleep(.1)

    try:
        standalone = root / 'standalone'
        standalone.mkdir()
        exe = standalone / 'ProductWorkbench.exe'
        shutil.copy2(exe_path, exe)
        with exe.open('rb') as stream:
            report['exe_identity'] = {'bytes': exe.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
        environment = isolated_environment(root)
        temporary = root / 'isolated-temp'
        temporary.mkdir()
        environment.update(TEMP=str(temporary), TMP=str(temporary))
        for name in ('OPENAI_API_KEY', 'OPENAI_ACCESS_TOKEN', 'CODEX_API_KEY', 'CODEX_TOKEN'):
            environment.pop(name, None)
        fake, report['fixture_compiler_cleanup'] = create_fake_codex(root, environment)
        data = root / 'data'
        snapshot, first = start_server(exe, standalone, data, environment, 'first')
        check('fresh_isolated_database', snapshot['projects'] == [])
        check('only_system32_on_PATH', environment['PATH'] == str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'))
        initial = request('/api/integrations/codex')
        check('no_real_or_synthetic_cli_discovered_automatically', initial['available'] is False)
        check('GET_without_saved_path_never_invokes_CLI', fixture_calls(fake) == [])

        saved = request('/api/integrations/codex', {'binary_path': str(fake)})
        check('synthetic_native_path_saved', Path(saved['binary_path']).resolve() == fake.resolve() and saved['command'] == [str(fake)])
        request('/api/integrations/codex')
        request('/api/state')
        check('save_and_GET_do_not_execute_CLI', fixture_calls(fake) == [])
        for kind in ('login', 'test'):
            for payload in ({}, {'confirmed': False}, {'confirmed': 'true'}, {'confirmed': 1}):
                request('/api/integrations/codex/' + kind, payload, expected=400)
        check('missing_or_nonboolean_confirmation_never_executes_CLI', fixture_calls(fake) == [])

        checked = operation('check', {})
        check('version_from_synthetic_CLI', checked['version'] == '0.0.0-fixture')
        check('initial_fake_account_not_logged_in', checked['auth']['status'] == 'not_logged_in')
        check('check_does_not_claim_model_test_passed', checked['test']['status'] == 'not_tested')
        check('check_runs_only_version_and_login_status', fixture_calls(fake) == [['--version'], ['login', 'status']])

        project = request('/api/projects', {'name': '冻结 Codex 接入合成项目', 'brief': PROJECT_MARKER}, expected=201)
        request('/api/documents', {'project_id': project['id'], 'name': 'synthetic-evidence.txt',
                                 'content': base64.b64encode(PROJECT_MARKER.encode()).decode()}, expected=201)
        logged = operation('login', {'confirmed': True})
        check('only_fake_marker_created', (fake.parent / 'synthetic-login.marker').is_file())
        check('fake_login_success_updates_auth_only', logged['auth']['status'] == 'logged_in' and logged['auth']['method'] == 'chatgpt' and logged['test']['status'] == 'not_tested')
        check('fake_login_uses_fixed_commands', fixture_calls(fake) == [['--version'], ['login', 'status'], ['login'], ['login', 'status']])

        tested = operation('test', {'confirmed': True})
        check('explicit_fake_minimum_model_test_passed', tested['test']['status'] == 'passed')
        calls = fixture_calls(fake)
        executions = [item for item in calls if item and item[0] == 'exec']
        check('exactly_one_fake_exec', len(executions) == 1)
        argv = executions[0]
        required_flags = {'--ignore-user-config', '--ephemeral', '--skip-git-repo-check'}
        check('test_ignores_user_configuration_and_is_ephemeral', required_flags <= set(argv))
        check('test_sandbox_read_only', '--sandbox' in argv and argv[argv.index('--sandbox') + 1] == 'read-only')
        overrides = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == '-c']
        check('test_disables_web_and_approvals', 'web_search="disabled"' in overrides and 'approval_policy="never"' in overrides)
        disabled = {argv[index + 1] for index, value in enumerate(argv[:-1]) if value == '--disable'}
        expected_disabled = {'shell_tool', 'unified_exec', 'multi_agent', 'multi_agent_v2', 'apps', 'plugins', 'hooks', 'computer_use', 'browser_use', 'memories', 'skill_search'}
        check('test_disables_general_tools_and_delegation', expected_disabled <= disabled)
        check('test_has_no_extra_MCP_or_image_input', '--image' not in argv and not any('mcp_servers' in item for item in overrides))
        prompts = [base64.b64decode(line).decode('utf-8') for line in (fake.parent / 'prompts.log').read_text(encoding='utf-8').splitlines()]
        check('test_uses_only_fixed_prompt_not_project_evidence', prompts == ['仅回复连接成功'] and all(PROJECT_MARKER not in item for item in prompts))
        test_cwd = Path((fake.parent / 'test-cwd.txt').read_text(encoding='utf-8')).resolve()
        check('test_uses_empty_isolated_temporary_directory', test_cwd.is_relative_to(temporary.resolve()) and (fake.parent / 'test-cwd-count.txt').read_text(encoding='utf-8') == '0' and not test_cwd.exists())
        check('all_public_responses_hide_private_CLI_output', bool(responses) and all(SECRET_MARKER.encode() not in item and b'auth.invalid/oauth' not in item for item in responses))

        package = request('/api/projects/' + project['id'] + '/export')
        (root / 'synthetic-project.zip').write_bytes(package)
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
            exported = json.loads(contents['data.json'])
            forbidden_values = [SECRET_MARKER, str(fake), str(fake).replace('\\', '\\\\'), 'codex-connection-v1']
            check('project_export_excludes_local_path_preferences_and_fake_login_marker',
                  'preferences' not in exported and all(not any(value.encode() in content for value in forbidden_values) for content in contents.values())
                  and not any('synthetic-cli' in name or 'auth.json' in name or 'synthetic-login.marker' in name for name in contents))
            check('project_export_keeps_product_evidence', any(PROJECT_MARKER.encode() in content for content in contents.values()))
        check('empty_profile_has_no_real_or_fake_auth_file', not (Path(environment['CODEX_HOME']) / 'auth.json').exists())

        stop_server(first)
        count_before_restart = len(fixture_calls(fake))
        restarted, _ = start_server(exe, standalone, data, environment, 'restart')
        persisted = restarted['integrations']['codex']
        check('saved_synthetic_path_survives_restart', persisted['binary_path'] == str(fake) and persisted['command'] == [str(fake)])
        check('restart_does_not_claim_cached_login_or_test', persisted['auth']['status'] == 'unknown' and persisted['test']['status'] == 'not_tested')
        check('restart_and_state_GET_never_execute_CLI', len(fixture_calls(fake)) == count_before_restart)
        report['fixture'] = {'kind': 'compiled synthetic .NET codex.exe', 'calls': len(calls), 'fake_exec_count': len(executions), 'synthetic_login_only': True}
        report['ok'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        for owned in reversed(servers):
            try:
                stop_server(owned)
            except Exception as error:
                report['ok'] = False
                report.setdefault('cleanup_errors', []).append(f'{type(error).__name__}: {error}')
        report['process_cleanup'] = [{'phase': item['phase'], **item.get('cleanup', {'verified': False})} for item in servers]
        report['ok'] = bool(report['ok'] and checks and all(item['passed'] for item in checks) and report.get('exe_identity') and report.get('fixture_compiler_cleanup', {}).get('verified') and servers and all(item.get('cleanup', {}).get('verified') for item in servers))
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (root / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Must not exist; contains synthetic fixtures only.')
    parser.add_argument('--timeout', type=float, default=60.)
    args = parser.parse_args()
    report = run(args.exe.resolve(), args.output.resolve(), args.timeout)
    print(json.dumps({'ok': report['ok'], 'passed': sum(item['passed'] for item in report['checks']),
                      'report': str(args.output.resolve() / 'verification.json'),
                      'error': report.get('error'), 'cleanup_errors': report.get('cleanup_errors')}, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
