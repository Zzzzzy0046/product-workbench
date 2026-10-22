"""Contract tests for the CLI boundary, without sending model requests."""

import importlib
import io
import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from workbench.core.codex_config import codex_runtime_settings

runner_module = importlib.import_module("workbench.adapters.codex_runner")
config_module = importlib.import_module("workbench.core.codex_config")


@pytest.fixture
def local_config(tmp_path, monkeypatch):
    directory = tmp_path / "codex-home"
    directory.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(directory))
    config = directory / "config.toml"
    config.write_text("", encoding="utf-8")
    return config


def test_connection_whitelist_preserves_selected_provider_without_tools_or_credentials(local_config, monkeypatch):
    local_config.write_text('''model = "current-model"
model_provider = "company"
model_reasoning_effort = "medium"
service_tier = "fast"
[model_providers.company]
name = "Company connection"
base_url = "https://example.invalid/v1"
wire_api = "responses"
requires_openai_auth = true
supports_websockets = false
env_key = "WORKBENCH_TEST_CREDENTIAL"
[model_providers.company.env_http_headers]
X-Client-Auth = "WORKBENCH_TEST_HEADER"
[model_providers.unselected]
experimental_bearer_token = "unselected-secret-must-not-be-copied"
[mcp_servers.private]
command = "private-tool"
[features]
shell_tool = true
''', encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_TEST_CREDENTIAL", "fake-test-secret")
    settings = codex_runtime_settings()
    overrides = settings["config_overrides"]
    assert 'model_provider="company"' in overrides
    assert 'model_providers."company".base_url="https://example.invalid/v1"' in overrides
    assert 'model_providers."company".requires_openai_auth=true' in overrides
    assert 'model_providers."company".supports_websockets=false' in overrides
    assert 'model_reasoning_effort="medium"' in overrides
    assert 'service_tier="fast"' in overrides
    assert settings["secret_env_names"] == ["WORKBENCH_TEST_CREDENTIAL", "WORKBENCH_TEST_HEADER"]
    serialized = json.dumps(settings)
    assert "fake-test-secret" not in serialized
    assert "unselected-secret" not in serialized
    assert "private-tool" not in serialized
    assert "shell_tool" not in serialized
    assert not any(item.startswith("model=") for item in overrides)


@pytest.mark.parametrize("entry", [
    'http_headers = { Authorization = "fake-static-secret" }',
    'experimental_bearer_token = "fake-static-secret"',
    'base_url = "https://user:fake-static-secret@example.invalid/v1"',
    'base_url = "https://example.invalid/v1?token=fake-static-secret"',
    'env_key = "not an env variable"',
    'env_http_headers = { Authorization = "Bearer fake-static-secret" }',
])
def test_connection_rejects_static_credentials_and_unsafe_endpoint(local_config, entry):
    local_config.write_text('model_provider = "company"\n[model_providers.company]\n' + entry, encoding="utf-8")
    with pytest.raises(ValueError) as error:
        codex_runtime_settings()
    assert "fake-static-secret" not in str(error.value)


def test_connection_does_not_read_auth_store(local_config, monkeypatch):
    original = Path.read_text
    reads = []

    def record(path, *args, **kwargs):
        reads.append(path.name)
        assert path.name != "auth.json"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", record)
    assert codex_runtime_settings() == {"config_overrides": [], "secret_env_names": []}
    assert reads == ["config.toml"]


class PromptInput(io.BytesIO):
    payload = b""

    def close(self):
        self.payload = self.getvalue()
        super().close()


class FakeProcess:
    pid = 54321

    def __init__(self, command, *, error="", output=None, exit_code=0, timeout=False):
        self.command = command
        self.stdin = PromptInput()
        self.stderr = io.BytesIO(error.encode("utf-8"))
        self.output = output
        self.exit_code = exit_code
        self.returncode = None
        self.timeout = timeout
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None):
        if self.timeout and self.returncode is None:
            raise subprocess.TimeoutExpired(self.command, timeout)
        if self.returncode is None:
            if self.output is not None:
                Path(self.command[self.command.index("-o") + 1]).write_text(self.output, encoding="utf-8")
            self.returncode = self.exit_code
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


