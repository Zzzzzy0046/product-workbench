"""Evidence-backed module/page/state/transition map. Never touches a device.

The map stores observation summaries only; full UI trees stay in observations/*.json.
An edge is valid only when the destination observation recorded the source as its
previous observation and the action matches byte for byte.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
from typing import Any
from urllib.parse import quote

STATUSES = {"pending", "partial", "complete", "blocked", "skipped"}
STATUS_LABELS = {"pending": "待采集", "partial": "部分覆盖", "complete": "所选路径已覆盖", "blocked": "阻塞", "skipped": "本轮跳过"}
COLLECTIONS = ("modules", "pages", "states", "transitions", "observations")
SUMMARY_KEYS = ("id", "package", "serial", "activity", "captured_at", "files", "status", "previous_observation_id",
                "action", "action_id", "auto_dismissed", "unresolved_action")


class MapError(ValueError):
    pass


def create_map(package_name: str, serial: str = "") -> dict[str, Any]:
    data: dict[str, Any] = {"schema_version": 1, "package_name": package_name, "serial": serial}
    data.update({key: [] for key in COLLECTIONS})
    return data


def summarize(observation: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(observation[key]) for key in SUMMARY_KEYS if key in observation}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def path_error(value: Any, root: Path | None = None) -> str | None:
    if not _nonempty(value):
        return "must be a nonempty relative path"
    windows, normalized = PureWindowsPath(value), value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if windows.drive or windows.root or posix.is_absolute() or ":" in normalized or "\x00" in value:
        return "absolute, drive and URI paths are not allowed"
    if any(part == ".." for part in posix.parts):
        return "parent traversal is not allowed"
    if any(ch in value for ch in "\r\n") or normalized in {"", "."}:
        return "invalid relative path"
    if root is not None:
        try:
            (root / normalized).resolve().relative_to(root.resolve())
        except (ValueError, OSError):
            return "resolved path escapes the research directory"
    return None


def check_map(data: Any, root: str | Path | None = None) -> dict[str, Any]:
    """Structural errors vs. missing files (warnings). ok means valid references, not coverage."""
    errors: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    counts: dict[str, int] = {}
    root_path = Path(root) if root is not None else None
    result = {"ok": False, "errors": errors, "warnings": warnings, "missing_files": missing, "counts": counts}

    def check_file(value: Any, label: str, optional: bool = False) -> None:
        if optional and value in ("", None):
            return
        issue = path_error(value, root_path)
        if issue:
            errors.append(f"{label}: {issue}")
        elif root_path is not None and not (root_path / value.replace("\\", "/")).is_file():
            if value not in missing:
                missing.append(value)
            warnings.append(f"{label}: file missing: {value}")

    if not isinstance(data, dict):
        errors.append("map must be an object")
        return result
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not _nonempty(data.get("package_name")):
        errors.append("package_name is required")
    records: dict[str, dict[str, dict[str, Any]]] = {}
    for key in COLLECTIONS:
        values = data.get(key)
        records[key] = {}
        if not isinstance(values, list):
            errors.append(f"{key} must be a list")
            counts[key] = 0
            continue
        counts[key] = len(values)
        for index, item in enumerate(values):
            if not isinstance(item, dict) or not _nonempty(item.get("id")):
                errors.append(f"{key}[{index}] requires a nonempty id")
                continue
            if item["id"] in records[key]:
                errors.append(f"{key}: duplicate id {item['id']}")
            records[key][item["id"]] = item
    if errors:
        return result
    modules, pages, states, transitions, observations = (records[key] for key in COLLECTIONS)

    for module_id, module in modules.items():
        if not _nonempty(module.get("title")):
            errors.append(f"module {module_id}: title is required")
        status = module.get("status")
        if status not in STATUSES:
            errors.append(f"module {module_id}: unknown status")
        if status in {"complete", "blocked", "skipped"} and not _nonempty(module.get("reason")):
            errors.append(f"module {module_id}: {status} requires reason")
        page_ids = {p["id"] for p in pages.values() if p.get("module_id") == module_id}
        has_states = any(s.get("page_id") in page_ids for s in states.values())
        if status == "complete" and not has_states:
            errors.append(f"module {module_id}: cannot complete without an observed state")
        if not has_states:
            warnings.append(f"module {module_id}: no observed states")

    for page_id, page in pages.items():
        if page.get("module_id") not in modules:
            errors.append(f"page {page_id}: unknown module_id")
        if not _nonempty(page.get("title")):
            errors.append(f"page {page_id}: title is required")
        if not any(s.get("page_id") == page_id for s in states.values()):
            warnings.append(f"page {page_id}: not observed yet")

    serials = set()
    for observation_id, observation in observations.items():
        if observation.get("package") != data.get("package_name"):
            errors.append(f"observation {observation_id}: package differs from map")
        if isinstance(observation.get("serial"), str):
            serials.add(observation["serial"])
        if data.get("serial") and observation.get("serial") != data["serial"]:
            errors.append(f"observation {observation_id}: serial differs from map")
        files = observation.get("files")
        if not isinstance(files, dict):
            errors.append(f"observation {observation_id}: files must be an object")
        else:
            check_file(files.get("screenshot"), f"observation {observation_id}.screenshot")
            check_file(files.get("ui_xml", ""), f"observation {observation_id}.ui_xml", optional=True)
        previous = observation.get("previous_observation_id")
        if previous not in (None, "") and previous not in observations:
            errors.append(f"observation {observation_id}: unknown previous_observation_id")
    if len(serials) > 1:
        errors.append("observations from different devices cannot share a map")

    used_observations: dict[str, str] = {}
    for state_id, state in states.items():
        if state.get("page_id") not in pages:
            errors.append(f"state {state_id}: unknown page_id")
        if not _nonempty(state.get("title")):
            errors.append(f"state {state_id}: title is required")
        observation_id = state.get("observation_id")
        if observation_id not in observations:
            errors.append(f"state {state_id}: unknown observation_id")
        elif observation_id in used_observations:
            errors.append(f"state {state_id}: observation already attached to {used_observations[observation_id]}")
        else:
            used_observations[observation_id] = state_id

    for transition_id, transition in transitions.items():
        source, target = states.get(transition.get("from_state")), states.get(transition.get("to_state"))
        if source is None or target is None:
            errors.append(f"transition {transition_id}: unknown source or destination state")
            continue
        target_observation = observations.get(target.get("observation_id"), {})
        if target_observation.get("previous_observation_id") != source.get("observation_id"):
            errors.append(f"transition {transition_id}: destination was not recorded right after source")
        elif target_observation.get("action") != transition.get("action"):
            errors.append(f"transition {transition_id}: action differs from destination observation")
    result["ok"] = not errors
    return result


def require_valid(data: Any, root: str | Path | None = None) -> None:
    report = check_map(data, root)
    if not report["ok"]:
        raise MapError("; ".join(report["errors"]))


def load_map(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise MapError(f"地图不存在：{target}")
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    require_valid(data, target.parent)
    return data


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
        stream.write(content)
        temporary = stream.name
    os.replace(temporary, path)


def save_map(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    require_valid(data, target.parent)
    atomic_text(target, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def next_id(data: dict[str, Any], collection: str, prefix: str) -> str:
    numbers = [int(match.group(1)) for item in data[collection]
               if (match := re.fullmatch(re.escape(prefix) + r"(\d+)", str(item.get("id", ""))))]
    return f"{prefix}{(max(numbers) if numbers else 0) + 1:02d}"


def _find(data: dict[str, Any], collection: str, item_id: str) -> dict[str, Any] | None:
    return next((item for item in data[collection] if item["id"] == item_id), None)


def _insert(data: dict[str, Any], collection: str, item: dict[str, Any]) -> None:
    existing = _find(data, collection, item["id"])
    if existing is None:
        data[collection].append(copy.deepcopy(item))
    elif existing != item:
        raise MapError(f"{collection}: id {item['id']} 已存在且内容不同，拒绝覆盖")


def _commit(data: dict[str, Any], candidate: dict[str, Any], root: Path | None = None) -> None:
    require_valid(candidate, root)
    data.clear()
    data.update(candidate)


def add_module(data: dict[str, Any], module_id: str, title: str, status: str = "pending", reason: str = "") -> None:
    candidate = copy.deepcopy(data)
    _insert(candidate, "modules", {"id": module_id, "title": title, "status": status, "reason": reason})
    _commit(data, candidate)


def add_page(data: dict[str, Any], page_id: str, module_id: str, title: str, kind: str = "page") -> None:
    candidate = copy.deepcopy(data)
    _insert(candidate, "pages", {"id": page_id, "module_id": module_id, "title": title, "kind": kind})
    _commit(data, candidate)


def set_status(data: dict[str, Any], module_id: str, status: str, reason: str = "") -> None:
    candidate = copy.deepcopy(data)
    module = _find(candidate, "modules", module_id)
    if module is None:
        raise MapError(f"未知模块 {module_id}")
    module.update(status=status, reason=reason)
    _commit(data, candidate)


def _register_chain(data: dict[str, Any], observation: dict[str, Any], root: Path) -> None:
    """Register the observation and any unregistered ancestors (summaries only)."""
    known = {item["id"] for item in data["observations"]}
    pending, current, seen = [], observation, set()
    while current["id"] not in known:
        if current["id"] in seen or len(pending) >= 512:
            raise MapError("previous-observation chain is cyclic or too long")
        seen.add(current["id"])
        if current.get("package") != data["package_name"]:
            raise MapError(f"observation {current['id']}: package differs from map")
        pending.append(summarize(current))
        previous = current.get("previous_observation_id")
        if not previous:
            break
        if not re.fullmatch(r"obs-[a-f0-9]{16}", previous):
            raise MapError("unsafe parent observation id")
        source = root / "observations" / f"{previous}.json"
        if not source.is_file():
            raise MapError(f"parent observation file missing: {source.name}")
        current = json.loads(source.read_text(encoding="utf-8-sig"))
    for item in reversed(pending):
        _insert(data, "observations", item)


def attach(data: dict[str, Any], observation: dict[str, Any], page_id: str, state_id: str, title: str,
           root: Path) -> None:
    candidate = copy.deepcopy(data)
    page = _find(candidate, "pages", page_id)
    if page is None:
        raise MapError(f"未知页面 {page_id}：先用 aw map page 登记")
    _register_chain(candidate, observation, root)
    _insert(candidate, "states", {"id": state_id, "page_id": page_id, "title": title or page["title"],
                                  "observation_id": observation["id"]})
    _commit(data, candidate, root)


def add_transition(data: dict[str, Any], transition_id: str, source: str, target: str, label: str = "") -> None:
    """Edge from two states; the action is always copied from the destination observation."""
    candidate = copy.deepcopy(data)
    target_state = _find(candidate, "states", target)
    if target_state is None:
        raise MapError(f"未知状态 {target}")
    observation = _find(candidate, "observations", target_state["observation_id"]) or {}
    item = {"id": transition_id, "from_state": source, "to_state": target, "action": observation.get("action"),
            "evidence_observation_ids": [observation.get("previous_observation_id"), observation.get("id")]}
    if label:
        item["label"] = label
    _insert(candidate, "transitions", item)
    _commit(data, candidate)


def auto_edge(data: dict[str, Any], target_state: str, label: str = "") -> str | None:
    """Connect the state recorded right before target_state, if that observation is a state."""
    state = _find(data, "states", target_state)
    observation = _find(data, "observations", state["observation_id"]) if state else None
    previous = (observation or {}).get("previous_observation_id")
    source = next((item for item in data["states"] if item["observation_id"] == previous), None) if previous else None
    if source is None:
        return None
    transition_id = next_id(data, "transitions", "T")
    add_transition(data, transition_id, source["id"], target_state, label)
    return transition_id


# ---------------- rendering ----------------

def action_label(action: Any) -> str:
    if isinstance(action, str):
        return action
    if not isinstance(action, dict):
        return "动作"
    kind = action.get("type")
    if kind == "back":
        return "返回"
    if kind == "swipe":
        return "滑动"
    if kind == "text":
        return f"输入 {action.get('value', '')}"
    if kind == "tap-xy":
        return f"点击坐标 {action.get('x')},{action.get('y')}"
    if kind == "tap":
        target = action.get("label") or action.get("rid") or f"控件 {action.get('index')}"
        target = " ".join(str(target).split())
        return "点击 " + (target if len(target) <= 40 else target[:39] + "…")
    return json.dumps(action, ensure_ascii=False)


def _md(value: Any) -> str:
    text = str(value).replace("\\", "\\\\").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    for character in "|[]`*_":
        text = text.replace(character, "\\" + character)
    return text


def _mermaid(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")


def render_markdown(data: dict[str, Any]) -> str:
    observations = {item["id"]: item for item in data["observations"]}
    lines = ["# App 模块与页面地图", "", f"应用：`{_md(data['package_name'])}` · 设备：`{_md(data['serial'] or '未指定')}`", "",
             "这是已观察结构，不是完整产品架构。没有跳转证据的关系保持未知；截图成功不等于模块覆盖完成。", "",
             "## 模块概览", "", "| 模块 | 状态 | 页面／状态 | 覆盖说明或阻塞原因 |", "| --- | --- | --- | --- |"]
    for module in data["modules"]:
        page_ids = {p["id"] for p in data["pages"] if p["module_id"] == module["id"]}
        states = [s for s in data["states"] if s["page_id"] in page_ids]
        lines.append(f"| {_md(module['title'])} (`{module['id']}`) | {STATUS_LABELS[module['status']]} | "
                     f"{len({s['page_id'] for s in states})} / {len(states)} | {_md(module['reason'] or '待补充')} |")
    for module in data["modules"]:
        lines += ["", f"## {_md(module['title'])} · {STATUS_LABELS[module['status']]}", ""]
        module_pages = [p for p in data["pages"] if p["module_id"] == module["id"]]
        if not module_pages:
            lines.append("尚未采集页面。")
        for page in module_pages:
            lines += [f"### {_md(page['title'])} (`{page['id']}`，{_md(page['kind'])})", ""]
            page_states = [s for s in data["states"] if s["page_id"] == page["id"]]
            if not page_states:
                lines += ["待采集。", ""]
            for state in page_states:
                shot = observations[state["observation_id"]]["files"]["screenshot"]
                lines += [f"- **{_md(state['title'])}** · `{state['id']}` · `{state['observation_id']}`", "",
                          f"![{_md(state['title'])}](<{quote(shot.replace(chr(92), '/'), safe='/-._~')}>)", ""]
    lines += ["## 已观察跳转", ""]
    if not data["transitions"]:
        lines.append("尚无已记录的跳转。")
    else:
        aliases = {s["id"]: f"s{i}" for i, s in enumerate(data["states"])}
        involved = {t[f] for t in data["transitions"] for f in ("from_state", "to_state")}
        lines += ["```mermaid", "flowchart LR"]
        for index, module in enumerate(data["modules"]):
            page_ids = {p["id"] for p in data["pages"] if p["module_id"] == module["id"]}
            members = [s for s in data["states"] if s["page_id"] in page_ids and s["id"] in involved]
            if members:
                lines.append(f'  subgraph m{index}["{_mermaid(module["title"])}"]')
                lines += [f'    {aliases[s["id"]]}["{_mermaid(s["title"])} ({s["id"]})"]' for s in members]
                lines.append("  end")
        for t in data["transitions"]:
            label = t.get("label") or action_label(t["action"])
            lines.append(f'  {aliases[t["from_state"]]} -->|"{_mermaid(label)}"| {aliases[t["to_state"]]}')
        lines += ["```"]
    incomplete = [m for m in data["modules"] if m["status"] != "complete"]
    lines += ["", "## 待补与阻塞", ""]
    lines += [f"- {_md(m['title'])}：{STATUS_LABELS[m['status']]}；{_md(m['reason'] or '待确认')}" for m in incomplete] or \
             ["已登记模块的所选路径均标记覆盖；未选择的入口不代表不存在。"]
    return "\n".join(lines) + "\n"
