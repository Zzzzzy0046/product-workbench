"""Session-bound Android research tools; no arbitrary shell or filesystem tools.

Source runs prefer android-walkthrough. Frozen builds use their bundled copy;
legacy sessions remain readable without inheriting the old action indices.
"""
from __future__ import annotations

from argparse import Namespace
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from typing import Any
from types import SimpleNamespace

from workbench.adapters.walkthrough_backend import REFERENCE_FILES, WalkthroughBackend, resolve_skill_root


_IMPORT_LOCK = threading.RLock()
_LIBRARIES: dict[str, tuple[Any, Any, Any, Any]] = {}
_OBSERVATION_ID = re.compile(r"obs-[a-f0-9]{16}")
_ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _windows_process_exited(pid: int) -> bool | None:
    """Query only. os.kill(pid, 0) is deliberately never used on Windows."""
    import ctypes
    from ctypes import wintypes

    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            # A valid positive PID which no longer exists returns this error.
            # Access denied and every other failure are intentionally unknown.
            return True if ctypes.get_last_error() == 87 else None
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return code.value != 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None


def _process_exited(pid: int) -> bool | None:
    """True only when death is established; False/None must retain the lock."""
    if type(pid) is not int or not 1 <= pid <= 0xFFFFFFFF:
        return None
    if os.name == "nt":
        return _windows_process_exited(pid)
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return None


def _recover_stale_device_lock(serial: str) -> bool:
    """Remove only this serial's lock after positively checking its dead owner.

    An unreadable/replaced file, malformed PID, live/reused PID, or uncertain
    process query preserves the original skill's mutual exclusion unchanged.
    """
    directory = Path(tempfile.gettempdir()) / "codex-android-capture-locks"
    path = directory / (hashlib.sha256(serial.encode()).hexdigest()[:24] + ".lock")
    try:
        if directory.is_symlink() or path.is_symlink() or getattr(directory, "is_junction", lambda: False)():
            return False
        if not path.is_file():
            return False
        before = path.stat()
        with path.open("rb") as stream:
            original = stream.read(129)
        if len(original) > 128 or not re.fullmatch(rb"[1-9][0-9]{0,9}\s*", original):
            return False
        pid = int(original)
        if _process_exited(pid) is not True:
            return False
        with path.open("rb") as stream:
            current = stream.read(129)
        after = path.stat()
        identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        if current != original or identity(before) != identity(after):
            return False
        # Do not remove a new link substituted while checking the owner.
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            return False
        path.unlink()
        return True
    except (OSError, ValueError, OverflowError):
        return False


def skill_root() -> Path:
    return resolve_skill_root()


@contextmanager
def _research_alias(module):
    # The original scripts intentionally remain byte-for-byte copies.  Their
    # sibling imports are scoped while loading/calling, never added to sys.path.
    with _IMPORT_LOCK:
        previous = sys.modules.get("research_map")
        sys.modules["research_map"] = module
        try:
            yield
        finally:
            if previous is None:
                sys.modules.pop("research_map", None)
            else:
                sys.modules["research_map"] = previous


