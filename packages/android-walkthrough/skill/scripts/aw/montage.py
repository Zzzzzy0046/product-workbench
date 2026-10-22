"""Render recorded transitions as per-module flow PNGs. No ADB, no HTML."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from .mapstore import STATUS_LABELS, action_label, check_map, path_error

WIDTH, MARGIN = 1280, 36
CARD_WIDTH, SHOT_HEIGHT = 386, 560
BG, WHITE, INK, MUTED, LINE, ACCENT, WARN = "#f5f6f4", "#ffffff", "#20332f", "#61716b", "#d9e0db", "#277568", "#a55c34"
FONT_CANDIDATES = {
    "regular": [r"C:\Windows\Fonts\msyh.ttc", "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"],
    "bold": [r"C:\Windows\Fonts\msyhbd.ttc", "/System/Library/Fonts/PingFang.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
             "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"],
}


def find_font(kind: str = "regular") -> str | None:
    return next((path for path in FONT_CANDIDATES[kind] if Path(path).is_file()), None)


def fonts() -> dict[str, Any]:
    from PIL import ImageFont
    regular = find_font("regular")
    if not regular:
        raise ValueError("未找到中文字体：Windows 需微软雅黑，macOS 需苹方，Linux 安装 Noto Sans CJK。")
    bold = find_font("bold") or regular
    return {key: ImageFont.truetype(bold if key in {"title", "module"} else regular, size)
            for key, size in {"title": 32, "module": 26, "body": 21, "small": 17}.items()}


def _step(font: Any) -> int:
    box = font.getbbox("国Ag")
    return max(box[3] - min(0, box[1]) + 6, 22)


def wrap_text(text: Any, font: Any, width: int, max_lines: int | None = None) -> list[str]:
    from PIL import Image, ImageDraw
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[str] = []
    for paragraph in str(text).replace("\r", "").split("\n"):
        current = ""
        for char in paragraph:
            if current and probe.textlength(current + char, font=font) > width:
                lines.append(current)
                current = char
            else:
                current += char
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and probe.textlength(lines[-1] + "…", font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _text(draw: Any, x: int, y: int, text: Any, font: Any, width: int, color: str = INK,
          max_lines: int | None = None, align: str = "left") -> int:
    for line in wrap_text(text, font, width, max_lines):
        offset = (width - draw.textlength(line, font=font)) / 2 if align == "center" else 0
        draw.text((x + offset, y), line, font=font, fill=color, anchor="lt")
        y += _step(font)
    return y


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]+", "_", value).strip("_.")[:55] or "module"


def rows_for_module(data: dict[str, Any], module_id: str) -> list[dict[str, Any]]:
    """Pack nonbranching edges into rows of up to three screenshots; branches get own rows."""
    pages = {p["id"]: p for p in data["pages"]}
    states = {s["id"]: s for s in data["states"]}
    local = {k for k, s in states.items() if pages[s["page_id"]]["module_id"] == module_id}
    edges = [e for e in sorted(data["transitions"], key=lambda e: e["id"])
             if e["from_state"] in local or e["to_state"] in local]
    incoming: dict[str, list] = {}
    outgoing: dict[str, list] = {}
    for edge in edges:
        incoming.setdefault(edge["to_state"], []).append(edge)
        outgoing.setdefault(edge["from_state"], []).append(edge)
    rows, involved, used = [], set(), set()

    def linear(state: str) -> bool:
        return state in local and len(incoming.get(state, [])) == 1 and len(outgoing.get(state, [])) == 1

    def append_chain(first: dict[str, Any]) -> None:
        pending = [first]
        while pending:
            first = pending.pop()
            if first["id"] in used:
                continue
            chain = [first]
            used.add(first["id"])
            while len(chain) < 2 and linear(chain[-1]["to_state"]):
                nxt = outgoing[chain[-1]["to_state"]][0]
                if nxt["id"] in used:
                    break
                chain.append(nxt)
                used.add(nxt["id"])
            ids = [chain[0]["from_state"], *[e["to_state"] for e in chain]]
            involved.update(ids)
            rows.append({"kind": "chain", "state_ids": ids, "edges": chain})
            if linear(ids[-1]) and outgoing[ids[-1]][0]["id"] not in used:
                pending.append(outgoing[ids[-1]][0])

    for edge in edges:
        if not linear(edge["from_state"]):
            append_chain(edge)
    for edge in edges:
        append_chain(edge)
    for identifier in sorted(local - involved):
        rows.append({"kind": "unlinked", "state_ids": [identifier], "edges": []})
    return rows or [{"kind": "empty"}]


def _image_issue(root: Path, ref: str) -> tuple[Path, str]:
    from PIL import Image, UnidentifiedImageError
    issue = path_error(ref, root)
    if issue:
        raise ValueError(f"Unsafe screenshot path {ref!r}: {issue}")
    path = root / ref.replace("\\", "/")
    if not path.is_file():
        return path, "缺图：原始截图不存在"
    try:
        with Image.open(path) as candidate:
            candidate.verify()
        return path, ""
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return path, "缺图：原始截图损坏"


def edge_badge(edge: dict[str, Any], states: dict[str, Any], observations: dict[str, Any]) -> str:
    """Ads closed or jumps returned during this step: core evidence for monetisation analysis."""
    target = observations.get(states[edge["to_state"]]["observation_id"], {})
    events = target.get("auto_dismissed") or []
    ads = sum(1 for e in events if e.get("kind") == "ad")
    jumps = [e.get("package", "") for e in events if e.get("kind") == "external_jump"]
    parts = []
    if ads:
        parts.append(f"途中广告×{ads}")
    if jumps:
        parts.append("外跳已返回 " + "、".join(sorted({j.rsplit(".", 1)[-1] for j in jumps})))
    if any(e.get("kind") == "app_exited" for e in events):
        parts.append("App 退出后重启")
    return "；".join(parts)


class Renderer:
    def __init__(self, data: dict[str, Any], root: Path, face: dict[str, Any], numbers: dict[str, str]):
        self.data, self.root, self.face, self.numbers = data, root, face, numbers
        self.states = {s["id"]: s for s in data["states"]}
        self.pages = {p["id"]: p for p in data["pages"]}
        self.modules = {m["id"]: m for m in data["modules"]}
        self.observations = {o["id"]: o for o in data["observations"]}

    def shot(self, state_id: str) -> str:
        return self.observations[self.states[state_id]["observation_id"]]["files"]["screenshot"]

    def geometry(self, count: int) -> tuple[int, int]:
        return (320, 480) if count == 3 else (CARD_WIDTH, SHOT_HEIGHT)

    def context(self, state_id: str, local_module: str) -> str:
        state = self.states[state_id]
        page = self.pages[state["page_id"]]
        text = f"{self.numbers[state_id]} · {page['id']} / {state_id}"
        if page["module_id"] != local_module:
            text += f" · 跨模块：{self.modules[page['module_id']]['title']}"
        return text

    def card_height(self, state_id: str, local_module: str, width: int, shot_height: int) -> int:
        state = self.states[state_id]
        page = self.pages[state["page_id"]]
        height = shot_height + 64
        for text, key, limit in ((self.context(state_id, local_module), "small", 2), (page["title"], "body", 3),
                                 (state["title"], "small", 3)):
            height += len(wrap_text(text, self.face[key], width - 36, limit)) * _step(self.face[key])
        return height

    def row_height(self, row: dict[str, Any], local_module: str) -> int:
        if row["kind"] == "empty":
            return 240
        width, shot_height = self.geometry(len(row["state_ids"]))
        return max(self.card_height(s, local_module, width, shot_height) for s in row["state_ids"]) + 66

    def card(self, image: Any, x: int, y: int, state_id: str, local_module: str, width: int, shot_height: int) -> str:
        from PIL import Image, ImageDraw, ImageOps
        draw = ImageDraw.Draw(image)
        state = self.states[state_id]
        page = self.pages[state["page_id"]]
        face, text_x, text_width = self.face, x + 18, width - 36
        height = self.card_height(state_id, local_module, width, shot_height)
        foreign = page["module_id"] != local_module
        draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=WHITE,
                               outline=ACCENT if foreign else LINE, width=2)
        position = _text(draw, text_x, y + 14, self.context(state_id, local_module), face["small"], text_width, ACCENT, 2)
        position = _text(draw, text_x, position + 5, page["title"], face["body"], text_width, INK, 3)
        position = _text(draw, text_x, position + 4, state["title"], face["small"], text_width, MUTED, 3)
        shot_y = y + height - shot_height - 26
        draw.rectangle((text_x, shot_y, text_x + text_width, shot_y + shot_height), fill="#eef1ed")
        path, issue = _image_issue(self.root, self.shot(state_id))
        if issue:
            _text(draw, text_x + 16, shot_y + 45, issue + "\n不使用其他截图补位", face["body"], text_width - 32, WARN)
        else:
            with Image.open(path) as original:
                picture = ImageOps.exif_transpose(original).convert("RGB")
                picture.thumbnail((text_width, shot_height), Image.Resampling.LANCZOS)
                image.paste(picture, (text_x + (text_width - picture.width) // 2,
                                      shot_y + (shot_height - picture.height) // 2))
        return issue

    def page(self, path: Path, module: dict[str, Any], rows: list[dict[str, Any]], part: int, total: int,
             title: str) -> dict[str, Any]:
        from PIL import Image, ImageDraw
        face = self.face
        header = [(f"{title} · 模块截图流程", "title", INK, 2), (f"{module['title']}  ·  {part}/{total}", "module", ACCENT, 3),
                  (f"{STATUS_LABELS[module['status']]} · 箭头均来自已记录的动作；橙色字为途中广告/外跳", "small", MUTED, 2)]
        header_height = 22 + sum(len(wrap_text(t, face[k], WIDTH - 2 * MARGIN, l)) * _step(face[k]) + 10
                                 for t, k, _, l in header)
        heights = [self.row_height(row, module["id"]) for row in rows]
        image = Image.new("RGB", (WIDTH, header_height + sum(heights) + 30), BG)
        draw = ImageDraw.Draw(image)
        y = 22
        for text, key, color, limit in header:
            y = _text(draw, MARGIN, y, text, face[key], WIDTH - 2 * MARGIN, color, limit) + 10
        y = header_height
        issues, state_ids, transition_ids = [], [], []
        for row, height in zip(rows, heights):
            if row["kind"] == "empty":
                draw.rounded_rectangle((MARGIN, y + 18, WIDTH - MARGIN, y + height - 18), radius=14, outline=LINE, fill=WHITE)
                _text(draw, MARGIN + 30, y + 50, "未采集：本模块尚无截图", face["module"], WIDTH - 2 * MARGIN - 60, MUTED)
                _text(draw, MARGIN + 30, y + 100, module["reason"] or "不借用其他模块截图。", face["body"],
                      WIDTH - 2 * MARGIN - 60, MUTED, 3)
                y += height
                continue
            ids, edges = row["state_ids"], row["edges"]
            label = "、".join(e["id"] for e in edges) + " · 已观察路径" if edges else "未关联流程 · 无已记录跳转，不画箭头"
            _text(draw, MARGIN, y + 4, label, face["small"], WIDTH - 2 * MARGIN, MUTED, 1)
            card_y = y + 36
            width, shot_height = self.geometry(len(ids))
            gap = (WIDTH - 2 * MARGIN - width * len(ids)) // max(1, len(ids) - 1)
            positions = [MARGIN + i * (width + gap) for i in range(len(ids))]
            for state_id, x in zip(ids, positions):
                issue = self.card(image, x, card_y, state_id, module["id"], width, shot_height)
                if state_id not in state_ids:
                    state_ids.append(state_id)
                if issue:
                    issues.append(f"{state_id}: {issue} ({self.shot(state_id)})")
            for i, edge in enumerate(edges):
                transition_ids.append(edge["id"])
                left, right = positions[i] + width + 12, positions[i + 1] - 12
                arrow_y = card_y + (290 if len(ids) == 3 else 335)
                draw.line((left, arrow_y, right, arrow_y), fill=ACCENT, width=4)
                draw.polygon([(right, arrow_y), (right - 17, arrow_y - 10), (right - 17, arrow_y + 10)], fill=ACCENT)
                font = face["small"] if len(ids) == 3 else face["body"]
                text_left, text_width = left - 10, right - left + 20
                bottom = _text(draw, text_left, arrow_y + 23, edge.get("label") or action_label(edge["action"]), font,
                               text_width, ACCENT, 6, "center")
                badge = edge_badge(edge, self.states, self.observations)
                if badge:
                    _text(draw, text_left, bottom + 6, badge, face["small"], text_width, WARN, 5, "center")
                _text(draw, left - 4, arrow_y - 38, f"{self.numbers[edge['from_state']]} → {self.numbers[edge['to_state']]}",
                      face["small"], right - left + 8, MUTED, 1, "center")
            if not edges:
                _text(draw, MARGIN + CARD_WIDTH + 45, card_y + 200, "此状态已有截图\n尚无流程连接证据", face["body"], 400, MUTED, 4)
            y += height
        image.save(path, format="PNG")
        return {"path": path, "module_id": module["id"], "part": part, "state_ids": state_ids,
                "transition_ids": transition_ids, "issues": list(dict.fromkeys(issues))}


def _md(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").replace("`", "'")


def build_montages(root: Path, title: str = "Android App", rows_per_image: int = 4) -> list[dict[str, Any]]:
    root = root.resolve()
    map_path = root / "research-map.json"
    data = json.loads(map_path.read_text(encoding="utf-8-sig"))
    report = check_map(data, root)
    if not report["ok"]:
        raise ValueError("地图无效：" + "; ".join(report["errors"]))
    if not 1 <= rows_per_image <= 12:
        raise ValueError("rows_per_image 需在 1–12")
    output = root / "flow_export"
    output.mkdir(exist_ok=True)
    for stale in output.glob("*_flow.png"):
        stale.unlink()  # derived files only; avoid mixing old and new runs
    numbers = {s["id"]: f"N{i:02d}" for i, s in enumerate(sorted(data["states"], key=lambda s: s["id"]), 1)}
    renderer = Renderer(data, root, fonts(), numbers)
    outputs = []
    for index, module in enumerate(data["modules"], 1):
        rows = rows_for_module(data, module["id"])
        parts = math.ceil(len(rows) / rows_per_image)
        for part in range(parts):
            path = output / f"{index:02d}_{_slug(module['id'])}_{_slug(module['title'])}_p{part + 1:02d}_flow.png"
            outputs.append(renderer.page(path, module, rows[part * rows_per_image:(part + 1) * rows_per_image],
                                         part + 1, parts, title))
    modules = {m["id"]: m for m in data["modules"]}
    notes = ["# 模块截图流程", "", "直接看下表的 PNG。箭头只来自已记录的动作；没有连接证据的状态单列为“未关联流程”；未采集模块不借图补位。", "",
             "| 模块 | 状态 | 文件 | 跳转 |", "| --- | --- | --- | --- |"]
    for item in outputs:
        module = modules[item["module_id"]]
        notes.append(f"| {_md(module['id'] + ' ' + module['title'])} | {STATUS_LABELS[module['status']]} | "
                     f"[{item['path'].name}](<{quote(item['path'].name)}>) | {_md(', '.join(item['transition_ids']) or '无')} |")
    pages = {p["id"]: p for p in data["pages"]}
    notes += ["", "## 截图编号", "", "| 编号 / 状态 | 模块 / 页面 / 状态 | 原始截图 |", "| --- | --- | --- |"]
    for state in sorted(data["states"], key=lambda s: s["id"]):
        page = pages[state["page_id"]]
        notes.append(f"| {numbers[state['id']]} / {state['id']} | "
                     f"{_md(modules[page['module_id']]['title'] + ' / ' + page['title'] + ' / ' + state['title'])} | "
                     f"`{renderer.shot(state['id'])}` |")
    notes += ["", "## 跳转与途中事件", ""]
    for edge in sorted(data["transitions"], key=lambda e: e["id"]):
        badge = edge_badge(edge, renderer.states, renderer.observations)
        notes.append(f"- `{edge['id']}`：{numbers[edge['from_state']]} → {_md(edge.get('label') or action_label(edge['action']))}"
                     f" → {numbers[edge['to_state']]}" + (f"；{_md(badge)}" if badge else ""))
    if not data["transitions"]:
        notes.append("没有已记录跳转。")
    notes += ["", "## 覆盖与缺口", ""]
    for module in data["modules"]:
        unobserved = [p["title"] for p in data["pages"] if p["module_id"] == module["id"]
                      and not any(s["page_id"] == p["id"] for s in data["states"])]
        notes.append(f"- {_md(module['title'])}：{STATUS_LABELS[module['status']]}；{_md(module['reason'] or '覆盖说明待补充')}"
                     + (f"；未采集页面：{_md('、'.join(unobserved))}" if unobserved else ""))
    for issue in dict.fromkeys(i for o in outputs for i in o["issues"]):
        notes.append(f"- {_md(issue)}")
    (output / "flow_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    return outputs
