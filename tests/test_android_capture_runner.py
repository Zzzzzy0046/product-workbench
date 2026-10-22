"""Capture-agent CLI boundary tests. FakeProcess never starts Codex or ADB."""
from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import tomllib
from types import SimpleNamespace

import pytest

from workbench.adapters import android_capture_runner as runner


class PromptInput(io.BytesIO):
    payload = b""

    def close(self):
        self.payload = self.getvalue()
        super().close()


class FakeProcess:
    pid = 76543

    def __init__(self, command, *, result=None, error="", exit_code=0, timeout=False, on_wait=None):
        self.command = list(command)
        self.stdin = PromptInput()
        self.stderr = io.BytesIO(error.encode("utf-8"))
        self.returncode = None
        self.result, self.exit_code, self.timeout, self.on_wait = result, exit_code, timeout, on_wait
        self.wait_timeouts = []
        self.terminated = False

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if self.on_wait:
            self.on_wait()
            self.on_wait = None
        if self.timeout and self.returncode is None:
            raise subprocess.TimeoutExpired(self.command, timeout)
        if self.returncode is None:
            if self.result is not None:
                directory = Path(self.command[self.command.index("-C") + 1])
                (directory / "agent-result.json").write_text(json.dumps(self.result, ensure_ascii=False), encoding="utf-8")
            self.returncode = self.exit_code
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15


@pytest.fixture
def capture_run(tmp_path, monkeypatch):
    codex_home = tmp_path / "isolated-codex-config"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text('''model = "config-model-is-not-the-snapshot"
model_provider = "selected"
model_reasoning_effort = "high"
service_tier = "fast"
[model_providers.selected]
name = "Fixture provider"
base_url = "https://example.invalid/v1"
wire_api = "responses"
requires_openai_auth = true
env_key = "CAPTURE_FIXTURE_API_KEY"
[model_providers.unselected]
experimental_bearer_token = "fixture-unselected-secret"
[mcp_servers.private]
command = "private-user-tool-must-not-be-inherited"
[features]
shell_tool = true
apps = true
''', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CAPTURE_FIXTURE_API_KEY", "fixture-live-secret-never-in-command")
    directory = tmp_path / "session"
    directory.mkdir()
    request = {"serial": "SYNTHETIC-ONLY", "package": "test.capture.app", "scope": "只看合成首页，不连接设备。",
               "title": "合成测试", "app_version": {"name": "fixture", "code": "0"},
               "model": "snapshot-capture-model", "max_actions": 60, "budget_seconds": 600,
               "python_path": sys.executable, "skill_root": str(Path(__file__).resolve().parents[1] / "packages/android-walkthrough/skill")}
    session = {"id": "fixture-session", "status": "running"}
    stopped = []

    def stop(process):
        stopped.append(process)
        process.terminate()
        return True

    service = SimpleNamespace(_capture_lock=threading.RLock(), _closed=threading.Event(), _capture_processes={},
                              _read=lambda _directory: session, stop_process=stop)
    calls, processes = [], []
    options = {"result": {"outcome": "paused", "summary": "合成结果", "reason": "未使用设备", "composites": []}}

    def popen(command, **kwargs):
        process = FakeProcess(command, **options)
        calls.append((list(command), kwargs))
        processes.append(process)
        return process

    monkeypatch.setattr(runner, "codex_command", lambda: ["fixture-codex"])
    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    return SimpleNamespace(directory=directory, request=request, session=session, service=service,
                           calls=calls, processes=processes, options=options, stopped=stopped)


def execute(fixture):
    return runner.run_capture_agent(fixture.service, fixture.session, fixture.directory, fixture.request)


def test_capture_runner_uses_the_connection_services_selected_cli(capture_run):
    capture_run.service.codex_connection = SimpleNamespace(command=lambda: ['selected-fixture-codex'])
    execute(capture_run)
    assert capture_run.calls[0][0][0] == 'selected-fixture-codex'


def test_capture_runner_isolates_only_capture_mcp_and_keeps_connection_and_model(capture_run):
    fixture = capture_run
    result = execute(fixture)
    assert result["outcome"] == "paused"
    command, kwargs = fixture.calls[0]
    assert command[0] == "fixture-codex"
    assert "--ignore-user-config" in command and "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--model") + 1] == "snapshot-capture-model"
    assert 'model_provider="selected"' in command
    assert 'model_reasoning_effort="high"' in command
    assert 'service_tier="fast"' in command
    assert 'approval_policy="never"' in command and 'web_search="disabled"' in command
    combined = " ".join(command)
    assert "config-model-is-not-the-snapshot" not in combined
    assert "fixture-live-secret" not in combined and "fixture-unselected-secret" not in combined
    assert "private-user-tool" not in combined
    overrides = [command[index + 1] for index, flag in enumerate(command[:-1]) if flag == "-c"]
    servers = [value for value in overrides if value.startswith("mcp_servers.")]
    assert len(servers) == 1
    config = tomllib.loads(servers[0])["mcp_servers"]
    assert set(config) == {"android_capture"}
    bridge = config["android_capture"]
    assert bridge["command"] == sys.executable
    assert bridge["enabled_tools"] == runner.CAPTURE_TOOLS
    assert bridge["args"] == ["-X", "utf8", str(Path(runner.__file__).resolve().parents[1] / "capture_mcp.py"),
                              "--session", str(fixture.directory)]
    assert bridge["required"] is True and bridge["cwd"] == str(fixture.directory)
    disabled = {command[index + 1] for index, flag in enumerate(command[:-1]) if flag == "--disable"}
    assert {"shell_tool", "unified_exec", "multi_agent", "multi_agent_v2", "apps", "plugins", "hooks",
            "computer_use", "browser_use", "memories", "skill_search"} <= disabled
    assert command[-1] == "-"
    assert kwargs["stdin"] == subprocess.PIPE and kwargs["stderr"] == subprocess.PIPE
    assert kwargs["stdout"].name.endswith("stdout-events.jsonl")
    assert not kwargs.get("shell", False)
    payload = fixture.processes[0].stdin.payload.decode("utf-8")
    assert fixture.request["scope"] in payload and "controls" in payload and "view_observation" in payload
    assert "fixture-live-secret" not in payload
    assert fixture.service._capture_processes[fixture.session["id"]] is fixture.processes[0]


