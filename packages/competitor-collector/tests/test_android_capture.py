from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import zipfile

from PIL import Image
import pytest

from competitor_collector import android_capture as capture


OWNER = {"id": "alice", "username": "Alice", "role": "member", "disabled": False}
OTHER = {"id": "bob", "username": "Bob", "role": "member", "disabled": False}
ADMIN = {"id": "admin", "username": "Administrator", "role": "admin", "disabled": False}
PACKAGE = "com.example.gba"
SERIAL = "emulator-5554"


class FakeAdb:
    def __init__(self):
        self.calls = []
        self.position = 0
        self.foreground = PACKAGE
        self.fail_tap = False
        self.invalid_ui = False
        self.installed = True
        stream = BytesIO()
        Image.new("RGB", (320, 640), "#aabbcc").save(stream, format="PNG")
        self.png = stream.getvalue()

    def xml(self):
        if self.invalid_ui:
            return b"bad xml"
        return (f'<hierarchy><node package="{PACKAGE}" text="Page {self.position}" class="android.widget.FrameLayout" bounds="[0,0][320,640]" enabled="true">'
                '<node package="com.example.gba" text="" class="android.widget.Button" clickable="true" enabled="true" bounds="[10,10][140,60]">'
                '<node package="com.example.gba" text="Next" enabled="true"/></node>'
                '<node package="com.example.gba" text="" class="android.widget.Button" clickable="true" enabled="true" bounds="[10,80][140,130]">'
                '<node package="com.example.gba" text="Subscribe" enabled="true"/></node>'
                '</node></hierarchy>').encode()

    def __call__(self, args, **kwargs):
        assert kwargs.get("shell") is not True
        assert 0 < kwargs["timeout"] <= 15
        args = list(args)
        self.calls.append(args)
        command = args[1:]
        code, data = 0, b""
        if command == ["devices", "-l"]:
            data = f"List of devices attached\n{SERIAL} device product:virtual model:Pixel_5 transport_id:1\nother-phone unauthorized\n".encode()
        else:
            assert command[:2] == ["-s", SERIAL]
            command = command[2:]
            if command == ["shell", "pm", "list", "packages", "-3"]:
                data = ("package:" + PACKAGE + "\n").encode() if self.installed else b""
            elif command[:4] == ["shell", "cmd", "package", "resolve-activity"]:
                data = (PACKAGE + "/.MainActivity\n").encode()
            elif command[:3] == ["shell", "am", "start"]:
                self.foreground = PACKAGE
            elif command == ["shell", "dumpsys", "package", PACKAGE]:
                data = b"Packages:\n versionCode=42 minSdk=23\n versionName=2.1.0\n"
            elif command == ["shell", "dumpsys", "window", "windows"]:
                data = f"mCurrentFocus=Window{{aa u0 {self.foreground}/.MainActivity}}\n".encode()
            elif len(command) == 2 and command[0] == "shell" and command[1].startswith("uiautomator dump "):
                data = self.xml()
            elif command == ["exec-out", "screencap", "-p"]:
                data = self.png
            elif command[:3] == ["shell", "input", "tap"]:
                self.position += 1
                code = int(self.fail_tap)
            elif command[:3] in (["shell", "input", "keyevent"], ["shell", "input", "swipe"]):
                self.position += 1
            else:
                raise AssertionError(command)
        return SimpleNamespace(returncode=code, stdout=data, stderr=b"")


@pytest.fixture
def service(tmp_path, monkeypatch):
    adb = tmp_path / "adb.exe"
    adb.write_bytes(b"fake executable")
    fake = FakeAdb()
    monkeypatch.setattr(capture.subprocess, "run", fake)
    tool = capture.AndroidCaptureService(tmp_path / "data", adb_path=adb)
    tool.fake = fake
    yield tool
    tool.close()


def create(service, user=OWNER, **kwargs):
    return service.create(user, {"serial": SERIAL, "package": PACKAGE, "title": "GBA 竞品", **kwargs})


def observe(service, record):
    return service.command(OWNER, record["id"], "observe")


def label(service, record, state="默认状态", module="游戏库", page="首页"):
    return service.command(OWNER, record["id"], "label", {"observation_id": record["observation"]["id"], "module_title": module, "page_title": page, "state_title": state})


def test_metadata_does_not_touch_device(service):
    assert service.meta()["available"]
    assert service.meta()["automatic_exploration"] is False
    assert service.fake.calls == []


