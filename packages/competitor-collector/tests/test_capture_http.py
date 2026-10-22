"""Real HTTP/session routing with a fake capture backend; no device is used.

The fake deliberately enforces record ownership so these tests verify that the
HTTP boundary passes the authenticated identity, not physical ADB safety.
"""
from copy import deepcopy
import http.cookiejar
import io
import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request
import uuid
import zipfile

import pytest

from competitor_collector.android_capture import CaptureError
from competitor_collector.server import CollectorApp, CollectorHTTPServer, Handler


OPERATIONS = ("launch", "observe", "action", "label", "export", "release", "resume")
PASSWORD = "Capture-test-password-394!"


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ""

    def call(self, path, method="GET", payload=None, *, csrf=True, origin=True, extra=None):
        headers = dict(extra or {})
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
            if csrf:
                headers["X-CSRF-Token"] = self.csrf
            if origin:
                headers.setdefault("Origin", self.base)
        request = Request(self.base + path, method=method, data=data, headers=headers)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as response:
            return response.code, response.headers, response.read()
        with response:
            return response.status, response.headers, response.read()

    def login(self, username):
        status, _, raw = self.call("/api/login", "POST", {"username": username, "password": PASSWORD})
        assert status == 200, raw
        self.csrf = json.loads(raw)["csrf_token"]
        return self


class FakeCaptureService:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir()
        self.records = {}
        self.calls = []
        self.archives = []
        self.closed = False

    def meta(self):
        self.calls.append(("meta",))
        return {"source": "fake-capture", "android_only": True}

    def devices(self, user):
        self.calls.append(("devices", user["id"]))
        return {"devices": [{"serial": "emulator-5554", "state": "device"}]}

    def apps(self, user, serial):
        self.calls.append(("apps", user["id"], serial))
        if not serial:
            raise CaptureError("请选择设备。", 400)
        return {"apps": [{"package": "com.synthetic.fixture"}], "serial": serial}

    def list_for(self, user):
        self.calls.append(("list", user["id"]))
        return [deepcopy(record) for record in self.records.values()
                if user["role"] == "admin" or record["owner_id"] == user["id"]]

    def get(self, user, identifier):
        self.calls.append(("get", user["id"], identifier))
        record = self.records.get(identifier)
        if not record or (user["role"] != "admin" and record["owner_id"] != user["id"]):
            raise CaptureError("记录不存在或无权访问。", 404)
        return deepcopy(record)

    def create(self, user, payload):
        self.calls.append(("create", user["id"], deepcopy(payload)))
        if payload.get("package") == "invalid":
            raise CaptureError("包名无效。", 400)
        identifier = uuid.uuid4().hex
        record = {"id": identifier, "owner_id": user["id"], "title": payload.get("title", ""),
                  "serial": payload.get("serial"), "package": payload.get("package"), "status": "ready"}
        self.records[identifier] = record
        directory = self.data_dir / identifier
        directory.mkdir()
        (directory / "screen.png").write_bytes(b"synthetic-png-test-content")
        (directory / "notes.md").write_text("# Synthetic evidence", encoding="utf-8")
        return deepcopy(record)

    def command(self, user, identifier, operation, payload):
        current = self.get(user, identifier)
        if current["owner_id"] != user["id"] and not (user["role"] == "admin" and operation == "release"):
            raise CaptureError("你无权控制此截图任务。", 403)
        self.calls.append(("command", user["id"], identifier, operation, deepcopy(payload)))
        if payload.get("synthetic_error"):
            raise CaptureError("设备正由另一任务使用。", 409)
        record = self.records[identifier]
        record["last_operation"] = operation
        return deepcopy(record)

    def file(self, user, identifier, relative):
        self.get(user, identifier)
        self.calls.append(("file", user["id"], identifier, relative))
        # This policy belongs to the fake; real capture tests own path safety.
        if relative not in {"screen.png", "notes.md"}:
            raise CaptureError("文件不存在。", 404)
        return self.data_dir / identifier / relative

    def archive(self, user, identifier):
        self.get(user, identifier)
        self.calls.append(("archive", user["id"], identifier))
        path = self.data_dir / (uuid.uuid4().hex + ".zip")
        with zipfile.ZipFile(path, "w") as packed:
            packed.write(self.data_dir / identifier / "screen.png", "screenshots/screen.png")
            packed.write(self.data_dir / identifier / "notes.md", "notes.md")
        self.archives.append(path)
        return path

    def close(self):
        self.closed = True


