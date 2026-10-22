"""Fixed, in-process android-walkthrough backend for the restricted MCP bridge.

Only repository/installed Skill modules are loaded. No model-selected script,
shell, directory, animation change or sensitive-confirmation flag is exposed.
"""
from __future__ import annotations

from argparse import Namespace
from contextlib import contextmanager
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_FILES = ("SKILL.md", "references/walkthrough.md", "references/ads.md", "references/delivery.md", "references/json-contract.md")
MODULES = ("adb", "device", "session", "workspace", "mapstore", "montage", "review", "cli")
_LOADED = {}
_LOCK = threading.RLock()


def complete_skill(root: Path) -> bool:
    return all((root / relative).is_file() for relative in (
        *REFERENCE_FILES, "scripts/aw.py", "scripts/aw/__init__.py",
        *(f"scripts/aw/{name}.py" for name in (*MODULES, "errors", "doctor", "ui")),
    ))


def resolve_skill_root(repository_root: Path | None = None) -> Path:
    root = repository_root or ROOT
    bundled = root / "packages/android-walkthrough/skill"
    if getattr(sys, "frozen", False):
        if complete_skill(bundled):
            return bundled.resolve()
        raise ValueError("EXE 随包 android-walkthrough 不完整，请重新安装或解压；不回退个人 Skill。")
    override = os.environ.get("WORKBENCH_ANDROID_SKILL", "").strip()
    if override:
        candidate = Path(override).expanduser()
        if not complete_skill(candidate):
            raise ValueError("WORKBENCH_ANDROID_SKILL 指定的 android-walkthrough 无效或不完整。")
        return candidate.resolve()
    personal = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills/android-walkthrough"
    for candidate in (personal, bundled):
        if complete_skill(candidate):
            return candidate.resolve()
    raise ValueError("未找到完整 android-walkthrough Skill 或随包副本。")


def load_modules(root: Path):
    key = str(root.resolve())
    with _LOCK:
        if key not in _LOADED:
            prefix = "_workbench_walkthrough_" + hashlib.sha256(key.encode()).hexdigest()[:16]
            source = root / "scripts/aw/__init__.py"
            spec = importlib.util.spec_from_file_location(prefix, source, submodule_search_locations=[str(source.parent)])
            if spec is None or spec.loader is None:
                raise ValueError("无法加载随包截图后端。")
            package = importlib.util.module_from_spec(spec)
            sys.modules[prefix] = package
            try:
                spec.loader.exec_module(package)
                modules = {name: importlib.import_module(prefix + "." + name) for name in (*MODULES, "errors")}
            except Exception:
                for name in list(sys.modules):
                    if name == prefix or name.startswith(prefix + "."):
                        sys.modules.pop(name, None)
                raise
            _LOADED[key] = SimpleNamespace(**modules, package=package)
        return _LOADED[key]


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or ":" in relative or "\\" in relative or Path(relative).is_absolute() or ".." in relative.split("/"):
        raise ValueError("证据必须是当前会话内的相对路径。")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("证据路径越界。")
    return target