def test_missing_adb_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_trusted_adb", lambda value: None)
    tool = capture.AndroidCaptureService(tmp_path / "empty")
    assert not tool.meta()["available"]
    with pytest.raises(capture.CaptureError) as failure:
        tool.devices(OWNER)
    assert failure.value.status == 503
    tool.close()


def test_devices_apps_and_installed_only_creation(service):
    devices = service.devices(OWNER)["devices"]
    assert devices[0] == {"serial": SERIAL, "state": "device", "model": "Pixel 5", "busy": False}
    assert service.apps(OWNER, SERIAL)["apps"] == [{"package": PACKAGE}]
    service.fake.installed = False
    with pytest.raises(capture.CaptureError, match="未安装"):
        create(service)
    with pytest.raises(capture.CaptureError):
        service.apps(OWNER, "other-phone")


def test_create_and_get_never_capture_or_launch(service):
    record = create(service)
    assert record["app_version"] == "2.1.0"
    assert record["version_code"] == "42"
    assert record["model"] == "Pixel 5"
    assert record["observation"] is None
    count = len(service.fake.calls)
    assert service.get(OWNER, record["id"])["status"] == "active"
    assert len(service.list_for(OWNER)) == 1
    assert service.list_for(OTHER) == []
    assert len(service.fake.calls) == count
    assert not any("screencap" in args or "start" in args for args in service.fake.calls)


def test_members_isolated_admin_readonly(service):
    record = create(service)
    with pytest.raises(capture.CaptureError) as failure:
        service.get(OTHER, record["id"])
    assert failure.value.status == 404
    assert service.get(ADMIN, record["id"])["can_control"] is False
    count = len(service.fake.calls)
    for operation in ("launch", "observe", "action", "resume", "label", "export"):
        with pytest.raises(capture.CaptureError) as failure:
            service.command(ADMIN, record["id"], operation)
        assert failure.value.status == 403
    assert len(service.fake.calls) == count


def test_admin_can_release_other_owner_without_device_command(service):
    record = create(service)
    count = len(service.fake.calls)
    released = service.command(ADMIN, record["id"], "release")
    assert released["status"] == "paused"
    assert len(service.fake.calls) == count
    with pytest.raises(capture.CaptureError, match="无权"):
        service.command(OTHER, record["id"], "release")
    assert create(service, OTHER)["status"] == "active"


def test_device_lease_persists_across_instances(service):
    record = create(service)
    second = capture.AndroidCaptureService(service.data_dir, service.adb_path)
    with pytest.raises(capture.CaptureError, match="占用"):
        create(second, OTHER)
    second.close()
    assert service.get(OWNER, record["id"])["status"] == "active"
    service.command(OWNER, record["id"], "release")
    assert create(service, OTHER)["owner_id"] == OTHER["id"]


def test_operation_mutex_and_no_double_control(service):
    record = create(service)
    with service._operation(record["id"], SERIAL):
        count = len(service.fake.calls)
        with pytest.raises(capture.CaptureError) as failure:
            observe(service, record)
        assert failure.value.status == 409
        assert len(service.fake.calls) == count


def test_dead_process_lease_recovers_paused_without_adb(service):
    record = create(service)
    with service._transaction() as db:
        db.execute("UPDATE capture_leases SET pid=?,process_stamp=?", (2147483000, "dead"))
    before = len(service.fake.calls)
    second = capture.AndroidCaptureService(service.data_dir, service.adb_path)
    paused = second.get(OWNER, record["id"])
    assert paused["status"] == "paused"
    assert len(service.fake.calls) == before
    with pytest.raises(capture.CaptureError, match="暂停"):
        observe(second, paused)
    resumed = second.command(OWNER, record["id"], "resume")
    assert resumed["observation"] is None
    second.close()


def test_launch_observe_and_snapshot_bound_actions(service):
    record = create(service)
    record = service.command(OWNER, record["id"], "launch")
    observation = record["observation"]
    assert observation["actionable"]
    assert observation["screenshot_url"].startswith(f"/api/captures/{record['id']}/files/observations/")
    assert observation["clickables"][0]["index"] == 0
    assert observation["clickables"][0]["text"] == "Next"
    assert observation["clickables"][0]["safe"] is True
    assert observation["clickables"][1]["text"] == "Subscribe"
    assert observation["clickables"][1]["blocked"] is True
    assert len(service.file(OWNER, record["id"], observation["screenshot_url"].split("/files/", 1)[1]).read_bytes()) > 100
    next_record = service.command(OWNER, record["id"], "action", {"observation_id": observation["id"], "action": "tap", "index": 0})
    assert next_record["observation"]["id"] != observation["id"]
    assert next_record["observation"]["previous_observation_id"] == observation["id"]
    with pytest.raises(capture.CaptureError, match="过期"):
        service.command(OWNER, record["id"], "action", {"observation_id": observation["id"], "action": "tap", "index": 0})


