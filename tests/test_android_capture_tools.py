"""Restricted capture bridge tests: synthetic screens only, no device/model."""
from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
import json
from pathlib import Path
import random

from PIL import Image
import pytest

from workbench.capture_tools import CaptureTools, review_session
from workbench import capture_tools


def image_bytes():
    pixels = random.Random(17).randbytes(120 * 200 * 3)
    stream = BytesIO()
    Image.frombytes("RGB", (120, 200), pixels).save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture
def session(tmp_path, monkeypatch):
    # Exercise the shipped fallback instead of relying on a personal skill.
    monkeypatch.delenv("WORKBENCH_ANDROID_SKILL", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-personal-codex"))
    # This suite intentionally preserves the previous engine as a legacy
    # evidence/runtime regression. New default behavior has a separate suite.
    monkeypatch.setattr(capture_tools, "skill_root", lambda: Path(__file__).resolve().parents[1] / "packages/android-capture/skill")
    request = {"adb_path": "synthetic-adb", "serial": "SYNTHETIC-ONLY", "package": "test.capture.app",
               "title": "合成走查", "scope": "仅验证合成首页到结果页", "app_version": "fixture",
               "max_actions": 4, "budget_seconds": 900}
    (tmp_path / "request.json").write_text(json.dumps(request), encoding="utf-8")
    tools = CaptureTools(tmp_path)
    device = {"screen": 0, "calls": [], "text": "Continue", "foreground": "test.capture.app/.MainActivity"}
    png = image_bytes()

    class FakeAdb:
        def __init__(self, *_args):
            self.serial = request["serial"]
            self.timings = []

        def run(self, args, phase, timeout=None):
            device["calls"].append((phase, args))
            self.timings.append({"phase": phase, "seconds": .001, "ok": True})
            if phase == "foreground":
                return f"mCurrentFocus=Window{{1 u0 {device['foreground']}}}".encode()
            if phase == "ui":
                return (f'<hierarchy><node text="Screen {device["screen"]}" package="test.capture.app" class="View" bounds="[0,0][120,200]">'
                        f'<node text="{device["text"]}" clickable="true" enabled="true" resource-id="next" class="Button" bounds="[0,0][100,80]" />'
                        '</node></hierarchy>').encode()
            if phase == "screenshot":
                return png
            if phase in {"tap", "back", "swipe", "launch"}:
                device["screen"] += 1
                return b""
            raise AssertionError(f"Unexpected synthetic ADB command: {phase}")

    monkeypatch.setattr(tools.capture, "AdbClient", FakeAdb)
    return tools, device, tmp_path


def attach(tools, observation, state):
    return tools.attach_observation(observation["id"], "M01", "P01", state, state)


def test_freshness_and_sensitive_click_guard_survive_bridge(session):
    tools, device, _ = session
    first = tools.observe()["observation"]
    device["screen"] = 1
    stale = tools.act_observe(first["id"], "tap", index=0)
    assert stale["ok"] is False
    assert "UI 已变化" in stale["error"]
    assert not stale["action_may_have_run"]
    assert not any(phase == "tap" for phase, _ in device["calls"])
    device["text"] = "Start Free Trial"
    paywall = tools.observe()["observation"]
    refused = tools.act_observe(paywall["id"], "tap", index=0)
    assert refused["ok"] is False
    assert "人工接管" in refused["error"]
    assert not any(phase == "tap" for phase, _ in device["calls"])


def test_outside_foreground_and_action_budget_do_not_send_input(session):
    tools, device, _ = session
    device["foreground"] = "com.android.permissioncontroller/.GrantPermissionsActivity"
    result = tools.observe()
    assert result["ok"] is False
    assert "前台不是目标" in result["error"]
    assert not any(phase == "screenshot" for phase, _ in device["calls"])
    device["foreground"] = "test.capture.app/.MainActivity"
    tools.request["max_actions"] = 1
    first = tools.observe()["observation"]
    after = tools.act_observe(first["id"], "tap", index=0)
    assert after["ok"]
    count = len(device["calls"])
    refused = tools.act_observe(after["observation"]["id"], "back")
    assert refused["ok"] is False and "动作预算" in refused["error"]
    assert len(device["calls"]) == count


def test_map_only_accepts_saved_observations_and_real_adjacent_actions(session):
    tools, _, root = session
    tools.add_module("M01", "合成首页")
    tools.add_page("P01", "M01", "合成页面")
    first = tools.observe()["observation"]
    second = tools.act_observe(first["id"], "tap", index=0)["observation"]
    third = tools.observe()["observation"]  # No recorded incoming action.
    assert attach(tools, first, "S01")["ok"]
    assert attach(tools, second, "S02")["ok"]
    assert attach(tools, third, "S03")["ok"]
    assert tools.add_transition("T01", "S01", "S02")["ok"]
    data = json.loads((root / "research-map.json").read_text(encoding="utf-8"))
    assert data["transitions"][0]["action"] == second["action"]
    assert not tools.add_transition("T02", "S02", "S03")["ok"]
    assert not tools.attach_observation("../../outside", "M01", "P01", "S04", "invalid")["ok"]
    assert not (root.parent / "outside").exists()


def test_finish_requires_review_and_explicit_key_path_completion(session):
    tools, _, root = session
    empty = tools.finish("completed", "无观察不能完成")
    assert empty["outcome"] == "blocked" and not empty["review"]["ok"]
    (root / "agent-result.json").unlink()  # A new server-authorized attempt.
    tools.add_module("M01", "合成首页")
    tools.add_page("P01", "M01", "合成页面")
    attach(tools, tools.observe()["observation"], "S01")
    partial = tools.finish("completed", "文件完整但尚未确认覆盖")
    assert partial["outcome"] == "paused" and partial["review"]["ok"]
    assert not tools.set_module_status("M01", "complete", "未经用户续跑不能改变终态")["ok"]
    (root / "agent-result.json").unlink()
    assert tools.set_module_status("M01", "complete", "已观察本轮唯一合成状态")["ok"]
    done = tools.finish("completed", "所选合成范围已覆盖")
    assert done["outcome"] == "completed" and done["review"]["ok"]
    assert len(done["composites"]) == 1
    assert all(not Path(item).is_absolute() for item in done["composites"])
    assert review_session(root)["ok"]
    saved = json.loads((root / "agent-result.json").read_text(encoding="utf-8"))
    assert saved["outcome"] == "completed"
    assert not tools.observe()["ok"]


def test_current_export_manifest_excludes_old_pngs_and_detects_tampered_observation(session):
    tools, _, root = session
    tools.add_module("M01", "合成首页")
    tools.add_page("P01", "M01", "合成页面")
    observation = tools.observe()["observation"]
    attach(tools, observation, "S01")
    old = root / "flow_export" / "old_flow.png"
    old.parent.mkdir()
    old.write_bytes(image_bytes())
    result = tools.export_flows()
    assert result["ok"] and result["review"]["ok"]
    assert "flow_export/old_flow.png" not in result["composites"]
    assert result["review"]["flow_count"] == len(result["composites"])
    path = root / "observations" / (observation["id"] + ".json")
    observation["activity"] = "fabricated"
    path.write_text(json.dumps(observation), encoding="utf-8")
    assert not review_session(root)["ok"]


def test_mcp_observe_returns_json_and_image_without_shell_tools(session, monkeypatch):
    from workbench import capture_mcp

    tools, _, root = session
    monkeypatch.setattr(capture_mcp, "CaptureTools", lambda _path: tools)
    server = capture_mcp.create_server(root)
    result = asyncio.run(server.call_tool("observe", {"include_image": True}))
    assert [item.type for item in result] == ["text", "image"]
    assert json.loads(result[0].text)["ok"]
    assert result[1].mimeType == "image/png"
    names = {item.name for item in asyncio.run(server.list_tools())}
    assert names == {"capture_context", "launch_app", "observe", "act_observe", "add_module", "add_page",
                     "attach_observation", "add_transition", "set_module_status", "export_flows", "finish", "view_observation"}


def test_explicit_new_attempt_resets_budget_without_discarding_evidence(session):
    tools, _, root = session
    observation = tools.observe()["observation"]
    assert tools.act_observe(observation["id"], "tap", index=0)["ok"]
    request = json.loads((root / "request.json").read_text(encoding="utf-8"))
    request["attempt_id"] = "new-human-authorized-attempt"
    (root / "request.json").write_text(json.dumps(request), encoding="utf-8")
    resumed = CaptureTools(root)
    assert resumed.state["actions_used"] == 0
    assert resumed.state["total_actions_used"] == 1
    assert (root / "observations" / (observation["id"] + ".json")).is_file()
    fresh = resumed.observe()["observation"]
    assert resumed.act_observe(fresh["id"], "tap", index=0)["ok"]
    assert resumed.state["total_actions_used"] == 2


def test_cancel_and_expired_time_budget_preserve_map_without_device_calls(session):
    tools, device, root = session
    tools.add_module("M01", "尚未采集")
    (root / "cancel.requested").write_text("stop", encoding="utf-8")
    assert not tools.observe()["ok"]
    assert device["calls"] == []
    (root / "cancel.requested").unlink()
    tools._budget_base = tools.request["budget_seconds"]
    assert not tools.observe()["ok"]
    assert device["calls"] == []
    assert tools.context()["map"]["modules"][0]["id"] == "M01"


@pytest.mark.parametrize("exited, removed", [(True, True), (False, False), (None, False)])
def test_only_confirmed_dead_owner_lock_is_recovered(tmp_path, monkeypatch, exited, removed):
    monkeypatch.setattr(capture_tools.tempfile, "gettempdir", lambda: str(tmp_path))
    directory = tmp_path / "codex-android-capture-locks"
    directory.mkdir()
    selected = directory / (hashlib.sha256(b"SYNTHETIC-SELECTED").hexdigest()[:24] + ".lock")
    other = directory / (hashlib.sha256(b"SYNTHETIC-OTHER").hexdigest()[:24] + ".lock")
    selected.write_text("123456", encoding="utf-8")
    other.write_text("654321", encoding="utf-8")
    queries = []

    def query(pid):
        queries.append(pid)
        return exited

    monkeypatch.setattr(capture_tools, "_process_exited", query)
    assert capture_tools._recover_stale_device_lock("SYNTHETIC-SELECTED") is removed
    assert selected.exists() is not removed
    assert queries == [123456]
    assert other.read_text(encoding="utf-8") == "654321"


def test_changed_lock_and_unparseable_owner_are_never_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_tools.tempfile, "gettempdir", lambda: str(tmp_path))
    directory = tmp_path / "codex-android-capture-locks"
    directory.mkdir()
    lock = directory / (hashlib.sha256(b"SYNTHETIC").hexdigest()[:24] + ".lock")
    lock.write_text("123456", encoding="utf-8")

    def owner_changed(_pid):
        lock.write_text("654321", encoding="utf-8")
        return True

    monkeypatch.setattr(capture_tools, "_process_exited", owner_changed)
    assert not capture_tools._recover_stale_device_lock("SYNTHETIC")
    assert lock.read_text(encoding="utf-8") == "654321"
    lock.write_text("not a process id", encoding="utf-8")
    monkeypatch.setattr(capture_tools, "_process_exited", lambda _: pytest.fail("Malformed owner must not be queried"))
    assert not capture_tools._recover_stale_device_lock("SYNTHETIC")
    assert lock.exists()