def prepare_runner(tmp_path, monkeypatch, **process_options):
    job = {"id": "cli-boundary-job", "project_id": "f" * 32, "prompt": "生成中文文档，保留截图来源。", "status": "running"}
    directory = tmp_path / "runs" / job["id"]
    directory.mkdir(parents=True)
    uploads = tmp_path / "uploads" / job["project_id"]
    uploads.mkdir(parents=True)
    image = uploads / "source.png"
    image.write_bytes(b"test-image")
    (directory / "执行记录.json").write_text(json.dumps({"model": "snapshot-model", "sources": [{"image_path": str(image)}, {"image_path": str(image)}]}), encoding="utf-8")
    host = SimpleNamespace(data=tmp_path, lock=threading.RLock(), processes={}, job=lambda _: job)
    processes = []
    popen_calls = []

    def popen(command, **kwargs):
        process = FakeProcess(command, **process_options)
        processes.append(process)
        popen_calls.append((command, kwargs))
        return process

    monkeypatch.setattr(runner_module, "codex_command", lambda: ["node", "codex.js"])
    monkeypatch.setattr(runner_module.subprocess, "Popen", popen)
    return runner_module.CodexRunner(host), job, directory, processes, popen_calls


def test_runner_builds_isolated_cli_uses_snapshot_model_and_utf8_prompt(tmp_path, local_config, monkeypatch):
    local_config.write_text('model_provider = "company"\n[model_providers.company]\nbase_url = "https://example.invalid/v1"\nenv_key = "WORKBENCH_TEST_CREDENTIAL"', encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_TEST_CREDENTIAL", "fake-live-secret-never-in-argv")
    runner, job, directory, processes, calls = prepare_runner(tmp_path / "data", monkeypatch, output="# 中文交付物\n\n这是本轮生成的正文。")
    assert runner.run_codex(job).startswith("# 中文交付物")
    command, kwargs = calls[0]
    assert "--ignore-user-config" in command
    assert command[command.index("--model") + 1] == "snapshot-model"
    assert 'model_provider="company"' in command
    assert "fake-live-secret-never-in-argv" not in " ".join(command)
    assert command.count("--image") == 1
    assert processes[0].stdin.payload == job["prompt"].encode("utf-8")
    assert kwargs["stderr"] == subprocess.PIPE
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert command[-1] == "-"
    assert Path(command[command.index("-o") + 1]).name.startswith("model-output-")
    assert len(list(directory.glob("codex-diagnostics-*.log"))) == 1


def test_runner_never_accepts_previous_attempt_output(tmp_path, local_config, monkeypatch):
    runner, job, directory, _, _ = prepare_runner(tmp_path / "data", monkeypatch)
    old = directory / "model-output.md"
    old.write_text("这是上一次失败留下的旧正文，不能当作本次成功。", encoding="utf-8")
    with pytest.raises(ValueError, match="未生成最终文档"):
        runner.run_codex(job)
    assert old.read_text(encoding="utf-8").startswith("这是上一次")


@pytest.mark.parametrize("raw, expected", [
    ("error: unexpected argument '--wrong'", "参数或配置"),
    ("HTTP 401 Unauthorized. Authorization: Bearer fake-leaked-token", "登录或认证"),
    ("Error: model_not_found: unknown model demo", "模型不可用"),
    ("Error: stream disconnected; failed to send request", "网络或连接"),
    ("HTTP 429 insufficient_quota", "额度不足"),
])
def test_runner_failures_are_actionable_and_redacted(tmp_path, local_config, monkeypatch, raw, expected):
    monkeypatch.setenv("WORKBENCH_TEST_TOKEN", "fake-leaked-token")
    runner, job, directory, _, _ = prepare_runner(tmp_path / "data", monkeypatch, error=raw, exit_code=1)
    with pytest.raises(ValueError) as error:
        runner.run_codex(job)
    assert expected in str(error.value)
    assert "fake-leaked-token" not in str(error.value)
    diagnostic = next(directory.glob("codex-diagnostics-*.log")).read_text(encoding="utf-8")
    assert "fake-leaked-token" not in diagnostic


def test_diagnostic_redacts_custom_env_credentials_headers_and_urls(monkeypatch):
    monkeypatch.setenv("UNUSUAL_VARIABLE", "fake-custom-secret")
    raw = 'failure fake-custom-secret\nAuthorization: Bearer other-secret\nhttp_headers = { "X-Secret": "another-secret" }\nPOST https://private.example.invalid/v1?token=bad\nsk-test123456789'
    clean = runner_module.redact_codex_diagnostic(raw, ["UNUSUAL_VARIABLE"])
    for secret in ("fake-custom-secret", "other-secret", "another-secret", "private.example.invalid", "sk-test123456789"):
        assert secret not in clean


def test_runner_diagnostic_is_bounded(tmp_path, local_config, monkeypatch):
    runner, job, directory, _, _ = prepare_runner(tmp_path / "data", monkeypatch, error="x" * 50_000 + "\nnetwork timeout", exit_code=1)
    with pytest.raises(ValueError, match="网络或连接"):
        runner.run_codex(job)
    assert len(next(directory.glob("codex-diagnostics-*.log")).read_text(encoding="utf-8")) <= runner_module.DIAGNOSTIC_LIMIT


def test_timeout_stops_process_without_replacing_timeout_reason(tmp_path, local_config, monkeypatch):
    runner, job, _, processes, _ = prepare_runner(tmp_path / "data", monkeypatch, timeout=True)

    def failed_taskkill(*args, **kwargs):
        raise subprocess.TimeoutExpired("taskkill", 15)

    monkeypatch.setattr(runner_module.subprocess, "run", failed_taskkill)
    with pytest.raises(ValueError, match="超过 30 分钟，已停止"):
        runner.run_codex(job)
    assert processes[0].terminated
    assert processes[0].poll() is not None


def test_cancellation_before_launch_does_not_start_cli(tmp_path, local_config, monkeypatch):
    runner, job, _, _, calls = prepare_runner(tmp_path / "data", monkeypatch)
    job["status"] = "cancelled"
    with pytest.raises(ValueError, match="已取消"):
        runner.run_codex(job)
    assert not calls


def test_stop_process_falls_back_to_kill_when_taskkill_and_terminate_fail(monkeypatch):
    process = FakeProcess(["codex"], timeout=True)

    def fail(*args, **kwargs):
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(runner_module.subprocess, "run", fail)
    process.terminate = fail
    assert runner_module.CodexRunner.stop_process(process) is True
    assert process.killed
    assert process.poll() == -9


def test_cancellation_after_launch_is_not_reported_as_model_error(tmp_path, local_config, monkeypatch):
    runner, job, _, _, _ = prepare_runner(tmp_path / "data", monkeypatch, error="connection closed", exit_code=-15)
    original_wait = FakeProcess.wait

    def cancelled_wait(process, timeout=None):
        job["status"] = "cancelled"
        return original_wait(process, timeout)

    monkeypatch.setattr(FakeProcess, "wait", cancelled_wait)
    with pytest.raises(ValueError, match="任务已取消"):
        runner.run_codex(job)


def prepare_discovery(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKBENCH_CODEX_BIN", raising=False)
    monkeypatch.delenv("WORKBENCH_CODEX_JS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    script = tmp_path / "appdata/npm/node_modules/@openai/codex/bin/codex.js"
    script.parent.mkdir(parents=True)
    script.write_text("// fake entry", encoding="utf-8")
    native_name = "codex.exe" if os.name == "nt" else "codex"
    binary = tmp_path / native_name
    binary.write_bytes(b"fake-native-cli")
    binary.chmod(0o755)
    found = {native_name: str(binary), "node": str(tmp_path / "node")}
    monkeypatch.setattr(config_module.shutil, "which", lambda name: found.get(name))
    return script, binary, found


def test_cli_discovery_prefers_explicit_binary_over_explicit_script(tmp_path, monkeypatch):
    script, binary, _ = prepare_discovery(tmp_path, monkeypatch)
    monkeypatch.setenv("WORKBENCH_CODEX_BIN", str(binary))
    monkeypatch.setenv("WORKBENCH_CODEX_JS", str(script))
    assert config_module.codex_command() == [str(binary.resolve())]


def test_cli_discovery_explicit_script_beats_native_binary(tmp_path, monkeypatch):
    script, _, found = prepare_discovery(tmp_path, monkeypatch)
    monkeypatch.setenv("WORKBENCH_CODEX_JS", str(script))
    assert config_module.codex_command() == [found["node"], str(script.resolve())]


def test_cli_discovery_prefers_native_over_default_npm_script(tmp_path, monkeypatch):
    _, binary, _ = prepare_discovery(tmp_path, monkeypatch)
    assert config_module.codex_command() == [str(binary)]


def test_cli_discovery_prefers_newest_desktop_bundle_over_path(tmp_path, monkeypatch):
    # The desktop app ships its CLI in hashed folders that are only on PATH inside
    # its own sessions; started elsewhere, PATH resolves to an older npm shim that
    # rejects newer models ("model not found").
    _, path_binary, _ = prepare_discovery(tmp_path, monkeypatch)
    native_name = "codex.exe" if os.name == "nt" else "codex"
    root = tmp_path / "localappdata/OpenAI/Codex/bin"
    older, newer = root / "aaa" / native_name, root / "bbb" / native_name
    for index, path in enumerate([root / native_name, older, newer]):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")
        os.utime(path, (1_700_000_000 + index * 100, 1_700_000_000 + index * 100))
    assert config_module.codex_command() == [str(newer)]
    assert config_module.codex_command() != [str(path_binary)]


def test_cli_discovery_explicit_binary_beats_desktop_bundle(tmp_path, monkeypatch):
    _, binary, _ = prepare_discovery(tmp_path, monkeypatch)
    native_name = "codex.exe" if os.name == "nt" else "codex"
    bundled = tmp_path / "localappdata/OpenAI/Codex/bin/ccc" / native_name
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"fake")
    monkeypatch.setenv("WORKBENCH_CODEX_BIN", str(binary))
    assert config_module.codex_command() == [str(binary.resolve())]


def test_cli_discovery_uses_npm_when_native_binary_is_absent(tmp_path, monkeypatch):
    script, _, found = prepare_discovery(tmp_path, monkeypatch)
    found.pop("codex.exe" if os.name == "nt" else "codex")
    assert config_module.codex_command() == [found["node"], str(script)]


@pytest.mark.parametrize("field", ["WORKBENCH_CODEX_BIN", "WORKBENCH_CODEX_JS"])
def test_invalid_explicit_cli_override_does_not_fall_back(tmp_path, monkeypatch, field):
    prepare_discovery(tmp_path, monkeypatch)
    monkeypatch.setenv(field, str(tmp_path / "missing-entry"))
    with pytest.raises(ValueError, match=field):
        config_module.codex_command()


def test_explicit_javascript_requires_node(tmp_path, monkeypatch):
    script, _, found = prepare_discovery(tmp_path, monkeypatch)
    found.pop("node")
    monkeypatch.setenv("WORKBENCH_CODEX_JS", str(script))
    with pytest.raises(ValueError, match="需要 Node.js"):
        config_module.codex_command()


@pytest.mark.skipif(os.name != "nt", reason="Windows shell wrappers must not be launched without shell")
@pytest.mark.parametrize("suffix", [".cmd", ".ps1", ".bat"])
def test_explicit_windows_binary_rejects_shell_wrappers(tmp_path, monkeypatch, suffix):
    prepare_discovery(tmp_path, monkeypatch)
    wrapper = tmp_path / ("codex" + suffix)
    wrapper.write_text("fake-wrapper", encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_CODEX_BIN", str(wrapper))
    with pytest.raises(ValueError, match="原生可执行文件"):
        config_module.codex_command()
