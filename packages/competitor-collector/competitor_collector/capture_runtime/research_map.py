#!/usr/bin/env python3
"""Maintain an evidence-backed module/page/state map. This script never uses ADB."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import tempfile
from typing import Any


STATUSES = {"pending", "partial", "complete", "blocked", "skipped"}
STATUS_LABELS = {"pending": "待采集", "partial": "部分覆盖", "complete": "所选路径已覆盖", "blocked": "阻塞", "skipped": "本轮跳过"}
COLLECTIONS = ("modules", "pages", "states", "transitions", "observations")


def create_map(package_name: str, serial: str = "") -> dict[str, Any]:
    """Create a map. The caller chooses observed modules; no generic tree is invented."""
    data = {"schema_version": 1, "package_name": package_name, "serial": serial}
    data.update({key: [] for key in COLLECTIONS})
    _require_valid(data)
    return data


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _path_error(value: Any, root: Path | None = None) -> str | None:
    if not _nonempty(value):
        return "must be a nonempty relative path"
    # Validate both path dialects even when running on the other operating system.
    win = PureWindowsPath(value)
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if win.drive or win.root or posix.is_absolute() or ":" in normalized or "\x00" in value:
        return "absolute paths, drive paths and URI paths are not allowed"
    if any(part == ".." for part in posix.parts):
        return "parent traversal is not allowed"
    if any(ch in value for ch in "\r\n") or normalized in {"", "."}:
        return "invalid relative path"
    if root is not None:
        try:
            (root / Path(normalized)).resolve().relative_to(root.resolve())
        except (ValueError, OSError, RuntimeError):
            return "resolved path escapes the research directory"
    return None


def _same_action(left: Any, right: Any) -> bool:
    return left == right


def check_map(data: Any, root: str | Path | None = None) -> dict[str, Any]:
    """Return structural errors separately from absent files and incomplete coverage.

    Missing files are warnings, so a module board may show explicit missing evidence.
    A successful check means valid references, not completed exploration.
    """
    errors: list[str] = []
    warnings: list[str] = []
    missing_files: list[str] = []
    counts: dict[str, int] = {}
    root_path = Path(root) if root is not None else None

    def fail(message: str) -> None:
        errors.append(message)

    def check_file(value: Any, label: str, optional: bool = False) -> None:
        if optional and value == "":
            return
        issue = _path_error(value, root_path)
        if issue:
            fail(f"{label}: {issue}")
        elif root_path is not None:
            candidate = root_path / value.replace("\\", "/")
            if not candidate.is_file():
                if value not in missing_files:
                    missing_files.append(value)
                warnings.append(f"{label}: file missing: {value}")
            elif candidate.stat().st_size == 0:
                warnings.append(f"{label}: file is empty: {value}")

    result = {"ok": False, "errors": errors, "warnings": warnings, "missing_files": missing_files, "counts": counts}
    if not isinstance(data, dict):
        fail("map must be an object")
        return result
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        fail("schema_version must be 1")
    if not _nonempty(data.get("package_name")):
        fail("package_name is required")
    if not isinstance(data.get("serial"), str):
        fail("serial must be a string")
    records: dict[str, dict[str, dict[str, Any]]] = {}
    for key in COLLECTIONS:
        values = data.get(key)
        records[key] = {}
        if not isinstance(values, list):
            fail(f"{key} must be a list")
            counts[key] = 0
            continue
        counts[key] = len(values)
        for index, item in enumerate(values):
            if not isinstance(item, dict) or not _nonempty(item.get("id")):
                fail(f"{key}[{index}] requires a nonempty id")
                continue
            if item["id"] in records[key]:
                fail(f"{key}: duplicate id {item['id']}")
            records[key][item["id"]] = item

    required_references = {"pages": ("module_id",), "states": ("page_id", "observation_id"), "transitions": ("from_state", "to_state")}
    for key, fields in required_references.items():
        for item in records[key].values():
            for field in fields:
                if not _nonempty(item.get(field)):
                    fail(f"{key} {item['id']}: {field} must be a nonempty string")
    for observation in records["observations"].values():
        previous = observation.get("previous_observation_id")
        if previous is not None and not isinstance(previous, str):
            fail(f"observation {observation['id']}: previous_observation_id must be a string")
    if errors:
        return result

    modules, pages, states, transitions, observations = (records[key] for key in COLLECTIONS)
    for module_id, module in modules.items():
        if not _nonempty(module.get("title")):
            fail(f"module {module_id}: title is required")
        if not isinstance(module.get("status"), str) or module.get("status") not in STATUSES:
            fail(f"module {module_id}: unknown status")
        if not isinstance(module.get("reason"), str):
            fail(f"module {module_id}: reason must be a string")
        if isinstance(module.get("status"), str) and module.get("status") in {"complete", "blocked", "skipped"} and not _nonempty(module.get("reason")):
            fail(f"module {module_id}: {module.get('status')} requires reason; complete requires key-path coverage explanation")
        related_pages = {p["id"] for p in pages.values() if p.get("module_id") == module_id}
        related_states = [s for s in states.values() if s.get("page_id") in related_pages]
        if module.get("status") == "complete" and not related_states:
            fail(f"module {module_id}: cannot complete without an observed state")
        if not related_states:
            warnings.append(f"module {module_id}: no observed states; coverage unknown")

    requested = data.get("requested_modules", [])
    if not isinstance(requested, list) or any(not isinstance(item, str) or item not in modules for item in requested):
        fail("requested_modules must contain known module ids")
    elif len(set(requested)) != len(requested):
        fail("requested_modules contains duplicate ids")

    for page_id, page in pages.items():
        if page.get("module_id") not in modules:
            fail(f"page {page_id}: unknown module_id")
        if not _nonempty(page.get("title")) or not _nonempty(page.get("kind")):
            fail(f"page {page_id}: title and kind are required")
        if not any(s.get("page_id") == page_id for s in states.values()):
            warnings.append(f"page {page_id}: not observed yet")

    for observation_id, observation in observations.items():
        for field in ("package", "serial", "activity", "captured_at"):
            if not isinstance(observation.get(field), str):
                fail(f"observation {observation_id}: {field} must be a string")
        if not _nonempty(observation.get("captured_at")):
            fail(f"observation {observation_id}: captured_at is required")
        if observation.get("package") != data.get("package_name"):
            fail(f"observation {observation_id}: package differs from map")
        if data.get("serial") and observation.get("serial") != data["serial"]:
            fail(f"observation {observation_id}: serial differs from map")
        files = observation.get("files")
        if not isinstance(files, dict):
            fail(f"observation {observation_id}: files must be an object")
        else:
            check_file(files.get("screenshot"), f"observation {observation_id}.screenshot")
            check_file(files.get("ui_xml", ""), f"observation {observation_id}.ui_xml", optional=True)
        previous = observation.get("previous_observation_id")
        if previous not in (None, "") and previous not in observations:
            fail(f"observation {observation_id}: unknown previous_observation_id")
        if previous == observation_id:
            fail(f"observation {observation_id}: cannot be its own previous observation")
        if "action" in observation and observation["action"] not in (None, ""):
            if not isinstance(observation["action"], (str, dict)) or not observation["action"]:
                fail(f"observation {observation_id}: action must be a string or object")

    device_serials = {item["serial"] for item in observations.values() if isinstance(item.get("serial"), str)}
    if len(device_serials) > 1:
        fail("observations from different device serials cannot share a map")

    # A previous-observation chain may not contain cycles.
    for observation_id in observations:
        seen: set[str] = set()
        current = observation_id
        while current in observations:
            if current in seen:
                fail(f"observation {observation_id}: previous-observation cycle")
                break
            seen.add(current)
            current = observations[current].get("previous_observation_id")

    for state_id, state in states.items():
        if state.get("page_id") not in pages:
            fail(f"state {state_id}: unknown page_id")
        if not _nonempty(state.get("title")):
            fail(f"state {state_id}: title is required")
        observation = observations.get(state.get("observation_id"))
        if observation is None:
            fail(f"state {state_id}: unknown observation_id")
        check_file(state.get("screenshot"), f"state {state_id}.screenshot")
        check_file(state.get("ui_xml", ""), f"state {state_id}.ui_xml", optional=True)
        if observation is not None and isinstance(observation.get("files"), dict):
            for field in ("screenshot", "ui_xml"):
                if state.get(field, "") != observation["files"].get(field, ""):
                    fail(f"state {state_id}: {field} differs from observation evidence")

    for transition_id, transition in transitions.items():
        source = states.get(transition.get("from_state"))
        target = states.get(transition.get("to_state"))
        if source is None or target is None:
            fail(f"transition {transition_id}: unknown source or destination state")
        if not isinstance(transition.get("action"), (str, dict)) or not transition.get("action"):
            fail(f"transition {transition_id}: explicit action is required")
        evidence = transition.get("evidence_observation_ids")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or item not in observations for item in evidence):
            fail(f"transition {transition_id}: evidence must reference known observation ids")
            continue
        if source is not None and target is not None:
            source_id, target_id = source.get("observation_id"), target.get("observation_id")
            if source_id not in evidence or target_id not in evidence:
                fail(f"transition {transition_id}: evidence must include both endpoint observations")
            target_observation = observations.get(target_id, {})
            if target_observation.get("previous_observation_id") != source_id:
                fail(f"transition {transition_id}: no recorded observation link between endpoints")
            if not target_observation.get("action"):
                fail(f"transition {transition_id}: destination observation has no recorded action")
            elif not _same_action(transition.get("action"), target_observation["action"]):
                fail(f"transition {transition_id}: action differs from destination observation")
    result["ok"] = not errors
    return result


def _require_valid(data: Any, root: str | Path | None = None) -> None:
    report = check_map(data, root)
    if not report["ok"]:
        raise ValueError("; ".join(report["errors"]))


def load_map(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    _require_valid(data, target.parent)
    return data


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def save_map(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    _require_valid(data, target.parent)
    _atomic_text(target, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _insert(data: dict[str, Any], collection: str, item: dict[str, Any]) -> None:
    existing = next((old for old in data[collection] if old["id"] == item["id"]), None)
    if existing is not None:
        if existing != item:
            raise ValueError(f"{collection}: id {item['id']} already exists with different content; refusing overwrite")
    else:
        data[collection].append(copy.deepcopy(item))


def _commit(original: dict[str, Any], candidate: dict[str, Any], root: str | Path | None = None) -> dict[str, Any]:
    _require_valid(candidate, root)
    original.clear()
    original.update(candidate)
    return original


def add_module(data: dict[str, Any], module_id: str, title: str, status: str = "pending", reason: str = "") -> dict[str, Any]:
    candidate = copy.deepcopy(data)
    _insert(candidate, "modules", {"id": module_id, "title": title, "status": status, "reason": reason})
    return _commit(data, candidate)


def add_page(data: dict[str, Any], page_id: str, module_id: str, title: str, kind: str = "page") -> dict[str, Any]:
    candidate = copy.deepcopy(data)
    _insert(candidate, "pages", {"id": page_id, "module_id": module_id, "title": title, "kind": kind})
    return _commit(data, candidate)


def _register_observation_chain(data: dict[str, Any], observation: dict[str, Any], root: str | Path | None) -> None:
    """Register original parent observations without assigning pages or inferring edges.

    Missing ancestors are read only from root/observations/<id>.json, never from a
    caller-controlled file field. The final map validation also checks every file
    reference, device/package, timestamp and original previous-observation link.
    """
    known = {item["id"]: item for item in data["observations"]}
    pending: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = observation
    expected_serial = data["serial"] or observation.get("serial")
    root_path = Path(root).resolve() if root is not None else None
    while True:
        if not isinstance(current, dict) or not _nonempty(current.get("id")):
            raise ValueError("observation requires an id")
        identifier = current["id"]
        if identifier in seen:
            raise ValueError("original observation files contain a previous-observation cycle")
        seen.add(identifier)
        if current.get("package") != data["package_name"]:
            raise ValueError(f"observation {identifier}: package differs from map")
        if current.get("serial") != expected_serial:
            raise ValueError(f"observation {identifier}: serial differs from observation chain")
        pending.append(current)
        previous = current.get("previous_observation_id")
        if previous in (None, "") or isinstance(previous, str) and previous in known:
            break
        if not isinstance(previous, str):
            raise ValueError(f"observation {identifier}: previous_observation_id must be a string")
        if root_path is None:
            raise ValueError(f"observation {identifier}: unknown previous_observation_id; pass root to register original parent evidence")
        # A parent id must be a plain basename, not a path or alternate data stream.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", previous):
            raise ValueError("missing parent observation id is not a safe filename")
        if len(pending) >= 512:
            raise ValueError("original observation chain exceeds the 512-record safety limit")
        relative = f"observations/{previous}.json"
        issue = _path_error(relative, root_path)
        if issue:
            raise ValueError(f"parent observation: {issue}")
        source = root_path / relative
        if not source.is_file():
            raise ValueError(f"original parent observation is missing: {relative}")
        if source.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(f"original parent observation exceeds 16 MiB: {relative}")
        current = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(current, dict) or current.get("id") != previous:
            raise ValueError(f"original parent observation id does not match filename: {relative}")
    for item in reversed(pending):
        _insert(data, "observations", item)


def attach_observation(data: dict[str, Any], observation: dict[str, Any], module_id: str, page_id: str, state_id: str, title: str = "", root: str | Path | None = None) -> dict[str, Any]:
    """Attach captured evidence to an existing page, without inventing edges/status.

    Adding the page/module is explicit. A state id is immutable: capture another state
    id for a later observation instead of silently replacing evidence. If root is
    supplied, original missing parents are registered from its observations/ folder;
    these intermediate observations do not acquire a page/state or transition.
    """
    candidate = copy.deepcopy(data)
    page = next((item for item in candidate["pages"] if item["id"] == page_id), None)
    if page is None or page.get("module_id") != module_id:
        raise ValueError("page_id must exist and belong to module_id")
    if not isinstance(observation, dict) or not _nonempty(observation.get("id")):
        raise ValueError("observation requires an id")
    files = observation.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("observation files must be an object")
    _register_observation_chain(candidate, observation, root)
    _insert(candidate, "states", {
        "id": state_id, "page_id": page_id, "title": title or page["title"],
        "observation_id": observation["id"], "screenshot": files.get("screenshot"), "ui_xml": files.get("ui_xml", ""),
    })
    return _commit(data, candidate, root)


def add_transition(data: dict[str, Any], transition_id: str, from_state: str, to_state: str, action: Any, evidence_observation_ids: list[str]) -> dict[str, Any]:
    candidate = copy.deepcopy(data)
    _insert(candidate, "transitions", {"id": transition_id, "from_state": from_state, "to_state": to_state, "action": action, "evidence_observation_ids": evidence_observation_ids})
    return _commit(data, candidate)


def set_module_status(data: dict[str, Any], module_id: str, status: str, reason: str = "") -> dict[str, Any]:
    candidate = copy.deepcopy(data)
    module = next((item for item in candidate["modules"] if item["id"] == module_id), None)
    if module is None:
        raise ValueError("unknown module_id")
    module.update(status=status, reason=reason)
    return _commit(data, candidate)


def _md(value: Any) -> str:
    text = str(value).replace("\\", "\\\\").replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace(">", "&gt;")
    for character in ("|", "[", "]", "`", "*", "_"):
        text = text.replace(character, "\\" + character)
    return text


def _mermaid(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ").replace("\r", " ")


def _image_path(value: str) -> str:
    from urllib.parse import quote
    return quote(value.replace("\\", "/"), safe="/-._~")


def _action_text(action: Any) -> str:
    return action if isinstance(action, str) else json.dumps(action, ensure_ascii=False, sort_keys=True)


def action_label(action: Any) -> str:
    """Readable display only; the original action remains the validation source."""
    if isinstance(action, str):
        return action
    if isinstance(action, dict):
        kind = action.get("type")
        if kind == "back":
            return "返回"
        if kind == "swipe":
            return "滑动"
        if kind == "tap":
            target = action.get("text") or action.get("content-desc") or action.get("resource_id")
            if not target:
                target = f"控件 {action['index']}" if "index" in action else "控件"
            target = " ".join(str(target).split())
            return "点击 " + (target if len(target) <= 60 else target[:59] + "…")
    return _action_text(action)


def render_markdown(data: dict[str, Any]) -> str:
    """Render module hierarchy plus explicit observed edges, never inferred edges."""
    _require_valid(data)
    lines = ["# App 模块与页面地图", "", f"应用：`{_md(data['package_name'])}` · 设备：`{_md(data['serial'] or '未指定')}`", "", "这是已观察结构，不是完整产品架构。分组由实际入口和任务判断；没有跳转证据的关系保持未知。文件有效、截图成功均不等于模块覆盖完成。", "", "## 模块概览", "", "| 模块 | 状态 | 已观察页面／状态 | 覆盖说明或阻塞原因 |", "| --- | --- | --- | --- |"]
    for module in data["modules"]:
        pages = [page for page in data["pages"] if page["module_id"] == module["id"]]
        page_ids = {page["id"] for page in pages}
        states = [state for state in data["states"] if state["page_id"] in page_ids]
        observed_pages = {state["page_id"] for state in states}
        lines.append(f"| {_md(module['title'])} (`{_md(module['id'])}`) | {STATUS_LABELS[module['status']]} | {len(observed_pages)} / {len(states)} | {_md(module['reason'] or '待补充覆盖说明')} |")
    if not data["modules"]:
        lines.append("| 尚未发现模块 | 待采集 | 0 / 0 | 先观察首页和导航，不预设完整模块 |")
    if data.get("requested_modules"):
        lines += ["", "本轮选定模块：" + "、".join(f"`{_md(item)}`" for item in data["requested_modules"])]
    for module in data["modules"]:
        lines += ["", f"## {_md(module['title'])} · {STATUS_LABELS[module['status']]}", "", _md(module["reason"]) if module["reason"] else "覆盖说明尚未填写。", ""]
        module_pages = [page for page in data["pages"] if page["module_id"] == module["id"]]
        if not module_pages:
            lines.append("尚未采集页面；不使用其他模块的截图补位。")
        for page in module_pages:
            lines += [f"### {_md(page['title'])} (`{_md(page['id'])}`，{_md(page['kind'])})", ""]
            page_states = [state for state in data["states"] if state["page_id"] == page["id"]]
            if not page_states:
                lines += ["待采集：尚无页面状态和截图。", ""]
            for state in page_states:
                lines += [f"- **{_md(state['title'])}** · 状态 `{_md(state['id'])}` · 观测 `{_md(state['observation_id'])}`", "", f"![{_md(state['title'])}](<{_image_path(state['screenshot'])}>)", ""]
                if state.get("ui_xml"):
                    lines += [f"[查看页面 UI 证据](<{_image_path(state['ui_xml'])}>)", ""]
    lines += ["## 已观察跳转", "", "只展示显式记录的动作和前后观测；模块归属不等于页面跳转。", ""]
    if not data["transitions"]:
        lines.append("尚无已记录的跳转边，页面间关系未知。")
    else:
        aliases = {state["id"]: f"s{index}" for index, state in enumerate(data["states"])}
        involved = {transition[field] for transition in data["transitions"] for field in ("from_state", "to_state")}
        lines += ["```mermaid", "flowchart LR"]
        for index, module in enumerate(data["modules"]):
            module_page_ids = {page["id"] for page in data["pages"] if page["module_id"] == module["id"]}
            module_states = [state for state in data["states"] if state["page_id"] in module_page_ids and state["id"] in involved]
            if module_states:
                lines.append(f'  subgraph m{index}["{_mermaid(module["title"])}"]')
                for state in module_states:
                    lines.append(f'    {aliases[state["id"]]}["{_mermaid(state["title"])} ({_mermaid(state["id"])})"]')
                lines.append("  end")
        for transition in data["transitions"]:
            lines.append(f'  {aliases[transition["from_state"]]} -->|"{_mermaid(action_label(transition["action"]))}"| {aliases[transition["to_state"]]}')
        lines += ["```", "", "| 跳转 | 动作 | 证据观测 |", "| --- | --- | --- |"]
        for transition in data["transitions"]:
            lines.append(f"| `{_md(transition['from_state'])}` → `{_md(transition['to_state'])}` | {_md(action_label(transition['action']))} | {_md(', '.join(transition['evidence_observation_ids']))} |")
        lines += ["", "动作标签仅用于阅读；原始动作对象、控件标识与前后观察保留在 research-map.json 中。"]
    incomplete = [module for module in data["modules"] if module["status"] != "complete"]
    lines += ["", "## 待补与阻塞", ""]
    if incomplete:
        lines += [f"- {_md(module['title'])}：{STATUS_LABELS[module['status']]}；{_md(module['reason'] or '待确认本轮关键路径与剩余状态')}" for module in incomplete]
    else:
        lines.append("已登记模块的所选路径均标记覆盖；未发现入口、未选择路径和未观察状态仍不代表不存在。")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain module/page/state evidence map without operating a device")
    parser.add_argument("--map", required=True, help="research-map.json in the screenshot research directory")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--package", required=True)
    init.add_argument("--serial", default="")
    module = commands.add_parser("module")
    module.add_argument("--id", required=True)
    module.add_argument("--title", required=True)
    module.add_argument("--status", choices=sorted(STATUSES), default="pending")
    module.add_argument("--reason", default="")
    page = commands.add_parser("page")
    page.add_argument("--id", required=True)
    page.add_argument("--module", required=True)
    page.add_argument("--title", required=True)
    page.add_argument("--kind", default="page")
    attach = commands.add_parser("attach")
    attach.add_argument("--observation", required=True)
    attach.add_argument("--module", required=True)
    attach.add_argument("--page", required=True)
    attach.add_argument("--state", required=True)
    attach.add_argument("--title", default="")
    transition = commands.add_parser("transition")
    transition.add_argument("--id", required=True)
    transition.add_argument("--from", dest="source", required=True)
    transition.add_argument("--to", dest="target", required=True)
    transition.add_argument("--action", required=True, help="Exact action string, or JSON object matching captured observation action")
    transition.add_argument("--evidence", nargs="+", required=True)
    status = commands.add_parser("status")
    status.add_argument("--module", required=True)
    status.add_argument("--status", choices=sorted(STATUSES), required=True)
    status.add_argument("--reason", default="")
    commands.add_parser("check")
    render = commands.add_parser("render")
    render.add_argument("--output", help="Defaults to app-map.md next to map")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Configure only the executable entrypoint; importing this module must not
    # change the host process' streams or encoding (including GBK Windows hosts).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    target = Path(args.map)
    try:
        if args.command == "init":
            data = create_map(args.package, args.serial)
            if target.exists():
                if load_map(target) != data:
                    raise ValueError("map already exists; refusing to replace existing research")
            else:
                save_map(target, data)
        elif args.command == "check":
            data = json.loads(target.read_text(encoding="utf-8-sig"))
            report = check_map(data, target.parent)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
        else:
            data = load_map(target)
            if args.command == "module":
                add_module(data, args.id, args.title, args.status, args.reason)
            elif args.command == "page":
                add_page(data, args.id, args.module, args.title, args.kind)
            elif args.command == "attach":
                observation = json.loads(Path(args.observation).read_text(encoding="utf-8-sig"))
                attach_observation(data, observation, args.module, args.page, args.state, args.title, target.parent)
            elif args.command == "transition":
                action = args.action
                if action.startswith(("{", "[")):
                    action = json.loads(action)
                add_transition(data, args.id, args.source, args.target, action, args.evidence)
            elif args.command == "status":
                set_module_status(data, args.module, args.status, args.reason)
            elif args.command == "render":
                output = Path(args.output) if args.output else target.parent / "app-map.md"
                if output.resolve() == target.resolve():
                    raise ValueError("render output must not overwrite the map")
                _atomic_text(output, render_markdown(data))
                print(str(output))
                return 0
            save_map(target, data)
        print(str(target))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
