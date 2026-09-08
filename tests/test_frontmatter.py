from pathlib import Path

import pytest

from product_kb.frontmatter import FrontmatterError, parse_markdown


def test_parse_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "entry.md"
    path.write_text("---\nid: test-entry\ntags: [a, b]\n---\n# 正文\n内容", encoding="utf-8")
    metadata, body = parse_markdown(path)
    assert metadata["id"] == "test-entry"
    assert metadata["tags"] == ["a", "b"]
    assert body.startswith("# 正文")


def test_unclosed_frontmatter_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.md"
    path.write_text("---\nid: broken\n# 正文", encoding="utf-8")
    with pytest.raises(FrontmatterError):
        parse_markdown(path)
