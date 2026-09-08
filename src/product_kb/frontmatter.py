from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class FrontmatterError(ValueError):
    pass


def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        raise FrontmatterError(f"Unclosed YAML frontmatter: {path}")

    raw = "\n".join(lines[1:closing])
    metadata = yaml.safe_load(raw) or {}
    if not isinstance(metadata, dict):
        raise FrontmatterError(f"Frontmatter must be a mapping: {path}")
    return metadata, "\n".join(lines[closing + 1 :]).strip()