class WalkthroughBackend:
    def __init__(self, root: Path, request: dict, skill: Path, before_adb=None, initialize=True):
        self.root, self.request, self.skill = root.resolve(), request, skill.resolve()
        self.modules = load_modules(self.skill)
        self.ws = self.modules.workspace.Workspace(self.root)
        self.before_adb = before_adb
        self.client = None
        if initialize:
            # Service.preflight already verified package/serial/version. Creating
            # the workspace itself must not touch ADB (context/stdio smoke).
            if self.ws.initialized:
                config = self.ws.config()
                if config.get("package") != request["package"] or config.get("serial") != request["serial"]:
                    raise ValueError("截图目录属于其他应用或设备。")
                config["adb"] = request["adb_path"]
            else:
                version = request.get("app_version", {})
                config = {"v": 1, "package": request["package"], "serial": request["serial"], "adb": request["adb_path"],
                          "app_version": version.get("name", "") if isinstance(version, dict) else version,
                          "app_version_code": version.get("code", "") if isinstance(version, dict) else "", "cache": {}}
            self.ws.save_config(config)

    def reset_actionability(self):
        checkpoint = self.ws.checkpoint()
        if checkpoint:
            checkpoint.update(last_observation_id=None, status="needs_observe")
            self.ws.save_checkpoint(checkpoint)

    @property
    def error_type(self):
        return self.modules.errors.AwError

    def _session(self):
        outer = self
        base = self.modules.adb.Adb

        class GuardedAdb(base):
            def run(self, args, phase, timeout=None, ok_codes=(0,)):
                if outer.before_adb:
                    outer.before_adb(phase, self)
                return super().run(args, phase, timeout, ok_codes)

        self.client = GuardedAdb(self.request["adb_path"], self.request["serial"])
        config = self.ws.config()
        device = self.modules.device.Device(self.client, self.request["package"], config.setdefault("cache", {}))
        # The Skill always rechecks target semantics before tap/text input;
        # freshness never grants permission to skip those guards.
        return self.modules.session.Session(self.ws, device, fresh_seconds=0)

    @contextmanager
    def device_lock(self):
        with self.modules.workspace.device_lock(self.request["serial"]):
            yield

    def observation(self, item: dict) -> dict:
        brief = self.modules.session.brief(item, self.root)
        # Stable id/files aliases let existing Workbench consumers keep reading
        # evidence while the model receives only compact controls, not UI trees.
        return {**brief, "id": item["id"], "files": item["files"], "captured_at": item.get("captured_at", ""),
                **({"action": item["action"]} if item.get("action") else {})}

    def error(self, error) -> dict:
        result = error.to_json()
        result["error"] = result.get("message", str(error))
        result["action_may_have_run"] = bool(result.get("acted"))
        observation = error.extra.get("observation")
        if observation:
            result["observation"] = self.observation(observation)
        return result

    def capture(self, command: str, observation_id=None, action=None, index=None, coords=None, value=None, submit=False, in_view=False):
        session = self._session()
        try:
            with self.device_lock():
                if command == "launch":
                    session.device.launch()
                    session.sleep(.5)
                    item = session.observe()
                elif command == "observe":
                    item = session.observe()
                else:
                    item = session.act(observation_id, action, index=index, coords=coords, value=value,
                                       submit=submit, in_view=in_view, confirm_sensitive=False)
            return {"v": 1, "ok": True, "observation": self.observation(item)}
        except self.error_type as error:
            return self.error(error)
        finally:
            config = self.ws.config()
            if "session" in locals():
                config["cache"] = session.device.cache
            self.ws.save_config(config)

    def public_map(self, data: dict) -> dict:
        return {"modules": data.get("modules", []), "pages": data.get("pages", []), "states": data.get("states", []),
                "transitions": data.get("transitions", []), "observations": [self.modules.mapstore.summarize(item) for item in data.get("observations", [])],
                "last_observation": self.ws.checkpoint().get("last_observation_id")}

    def attach(self, data: dict, item: dict, module_id: str, page_id: str, state_id: str, title: str):
        page = next((entry for entry in data["pages"] if entry["id"] == page_id), None)
        if not page or page.get("module_id") != module_id:
            raise ValueError("页面不属于指定模块。")
        self.modules.mapstore.attach(data, item, page_id, state_id, title, self.root)
        # Store evidence digests alongside summaries, without modifying raw
        # observations. This preserves tamper detection after summary migration.
        for record in data["observations"]:
            source = _inside(self.root, f"observations/{record['id']}.json")
            record.setdefault("evidence_sha256", hashlib.sha256(source.read_bytes()).hexdigest())
        edge = self.modules.mapstore.auto_edge(data, state_id)
        return {"state": state_id, "edge": edge}

    def transition(self, data: dict, transition_id: str, source: str, target: str):
        existing = next((item for item in data["transitions"] if item["from_state"] == source and item["to_state"] == target), None)
        if existing:
            return {"edge": existing["id"], "already_recorded": True}
        self.modules.mapstore.add_transition(data, transition_id, source, target)
        return {"edge": transition_id}

    def build(self, title: str) -> dict:
        return self.modules.cli._build(Namespace(title=title, rows=4), self.ws)

    def review(self) -> dict:
        return self.modules.review.review(self.root, require_flow=True)