def test_stale_ui_rejects_before_input(service):
    record = observe(service, create(service))
    service.fake.position += 1
    with pytest.raises(capture.CaptureError, match="UI 已变化") as failure:
        service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], "action": "tap", "index": 0})
    assert failure.value.action_may_have_run is False
    assert failure.value.record["observation"]["actionable"] is False
    assert not any(args[-5:-2] == ["input", "tap", "75"] for args in service.fake.calls)


def test_sensitive_container_child_blocked_before_input(service):
    record = observe(service, create(service))
    with pytest.raises(capture.CaptureError, match="购买"):
        service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], "action": "tap", "index": 1})
    assert not any("tap" in args for args in service.fake.calls)


def test_failed_input_retains_screenshot_and_demands_fresh_observation(service):
    record = observe(service, create(service))
    service.fake.fail_tap = True
    with pytest.raises(capture.CaptureError) as failure:
        service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], "action": "tap", "index": 0})
    assert failure.value.action_may_have_run is True
    assert failure.value.record["observation"]["screenshot_url"] == record["observation"]["screenshot_url"]
    assert failure.value.record["observation"]["actionable"] is False
    with pytest.raises(capture.CaptureError, match="重新观察"):
        service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], "action": "tap", "index": 0})
    fresh = observe(service, record)
    assert fresh["observation"]["actionable"]
    checkpoint = json.loads((service._root(record["id"]) / "capture-session.json").read_text())
    assert len(checkpoint["unresolved_actions"]) == 1


def test_outside_foreground_never_screenshots(service):
    record = create(service)
    service.fake.foreground = "com.android.permissioncontroller"
    with pytest.raises(capture.CaptureError, match="前台不是目标"):
        observe(service, record)
    assert not any("screencap" in args for args in service.fake.calls)


def test_invalid_xml_visual_capture_cannot_click(service):
    record = create(service)
    service.fake.invalid_ui = True
    record = observe(service, record)
    assert record["observation"]["status"] == "visual_only"
    assert not record["observation"]["actionable"]
    assert record["observation"]["screenshot_url"]


@pytest.mark.parametrize("direction", ["up", "down", "left", "right"])
def test_only_directional_swipes(service, direction):
    record = observe(service, create(service))
    updated = service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], "action": "swipe", "direction": direction, "swipe": [0, 0, 1, 1]})
    assert updated["observation"]["previous_observation_id"]
    actual = next(args for args in service.fake.calls if "swipe" in args)
    assert actual[-5:-1] != ["0", "0", "1", "1"]


@pytest.mark.parametrize("payload", [{"action": "shell", "command": "rm -rf /"}, {"action": "tap", "index": True}, {"action": "swipe", "direction": "../up"}])
def test_no_arbitrary_shell_coordinates_or_boolean_index(service, payload):
    record = observe(service, create(service))
    count = len(service.fake.calls)
    with pytest.raises(capture.CaptureError):
        service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], **payload})
    assert len(service.fake.calls) == count


def test_labels_reuse_module_page_and_preserve_observed_edge(service):
    record = label(service, observe(service, create(service)), "空列表")
    record = service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], "action": "tap", "index": 0})
    record = label(service, record, "有游戏")
    assert len(record["modules"]) == 1
    assert len(record["pages"]) == 1
    assert len(record["states"]) == 2
    assert len(record["transitions"]) == 1
    assert label(service, record, "有游戏")["states"] == record["states"]
    with pytest.raises(capture.CaptureError, match="已归档"):
        label(service, record, "更改原始状态")


def test_no_guessed_edge_when_source_not_labelled(service):
    record = observe(service, create(service))
    record = service.command(OWNER, record["id"], "action", {"observation_id": record["observation"]["id"], "action": "tap", "index": 0})
    record = label(service, record)
    assert len(record["states"]) == 1
    assert record["transitions"] == []


def test_stale_label_rejected_and_blank_state_defaults(service):
    record = observe(service, create(service))
    old_id = record["observation"]["id"]
    record = observe(service, record)
    with pytest.raises(capture.CaptureError, match="过期"):
        service.command(OWNER, record["id"], "label", {"observation_id": old_id, "module_title": "游戏库", "page_title": "首页"})
    record = label(service, record, state="")
    assert record["states"][0]["title"] == "默认状态"