def test_synthetic_resume_observe_recovers_dead_session_lock_before_skill_mutex(session, monkeypatch):
    tools, _, root = session
    monkeypatch.setattr(capture_tools.tempfile, "gettempdir", lambda: str(root))
    directory = root / "codex-android-capture-locks"
    directory.mkdir()
    selected = directory / (hashlib.sha256(tools.request["serial"].encode()).hexdigest()[:24] + ".lock")
    other = directory / (hashlib.sha256(b"OTHER-SERIAL").hexdigest()[:24] + ".lock")
    selected.write_text("123456", encoding="utf-8")
    other.write_text("654321", encoding="utf-8")
    monkeypatch.setattr(capture_tools, "_process_exited", lambda pid: True if pid == 123456 else None)
    assert tools.observe()["ok"]
    assert not selected.exists()  # Original skill acquired/released its own lock.
    assert other.read_text(encoding="utf-8") == "654321"


@pytest.mark.parametrize("handle, last_error, exit_code, query_ok, expected", [
    (101, 0, 0, True, True),
    (101, 0, 259, True, False),
    (101, 0, 0, False, None),
    (0, 87, 0, False, True),
    (0, 5, 0, False, None),
])
def test_windows_owner_query_is_read_only_and_keeps_uncertain_owners(monkeypatch, handle, last_error, exit_code, query_ok, expected):
    import ctypes
    from types import SimpleNamespace

    opened, closed = [], []

    class Function:
        def __init__(self, function):
            self.function = function

        def __call__(self, *args):
            return self.function(*args)

    def open_process(access, inherit, pid):
        opened.append((access, inherit, pid))
        return handle

    def get_code(_handle, destination):
        destination._obj.value = exit_code
        return query_ok

    kernel = SimpleNamespace(OpenProcess=Function(open_process), GetExitCodeProcess=Function(get_code),
                             CloseHandle=Function(lambda value: closed.append(value) or True))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: last_error, raising=False)
    monkeypatch.setattr(capture_tools.os, "kill", lambda *_: pytest.fail("No signal may be sent to a Windows PID"))
    assert capture_tools._windows_process_exited(123456) is expected
    assert opened == [(0x1000, False, 123456)]
    assert closed == ([handle] if handle else [])
