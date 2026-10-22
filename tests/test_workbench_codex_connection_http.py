"""Loopback HTTP contracts; fake connection service never starts the real CLI."""

import io
import json
import threading
import urllib.error
import urllib.request
import zipfile
from types import SimpleNamespace

import pytest

from workbench.api.handler import Handler
from workbench.core.runtime import ThreadingHTTPServer


class FakeCodexConnection:
    """Only the service contract is faked; Host/Origin/token checks stay real."""

    def __init__(self):
        self.calls = []

    def snapshot(self):
        self.calls.append(("snapshot",))
        return {"available": True, "auth": {"status": "unknown"}, "operation": None}

    def configure(self, payload):
        self.calls.append(("configure", payload))
        return {"saved": True}

    def start(self, kind, payload):
        if kind in {"login", "test"} and payload.get("confirmed") is not True:
            raise ValueError("请明确确认本次操作。")
        self.calls.append(("start", kind, payload))
        return {"operation": {"id": "synthetic-operation", "kind": kind, "status": "running"}}

    def cancel(self, operation_id):
        self.calls.append(("cancel", operation_id))
        return {"operation": {"id": operation_id, "status": "cancelled"}}


@pytest.fixture
def codex_http():
    service = FakeCodexConnection()
    bench = SimpleNamespace(token="synthetic-workbench-http-token", codex_connection=service)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.app = bench
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path="/api/integrations/codex", payload=None, *, token=True, origin=None, host=None, method=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Workbench-Token"] = bench.token if token is True else token
        if origin is not None:
            headers["Origin"] = origin
        if host is not None:
            headers["Host"] = host
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(base + path, data=body, headers=headers, method=method)
        try:
            with opener.open(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8")), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8")), error.headers

    try:
        yield service, request, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_codex_snapshot_is_read_only_and_never_cacheable(codex_http):
    service, request, _ = codex_http
    status, payload, headers = request(token=False)
    assert status == 200
    assert payload["auth"]["status"] == "unknown"
    assert service.calls == [("snapshot",)]
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("action", ["", "/check", "/login", "/test", "/cancel"])
@pytest.mark.parametrize("bad_token", [False, "wrong-local-token"])
def test_codex_mutations_require_workbench_token(codex_http, action, bad_token):
    service, request, _ = codex_http
    status, _, _ = request("/api/integrations/codex" + action, {"confirmed": True}, token=bad_token)
    assert status == 403
    assert service.calls == []


@pytest.mark.parametrize("action", ["", "/check", "/login", "/test", "/cancel"])
def test_codex_mutations_reject_foreign_origin_and_host(codex_http, action):
    service, request, _ = codex_http
    path = "/api/integrations/codex" + action
    assert request(path, {"confirmed": True}, origin="https://foreign.example")[0] == 403
    assert request(path, {"confirmed": True}, origin="null")[0] == 403
    assert request(path, {"confirmed": True}, host="foreign.example")[0] == 403
    assert service.calls == []


def test_codex_snapshot_rejects_nonloopback_host(codex_http):
    service, request, _ = codex_http
    assert request(host="foreign.example")[0] == 403
    assert service.calls == []


@pytest.mark.parametrize("kind", ["check", "login", "test"])
def test_codex_actions_use_async_contract_and_preserve_confirmation(codex_http, kind):
    service, request, base = codex_http
    body = {} if kind == "check" else {"confirmed": True}
    status, payload, _ = request("/api/integrations/codex/" + kind, body, origin=base)
    assert status == 202
    assert payload["operation"]["kind"] == kind
    assert service.calls == [("start", kind, body)]


@pytest.mark.parametrize("kind", ["login", "test"])
@pytest.mark.parametrize("confirmation", [None, False, "true", 1])
def test_codex_expensive_actions_do_not_coerce_confirmation(codex_http, kind, confirmation):
    service, request, _ = codex_http
    body = {} if confirmation is None else {"confirmed": confirmation}
    assert request("/api/integrations/codex/" + kind, body)[0] == 400
    assert service.calls == []


def test_codex_save_and_cancel_use_exact_service_contract(codex_http):
    service, request, _ = codex_http
    body = {"binary_path": r"C:\Synthetic Codex\codex.exe"}
    assert request(payload=body)[0] == 200
    assert service.calls == [("configure", body)]
    service.calls.clear()
    assert request("/api/integrations/codex/cancel", {"operation_id": "synthetic-operation"})[0] == 200
    assert service.calls == [("cancel", "synthetic-operation")]


@pytest.mark.parametrize("kind", ["check", "login", "test", "cancel"])
def test_codex_action_gets_never_start_processes(codex_http, kind):
    service, request, _ = codex_http
    assert request("/api/integrations/codex/" + kind, token=False)[0] == 404
    assert service.calls == []


def test_project_package_excludes_machine_codex_preferences_and_diagnostics(tmp_path):
    """Portable project ZIP is not an executable/configuration backup."""
    from workbench.app import Workbench

    bench = Workbench(tmp_path / "source", runner=lambda _: "# synthetic")
    marker = "MACHINE_ONLY_CODEX_SENTINEL_0123456789"
    project = bench.create_project("独立的资料项目", "合成测试数据")
    doc = bench.add_document(project["id"], "资料.txt", "可携带的产品资料".encode("utf-8"))
    with bench.db() as db:
        db.execute("INSERT OR REPLACE INTO preferences VALUES(?,?)", ("integration:codex", json.dumps({"binary_path": marker, "token": marker})))
        db.execute("INSERT OR REPLACE INTO preferences VALUES(?,?)", ("codex_connection", json.dumps({"binary_path": marker})))
        db.execute("INSERT OR REPLACE INTO preferences VALUES(?,?)", ("codex-connection-v1", json.dumps({"binary_path": marker})))
    private = bench.data / "codex-connection"
    private.mkdir()
    (private / "diagnostic.json").write_text(marker, encoding="utf-8")
    (bench.data / "auth.json").write_text(marker, encoding="utf-8")
    content, _ = bench.export_project(project["id"])
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
        snapshot = json.loads(members["data.json"])
        assert "preferences" not in snapshot
        assert doc["id"] in {item["id"] for item in snapshot["documents"]}
        assert all(marker.encode() not in value for value in members.values())
        assert not any("auth" in name or "codex-connection" in name for name in members)
    target = Workbench(tmp_path / "target", runner=lambda _: "# synthetic")
    target.import_project(content)
    assert not target.rows("SELECT * FROM preferences WHERE key LIKE '%codex%'")
    assert not (target.data / "auth.json").exists()
    bench.codex_connection.close()
    target.codex_connection.close()
