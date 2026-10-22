"""Connection onboarding uses fake CLI processes only; no real login or model."""

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time

import pytest

from workbench.core import codex_config as config
from workbench.services import codex_connection_service as module


class App:
    def __init__(self, directory):
        self.path = directory / "test.sqlite3"
        self.lock = threading.RLock()
        with self.db() as db:
            db.execute("CREATE TABLE preferences(key TEXT PRIMARY KEY,value TEXT)")
            db.execute("CREATE TABLE jobs(id TEXT,status TEXT)")

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def rows(self, sql, args=()):
        with self.db() as db:
            return [dict(row) for row in db.execute(sql, args)]


@pytest.fixture
def service(tmp_path, monkeypatch):
    for name in ("WORKBENCH_CODEX_BIN", "WORKBENCH_CODEX_JS", "WORKBENCH_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    instance = module.CodexConnectionService(App(tmp_path))
    yield instance
    instance.close()


def binary(directory):
    path = directory / ("codex.exe" if os.name == "nt" else "codex")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ-fixture-only")
    path.chmod(0o755)
    return str(path.resolve())


def ready(service, tmp_path):
    path = binary(tmp_path / "native")
    service.configure({"binary_path": path})
    return path


def finished(service):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = service.snapshot()
        if state["operation"] and state["operation"]["status"] != "running":
            return state
        time.sleep(0.005)
    pytest.fail("fake connection operation failed to finish")


def test_snapshot_missing_never_spawns(service, monkeypatch):
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("GET spawned CLI"))
    state = service.snapshot()
    assert not state["available"]
    assert state["source"] == "missing"
    assert state["auth"]["status"] == "unknown"
    assert state["test"]["status"] == "not_tested"
    assert state["operation"] is None


@pytest.mark.parametrize("value", ["codex login", "codex.exe --token sk-secret", "./codex.exe", "\\\\server\\share\\codex.exe", "//server/share/codex.exe", "bad\npath"])
def test_rejects_commands_and_network_paths(service, value):
    with pytest.raises(ValueError):
        service.configure({"binary_path": value})
    assert service.app.rows("SELECT * FROM preferences") == []


def test_windows_manual_path_requires_named_pe(service, tmp_path):
    if os.name != "nt":
        pytest.skip("Windows native selection")
    for name, content in (("other.exe", b"MZ"), ("codex.cmd", b"echo hello"), ("codex.exe", b"not a PE")):
        path = tmp_path / name
        path.write_bytes(content)
        with pytest.raises(ValueError):
            service.configure({"binary_path": str(path)})


def test_saved_path_is_per_workbench_and_only_saved_preference(service, tmp_path):
    path = ready(service, tmp_path)
    assert service.command() == [path]
    assert service.snapshot()["source"] == "saved"
    prefs = service.app.rows("SELECT value FROM preferences")
    assert json.loads(prefs[0]["value"]) == {"binary_path": path}
    other = tmp_path / "other"
    other.mkdir()
    assert module.CodexConnectionService(App(other)).command() is None
    assert not os.environ.get("WORKBENCH_CODEX_BIN")


def test_environment_override_has_priority_and_cannot_be_edited(service, tmp_path, monkeypatch):
    saved = ready(service, tmp_path)
    override = binary(tmp_path / "override")
    monkeypatch.setenv("WORKBENCH_CODEX_BIN", override)
    state = service.snapshot()
    assert state["command"] == service.command() == [override]
    assert state["binary_path"] == saved
    assert state["env_managed"] and state["source"] == "environment"
    with pytest.raises(ValueError, match="环境变量"):
        service.configure({"binary_path": ""})


