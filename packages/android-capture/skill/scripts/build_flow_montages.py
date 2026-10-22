#!/usr/bin/env python3
"""Render actual screenshot transitions as module PNG montages, without ADB or HTML."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from research_map import STATUS_LABELS, _path_error, action_label, check_map


WIDTH = 1280
MARGIN = 36
CARD_WIDTH = 386
SHOT_WIDTH, SHOT_HEIGHT = 350, 560
BG = "#f5f6f4"
WHITE = "#ffffff"
INK = "#20332f"
MUTED = "#61716b"
LINE = "#d9e0db"
ACCENT = "#277568"
WARN = "#a55c34"


def fonts() -> dict[str, Any]:
    regular = next((str(path) for path in map(Path, [
        r"C:\Windows\Fonts\msyh.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]) if path.is_file()), None)
    bold = next((str(path) for path in map(Path, [r"C:\Windows\Fonts\msyhbd.ttc"]) if path.is_file()), regular)
    return {key: ImageFont.truetype(bold if key in {"title", "module"} else regular, size)
            if regular else ImageFont.load_default(size=size)
            for key, size in {"title": 32, "module": 26, "body": 21, "small": 17}.items()}


def wrap_text(text: Any, font: Any, width: int, max_lines: int | None = None) -> list[str]:
    """Wrap character-wise, including CJK and uninterrupted control identifiers."""
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


def _text(draw: Any, x: int, y: int, text: Any, font: Any, width: int,
          color: str = INK, max_lines: int | None = None, align: str = "left") -> int:
    step = max(font.getbbox("国Ag")[3] - min(0, font.getbbox("国Ag")[1]) + 6, 22)
    for line in wrap_text(text, font, width, max_lines):
        offset = (width - draw.textlength(line, font=font)) / 2 if align == "center" else 0
        draw.text((x + offset, y), line, font=font, fill=color, anchor="lt")
        y += step
    return y


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]+", "_", value).strip("_.")[:55] or "module"


def rows_for_module(data: dict[str, Any], module_id: str) -> list[dict[str, Any]]:
    """Pack nonbranching recorded edges into at most three screenshots per row.

    Branches and revisits retain the same global state number. Cross-module edges
    are shown in both endpoint modules with the external module explicitly named.
    Sorting is for locating records only, never evidence of temporal precedence.
    """
    pages = {page["id"]: page for page in data["pages"]}
    states = {state["id"]: state for state in data["states"]}
    local = {key for key, state in states.items() if pages[state["page_id"]]["module_id"] == module_id}
    edges = [edge for edge in sorted(data["transitions"], key=lambda item: item["id"])
             if edge["from_state"] in local or edge["to_state"] in local]
    incoming: dict[str, list[dict[str, Any]]] = {}
    outgoing: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        incoming.setdefault(edge["to_state"], []).append(edge)
        outgoing.setdefault(edge["from_state"], []).append(edge)
    rows, involved, used = [], set(), set()

    def append_chain(first: dict[str, Any]) -> None:
        pending = [first]
        while pending:
            first = pending.pop()
            if first["id"] in used:
                continue
            chain = [first]
            used.add(first["id"])
            while len(chain) < 2:
                endpoint = chain[-1]["to_state"]
                if endpoint not in local or len(incoming.get(endpoint, [])) != 1 or len(outgoing.get(endpoint, [])) != 1:
                    break
                next_edge = outgoing[endpoint][0]
                if next_edge["id"] in used:
                    break
                chain.append(next_edge)
                used.add(next_edge["id"])
            identifiers = [chain[0]["from_state"], *[edge["to_state"] for edge in chain]]
            involved.update(identifiers)
            rows.append({"kind": "chain" if len(chain) > 1 else "edge", "source": identifiers[0],
                         "target": identifiers[-1], "state_ids": identifiers, "edges": chain})
            endpoint = identifiers[-1]
            if endpoint in local and len(incoming.get(endpoint, [])) == len(outgoing.get(endpoint, [])) == 1:
                next_edge = outgoing[endpoint][0]
                if next_edge["id"] not in used:
                    pending.append(next_edge)

    for edge in edges:
        source = edge["from_state"]
        if source not in local or len(incoming.get(source, [])) != 1 or len(outgoing.get(source, [])) != 1:
            append_chain(edge)
    # Remaining segments are continuation chunks, or loops not reached at a fork.
    # Each edge is consumed once; no full paths are enumerated.
    for edge in edges:
        append_chain(edge)
    for identifier in sorted(local - involved):
        rows.append({"kind": "unlinked", "source": identifier})
    return rows or [{"kind": "empty"}]


def _image_status(root: Path, ref: str) -> tuple[Path, str]:
    issue = _path_error(ref, root)
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
        return path, "缺图：原始截图损坏或无效"


def _card(image: Image.Image, x: int, y: int, state: dict[str, Any], page: dict[str, Any],
          module: dict[str, Any], local_module: str, number: str, root: Path,
          face: dict[str, Any], card_width: int = CARD_WIDTH, shot_height: int = SHOT_HEIGHT) -> tuple[int, str]:
    draw = ImageDraw.Draw(image)
    text_x, text_width = x + 18, card_width - 36
    shot_width = card_width - 36
    page_lines = wrap_text(page["title"], face["body"], text_width, 3)
    state_lines = wrap_text(state["title"], face["small"], text_width, 3)
    context = f"{number} · {page['id']} / {state['id']}"
    if module["id"] != local_module:
        context = f"{number} · {page['id']} / {state['id']} · 跨模块：{module['title']}"
    context_lines = wrap_text(context, face["small"], text_width, 2)
    # Fixed line spacing is shared with _text and expanded for tall font bearings.
    body_step = max(face["body"].getbbox("国Ag")[3] - min(0, face["body"].getbbox("国Ag")[1]) + 6, 22)
    small_step = max(face["small"].getbbox("国Ag")[3] - min(0, face["small"].getbbox("国Ag")[1]) + 6, 22)
    title_height = len(context_lines) * small_step + len(page_lines) * body_step + len(state_lines) * small_step + 26
    height = title_height + shot_height + 38
    draw.rounded_rectangle((x, y, x + card_width, y + height), radius=14, fill=WHITE,
                           outline=ACCENT if module["id"] != local_module else LINE, width=2)
    position = _text(draw, text_x, y + 14, context, face["small"], text_width, ACCENT, 2)
    position = _text(draw, text_x, position + 5, page["title"], face["body"], text_width, INK, 3)
    position = _text(draw, text_x, position + 4, state["title"], face["small"], text_width, MUTED, 3)
    shot_y = y + title_height + 12
    draw.rectangle((text_x, shot_y, text_x + shot_width, shot_y + shot_height), fill="#eef1ed")
    path, issue = _image_status(root, state["screenshot"])
    if issue:
        _text(draw, text_x + 16, shot_y + 45, issue + "\n不使用其他截图补位", face["body"], shot_width - 32, WARN)
    else:
        with Image.open(path) as original:
            screenshot = ImageOps.exif_transpose(original).convert("RGB")
            screenshot.thumbnail((shot_width, shot_height), Image.Resampling.LANCZOS)
            image.paste(screenshot, (text_x + (shot_width - screenshot.width) // 2,
                                     shot_y + (shot_height - screenshot.height) // 2))
    return height, issue


def _row_height(row: dict[str, Any], states: dict[str, Any], pages: dict[str, Any],
                modules: dict[str, Any], local_module: str, numbers: dict[str, str], face: dict[str, Any]) -> int:
    if row["kind"] == "empty":
        return 240
    # Measure the same card geometry without allocating a full montage.
    # Calculate text blocks directly; do not open evidence merely for layout.
    identifiers = row.get("state_ids", [row["source"]])
    card_width, shot_height = (320, 480) if len(identifiers) == 3 else (CARD_WIDTH, SHOT_HEIGHT)
    def measure(identifier: str) -> int:
        state, page = states[identifier], pages[states[identifier]["page_id"]]
        module = modules[page["module_id"]]
        context = f"{numbers[identifier]} · {page['id']} / {state['id']}"
        if module["id"] != local_module:
            context += f" · 跨模块：{module['title']}"
        result = shot_height + 64
        for text, key, limit in ((context, "small", 2), (page["title"], "body", 3), (state["title"], "small", 3)):
            step = max(face[key].getbbox("国Ag")[3] - min(0, face[key].getbbox("国Ag")[1]) + 6, 22)
            result += len(wrap_text(text, face[key], card_width - 36, limit)) * step
        return result
    card_height = max(measure(identifier) for identifier in identifiers)
    return card_height + 66


def _render_page(path: Path, data: dict[str, Any], module: dict[str, Any], rows: list[dict[str, Any]],
                 number: int, total: int, title: str, root: Path, numbers: dict[str, str], face: dict[str, Any]) -> dict[str, Any]:
    states = {item["id"]: item for item in data["states"]}
    pages = {item["id"]: item for item in data["pages"]}
    modules = {item["id"]: item for item in data["modules"]}
    header_blocks = [(f"{title} · 模块截图流程", "title", INK, 2),
                     (f"{module['title']}  ·  {number}/{total}", "module", ACCENT, 3),
                     (f"{STATUS_LABELS[module['status']]} · 连续路径横排；分支与续行共享编号；不补造流程", "small", MUTED, 2)]
    header_height = 22
    for text, key, color, limit in header_blocks:
        step = max(face[key].getbbox("国Ag")[3] - min(0, face[key].getbbox("国Ag")[1]) + 6, 22)
        header_height += len(wrap_text(text, face[key], WIDTH - 2 * MARGIN, limit)) * step + 10
    heights = [_row_height(row, states, pages, modules, module["id"], numbers, face) for row in rows]
    image = Image.new("RGB", (WIDTH, header_height + sum(heights) + 30), BG)
    draw = ImageDraw.Draw(image)
    y = 22
    for text, key, color, limit in header_blocks:
        y = _text(draw, MARGIN, y, text, face[key], WIDTH - 2 * MARGIN, color, limit) + 10
    y = header_height
    issues, state_ids, transition_ids = [], [], []
    for row, height in zip(rows, heights):
        if row["kind"] == "empty":
            draw.rounded_rectangle((MARGIN, y + 18, WIDTH - MARGIN, y + height - 18), radius=14, outline=LINE, fill=WHITE)
            _text(draw, MARGIN + 30, y + 50, "未采集：本模块尚无截图", face["module"], WIDTH - 2 * MARGIN - 60, MUTED)
            _text(draw, MARGIN + 30, y + 100, module["reason"] or "不借用其他模块截图，不补齐未观察流程。", face["body"], WIDTH - 2 * MARGIN - 60, MUTED, 3)
        else:
            edges = row.get("edges", [])
            identifiers = row.get("state_ids", [row["source"]])
            label = "、".join(edge["id"] for edge in edges) + " · 已观察路径" if edges else "未关联流程 · 无已记录跳转，不添加箭头"
            _text(draw, MARGIN, y + 4, label, face["small"], WIDTH - 2 * MARGIN, MUTED, 1)
            card_y = y + 36
            card_width, shot_height = (320, 480) if len(identifiers) == 3 else (CARD_WIDTH, SHOT_HEIGHT)
            gap = (WIDTH - 2 * MARGIN - card_width * len(identifiers)) // max(1, len(identifiers) - 1)
            positions = [MARGIN + index * (card_width + gap) for index in range(len(identifiers))]
            for identifier, x in zip(identifiers, positions):
                state = states[identifier]
                page = pages[state["page_id"]]
                _, issue = _card(image, x, card_y, state, page, modules[page["module_id"]], module["id"], numbers[identifier], root, face, card_width, shot_height)
                if identifier not in state_ids:
                    state_ids.append(identifier)
                if issue:
                    issues.append(f"{identifier}: {issue} ({state['screenshot']})")
            for index, edge in enumerate(edges):
                transition_ids.append(edge["id"])
                arrow_left, arrow_right = positions[index] + card_width + 12, positions[index + 1] - 12
                arrow_y = card_y + (290 if len(identifiers) == 3 else 335)
                draw.line((arrow_left, arrow_y, arrow_right, arrow_y), fill=ACCENT, width=4)
                draw.polygon([(arrow_right, arrow_y), (arrow_right - 17, arrow_y - 10), (arrow_right - 17, arrow_y + 10)], fill=ACCENT)
                action = action_label(edge["action"])
                _text(draw, arrow_left + 4, arrow_y + 23, action, face["small"] if len(identifiers) == 3 else face["body"], arrow_right - arrow_left - 8, ACCENT, 10, "center")
                relation = f"{numbers[edge['from_state']]} → {numbers[edge['to_state']]}"
                _text(draw, arrow_left - 4, arrow_y - 38, relation, face["small"], arrow_right - arrow_left + 8, MUTED, 1, "center")
            if not edges:
                _text(draw, MARGIN + CARD_WIDTH + 45, card_y + 200, "此状态已有截图\n尚无流程连接证据", face["body"], 400, MUTED, 4)
        y += height
    image.save(path, format="PNG")
    return {"path": path, "module_id": module["id"], "part": number, "rows": len(rows),
            "state_ids": state_ids, "transition_ids": transition_ids, "issues": list(dict.fromkeys(issues)),
            "width": image.width, "height": image.height}


def _md(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").replace("`", "'")


def build_montages(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Build one or more flow PNGs per module and flow_notes.md.

    Map validation runs before writing. There is no Markdown/folder fallback:
    unrelated pictures and order on disk cannot become flow evidence.
    """
    root = Path(args.input_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"Input directory not found: {root}")
    map_arg = getattr(args, "research_map", None)
    map_path = Path(map_arg).resolve() if map_arg else root / "research-map.json"
    data = json.loads(map_path.read_text(encoding="utf-8-sig"))
    validation = check_map(data, root)
    if not validation["ok"]:
        raise ValueError("Invalid research map: " + "; ".join(validation["errors"]))
    limit = getattr(args, "rows_per_image", 4)
    if type(limit) is not int or not 1 <= limit <= 12:
        raise ValueError("--rows-per-image must be an integer from 1 to 12")
    output_arg = getattr(args, "out_dir", None)
    output_dir = Path(output_arg).resolve() if output_arg else root / "flow_export"
    if output_dir == root or root.is_relative_to(output_dir):
        raise ValueError("Output must be a separate directory, not the input directory or its ancestor")
    face = fonts()
    numbers = {item["id"]: f"N{index:02d}" for index, item in enumerate(sorted(data["states"], key=lambda item: item["id"]), 1)}
    title = getattr(args, "title", "Android App")
    outputs = []
    # Reserve all input evidence paths before selecting generated filenames.
    protected = {map_path.resolve()}
    protected.update((root / item["screenshot"].replace("\\", "/")).resolve() for item in data["states"])
    protected.update((root / ref.replace("\\", "/")).resolve()
                     for observation in data["observations"]
                     for ref in observation["files"].values() if isinstance(ref, str) and ref)
    plans = []
    for index, module in enumerate(data["modules"], 1):
        rows = rows_for_module(data, module["id"])
        parts = math.ceil(len(rows) / limit)
        for part in range(parts):
            path = output_dir / f"{index:02d}_{_slug(module['id'])}_{_slug(module['title'])}_p{part + 1:02d}_flow.png"
            if path.resolve() in protected:
                raise ValueError("Generated output would overwrite source evidence")
            plans.append((path, module, rows[part * limit:(part + 1) * limit], part + 1, parts))
    notes_path = output_dir / "flow_notes.md"
    if notes_path.resolve() in protected:
        raise ValueError("Flow notes would overwrite source evidence")
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, module, rows, part, parts in plans:
        outputs.append(_render_page(path, data, module, rows, part, parts, title, root, numbers, face))
    notes = ["# 模块截图流程", "", "直接查看本次清单中的 PNG 即可。连续无分支路径每行最多三张截图，长链用共享 N 编号续行；分支、返回和跨模块跳转同样保留共享编号，不按截图文件顺序编造主线。", "",
             "图片标题为便于阅读可能缩短，完整标题、动作、原始截图引用在下表与 research-map.json 中保留。无连接证据的状态单列为‘未关联流程’；未采集模块不借图补位。", "",
             f"来源地图：`{map_path}`", "", "## 本次生成", "", "| 模块 | 状态 | 文件 | 跳转记录 |", "| --- | --- | --- | --- |"]
    modules = {item["id"]: item for item in data["modules"]}
    for item in outputs:
        module = modules[item["module_id"]]
        notes.append(f"| {_md(module['id'] + ' ' + module['title'])} | {STATUS_LABELS[module['status']]} | [{item['path'].name}](<{quote(item['path'].name)}>) | {_md(', '.join(item['transition_ids']) or '无；未关联流程或未采集')} |")
    if not outputs:
        notes.append("| 未登记模块 | 待采集 | 无 | 不猜测模块和流程 |")
    pages = {item["id"]: item for item in data["pages"]}
    notes += ["", "## 截图编号与原始引用", "", "| 编号 / 状态 | 模块 / 页面 / 状态标题 | 原始截图 |", "| --- | --- | --- | --- |"]
    for state in sorted(data["states"], key=lambda item: item["id"]):
        page = pages[state["page_id"]]
        module = modules[page["module_id"]]
        notes.append(f"| {numbers[state['id']]} / {_md(state['id'])} | {_md(module['title'] + ' / ' + page['title'] + ' / ' + state['title'])} | `{_md(state['screenshot'])}` |")
    notes += ["", "## 已记录的一跳关系", ""]
    for edge in sorted(data["transitions"], key=lambda item: item["id"]):
        notes.append(f"- `{_md(edge['id'])}`：{numbers[edge['from_state']]} → {_md(action_label(edge['action']))} → {numbers[edge['to_state']]}；原始动作 `{_md(json.dumps(edge['action'], ensure_ascii=False))}`；观察 `{_md(', '.join(edge['evidence_observation_ids']))}`。")
    if not data["transitions"]:
        notes.append("没有已记录跳转；截图之间不画箭头。")
    notes += ["", "## 覆盖与缺口", "", "文件有效不等于流程覆盖完成；状态来自地图，不由截图数量或本脚本自动升级。旧的导出文件可能仍在目录中，以‘本次生成’清单为准。", ""]
    for module in data["modules"]:
        local_pages = [page for page in data["pages"] if page["module_id"] == module["id"]]
        unobserved = [page["title"] for page in local_pages if not any(state["page_id"] == page["id"] for state in data["states"])]
        notes.append(f"- {_md(module['title'])}：{STATUS_LABELS[module['status']]}；{_md(module['reason'] or '覆盖说明待补充')}。" + (f" 未采集页面：{_md('、'.join(unobserved))}。" if unobserved else ""))
    for issue in dict.fromkeys(issue for output in outputs for issue in output["issues"]):
        notes.append(f"- {_md(issue)}。未使用其他截图补位。")
    notes_path.write_text("\n".join(notes) + "\n", encoding="utf-8")
    return outputs


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Build module screenshot-flow PNGs from recorded transitions")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--research-map", help="Defaults to <input-dir>/research-map.json")
    parser.add_argument("--out-dir", help="Defaults to <input-dir>/flow_export")
    parser.add_argument("--title", default="Android App")
    parser.add_argument("--rows-per-image", type=int, default=4, help="1–12; default 4")
    args = parser.parse_args(argv)
    try:
        outputs = build_montages(args)
        print(json.dumps({"ok": True, "files": [str(item["path"]) for item in outputs]}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
