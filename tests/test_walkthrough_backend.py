"""New shipped walkthrough backend, synthetic ADB only; no device or model."""
from __future__ import annotations

import asyncio
from io import BytesIO
import json
from pathlib import Path
import random
import shutil

from PIL import Image
import pytest

from workbench import capture_mcp, capture_tools
from workbench.capture_tools import CaptureTools, review_session
from workbench.adapters import walkthrough_backend as adapter


def png():
    stream = BytesIO()
    Image.frombytes("RGB", (120, 200), random.Random(11).randbytes(120 * 200 * 3)).save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKBENCH_ANDROID_SKILL", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "empty-codex"))
    request = {"adb_path": "ADB-MUST-NEVER-RUN", "serial": "SYNTHETIC-NEW", "package": "test.capture.app",
               "title": "合成新版", "scope": "仅检查合成页面", "app_version": {"name": "fixture", "code": "0"},
               "max_actions": 60, "budget_seconds": 600, "attempt_id": "synthetic-first"}
    (tmp_path / "request.json").write_text(json.dumps(request), encoding="utf-8")
    tools = CaptureTools(tmp_path)
    assert tools.backend and tools.context()["skill_source"] == "bundled"
    modules = tools.backend.modules
    state = {"screen": 0, "text": "Continue", "edit": False, "focused": False,
             "foreground": "test.capture.app/.MainActivity", "calls": [], "fail_shot": False}
    picture = png()

    def run(client, args, phase, timeout=None, ok_codes=(0,)):
        state["calls"].append((phase, args))
        client.timings.append({"phase": phase, "seconds": .001, "ok": True})
        if phase == "foreground":
            return f"mCurrentFocus=Window{{1 u0 {state['foreground']}}}".encode()
        if phase == "ui":
            widget = "android.widget.EditText" if state["edit"] else "android.widget.Button"
            return (f'<hierarchy><node text="Screen {state["screen"]}" package="test.capture.app" class="View" bounds="[0,0][120,200]">'
                    f'<node text="{state["text"]}" clickable="true" enabled="true" focused="{str(state["focused"]).lower()}" '
                    f'resource-id="test.capture.app:id/next" class="{widget}" bounds="[0,0][100,80]" />'
                    '</node></hierarchy>').encode()
        if phase == "screenshot":
            if state["fail_shot"]:
                state["fail_shot"] = False
                raise modules.errors.AwError("SCREENSHOT_INVALID", "Synthetic capture failed after input")
            return picture
        if phase in {"tap", "back", "swipe", "text", "key", "launch"}:
            state["screen"] += 1
            if phase == "back": state["foreground"] = "test.capture.app/.MainActivity"
            return b""
        raise AssertionError(f"No real ADB is permitted: {phase}")

    monkeypatch.setattr(modules.adb.Adb, "run", run)
    old_session_init = modules.session.Session.__init__
    old_device_init = modules.device.Device.__init__

    def session_init(self, *args, **kwargs):
        old_session_init(self, *args, **kwargs)
        self.sleep = lambda *_: None

    def device_init(self, *args, **kwargs):
        old_device_init(self, *args, **kwargs)
        self.sleep = lambda *_: None

    monkeypatch.setattr(modules.session.Session, "__init__", session_init)
    monkeypatch.setattr(modules.device.Device, "__init__", device_init)
    return tools, state, tmp_path, request


def register(tools, observation, state_id):
    return tools.attach_observation(observation["id"], "M01", "P01", state_id, state_id)


def test_default_new_bundle_frozen_priority_and_invalid_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "empty"))
    monkeypatch.delenv("WORKBENCH_ANDROID_SKILL", raising=False)
    shipped = adapter.ROOT / "packages/android-walkthrough/skill"
    assert adapter.resolve_skill_root() == shipped.resolve()
    monkeypatch.setenv("WORKBENCH_ANDROID_SKILL", str(tmp_path / "invalid-override"))
    with pytest.raises(ValueError, match="WORKBENCH_ANDROID_SKILL"):
        adapter.resolve_skill_root()
    monkeypatch.setattr(adapter.sys, "frozen", True, raising=False)
    assert adapter.resolve_skill_root() == shipped.resolve()


