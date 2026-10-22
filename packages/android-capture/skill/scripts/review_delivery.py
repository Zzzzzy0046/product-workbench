#!/usr/bin/env python3
"""Validate Android screenshot delivery artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path, PureWindowsPath


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def markdown_image_refs(text: str) -> list[str]:
    refs: list[str] = []
    refs.extend(re.findall(r'<img\s+[^>]*src=[\"\']([^\"\']+)[\"\']', text))
    refs.extend(ref.strip("<>") for ref in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text))
    return refs


def safe_evidence_path(root: Path, ref: str) -> Path:
    if not isinstance(ref, str) or not ref.strip() or "\x00" in ref:
        raise ValueError(f"无效证据路径：{ref!r}")
    normalized = ref.replace("\\", "/")
    path, windows = Path(normalized), PureWindowsPath(ref)
    if path.is_absolute() or windows.is_absolute() or windows.drive or ".." in path.parts or ":" in normalized:
        raise ValueError(f"证据路径必须是研究目录内的相对路径：{ref}")
    resolved = (root / path).resolve()
    if not is_relative_to(resolved, root):
        raise ValueError(f"证据路径越出研究目录：{ref}")
    return resolved


def png_error(path: Path) -> str | None:
    """Check derived PNGs without making Pillow a required review dependency."""
    try:
        if path.stat().st_size == 0:
            return "文件为空"
        with path.open("rb") as stream:
            header = stream.read(33)
            if len(header) != 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
                return "不是有效的 PNG 文件头"
            if struct.unpack(">I", header[8:12])[0] != 13 or not all(struct.unpack(">II", header[16:24])):
                return "PNG 尺寸或 IHDR 无效"
            stream.seek(-12, 2)
            if stream.read() != b"\x00\x00\x00\x00IEND\xaeB`\x82":
                return "PNG 不完整，缺少有效 IEND"
        try:
            from PIL import Image
        except ImportError:
            return None  # Only header/end checks are available in a stdlib-only environment.
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            # Pillow's decompression-bomb protection is not an OSError subclass.
            return f"PNG 无法验证：{exc}"
        return None
    except (OSError, ValueError, SyntaxError, struct.error) as exc:
        return f"PNG 无法读取：{exc}"


def review_delivery(args: argparse.Namespace) -> dict:

    root = Path(args.input_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Input directory not found: {root}")

    issues: list[str] = []
    warnings: list[str] = []
    map_arg = getattr(args, "research_map", None)
    map_path = Path(map_arg).resolve() if map_arg else root / "research-map.json"
    map_mode = map_path.exists() or bool(map_arg)
    map_data: dict = {}
    map_result: dict = {}
    if map_mode:
        try:
            from research_map import check_map
            map_data = json.loads(map_path.read_text(encoding="utf-8-sig"))
            map_result = check_map(map_data, root)
            issues.extend(f"research-map: {item}" for item in map_result.get("errors", []))
            warnings.extend(f"research-map: {item}" for item in map_result.get("warnings", []))
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"无法读取 research-map：{exc}")

    axure_dir = root / "axure_export"
    flow_dir = root / "flow_export"
    pngs = sorted(p for p in root.rglob("*.png") if p.is_file()
                  and not is_relative_to(p, axure_dir) and not is_relative_to(p, flow_dir)
                  and is_relative_to(p, root))
    zero_or_tiny = [p for p in pngs if p.stat().st_size < 1024]

    hash_groups: dict[str, list[Path]] = {}
    for p in pngs:
        hash_groups.setdefault(md5(p), []).append(p)
    duplicates = {h: ps for h, ps in hash_groups.items() if len(ps) > 1}

    summary_arg = getattr(args, "summary", None)
    summary_path = Path(summary_arg).resolve() if summary_arg else root / "product_summary.md"
    summary_exists = summary_path.exists()
    docx_path = summary_path.with_suffix(".docx")
    docx_exists = docx_path.exists()
    docx_raw_table = False
    docx_valid = False
    if docx_exists:
        try:
            with zipfile.ZipFile(docx_path) as docx_zip:
                xml = docx_zip.read("word/document.xml").decode("utf-8", errors="ignore")
            docx_raw_table = "|---|" in xml or "| 类型 |" in xml
            docx_valid = True
        except Exception:
            warnings.append("无法检查 product_summary.docx 的内部结构。")
            if getattr(args, "require_docx", False):
                issues.append("要求 Word 报告，但 product_summary.docx 损坏或缺少有效文档结构。")
    missing_refs: list[str] = []
    section_count = 0
    if summary_exists:
        text = summary_path.read_text(encoding="utf-8")
        section_count = sum(1 for line in text.splitlines() if line.startswith("## "))
        for ref in markdown_image_refs(text):
            if ref.startswith("http://") or ref.startswith("https://"):
                continue
            try:
                path = safe_evidence_path(root, ref)
            except ValueError as exc:
                issues.append(str(exc))
                missing_refs.append(ref)
                continue
            if not path.is_file():
                missing_refs.append(ref)

    map_missing_refs: list[str] = []
    if map_mode and isinstance(map_data, dict):
        states = map_data.get("states", [])
        for state in states if isinstance(states, list) else []:
            if not isinstance(state, dict):
                continue
            for field in ("screenshot", "ui_xml"):
                ref = state.get(field)
                if not ref:
                    if field == "screenshot":
                        warnings.append(f"状态 {state.get('id', '?')} 未采集截图。")
                    continue
                try:
                    path = safe_evidence_path(root, ref)
                    if not path.is_file():
                        map_missing_refs.append(f"{state.get('id', '?')}.{field}: {ref}")
                except ValueError as exc:
                    issues.append(str(exc))
        for ref in map_result.get("missing_files", []):
            if not any(item.endswith(f": {ref}") for item in map_missing_refs):
                map_missing_refs.append(f"observation evidence: {ref}")

    axure_boards = sorted(axure_dir.glob("*_board.png")) if axure_dir.exists() else []
    axure_notes = axure_dir / "axure_notes.md"
    flow_montages = sorted(flow_dir.glob("*_flow.png")) if flow_dir.is_dir() else []
    flow_notes = flow_dir / "flow_notes.md"
    flow_invalid: list[str] = []
    for montage in flow_montages:
        if not is_relative_to(montage, root) or not montage.is_file():
            error = "流程拼图必须是研究目录内的文件"
        else:
            error = png_error(montage)
        if error:
            flow_invalid.append(f"{montage.name}: {error}")
    if getattr(args, "require_flow", False) and not flow_montages:
        issues.append("要求模块流程拼图，但未找到 flow_export/*_flow.png。")
    if flow_montages:
        if not flow_notes.is_file() or not is_relative_to(flow_notes, root):
            issues.append("找到模块流程拼图，但缺少研究目录内的 flow_export/flow_notes.md。")
        else:
            try:
                if not flow_notes.read_text(encoding="utf-8-sig").strip():
                    issues.append("模块流程拼图的 flow_notes.md 为空。")
            except (OSError, UnicodeError) as exc:
                issues.append(f"无法读取模块流程拼图说明：{exc}")
    if flow_invalid:
        issues.extend(f"模块流程拼图无效：{item}" for item in flow_invalid)

    if not pngs:
        if map_mode:
            warnings.append("未找到原始 PNG 截图；当前仅有采集结构，不代表页面已覆盖。")
        else:
            issues.append("未找到原始 PNG 截图。")
    if zero_or_tiny:
        issues.append(f"发现 {len(zero_or_tiny)} 个小于 1KB 的可疑截图。")
    if not summary_exists and not map_mode:
        warnings.append("缺少 product_summary.md。")
    if getattr(args, "require_summary", False) and not summary_exists:
        issues.append("要求 Markdown 报告，但未找到 product_summary.md。")
    if getattr(args, "require_docx", False) and not docx_exists:
        issues.append("要求 Word 报告，但未找到 product_summary.docx。")
    if docx_raw_table:
        issues.append("product_summary.docx 中疑似残留 Markdown 表格原文，应导出为真实 Word 表格。")
    if missing_refs:
        issues.append(f"product_summary.md 中有 {len(missing_refs)} 个截图引用不存在。")
    if map_missing_refs:
        issues.append(f"research-map 中有 {len(map_missing_refs)} 个证据文件引用不存在。")
    if duplicates:
        warnings.append(f"发现 {len(duplicates)} 组 MD5 重复截图，需要判断是否代表不同入口。")
    if getattr(args, "require_axure", False) and not axure_boards:
        issues.append("要求 Axure board，但未找到 axure_export\\*_board.png。")
    if axure_boards and not axure_notes.exists():
        issues.append("找到 Axure board，但缺少 axure_notes.md。")

    lines: list[str] = []
    lines.append("# 截图交付检查")
    lines.append("")
    lines.append(f"- 研究目录：`{root}`")
    lines.append(f"- 原始 PNG 截图：{len(pngs)}（不含流程拼图等派生图）")
    lines.append(f"- 模块流程拼图：{len(flow_montages)}")
    lines.append(f"- 流程拼图说明：{'有' if flow_notes.is_file() else '无'}")
    lines.append(f"- 模块地图：{'有' if map_mode else '无'}")
    lines.append(f"- product_summary.md：{'有' if summary_exists else '无'}")
    lines.append(f"- product_summary.docx：{'有' if docx_exists else '无'}")
    if docx_exists:
        lines.append(f"- Word 残留 Markdown 表格：{'有' if docx_raw_table else '无'}")
    if summary_exists:
        lines.append(f"- 报告章节：{section_count}")
        lines.append(f"- 缺失图片引用：{len(missing_refs)}")
    lines.append(f"- 原图 MD5 重复组：{len(duplicates)}")
    lines.append(f"- 小于 1KB 的原图：{len(zero_or_tiny)}")
    if axure_boards or getattr(args, "require_axure", False):
        lines.append(f"- 旧版 Axure 拼板（兼容项）：{len(axure_boards)}")
    lines.append("")

    status = "PASS" if not issues else "FAIL"
    lines.append(f"## 检查状态：{status}")
    lines.append("")
    lines.append("文件有效≠覆盖完成。PASS 仅代表本次自动文件/引用检查通过，不证明页面语义正确、核心路径完成或 App 已被完整探索。")
    lines.append("")
    if map_mode:
        lines.extend(["## 模块覆盖记录", ""])
        modules = map_data.get("modules", []) if isinstance(map_data, dict) else []
        for module in modules if isinstance(modules, list) else []:
            if not isinstance(module, dict):
                continue
            lines.append(f"- {module.get('id', '?')} {module.get('title', '?')}: {module.get('status', 'pending')} — {module.get('reason') or '未提供覆盖说明'}")
        lines.extend(["", "默认交付关注原始截图与模块流程拼图；Word、长报告及旧版 Axure 拼板不作为默认条件。", ""])

    if flow_montages:
        lines.extend(["## 模块流程拼图", ""])
        lines.extend(f"- [{path.name}](flow_export/{path.name})" for path in flow_montages)
        lines.extend(["", "需目检同一模块的截图顺序、分支与操作标注；文件有效不代表流程关系已经核实。", ""])

    if issues:
        lines.append("## 问题")
        lines.extend(f"- {item}" for item in issues)
        lines.append("")

    if warnings:
        lines.append("## 提醒")
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")

    if missing_refs:
        lines.append("## 缺失图片引用")
        lines.extend(f"- `{ref}`" for ref in missing_refs[:50])
        if len(missing_refs) > 50:
            lines.append(f"- ... {len(missing_refs) - 50} more")
        lines.append("")

    if map_missing_refs:
        lines.extend(["## 缺失模块地图证据", ""])
        lines.extend(f"- `{ref}`" for ref in map_missing_refs[:50])
        lines.append("")

    if duplicates:
        lines.append("## 原图 MD5 重复组")
        for h, files in list(duplicates.items())[:20]:
            lines.append(f"- `{h}`")
            for file in files:
                lines.append(f"  - `{file.relative_to(root)}`")
        if len(duplicates) > 20:
            lines.append(f"- ... {len(duplicates) - 20} more groups")
        lines.append("")

    if zero_or_tiny:
        lines.append("## 可疑小尺寸原图")
        lines.extend(f"- `{p.relative_to(root)}` ({p.stat().st_size} bytes)" for p in zero_or_tiny[:50])
        lines.append("")

    lines.append("## 人工目检")
    lines.extend(
        [
            "- 核心任务路径是否走到结果页。",
            "- paywall、评分弹窗、广告触点是否记录出现时机。",
            "- 重要结论是否有截图证据。",
            "- 如要求 Word：product_summary.docx 是否生成，且图片能在 Word 内直接看到。",
            "- 双设备流程是否验证两端状态。",
            "- 最终报告是否避免暴露隐私信息。",
            "- 模块流程拼图是否按实际操作顺序排列；分支是否单独展示，没有把采集顺序误当跳转。",
            "- 截图和连接文字是否可读；缺图是否明确标记，没有用其他模块图片补位。",
        ]
    )
    if axure_boards or getattr(args, "require_axure", False):
        lines.append("- 如仍需旧版 Axure：兼容拼板是否可读，且没有其他模块图片补位。")

    out_arg = getattr(args, "out", None)
    out = Path(out_arg).resolve() if out_arg else root / "delivery_review.md"
    out.write_text("\n".join(lines), encoding="utf-8-sig")
    return {"ok": not issues, "status": status, "out": out, "issues": issues, "warnings": warnings,
            "map_missing_refs": map_missing_refs, "docx_valid": docx_valid, "map_result": map_result,
            "png_count": len(pngs), "flow_count": len(flow_montages), "flow_invalid": flow_invalid}


def main() -> None:
    # Match the UTF-8 report/path output without mutating streams on import.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Review Android screenshot delivery artifacts; validity is not coverage.")
    parser.add_argument("--input-dir", required=True, help="Screenshot output directory.")
    parser.add_argument("--summary", help="Defaults to <input-dir>/product_summary.md.")
    parser.add_argument("--research-map", help="Research map JSON. Defaults to <input-dir>/research-map.json if present.")
    parser.add_argument("--require-summary", action="store_true", help="Require a Markdown report even in map capture mode.")
    parser.add_argument("--require-flow", action="store_true", help="Fail if flow_export module flow PNGs or notes are missing/invalid.")
    parser.add_argument("--require-axure", action="store_true", help="Fail if axure_export boards are missing.")
    parser.add_argument("--require-docx", action="store_true", help="Fail if product_summary.docx is missing or invalid.")
    parser.add_argument("--out", help="Review report path. Defaults to <input-dir>/delivery_review.md.")
    result = review_delivery(parser.parse_args())
    print(result["out"])
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
