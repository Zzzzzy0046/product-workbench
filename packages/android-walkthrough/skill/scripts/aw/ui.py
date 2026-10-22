"""Parse uiautomator XML into nodes, a compact control table and a structural fingerprint."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from typing import Any

from .errors import AwError

BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
TEXT_KEYS = ("text", "content-desc")
FLAG_KEYS = ("clickable", "long-clickable", "scrollable", "enabled", "focused", "checkable", "password", "selected")
LABEL_LIMIT = 30


def actionable_structure(controls: list[dict[str, Any]]) -> list[tuple]:
    return [(control.get("class"), control.get("rid"), control.get("bounds"), control.get("kind")) for control in controls]


def actionable_signature(controls: list[dict[str, Any]]) -> list[tuple]:
    """Identity and meaning of the controls about to receive input.

    The display fingerprint stays structural for observation summaries. Inputs
    also need the full guard text, focus and password state: the same button can
    become a purchase action without moving or changing its resource id.
    """
    result = []
    for control in controls:
        guard = control.get("guard_text", control.get("label", ""))
        result.append((control.get("class"), control.get("rid"), control.get("bounds"), control.get("kind"),
                       " ".join(str(guard).split()), bool(control.get("focused")), bool(control.get("password")),
                       bool(control.get("guard_password"))))
    return result


def parse_bounds(value: str) -> tuple[int, int, int, int] | None:
    match = BOUNDS_RE.fullmatch(value or "")
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def _short_rid(rid: str) -> str:
    return rid.split(":id/", 1)[-1] if ":id/" in rid else rid


def _is_edit(node: dict[str, Any]) -> bool:
    return "EditText" in node["class"] or "AutoCompleteTextView" in node["class"]


def _is_spinner(node: dict[str, Any]) -> bool:
    """Only a small, roughly square ProgressBar means "loading".

    Horizontal bars (audio progress, onboarding steps, quota meters) are permanent UI
    and must not lock a page as non-actionable.
    """
    if not node["class"].endswith("ProgressBar") or not node["box"]:
        return False
    x1, y1, x2, y2 = node["box"]
    width, height = x2 - x1, y2 - y1
    return max(width, height) <= 320 and abs(width - height) <= 0.3 * max(width, height)


def parse_ui(raw: bytes) -> dict[str, Any]:
    start, end = raw.find(b"<hierarchy"), raw.rfind(b"</hierarchy>")
    if start < 0 or end < start:
        raise AwError("ADB_FAILED", "设备未返回有效 UI XML。")
    xml = raw[start:end + len(b"</hierarchy>")]
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise AwError("ADB_FAILED", f"UI XML 解析失败：{error}") from None
    nodes: list[dict[str, Any]] = []

    def visit(element: ET.Element, parent: int | None, depth: int, in_webview: bool) -> None:
        for child in element:
            attrs = child.attrib
            node: dict[str, Any] = {"node_id": len(nodes), "parent_id": parent, "depth": depth,
                                    "class": attrs.get("class", ""), "resource-id": attrs.get("resource-id", ""),
                                    "package": attrs.get("package", ""), "bounds": attrs.get("bounds", "")}
            for key in TEXT_KEYS:
                node[key] = attrs.get(key, "")
            for key in FLAG_KEYS:
                node[key] = attrs.get(key) == "true"
            node["box"] = parse_bounds(node["bounds"])
            node["in_webview"] = in_webview
            nodes.append(node)
            visit(child, node["node_id"], depth + 1, in_webview or "WebView" in node["class"])

    visit(root, None, 0, False)
    children: dict[int, list[int]] = {}
    for node in nodes:
        if node["parent_id"] is not None:
            children.setdefault(node["parent_id"], []).append(node["node_id"])

    def subtree(node_id: int) -> list[dict[str, Any]]:
        result, stack = [], [node_id]
        while stack:
            current = stack.pop()
            result.append(nodes[current])
            stack.extend(reversed(children.get(current, [])))
        return result

    controls: list[dict[str, Any]] = []
    for node in nodes:
        if not node["enabled"] or not node["box"]:
            continue
        edit = _is_edit(node)
        if not (node["clickable"] or node["long-clickable"] or node["scrollable"] or edit):
            continue
        kind = "edit" if edit else "tap" if (node["clickable"] or node["long-clickable"]) else "scroll"
        own = node["text"] or node["content-desc"]
        tree = subtree(node["node_id"])
        if not own:
            own = " ".join(item["text"] or item["content-desc"] for item in tree[1:]
                           if item["text"] or item["content-desc"])
        own = " ".join(own.split())
        x1, y1, x2, y2 = node["box"]
        controls.append({"index": len(controls), "node_id": node["node_id"], "kind": kind,
                         "label": own if len(own) <= LABEL_LIMIT else own[:LABEL_LIMIT - 1] + "…",
                         "rid": _short_rid(node["resource-id"]), "class": node["class"],
                         "bounds": node["bounds"], "center": [(x1 + x2) // 2, (y1 + y2) // 2],
                         "focused": node["focused"], "password": node["password"],
                         "in_webview": node["in_webview"],
                         "guard_text": " ".join(item[key] for item in tree for key in (*TEXT_KEYS, "resource-id")),
                         "guard_password": any(item["password"] for item in tree)})
    # Structure only: rotating banner text, clocks and countdowns do not invalidate an
    # observation; moved, added or removed controls do. Ad WebView internals are ignored.
    structure = [(c["class"], c["rid"], c["bounds"], c["kind"]) for c in controls if not c["in_webview"]]
    fingerprint = hashlib.sha256(json.dumps(structure, ensure_ascii=False).encode()).hexdigest()
    screen = next((node["box"] for node in nodes if node["box"]), None)
    return {"xml": xml, "nodes": nodes, "controls": controls, "fingerprint": fingerprint,
            "loading": any(_is_spinner(node) for node in nodes),
            "screen": [screen[2], screen[3]] if screen else None}


def control_rows(controls: list[dict[str, Any]], limit: int = 60) -> list[list[Any]]:
    """Compact rows for the agent: [index, label, rid, [x, y], kind?]."""
    rows = []
    for control in controls[:limit]:
        row: list[Any] = [control["index"], control["label"], control["rid"], control["center"]]
        if control["kind"] != "tap":
            row.append(control["kind"] + ("*" if control["focused"] else ""))
        rows.append(row)
    return rows