def test_controls_first_thumbnail_tool_reads_existing_observation_without_adb(synthetic, monkeypatch):
    tools, device, root, _ = synthetic
    monkeypatch.setattr(capture_mcp, "CaptureTools", lambda _root: tools)
    server = capture_mcp.create_server(root)
    content = asyncio.run(server.call_tool("observe", {}))
    assert [block.type for block in content] == ["text"]
    observation = json.loads(content[0].text)["observation"]
    assert observation["controls"] and "nodes" not in observation and "clickables" not in observation
    assert observation["files"]["view"].endswith(".view.jpg")
    before = list(device["calls"])
    viewed = asyncio.run(server.call_tool("view_observation", {"observation_id": observation["id"]}))
    assert [block.type for block in viewed] == ["text", "image"] and viewed[1].mimeType == "image/jpeg"
    assert device["calls"] == before
    assert not tools.view_observation("../../outside")["ok"]
    assert set(item.name for item in asyncio.run(server.list_tools())) == {
        "capture_context", "launch_app", "observe", "act_observe", "view_observation", "add_module", "add_page",
        "attach_observation", "add_transition", "set_module_status", "export_flows", "finish"}


def test_new_errors_keep_new_observation_and_never_replay_uncertain_input(synthetic):
    tools, device, _, _ = synthetic
    first = tools.observe()["observation"]
    device["screen"] += 1
    device["text"] = "A different action"
    changed = tools.act_observe(first["id"], "tap", index=0)
    assert not changed["ok"] and changed["code"] == "UI_CHANGED" and changed["next"] == "choose_again"
    assert changed["acted"] is False and changed["observation"]["id"] != first["id"]
    assert not any(phase == "tap" for phase, _ in device["calls"])
    fresh = changed["observation"]
    device["fail_shot"] = True
    uncertain = tools.act_observe(fresh["id"], "tap", index=0)
    assert not uncertain["ok"] and uncertain["acted"] is True and uncertain["action_may_have_run"] is True
    count = sum(phase == "tap" for phase, _ in device["calls"])
    refused = tools.act_observe(fresh["id"], "tap", index=0)
    assert not refused["ok"] and refused["code"] == "STALE_OBSERVATION"
    assert sum(phase == "tap" for phase, _ in device["calls"]) == count
    recovered = tools.observe()
    assert recovered["ok"] and recovered["observation"].get("unresolved_action")


def test_tap_xy_and_restricted_focused_text_use_guarded_inputs(synthetic):
    tools, device, _, _ = synthetic
    observed = tools.observe()["observation"]
    before = list(device["calls"])
    invalid = tools.act_observe(observed["id"], "tap-xy", coordinates=[-1, 20])
    assert not invalid["ok"] and invalid["code"] == "BAD_ARGS" and device["calls"] == before
    tapped = tools.act_observe(observed["id"], "tap-xy", coordinates=[20, 20], in_view=True)
    assert tapped["ok"] and tapped["observation"]["action"] == {"type": "tap-xy", "x": 20, "y": 20}
    assert any(phase == "tap" and args == ["shell", "input tap 20 20"] for phase, args in device["calls"])
    current = tapped["observation"]
    rejected = tools.act_observe(current["id"], "text", text="London")
    assert not rejected["ok"] and rejected["code"] == "NO_FOCUSED_INPUT"
    before = list(device["calls"])
    assert not tools.act_observe(current["id"], "text", text="a; rm")["ok"] and device["calls"] == before
    device.update(edit=True, focused=True, text="Search")
    focused = tools.observe()["observation"]
    accepted = tools.act_observe(focused["id"], "text", text="London", submit=True)
    assert accepted["ok"] and accepted["observation"]["action"] == {"type": "text", "value": "London", "submit": True}
    assert sum(phase == "text" for phase, _ in device["calls"]) == 1
    assert sum(phase == "key" for phase, _ in device["calls"]) == 1


def test_map_summaries_auto_edges_build_and_original_finish_contract(synthetic):
    tools, _, root, _ = synthetic
    assert tools.add_module("M01", "合成模块")["ok"]
    assert tools.add_page("P01", "M01", "合成页")["ok"]
    first = tools.observe()["observation"]
    assert register(tools, first, "S01")["edge"] is None
    second = tools.act_observe(first["id"], "tap", index=0)["observation"]
    attached = register(tools, second, "S02")
    assert attached["edge"] == "T01"
    assert tools.add_transition("T99", "S01", "S02")["already_recorded"]
    data = json.loads((root / "research-map.json").read_text(encoding="utf-8"))
    assert len(data["transitions"]) == 1
    assert "nodes" not in data["observations"][0] and "controls" not in data["observations"][0]
    assert data["observations"][0]["evidence_sha256"]
    assert tools.set_module_status("M01", "complete", "本轮合成关键路径已观察")["ok"]
    built = tools.export_flows()
    assert built["review"]["ok"] and built["build_review"] == "PASS"
    done = tools.finish("completed", "合成范围已完成")
    assert done["outcome"] == "completed" and done["composites"] and done["review"]["ok"]
    assert all(not Path(path).is_absolute() for path in done["composites"])
    assert review_session(root)["ok"]
    original = root / "observations" / f"{first['id']}.json"
    item = json.loads(original.read_text(encoding="utf-8")); item["controls"] = []
    original.write_text(json.dumps(item), encoding="utf-8")
    assert not review_session(root)["ok"]