def test_flow_action_uses_observed_descendant_label(service):
    record = label(service, observe(service, create(service)))
    record = service.command(OWNER, record["id"], "action", {
        "observation_id": record["observation"]["id"], "action": "tap", "index": 0,
    })
    record = label(service, record, page="详情页", state="完成")
    assert record["transitions"][0]["action"]["text"] == "Next"


def test_export_real_png_and_archive_allowlist(service):
    record = label(service, observe(service, create(service)))
    before = len(service.fake.calls)
    record = service.command(OWNER, record["id"], "export")
    assert len(service.fake.calls) == before
    assert record["flows"] and record["map_url"]
    relative = record["flows"][0]["url"].split("/files/", 1)[1]
    from urllib.parse import unquote
    png = service.file(OWNER, record["id"], unquote(relative))
    with Image.open(png) as image:
        assert image.width == 1280
        image.verify()
    (service._root(record["id"]) / "secret.env").write_text("TOKEN=private")
    bundle = service.archive(ADMIN, record["id"])
    with zipfile.ZipFile(bundle) as archive:
        assert "research-map.json" in archive.namelist()
        assert "app-map.md" in archive.namelist()
        manifest = json.loads(archive.read("evidence-manifest.json"))
        assert any(item["file"] == "research-map.json" and len(item["sha256"]) == 64 for item in manifest["files"])
        assert not any("sqlite" in name or "secret" in name or name.startswith("/") for name in archive.namelist())
        notes = next(name for name in archive.namelist() if name.endswith("flow_notes.md"))
        assert str(service.data_dir) not in archive.read(notes).decode()
    bundle.unlink()


@pytest.mark.parametrize("relative", ["../auth.sqlite3", "/etc/passwd", "C:/x.json", "observations/../../x.png", "observations\\x.png", "file://x.png", "x.exe", "x.json:stream", "./research-map.json"])
def test_safe_file_paths(service, relative):
    record = create(service)
    with pytest.raises(capture.CaptureError):
        service.file(OWNER, record["id"], relative)


def test_symlink_and_reparse_rejected(service, tmp_path, monkeypatch):
    record = observe(service, create(service))
    root = service._root(record["id"])
    original = capture._linked
    monkeypatch.setattr(capture, "_linked", lambda path: Path(path) == root / "observations" or original(path))
    name = record["observation"]["screenshot_url"].split("/files/", 1)[1]
    with pytest.raises(capture.CaptureError, match="链接"):
        service.file(OWNER, record["id"], name)
    with pytest.raises(capture.CaptureError, match="链接"):
        service.archive(OWNER, record["id"])


def test_limits_no_unbounded_capture(service, monkeypatch):
    record = observe(service, create(service))
    monkeypatch.setattr(capture, "MAX_OBSERVATIONS", 1)
    before = len(service.fake.calls)
    with pytest.raises(capture.CaptureError, match="上限"):
        observe(service, record)
    assert len(service.fake.calls) == before


def test_release_resume_and_clean_close(service):
    record = observe(service, create(service))
    record = service.command(OWNER, record["id"], "release")
    assert record["status"] == "paused"
    assert not record["observation"]["actionable"]
    record = service.command(OWNER, record["id"], "resume")
    assert record["status"] == "active" and record["observation"] is None
    service.close()
    second = capture.AndroidCaptureService(service.data_dir, service.adb_path)
    assert second.get(OWNER, record["id"])["status"] == "paused"
    second.close()


def test_clean_close_does_not_pause_transferred_lease(service):
    record = create(service)
    second = capture.AndroidCaptureService(service.data_dir, service.adb_path)
    with pytest.raises(capture.CaptureError, match="另一个采集器"):
        observe(second, record)
    second.command(OWNER, record["id"], "resume")
    service.close()
    assert second.get(OWNER, record["id"])["status"] == "active"
    assert observe(second, record)["observation"]["actionable"]
    second.close()


def test_shared_runtime_device_lock_blocks_without_adb(service):
    record = create(service)
    before = len(service.fake.calls)
    with capture.runtime.device_lock(SERIAL):
        with pytest.raises(capture.CaptureError, match="已有采集操作") as failure:
            observe(service, record)
        assert failure.value.status == 409
    assert len(service.fake.calls) == before


def test_version_failure_stays_unknown_without_fabrication(service, monkeypatch):
    actual = service._run
    def failed_version(args):
        if "dumpsys" in args:
            raise capture.CaptureError("Device unavailable", 409)
        return actual(args)
    monkeypatch.setattr(service, "_run", failed_version)
    record = create(service)
    assert record["app_version"].startswith("未知")
    assert record["version_code"] is None
    assert "读取失败" in record["warning"]