def test_capture_runner_missing_finish_is_failure_even_when_cli_exits_success(capture_run):
    capture_run.options["result"] = None
    with pytest.raises(ValueError, match="未调用 finish"):
        execute(capture_run)
    assert len(capture_run.processes) == 1


@pytest.mark.parametrize("already_closed", [False, True])
def test_capture_runner_never_spawns_after_cancel_or_close(capture_run, already_closed):
    if already_closed:
        capture_run.service._closed.set()
    else:
        capture_run.session["status"] = "cancelled"
    with pytest.raises(ValueError, match="已停止"):
        execute(capture_run)
    assert capture_run.processes == []


def test_capture_runner_ignores_finish_after_midrun_cancel(capture_run):
    capture_run.options["on_wait"] = lambda: capture_run.session.update(status="cancelled")
    with pytest.raises(ValueError, match="已停止"):
        execute(capture_run)
    assert (capture_run.directory / "agent-result.json").is_file()


def test_capture_runner_timeout_stops_process_and_preserves_timeout_reason(capture_run):
    capture_run.options["timeout"] = True
    capture_run.options["result"] = None
    with pytest.raises(ValueError, match="时间上限"):
        execute(capture_run)
    assert capture_run.stopped == capture_run.processes
    assert capture_run.processes[0].terminated
    assert capture_run.processes[0].wait_timeouts == [780]
    assert not (capture_run.directory / "agent-result.json").exists()


def test_capture_runner_cli_error_redacts_selected_connection_credentials(capture_run):
    capture_run.options.update(result=None, exit_code=1, error="HTTP 401 Unauthorized fixture-live-secret-never-in-command")
    with pytest.raises(ValueError, match="登录或认证") as failure:
        execute(capture_run)
    assert "fixture-live-secret" not in str(failure.value)
    diagnostics = next(capture_run.directory.glob("attempts/*/codex-diagnostics.log")).read_text(encoding="utf-8")
    assert "fixture-live-secret" not in diagnostics
