"""Delivery check: valid files and references. PASS never means coverage is complete."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import zipfile
from typing import Any

from .mapstore import STATUS_LABELS, check_map


def png_error(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            header = stream.read(33)
            if len(header) != 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
                return "不是有效 PNG"
            if not all(struct.unpack(">II", header[16:24])):
                return "PNG 尺寸无效"
            stream.seek(-12, 2)
            if stream.read() != b"\x00\x00\x00\x00IEND\xaeB`\x82":
                return "PNG 不完整"
        return None
    except (OSError, struct.error) as error:
        return f"无法读取：{error}"


def review(root: Path, require_flow: bool = True, require_docx: bool = False) -> dict[str, Any]:
    root = root.resolve()
    issues: list[str] = []
    warnings: list[str] = []
    data: dict[str, Any] = {}
    map_path = root / "research-map.json"
    if not map_path.is_file():
        issues.append("缺少 research-map.json")
    else:
        data = json.loads(map_path.read_text(encoding="utf-8-sig"))
        report = check_map(data, root)
        issues += [f"地图：{item}" for item in report["errors"]]
        warnings += [f"地图：{item}" for item in report["warnings"] if "file missing" not in item]
        if report["missing_files"]:
            issues.append(f"地图引用的 {len(report['missing_files'])} 个证据文件不存在：" + "、".join(report["missing_files"][:10]))
    state_shots = []
    observations = {o["id"]: o for o in data.get("observations", [])}
    for state in data.get("states", []):
        shot = observations.get(state.get("observation_id"), {}).get("files", {}).get("screenshot")
        if shot:
            state_shots.append(root / shot)
    tiny = [p for p in state_shots if p.is_file() and p.stat().st_size < 1024]
    if tiny:
        issues.append(f"{len(tiny)} 张状态截图小于 1KB，疑似无效")
    digests: dict[str, list[str]] = {}
    for path in state_shots:
        if path.is_file():
            digests.setdefault(hashlib.md5(path.read_bytes()).hexdigest(), []).append(path.name)
    duplicates = [names for names in digests.values() if len(names) > 1]
    if duplicates:
        warnings.append(f"{len(duplicates)} 组状态截图完全相同，确认是否代表不同入口")
    flow_dir = root / "flow_export"
    montages = sorted(flow_dir.glob("*_flow.png")) if flow_dir.is_dir() else []
    if require_flow and not montages:
        issues.append("缺少 flow_export/*_flow.png")
    for montage in montages:
        error = png_error(montage)
        if error:
            issues.append(f"流程图 {montage.name}：{error}")
    if montages and not (flow_dir / "flow_notes.md").is_file():
        issues.append("缺少 flow_export/flow_notes.md")
    docx = root / "product_summary.docx"
    if docx.is_file():
        try:
            with zipfile.ZipFile(docx) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", "ignore")
            if "|---|" in xml or "| --- |" in xml:
                issues.append("Word 中残留 Markdown 表格源码")
        except (OSError, KeyError, zipfile.BadZipFile):
            issues.append("product_summary.docx 损坏")
    elif require_docx:
        issues.append("要求 Word，但缺少 product_summary.docx")
    unresolved = json.loads((root / "capture-session.json").read_text(encoding="utf-8")).get("unresolved_actions", []) \
        if (root / "capture-session.json").is_file() else []
    if unresolved:
        warnings.append(f"{len(unresolved)} 个动作结果未确认（发出后采集失败），未连成箭头")

    status = "PASS" if not issues else "FAIL"
    lines = ["# 交付检查", "", f"- 目录：`{root}`", f"- 状态截图：{len(state_shots)}", f"- 流程图：{len(montages)}",
             f"- 跳转：{len(data.get('transitions', []))}", "", f"## 结果：{status}", "",
             "PASS 只说明文件和引用有效，不说明页面语义正确或覆盖完整；仍需人工打开流程图核对箭头、分支和缺图。", ""]
    if data.get("modules"):
        lines += ["## 模块覆盖", ""]
        lines += [f"- {m['id']} {m['title']}：{STATUS_LABELS.get(m['status'], m['status'])} — {m.get('reason') or '未填写覆盖说明'}"
                  for m in data["modules"]]
        lines.append("")
    if issues:
        lines += ["## 问题", "", *[f"- {item}" for item in issues], ""]
    if warnings:
        lines += ["## 提醒", "", *[f"- {item}" for item in warnings], ""]
    (root / "delivery_review.md").write_text("\n".join(lines), encoding="utf-8")
    return {"status": status, "issues": issues, "warnings": warnings, "montages": [str(p) for p in montages],
            "report": str(root / "delivery_review.md")}