def test_invalid_environment_is_safe_and_does_not_fallback(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    monkeypatch.setenv("WORKBENCH_CODEX_BIN", "missing sk-VERYSECRET --password private")
    state = service.snapshot()
    assert not state["available"]
    assert "VERYSECRET" not in json.dumps(state)
    assert "password" not in json.dumps(state)
    with pytest.raises(ValueError):
        service.command()


def test_desktop_discovery_is_bounded_and_saved_path_beats_auto(service, tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows desktop discovery")
    desktop = binary(tmp_path / "local/OpenAI/Codex/bin/1234")
    state = service.snapshot()
    assert state["command"] == [desktop]
    assert state["source"] == "desktop"
    assert state["candidates"] == [{"path": desktop, "label": "Codex 桌面客户端", "source": "desktop"}]
    saved = ready(service, tmp_path)
    assert service.command() == [saved]


@pytest.mark.parametrize("kind", ["login", "test"])
@pytest.mark.parametrize("payload", [None, {}, {"confirmed": 1}, {"confirmed": "true"}, {"confirmed": False}])
def test_login_and_test_require_explicit_boolean_confirmation(service, tmp_path, monkeypatch, kind, payload):
    ready(service, tmp_path)
    monkeypatch.setattr(service, "_execute", lambda *args, **kwargs: pytest.fail("unconfirmed subprocess"))
    with pytest.raises(ValueError, match="确认"):
        service.start(kind, payload)


def test_check_parses_only_known_status_and_does_not_mark_test_passed(service, tmp_path, monkeypatch):
    path = ready(service, tmp_path)
    calls = []

    def execute(identifier, argv, timeout, **kwargs):
        calls.append(argv)
        return 0, "codex-cli 0.123.4\nsecret=sk-DO-NOT-RETURN" if argv[-1] == "--version" else "Logged in using ChatGPT\nhttps://secret.example?token=private"

    monkeypatch.setattr(service, "_execute", execute)
    service.start("check")
    state = finished(service)
    assert state["version"] == "0.123.4"
    assert state["auth"]["status"] == "logged_in"
    assert state["auth"]["method"] == "chatgpt"
    assert state["test"]["status"] == "not_tested"
    assert calls == [[path, "--version"], [path, "login", "status"]]
    serialized = json.dumps(state)
    assert "DO-NOT-RETURN" not in serialized and "secret.example" not in serialized
    assert len(service.app.rows("SELECT * FROM preferences")) == 1


@pytest.mark.parametrize("output,code,status,method", [("Not logged in", 1, "not_logged_in", "unknown"), ("Logged in using an API key: sk-secret", 0, "logged_in", "api_key"), ("Logged in using access token", 0, "logged_in", "access_token"), ("private secret unexpected text", 0, "error", "unknown")])
def test_login_status_classification_never_returns_raw_output(service, tmp_path, monkeypatch, output, code, status, method):
    ready(service, tmp_path)
    monkeypatch.setattr(service, "_execute", lambda identifier, argv, timeout, **kw: (0, "codex-cli 0.123.4") if argv[-1] == "--version" else (code, output))
    service.start("check")
    state = finished(service)
    assert state["auth"]["status"] == status
    assert state["auth"]["method"] == method
    assert "sk-secret" not in json.dumps(state)


def test_login_uses_official_flow_discards_oauth_and_requires_status_check(service, tmp_path, monkeypatch):
    path = ready(service, tmp_path)
    calls = []

    def execute(identifier, argv, timeout, **kwargs):
        calls.append((argv, timeout, kwargs))
        return (0, "") if argv[-1] == "login" else (0, "Logged in using ChatGPT")

    monkeypatch.setattr(service, "_execute", execute)
    service.start("login", {"confirmed": True})
    state = finished(service)
    assert calls[0] == ([path, "login"], 300, {"discard": True})
    assert calls[1][0] == [path, "login", "status"]
    assert state["auth"]["status"] == "logged_in"
    assert state["test"]["status"] == "not_tested"


@pytest.mark.parametrize("failure", ["exit", "timeout", "spawn"])
def test_login_failure_timeout_and_spawn_error_do_not_claim_success(service, tmp_path, monkeypatch, failure):
    ready(service, tmp_path)

    def execute(*args, **kwargs):
        if failure == "timeout":
            raise TimeoutError("https://secret.example?token=private")
        if failure == "spawn":
            raise OSError("sk-secret")
        return 1, "sk-secret https://secret.example"

    monkeypatch.setattr(service, "_execute", execute)
    service.start("login", {"confirmed": True})
    state = finished(service)
    assert state["operation"]["status"] == "failed"
    assert state["auth"]["status"] == "error"
    assert state["test"]["status"] == "not_tested"
    assert "sk-secret" not in json.dumps(state)
    assert "secret.example" not in json.dumps(state)


def test_cancel_remains_exclusive_until_worker_cleanup(service, tmp_path, monkeypatch):
    path = ready(service, tmp_path)
    entered, release = threading.Event(), threading.Event()

    def execute(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        raise InterruptedError()

    monkeypatch.setattr(service, "_execute", execute)
    operation = service.start("login", {"confirmed": True})["operation"]
    assert entered.wait(1)
    service.cancel(operation["id"])
    with pytest.raises(ValueError, match="正在执行"):
        service.start("check")
    with pytest.raises(ValueError, match="正在执行"):
        service.configure({"binary_path": path})
    release.set()
    assert finished(service)["operation"]["status"] == "cancelled"


def test_generation_blocks_login_test_and_path_change_but_not_check(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    with service.app.db() as db:
        db.execute("INSERT INTO jobs VALUES('job','queued')")
    for kind in ("login", "test"):
        with pytest.raises(ValueError, match="正在生成"):
            service.start(kind, {"confirmed": True})
    with pytest.raises(ValueError, match="正在生成"):
        service.configure({"binary_path": ""})
    monkeypatch.setattr(service, "_execute", lambda identifier, argv, timeout, **kwargs: (0, "codex-cli 0.123.4") if argv[-1] == "--version" else (1, "Not logged in"))
    service.start("check")
    assert finished(service)["auth"]["status"] == "not_logged_in"


def test_minimal_test_isolated_no_tools_and_cleanup(service, tmp_path, monkeypatch):
    path = ready(service, tmp_path)
    monkeypatch.setenv("WORKBENCH_MODEL", "fixture-model")
    calls = []

    def execute(identifier, argv, timeout, **kwargs):
        calls.append((argv, timeout, kwargs))
        output_file = Path(argv[argv.index("-o") + 1])
        assert list(output_file.parent.iterdir()) == []
        output_file.write_text("连接成功。", encoding="utf-8")
        return 0, "sensitive irrelevant stderr"

    monkeypatch.setattr(service, "_execute", execute)
    service.start("test", {"confirmed": True})
    state = finished(service)
    argv, timeout, kwargs = calls[0]
    assert argv[:2] == [path, "exec"]
    assert timeout == 90 and kwargs["prompt"] == "仅回复连接成功"
    assert "--ignore-user-config" in argv and "--ephemeral" in argv
    assert 'web_search="disabled"' in argv and 'approval_policy="never"' in argv
    assert argv[argv.index("--model") + 1] == "fixture-model"
    for feature in module.FEATURES_DISABLED:
        index = argv.index(feature)
        assert argv[index - 1] == "--disable"
    assert not Path(kwargs["cwd"]).exists()
    assert state["test"]["status"] == "passed"
    assert state["auth"]["status"] == "unknown"
    assert service.app.rows("SELECT * FROM jobs") == []
    assert "sensitive" not in json.dumps(state)
    monkeypatch.setenv("WORKBENCH_MODEL", "different-model")
    assert service.snapshot()["test"]["status"] == "not_tested"


def test_provider_change_invalidates_cached_auth(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    monkeypatch.setattr(service, "_execute", lambda identifier, argv, timeout, **kwargs: (0, "codex-cli 0.123.4") if argv[-1] == "--version" else (0, "Logged in using ChatGPT"))
    service.start("check")
    assert finished(service)["auth"]["status"] == "logged_in"
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text('model_provider="other"\n[model_providers.other]\nname="other"\nbase_url="https://example.test/v1"\nwire_api="responses"\n', encoding="utf-8")
    assert service.snapshot()["auth"]["status"] == "unknown"


def test_execute_uses_no_shell_hidden_pipes_and_discards_login_output(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    observed = []

    class Process:
        def __init__(self, command, **kwargs):
            observed.append((command, kwargs))
            self.stdout = io.BytesIO(b"codex-cli 0.123.4") if kwargs["stdout"] == subprocess.PIPE else None
            self.stderr = io.BytesIO(b"secret") if kwargs["stderr"] == subprocess.PIPE else None
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(module.subprocess, "Popen", Process)
    service._execute("fake", ["codex", "--version"], 1)
    service._execute("fake", ["codex", "login"], 1, discard=True)
    assert all(not kwargs.get("shell") for _, kwargs in observed)
    assert all(kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0) for _, kwargs in observed)
    assert observed[1][1]["stdout"] == subprocess.DEVNULL
    assert observed[1][1]["stderr"] == subprocess.DEVNULL
    assert service._processes == {}


def test_does_not_read_auth_store(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    original = Path.read_text

    def read(path, *args, **kwargs):
        assert path.name != "auth.json"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    service.snapshot()
    service.command()


def test_close_only_stops_owned_processes(service, monkeypatch):
    marker = object()
    stopped = []
    service._processes["owned"] = marker
    monkeypatch.setattr(service, "_stop", stopped.append)
    service.close()
    assert stopped == [marker]
    with pytest.raises(ValueError, match="已关闭"):
        service.start("check")


@pytest.mark.parametrize("diagnostic,expected", [("401 access_token=sk-VERYSECRET", "认证"), ("rate limit 429 sk-VERYSECRET", "限流"), ("model_not_found sk-VERYSECRET", "模型不可用"), ("network TLS sk-VERYSECRET", "网络"), ("unexpected argument sk-VERYSECRET", "不兼容")])
def test_minimal_test_failure_is_classified_without_raw_details(service, tmp_path, monkeypatch, diagnostic, expected):
    ready(service, tmp_path)
    monkeypatch.setattr(service, "_execute", lambda *args, **kwargs: (1, diagnostic))
    service.start("test", {"confirmed": True})
    state = finished(service)
    assert state["test"]["status"] == "failed"
    assert expected in state["test"]["message"]
    assert "VERYSECRET" not in json.dumps(state)
    assert service.app.rows("SELECT * FROM jobs") == []


def test_auth_and_model_output_are_not_persisted(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    service.configure({"binary_path": service.command()[0], "token": "do-not-store", "auth": {"secret": "private"}})
    monkeypatch.setattr(service, "_execute", lambda identifier, argv, timeout, **kwargs: (0, "codex-cli 0.123.4") if argv[-1] == "--version" else (0, "Logged in using an API key: sk-secret"))
    service.start("check")
    finished(service)
    raw = json.dumps(service.app.rows("SELECT * FROM preferences"))
    assert all(word not in raw for word in ("do-not-store", "private", "sk-secret", "logged_in", "checked_at"))


def test_capture_in_progress_blocks_login_and_configuration(service, tmp_path):
    ready(service, tmp_path)
    service.app.android_capture = type("Capture", (), {"_capture_processes": {"owned": object()}, "_capture_threads": {}})()
    with pytest.raises(ValueError, match="实机走查"):
        service.start("login", {"confirmed": True})
    with pytest.raises(ValueError, match="实机走查"):
        service.configure({"binary_path": ""})


def test_execute_timeout_stops_and_reaps_only_this_process(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    stopped = []

    class Process:
        def __init__(self, *args, **kwargs):
            self.stdout = io.BytesIO(b"token=sk-secret")
            self.stderr = io.BytesIO(b"https://secret.example")
            self.returncode = None

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("codex", timeout)

        def poll(self):
            return self.returncode

    def stop(process):
        stopped.append(process)
        process.returncode = -1
        return True

    monkeypatch.setattr(module.subprocess, "Popen", Process)
    monkeypatch.setattr(service, "_stop", stop)
    with pytest.raises(TimeoutError):
        service._execute("owned-test", ["codex", "--version"], 1)
    assert len(stopped) == 1
    assert service._processes == {}


def test_negative_authentication_text_does_not_claim_logged_in(service, tmp_path, monkeypatch):
    ready(service, tmp_path)
    monkeypatch.setattr(service, "_execute", lambda identifier, argv, timeout, **kwargs: (0, "codex-cli 0.123.4") if argv[-1] == "--version" else (0, "unauthenticated"))
    service.start("check")
    state = finished(service)
    assert state["auth"]["status"] == "error"