def test_auto_dismiss_actions_budget_cancellation_and_sensitive_guards(synthetic):
    tools, device, root, _ = synthetic
    tools.request["max_actions"] = 1
    device["foreground"] = "test.capture.app/com.google.android.gms.ads.AdActivity"
    result = tools.observe()
    assert result["ok"] and result["observation"]["ads_closed"]
    assert tools.state["actions_used"] == 1
    before = list(device["calls"])
    assert not tools.act_observe(result["observation"]["id"], "back")["ok"]
    assert device["calls"] == before
    tools.request["max_actions"] = 60
    device["text"] = "Start Free Trial"
    payment = tools.observe()["observation"]
    blocked = tools.act_observe(payment["id"], "tap", index=0)
    assert not blocked["ok"] and blocked["code"] == "BLOCKED_SENSITIVE"
    before = list(device["calls"])
    (root / "cancel.requested").write_text("stop", encoding="utf-8")
    assert not tools.observe()["ok"] and device["calls"] == before


def test_legacy_evidence_resumes_only_after_fresh_new_observe(synthetic):
    tools, device, root, request = synthetic
    first = tools.observe()["observation"]
    assert tools.add_module("M01", "旧范围")["ok"] and tools.add_page("P01", "M01", "旧页面")["ok"]
    register(tools, first, "S01")
    # Preserve this observation and map but emulate the previous session marker.
    (root / "aw.json").unlink()
    state = json.loads((root / "capture-tool-state.json").read_text(encoding="utf-8"))
    state.pop("backend", None); state.pop("backend_version", None)
    (root / "capture-tool-state.json").write_text(json.dumps(state), encoding="utf-8")
    request["attempt_id"] = "human-resume"
    (root / "request.json").write_text(json.dumps(request), encoding="utf-8")
    resumed = CaptureTools(root)
    before = list(device["calls"])
    rejected = resumed.act_observe(first["id"], "tap", index=0)
    assert not rejected["ok"] and rejected["code"] == "STALE_OBSERVATION" and device["calls"] == before
    fresh = resumed.observe()["observation"]
    assert fresh["id"] != first["id"] and (root / "observations" / (first["id"] + ".json")).is_file()
    assert resumed._map()["states"][0]["id"] == "S01"


def test_new_result_is_visible_to_service_and_confirm_imports_real_evidence(synthetic, tmp_path, monkeypatch):
    from workbench.app import Workbench
    from workbench.services import android_capture_service
    tools, _, root, request = synthetic
    tools.add_module("M01", "合成范围"); tools.add_page("P01", "M01", "合成页面")
    register(tools, tools.observe()["observation"], "S01")
    tools.set_module_status("M01", "complete", "已观察唯一合成状态")
    final = tools.finish("completed", "合成会话可确认")
    assert final["outcome"] == "completed"
    workbench = Workbench(data_dir=tmp_path / "isolated-workbench", runner=lambda _: "never called")
    project = workbench.create_project("Synthetic project", "")
    service = workbench.android_capture
    monkeypatch.setattr(type(service), "preflight", lambda *_: {"serial": request["serial"], "app_version": request["app_version"]})
    session = service.create({"project_id": project["id"], "package": request["package"], "serial": request["serial"], "scope": request["scope"]})
    target, _ = service._find(session["id"])
    for source in root.iterdir():
        if source.name == "isolated-workbench": continue
        if source.is_dir(): shutil.copytree(source, target / source.name, dirs_exist_ok=True)
        else: shutil.copy2(source, target / source.name)
    monkeypatch.setattr(android_capture_service, "run_capture_agent", lambda *_: final)
    service._execute(session["id"], target, request)
    public = service.get(session["id"])
    assert public["status"] == "ready" and public["backend"] == "android-walkthrough"
    assert public["observations"] and public["composites"]
    confirmed = service.confirm(session["id"])
    assert confirmed["status"] == "confirmed" and len(confirmed["document_ids"]) >= 3
    content, _ = service.export(session["id"])
    import zipfile
    with zipfile.ZipFile(BytesIO(content)) as archive:
        assert "aw.json" not in archive.namelist() and any(name.endswith(".view.jpg") for name in archive.namelist())