@pytest.fixture(scope="module")
def capture_http(tmp_path_factory):
    directory = tmp_path_factory.mktemp("capture-http")
    app = CollectorApp(directory / "data", runner=lambda payload: pytest.fail("no store collection expected"))
    original = app.captures
    if hasattr(original, "close"):
        original.close()
    app.captures = fake = FakeCaptureService(directory / "fake-captures")
    admin = app.auth.bootstrap_admin("capture_admin", PASSWORD)
    member = app.auth.create_user(admin, "capture_member", PASSWORD)
    other = app.auth.create_user(admin, "capture_other", PASSWORD)
    server = CollectorHTTPServer(("127.0.0.1", 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    manager = Client(base).login("capture_admin")
    first = Client(base).login("capture_member")
    second = Client(base).login("capture_other")
    try:
        yield app, fake, base, manager, first, second, admin, member, other
    finally:
        server.shutdown()
        server.server_close()
        app.close()
        thread.join(timeout=5)
    assert fake.closed


def create_capture(client, **extra):
    payload = {"serial": "emulator-5554", "package": "com.synthetic.fixture", "title": "真实页面走查", **extra}
    status, _, raw = client.call("/api/captures", "POST", payload)
    assert status == 201, raw
    return json.loads(raw)["capture"]


def test_every_capture_route_requires_session(capture_http):
    _, fake, base, *_ = capture_http
    anonymous = Client(base)
    identifier = "a" * 32
    paths = ["/api/capture/meta", "/api/capture/devices", "/api/capture/apps?serial=emulator-5554",
             "/api/captures", f"/api/captures/{identifier}", f"/api/captures/{identifier}/archive",
             f"/api/captures/{identifier}/files/screen.png"]
    previous = len(fake.calls)
    for path in paths:
        assert anonymous.call(path)[0] == 401, path
    for path in ["/api/captures", *(f"/api/captures/{identifier}/{op}" for op in OPERATIONS)]:
        assert anonymous.call(path, "POST", {})[0] == 401, path
    assert len(fake.calls) == previous


def test_capture_read_routes_and_serial_query_are_read_only(capture_http):
    _, fake, _, _, first, *_ = capture_http
    assert json.loads(first.call("/api/capture/meta")[2])["source"] == "fake-capture"
    assert json.loads(first.call("/api/capture/devices")[2])["devices"][0]["state"] == "device"
    serial = "serial-test:5555"
    status, _, raw = first.call("/api/capture/apps?serial=" + quote(serial, safe=""))
    assert status == 200 and json.loads(raw)["serial"] == serial
    assert fake.calls[-1][2] == serial
    for suffix in ("", "?serial=", "?serial=one&serial=two"):
        assert first.call("/api/capture/apps" + suffix)[0] == 400
    record = create_capture(first)
    previous_commands = sum(call[0] == "command" for call in fake.calls)
    for operation in OPERATIONS:
        assert first.call(f"/api/captures/{record['id']}/{operation}")[0] == 404
    assert sum(call[0] == "command" for call in fake.calls) == previous_commands


@pytest.mark.parametrize("operation", ("create", *OPERATIONS))
def test_every_write_requires_csrf_and_exact_origin(capture_http, operation):
    _, fake, _, _, first, *_ = capture_http
    identifier = create_capture(first)["id"]
    path = "/api/captures" if operation == "create" else f"/api/captures/{identifier}/{operation}"
    previous = len(fake.calls)
    assert first.call(path, "POST", {}, csrf=False)[0] == 403
    assert first.call(path, "POST", {}, origin=False)[0] == 403
    assert first.call(path, "POST", {}, extra={"Origin": "http://attacker.example"})[0] == 403
    assert first.call(path, "POST", {}, extra={"Content-Type": "text/plain"})[0] == 415
    assert len(fake.calls) == previous


def test_commands_whitelist_status_and_actor_are_preserved(capture_http):
    _, fake, _, _, first, _, _, member, other = capture_http
    record = create_capture(first, owner_id=other["id"], role="admin")
    identifier = record["id"]
    assert record["owner_id"] == member["id"]
    for operation in OPERATIONS:
        status, _, raw = first.call(f"/api/captures/{identifier}/{operation}", "POST", {"marker": operation})
        assert status == 200, raw
        assert json.loads(raw)["capture"]["last_operation"] == operation
        assert fake.calls[-1][1:4] == (member["id"], identifier, operation)
    previous = len(fake.calls)
    for operation in ("delete", "shell", "exec", "install", "archive", "observe/extra"):
        assert first.call(f"/api/captures/{identifier}/{operation}", "POST", {})[0] == 404
    assert first.call(f"/api/captures/{identifier}", "POST", {})[0] == 404
    assert len(fake.calls) == previous
    status, _, raw = first.call(f"/api/captures/{identifier}/observe", "POST", {"synthetic_error": True})
    assert status == 409 and json.loads(raw)["error"] == "设备正由另一任务使用。"
    assert first.call("/api/captures", "POST", {"package": "invalid"})[0] == 400


def test_record_files_archive_are_owner_scoped_and_zip_deleted(capture_http):
    _, fake, _, manager, first, second, _, member, _ = capture_http
    record = create_capture(first)
    identifier = record["id"]
    assert record in json.loads(first.call("/api/captures")[2])["captures"]
    assert identifier not in {row["id"] for row in json.loads(second.call("/api/captures")[2])["captures"]}
    assert identifier in {row["id"] for row in json.loads(manager.call("/api/captures")[2])["captures"]}
    for path in (f"/api/captures/{identifier}", f"/api/captures/{identifier}/archive",
                 f"/api/captures/{identifier}/files/screen.png"):
        assert second.call(path)[0] == 404
        assert manager.call(path)[0] == 200
    for operation in OPERATIONS:
        assert second.call(f"/api/captures/{identifier}/{operation}", "POST", {})[0] == 404
    status, headers, raw = first.call(f"/api/captures/{identifier}/files/screen.png")
    assert status == 200 and raw == b"synthetic-png-test-content"
    assert headers["Content-Type"] == "image/png" and headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Disposition" not in headers
    status, headers, raw = first.call(f"/api/captures/{identifier}/files/notes.md")
    assert status == 200 and headers["Content-Disposition"].startswith("attachment;")
    status, headers, raw = first.call(f"/api/captures/{identifier}/archive")
    assert status == 200 and "materials.zip" in headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(raw)) as packed:
        assert set(packed.namelist()) == {"screenshots/screen.png", "notes.md"}
    deadline = time.monotonic() + 2
    while any(path.exists() for path in fake.archives) and time.monotonic() < deadline:
        time.sleep(.01)
    assert all(not path.exists() for path in fake.archives)
    assert ("file", member["id"], identifier, "screen.png") in fake.calls
    for relative in ("%2e%2e/auth.sqlite3", "capture.py", "%2e%2e%5csecret", "file%00.png"):
        assert first.call(f"/api/captures/{identifier}/files/{relative}")[0] == 404


def test_no_capture_source_or_data_is_a_public_static_file(capture_http):
    _, fake, base, _, first, *_ = capture_http
    previous = len(fake.calls)
    for path in ("/android_capture.py", "/capture.py", "/scripts/capture_session.py",
                 "/data/captures/anything.png", "/competitor_collector/android_capture.py"):
        assert Client(base).call(path)[0] == 401
        assert first.call(path)[0] == 404
    for identifier in ("not-an-id", "A" * 32, "a" * 31):
        assert first.call(f"/api/captures/{identifier}")[0] == 404
    assert len(fake.calls) == previous


def test_admin_can_release_but_cannot_drive_another_members_device(capture_http):
    _, fake, _, manager, first, *_ = capture_http
    identifier = create_capture(first)["id"]
    for operation in ("launch", "observe", "action", "label", "export", "resume"):
        assert manager.call(f"/api/captures/{identifier}/{operation}", "POST", {})[0] == 403
    status, _, raw = manager.call(f"/api/captures/{identifier}/release", "POST", {})
    assert status == 200 and json.loads(raw)["capture"]["last_operation"] == "release"
    assert fake.calls[-1][3] == "release"


def test_archive_is_removed_even_if_response_streaming_fails(capture_http, monkeypatch):
    _, fake, _, _, first, *_ = capture_http
    identifier = create_capture(first)["id"]
    original = Handler._file

    def fail_zip_response(handler, path, attachment=False):
        if path.suffix == ".zip":
            raise OSError("Synthetic read failure: must not reach client")
        return original(handler, path, attachment)

    monkeypatch.setattr(Handler, "_file", fail_zip_response)
    status, _, raw = first.call(f"/api/captures/{identifier}/archive")
    assert status == 500 and b"Synthetic read failure" not in raw
    assert not fake.archives[-1].exists()


def test_logout_and_admin_disabling_revoke_capture_access(capture_http):
    _, fake, base, manager, *_ = capture_http
    # Dedicated accounts prevent this session-revocation test changing other cases.
    status, _, raw = manager.call("/api/users", "POST", {"username": "capture_revoked", "password": PASSWORD})
    assert status == 201, raw
    user = json.loads(raw)["user"]
    client = Client(base).login("capture_revoked")
    record = create_capture(client)
    assert client.call("/api/logout", "POST", {})[0] == 200
    previous = len(fake.calls)
    assert client.call("/api/captures")[0] == 401
    assert client.call(f"/api/captures/{record['id']}/files/screen.png")[0] == 401
    assert len(fake.calls) == previous
    client.login("capture_revoked")
    assert manager.call("/api/users/" + user["id"], "PATCH", {"disabled": True})[0] == 200
    previous = len(fake.calls)
    for path, method, payload in (("/api/capture/devices", "GET", None),
                                  (f"/api/captures/{record['id']}", "GET", None),
                                  (f"/api/captures/{record['id']}/archive", "GET", None),
                                  (f"/api/captures/{record['id']}/observe", "POST", {})):
        assert client.call(path, method, payload)[0] == 401
    assert len(fake.calls) == previous