def _load_libraries(root: Path | None = None):
    root = (root or skill_root()).resolve()
    key = str(root)
    with _IMPORT_LOCK:
        if key not in _LIBRARIES:
            prefix = "_workbench_capture_" + hashlib.sha256(key.encode()).hexdigest()[:12]

            def load(name):
                spec = importlib.util.spec_from_file_location(prefix + "_" + name, root / "scripts" / (name + ".py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

            capture, research = load("capture_session"), load("research_map")
            with _research_alias(research):
                montage, review = load("build_flow_montages"), load("review_delivery")
            _LIBRARIES[key] = capture, research, montage, review
        return _LIBRARIES[key]


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("会话文件标识无效。")
    if Path(relative).is_absolute() or re.match(r"^[A-Za-z]:", relative) or ":" in relative:
        raise ValueError("会话文件必须使用相对路径。")
    normalized = relative.replace("\\", "/")
    if ".." in normalized.split("/"):
        raise ValueError("会话文件不能越过当前目录。")
    target = (root / normalized).resolve()
    if not target.is_relative_to(root):
        raise ValueError("会话文件超出当前目录。")
    return target


def _json(root: Path, relative: str, default=None):
    path = _inside(root, relative)
    if not path.is_file():
        if default is not None:
            return default
        raise ValueError("会话资料不存在。")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("会话资料超过读取上限。")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("会话资料必须是 JSON 对象。")
    return value


def _request(root: Path) -> dict:
    request = _json(root, "request.json")
    for field in ("adb_path", "serial", "package", "scope"):
        if not isinstance(request.get(field), str) or not request[field].strip():
            raise ValueError(f"走查请求缺少 {field}。")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", request["serial"]):
        raise ValueError("设备 serial 无效。")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", request["package"]):
        raise ValueError("目标包名无效。")
    for field, fallback, upper in (("max_actions", 60, 1000), ("budget_seconds", 900, 14400)):
        value = request.get(field, fallback)
        if type(value) is not int or not 1 <= value <= upper:
            raise ValueError(f"{field} 超出允许范围。")
        request[field] = value
    attempt = request.get("attempt_id", "")
    if not isinstance(attempt, str) or len(attempt) > 128 or attempt and not re.fullmatch(r"[A-Za-z0-9_-]+", attempt):
        raise ValueError("attempt_id 无效。")
    return request


def _observation(root: Path, identifier: str, request: dict) -> dict:
    if not isinstance(identifier, str) or not _OBSERVATION_ID.fullmatch(identifier):
        raise ValueError("observation_id 无效。")
    item = _json(root, f"observations/{identifier}.json")
    if item.get("id") != identifier or item.get("package") != request["package"] or item.get("serial") != request["serial"]:
        raise ValueError("观察记录与当前应用或设备不一致。")
    files = item.get("files") or {}
    if files.get("screenshot") != f"observations/{identifier}.png":
        raise ValueError("观察截图与原始记录不匹配。")
    for field in ("screenshot", "ui_xml"):
        ref = files.get(field)
        if ref:
            if field == "ui_xml" and ref != f"observations/{identifier}.xml":
                raise ValueError("观察 XML 与原始记录不匹配。")
            if not _inside(root, ref).is_file():
                raise ValueError("观察原始证据文件缺失。")
    if files.get("view") and (files["view"] != f"observations/{identifier}.view.jpg" or not _inside(root, files["view"]).is_file()):
        raise ValueError("观察缩略图与原始记录不匹配。")
    return item


def review_session(session_dir: str | Path) -> dict:
    """Independently validate original observations and current flow exports.

    This never talks to ADB, starts a model, marks modules complete, or changes
    agent-result.json. It may write the deterministic delivery review report.
    """
    root = Path(session_dir).resolve()
    request = _request(root)
    if (root / "aw.json").is_file() or _json(root, "capture-tool-state.json", {}).get("backend") == "android-walkthrough":
        return _review_walkthrough(root, request)
    _, research, _, review = _load_libraries(_ROOT / "packages/android-capture/skill")
    errors: list[str] = []
    data = _json(root, "research-map.json", {})
    for item in data.get("observations", []):
        try:
            saved = _observation(root, item.get("id"), request)
            if saved != item:
                errors.append("地图观察与原始记录不一致。")
        except (ValueError, OSError, TypeError) as exc:
            errors.append(str(exc))
    if not data.get("observations") or not data.get("states"):
        errors.append("尚无已登记的真实观察与页面状态。")
    manifest = _json(root, "flow-manifest.json", {})
    composites = manifest.get("composites", [])
    if not isinstance(composites, list) or not composites:
        errors.append("本轮尚无有效流程拼图清单。")
        composites = []
    for relative in composites:
        try:
            path = _inside(root, relative)
            if not isinstance(relative, str) or not relative.startswith("flow_export/") or not relative.endswith("_flow.png") or not path.is_file():
                errors.append("本轮流程拼图清单引用无效。")
        except ValueError as exc:
            errors.append(str(exc))
    try:
        with _research_alias(research):
            report = review.review_delivery(Namespace(
                input_dir=str(root), research_map=str(_inside(root, "research-map.json")),
                summary=None, require_summary=False, require_flow=True,
                require_axure=False, require_docx=False, out=str(_inside(root, "delivery_review.md")),
            ))
    except (ValueError, OSError, KeyError, TypeError, SystemExit):
        report = {"ok": False, "issues": ["走查交付检查无法完成，请核对地图与原始证据。"], "warnings": []}
    issues = list(dict.fromkeys([*report.get("issues", []), *errors]))
    return {"ok": bool(report.get("ok")) and not issues, "issues": issues,
            "warnings": report.get("warnings", []), "map_result": report.get("map_result", {}),
            "flow_count": len(composites), "report": "delivery_review.md"}


def _review_walkthrough(root, request):
    backend = WalkthroughBackend(root, request, skill_root(), initialize=False)
    issues = []
    data = _json(root, "research-map.json", {})
    for item in data.get("observations", []):
        try:
            saved = _observation(root, item.get("id"), request)
            summarize = backend.modules.mapstore.summarize
            if summarize(saved) != summarize(item):
                issues.append("地图观察摘要与原始记录不一致。")
            expected = item.get("evidence_sha256")
            if expected and hashlib.sha256(_inside(root, f"observations/{item['id']}.json").read_bytes()).hexdigest() != expected:
                issues.append("原始观察记录摘要校验失败。")
        except (ValueError, OSError, TypeError) as error:
            issues.append(str(error))
    observations = {item["id"]: item for item in data.get("observations", [])}
    for state in data.get("states", []):
        original = observations.get(state.get("observation_id"), {}).get("files", {})
        for name in ("screenshot", "ui_xml"):
            if name in state and state[name] != original.get(name, ""):
                issues.append("旧页面状态与观察证据不一致。")
    if not data.get("observations") or not data.get("states"):
        issues.append("尚无已登记的真实观察与页面状态。")
    manifest = _json(root, "flow-manifest.json", {})
    composites = manifest.get("composites", [])
    if not isinstance(composites, list) or not composites:
        composites = []
        issues.append("本轮尚无有效流程拼图清单。")
    for relative in composites:
        try:
            path = _inside(root, relative)
            if not relative.startswith("flow_export/") or not relative.endswith("_flow.png") or not path.is_file():
                issues.append("本轮流程拼图清单引用无效。")
        except (ValueError, TypeError):
            issues.append("本轮流程拼图清单引用无效。")
    try:
        report = backend.review()
    except (ValueError, OSError, KeyError, TypeError):
        report = {"status": "FAIL", "issues": ["新版交付检查无法完成。"], "warnings": []}
    issues = list(dict.fromkeys([*report.get("issues", []), *issues]))
    return {"ok": report.get("status") == "PASS" and not issues, "issues": issues,
            "warnings": report.get("warnings", []), "map_result": backend.modules.mapstore.check_map(data, root),
            "flow_count": len(composites), "report": "delivery_review.md", "backend": "android-walkthrough"}


class CaptureTools:
    def __init__(self, session_dir: str | Path):
        self.root = Path(session_dir).resolve()
        if not self.root.is_dir():
            raise ValueError("走查会话目录不存在。")
        self.request = _request(self.root)
        self.skill = skill_root()
        self.backend = WalkthroughBackend(self.root, self.request, self.skill, self._before_adb) if (self.skill / "scripts/aw/__init__.py").is_file() else None
        if self.backend:
            self.capture = SimpleNamespace(atomic_json=self.backend.modules.workspace.atomic_json, CaptureError=self.backend.error_type)
            self.research, self.montage = self.backend.modules.mapstore, None
        else:
            self.capture, self.research, self.montage, _ = _load_libraries(self.skill)
        self.lock = threading.RLock()
        self.state = _json(self.root, "capture-tool-state.json", {"actions_used": 0, "budget_seconds_used": 0})
        new_attempt = self.state.get("attempt_id", "") != self.request.get("attempt_id", "")
        if new_attempt:
            self.state = {"attempt_id": self.request.get("attempt_id", ""), "actions_used": 0, "budget_seconds_used": 0,
                          "total_actions_before_attempt": self.state.get("total_actions_used", self.state.get("actions_used", 0)),
                          "total_seconds_before_attempt": self.state.get("total_budget_seconds_used", self.state.get("budget_seconds_used", 0))}
        self.started = time.monotonic()
        self._budget_base = float(self.state.get("budget_seconds_used", 0))
        map_path = _inside(self.root, "research-map.json")
        if not map_path.exists():
            self.research.save_map(map_path, self.research.create_map(self.request["package"], self.request["serial"]))
        data = self._map()
        if data.get("package_name") != self.request["package"] or data.get("serial") != self.request["serial"]:
            raise ValueError("会话地图属于其他应用或设备。")
        if self.backend:
            if new_attempt or self.state.get("backend") != "android-walkthrough":
                self.backend.reset_actionability()
            self.state["backend"] = "android-walkthrough"
            self.state["backend_version"] = self.backend.modules.package.VERSION
        self._persist()

    def _map(self):
        return self.research.load_map(_inside(self.root, "research-map.json"))

    def _elapsed(self):
        return self._budget_base + max(0, time.monotonic() - self.started)

    def _persist(self):
        self.state["budget_seconds_used"] = round(self._elapsed(), 3)
        self.state["total_actions_used"] = self.state.get("total_actions_before_attempt", 0) + self.state.get("actions_used", 0)
        self.state["total_budget_seconds_used"] = round(self.state.get("total_seconds_before_attempt", 0) + self.state["budget_seconds_used"], 3)
        self.capture.atomic_json(_inside(self.root, "capture-tool-state.json"), self.state)

    def _progress(self, tool, status, observation_id=""):
        names = {"capture_context": "读取走查范围和断点", "launch_app": "启动指定应用", "observe": "观察当前页面",
                 "act_observe": "执行单步并核对新页面", "add_module": "整理模块", "add_page": "登记页面",
                 "attach_observation": "绑定页面截图", "add_transition": "记录实际跳转",
                 "set_module_status": "更新模块覆盖", "export_flows": "导出流程拼图", "finish": "整理本轮结果"}
        states = {"started": "开始", "completed": "完成", "paused": "暂停，请复核"}
        record = {"at": _now(), "tool": tool, "status": status,
                  "attempt_id": self.request.get("attempt_id", ""),
                  "message": f"{names.get(tool, tool)}：{states.get(status, status)}" + (f"（{observation_id}）" if observation_id else ""),
                  "observation_id": observation_id, "actions_used": self.state.get("actions_used", 0),
                  "elapsed_seconds": round(self._elapsed(), 2)}
        with _inside(self.root, "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _guard(self, action=False):
        if _inside(self.root, "cancel.requested").exists():
            raise ValueError("走查已取消；保留已有地图和证据，不再操作设备。")
        if _inside(self.root, "agent-result.json").exists():
            raise ValueError("本轮已收尾；如需续跑请由工作台重新开始。")
        if self._elapsed() >= self.request["budget_seconds"]:
            raise ValueError("本轮时间预算已用完；请整理已有证据并以 paused 收尾。")
        if action and self.state.get("actions_used", 0) >= self.request["max_actions"]:
            raise ValueError("本轮动作预算已用完；请整理已有证据并以 paused 收尾。")

    def _run(self, tool, operation):
        with self.lock:
            self._current_client = None
            started = time.monotonic()
            self._progress(tool, "started")
            try:
                result = operation()
                self._progress(tool, "paused" if isinstance(result, dict) and result.get("ok") is False else "completed",
                               (result.get("observation") or {}).get("id", "") if isinstance(result, dict) else "")
                return result
            except (ValueError, OSError, TypeError, KeyError, self.capture.CaptureError) as exc:
                self._progress(tool, "paused")
                if self.backend and isinstance(exc, self.backend.error_type):
                    return self.backend.error(exc)
                return {"ok": False, "error": str(exc), "hint": "保留当前证据；动作失败后先重新观察，不重复上次点击。"}
            finally:
                if self._current_client is not None:
                    client = self._current_client
                    with _inside(self.root, "timings.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"at": _now(), "command": tool,
                            "seconds": round(time.monotonic() - started, 4), "adb_calls": len(client.timings),
                            "phases": client.timings}, ensure_ascii=False) + "\n")
                self._persist()

    def context(self):
        def run():
            references = {}
            for relative in (REFERENCE_FILES if self.backend else ("SKILL.md", "references/module-capture.md", "references/screenshot-flow.md", "references/ad_handling.md", "references/delivery_review.md")):
                path = self.skill / relative
                if path.is_file():
                    references[relative] = path.read_text(encoding="utf-8")
            return {"ok": True, "target": {key: self.request.get(key, "") for key in
                    ("serial", "package", "title", "scope", "app_version", "max_actions", "budget_seconds")},
                    "skill_source": "bundled" if self.skill in {(_ROOT / "packages/android-capture/skill").resolve(), (_ROOT / "packages/android-walkthrough/skill").resolve()} else "installed",
                    "backend": "android-walkthrough" if self.backend else "legacy", "backend_version": self.state.get("backend_version", "legacy"),
                    "protocol": references, "map": self.backend.public_map(self._map()) if self.backend else self._map(),
                    "checkpoint": _json(self.root, "capture-session.json", {}),
                    "actions_used": self.state.get("actions_used", 0), "elapsed_seconds": round(self._elapsed(), 2),
                    "attempt_id": self.request.get("attempt_id", ""),
                    "instruction": "先用 controls 判断；页面身份、视觉、价格或广告信息不足时再 view_observation 读取已有观察缩略图，不重复ADB。恢复时先 observe，不沿用旧index；仅用此MCP，无shell或任意文件。"}
        return self._run("capture_context", run)

    def _before_adb(self, phase, client):
        self._current_client = client
        is_action = phase in {"tap", "back", "swipe", "text", "key", "launch"}
        reserved = is_action and getattr(self, "_reserved_phase", None) == phase
        try:
            self._guard(action=is_action and not reserved)
            if reserved:
                self._reserved_phase = None
            elif is_action:
                self.state["actions_used"] = self.state.get("actions_used", 0) + 1
                self._persist()
        except ValueError as error:
            code = "CANCELLED" if (self.root / "cancel.requested").exists() else "BUDGET_EXHAUSTED"
            raise self.backend.error_type(code, str(error), next_step="finish_paused") from None

    def _new_capture(self, command, observation_id=None, action=None, index=None, coords=None, value=None, submit=False, in_view=False):
        self._guard(action=command in {"launch", "act"})
        self._reserved_phase = None
        if command in {"launch", "act"}:
            self.state["actions_used"] = self.state.get("actions_used", 0) + 1
            self._persist()
            self._reserved_phase = "launch" if command == "launch" else "tap" if action == "tap-xy" else action
        try:
            return self.backend.capture(command, observation_id, action, index, coords, value, submit, in_view)
        finally:
            self._reserved_phase = None

    def _device(self, action=False):
        self._guard(action)
        _recover_stale_device_lock(self.request["serial"])
        client = self.capture.AdbClient(self.request["adb_path"], self.request["serial"])
        self._current_client = client
        session = self.capture.CaptureSession(client, self.root, self.request["package"])
        return client, session

    def launch_app(self):
        def run():
            if self.backend:
                return self._new_capture("launch")
            client, session = self._device(action=True)
            with self.capture.device_lock(self.request["serial"]):
                self.state["actions_used"] = self.state.get("actions_used", 0) + 1
                self._persist()
                client.run(["shell", "monkey", "-p", self.request["package"], "-c", "android.intent.category.LAUNCHER", "1"], "launch")
                return {"ok": True, "observation": session.observe()}
        return self._run("launch_app", run)

    def observe(self):
        def run():
            if self.backend:
                return self._new_capture("observe")
            _, session = self._device()
            with self.capture.device_lock(self.request["serial"]):
                return {"ok": True, "observation": session.observe()}
        return self._run("observe", run)

    def act_observe(self, observation_id: str, action: str, index: int | None = None, swipe: list[int] | None = None,
                    coordinates: list[int] | None = None, text: str | None = None, submit: bool = False, in_view: bool = False):
        def run():
            if self.backend:
                if action not in {"tap", "tap-xy", "back", "swipe", "text"}:
                    raise ValueError("只允许 tap、tap-xy、back、swipe、text。")
                if index is not None and type(index) is not int or type(submit) is not bool or type(in_view) is not bool:
                    raise ValueError("动作参数类型无效。")
                points = coordinates if coordinates is not None else swipe
                if points is not None and (not isinstance(points, list) or any(type(value) is not int for value in points)):
                    raise ValueError("坐标必须是整数数组。")
                if action == "text" and (not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9 @._+,:/=-]{1,200}", text)):
                    raise ValueError("text 仅支持最多 200 字符的普通 ASCII 测试文本。")
                return self._new_capture("act", observation_id, action, index, points, text, submit, in_view)
            if action not in {"tap", "back", "swipe"}:
                raise ValueError("只允许 tap、back、swipe。")
            if index is not None and type(index) is not int:
                raise ValueError("元素 index 必须是整数。")
            client, session = self._device(action=True)
            try:
                with self.capture.device_lock(self.request["serial"]):
                    # Count attempted actions conservatively, including stale UI
                    # refusals; repeated failure cannot evade the bounded run.
                    self.state["actions_used"] = self.state.get("actions_used", 0) + 1
                    self._persist()
                    return {"ok": True, "observation": session.act_observe(observation_id, action, index, swipe)}
            except (ValueError, OSError, self.capture.CaptureError) as exc:
                return {"ok": False, "error": str(exc),
                        "action_may_have_run": any(t["phase"] in {"tap", "back", "swipe"} for t in client.timings),
                        "hint": "先 observe 当前位置；不要重发上次动作。"}
        return self._run("act_observe", run)

    def _edit(self, name, operation):
        def run():
            if _inside(self.root, "agent-result.json").exists():
                raise ValueError("本轮已收尾；请由工作台明确续跑后再修改地图。")
            data = self._map()
            details = operation(data)
            self.research.save_map(_inside(self.root, "research-map.json"), data)
            _inside(self.root, "app-map.md").write_text(self.research.render_markdown(data), encoding="utf-8")
            return {"ok": True, "map": self.backend.public_map(data) if self.backend else data,
                    **(details if self.backend and isinstance(details, dict) else {})}
        return self._run(name, run)

    def add_module(self, module_id: str, title: str):
        return self._edit("add_module", lambda data: self.research.add_module(data, module_id, title))

    def add_page(self, page_id: str, module_id: str, title: str, kind: str = "page"):
        return self._edit("add_page", lambda data: self.research.add_page(data, page_id, module_id, title, kind))

    def attach_observation(self, observation_id: str, module_id: str, page_id: str, state_id: str, title: str):
        if self.backend:
            return self._edit("attach_observation", lambda data: self.backend.attach(
                data, _observation(self.root, observation_id, self.request), module_id, page_id, state_id, title))
        return self._edit("attach_observation", lambda data: self.research.attach_observation(
            data, _observation(self.root, observation_id, self.request), module_id, page_id, state_id, title, root=self.root))

    def add_transition(self, transition_id: str, from_state: str, to_state: str):
        def change(data):
            if self.backend:
                return self.backend.transition(data, transition_id, from_state, to_state)
            states = {item["id"]: item for item in data["states"]}
            source, target = states[from_state], states[to_state]
            observation = _observation(self.root, target["observation_id"], self.request)
            if observation.get("previous_observation_id") != source["observation_id"] or not observation.get("action"):
                raise ValueError("两端不是有动作证据的相邻观察，不能推测跳转。")
            self.research.add_transition(data, transition_id, from_state, to_state, observation["action"],
                                         [source["observation_id"], target["observation_id"]])
        return self._edit("add_transition", change)

    def set_module_status(self, module_id: str, status: str, reason: str):
        return self._edit("set_module_status", lambda data: (self.research.set_status if self.backend else self.research.set_module_status)(data, module_id, status, reason))

    def _export(self):
        if self.backend:
            built = self.backend.build(self.request.get("title") or self.request["package"])
            composites = []
            for value in built.get("flow_pngs", []):
                path = Path(value).resolve()
                if not path.is_relative_to(self.root) or not path.is_file() or path.parent != self.root / "flow_export" or not path.name.endswith("_flow.png"):
                    raise ValueError("新版 build 返回了会话外或无效拼图。")
                composites.append(path.relative_to(self.root).as_posix())
            self.capture.atomic_json(_inside(self.root, "flow-manifest.json"), {"composites": composites, "exported_at": _now(), "backend": "android-walkthrough"})
            return {"ok": True, "composites": composites, "review": review_session(self.root), "issues": built.get("issues", []), "build_review": built.get("review")}
        _inside(self.root, "app-map.md").write_text(self.research.render_markdown(self._map()), encoding="utf-8")
        with _research_alias(self.research):
            outputs = self.montage.build_montages(Namespace(input_dir=str(self.root), research_map=None, out_dir=None,
                title=self.request.get("title") or self.request["package"], rows_per_image=4))
        composites = [str(item["path"].resolve().relative_to(self.root)).replace("\\", "/") for item in outputs]
        self.capture.atomic_json(_inside(self.root, "flow-manifest.json"), {"composites": composites, "exported_at": _now()})
        return {"ok": True, "composites": composites, "review": review_session(self.root),
                "issues": [issue for item in outputs for issue in item["issues"]]}

    def export_flows(self):
        return self._run("export_flows", self._export)

    def finish(self, outcome: str, summary: str, reason: str = ""):
        def run():
            if _inside(self.root, "agent-result.json").exists():
                return {"ok": True, **_json(self.root, "agent-result.json")}
            final_reason = reason
            if outcome not in {"completed", "paused", "blocked"}:
                raise ValueError("outcome 只能是 completed、paused 或 blocked。")
            if not isinstance(summary, str) or not summary.strip() or len(summary) > 6000:
                raise ValueError("需要不超过 6000 字的走查摘要。")
            if not isinstance(reason, str) or len(reason) > 2000:
                raise ValueError("原因超过允许长度。")
            selected = outcome
            try:
                exported = self._export()
            except (ValueError, OSError, KeyError, TypeError):
                exported = {"composites": [], "review": review_session(self.root)}
            data = self._map()
            modules = data.get("modules", [])
            if selected == "completed":
                if not exported["review"]["ok"]:
                    selected = "blocked"
                    final_reason = final_reason or "证据或流程导出未通过检查，不能标记完成。"
                elif not any(module["status"] == "complete" for module in modules) or any(module["status"] in {"pending", "partial", "blocked"} for module in modules):
                    selected = "blocked" if any(module["status"] == "blocked" for module in modules) else "paused"
                    final_reason = final_reason or "地图仍有未覆盖或阻塞模块，保留当前证据待续跑。"
            result = {"outcome": selected, "summary": summary.strip(), "reason": final_reason.strip(),
                      "composites": exported["composites"], "review": exported["review"],
                      "package": self.request["package"], "serial": self.request["serial"],
                      "app_version": self.request.get("app_version", ""), "scope": self.request["scope"],
                      "observation_count": len(data.get("observations", [])), "actions_used": self.state.get("actions_used", 0),
                      "attempt_id": self.request.get("attempt_id", ""), "total_actions_used": self.state.get("total_actions_used", 0),
                      "elapsed_seconds": round(self._elapsed(), 2), "finished_at": _now()}
            self.capture.atomic_json(_inside(self.root, "agent-result.json"), result)
            return {"ok": True, **result}
        return self._run("finish", run)

    def image_bytes(self, result: dict) -> bytes | None:
        with self.lock:
            item = result.get("observation")
            if not item:
                return None
            saved = _observation(self.root, item["id"], self.request)
            return _inside(self.root, saved["files"].get("view") if self.backend and saved["files"].get("view") else saved["files"]["screenshot"]).read_bytes()

    def image_mime(self, result: dict) -> str:
        return "image/jpeg" if self.backend and (result.get("observation") or {}).get("files", {}).get("view") else "image/png"

    def view_observation(self, observation_id: str):
        def run():
            saved = _observation(self.root, observation_id, self.request)
            return {"ok": True, "observation": self.backend.observation(saved) if self.backend else
                    {"id": saved["id"], "files": saved["files"], "captured_at": saved.get("captured_at", "")}}
        return self._run("view_observation", run)
