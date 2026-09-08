from pathlib import Path

import pytest

from product_kb.config import Settings
from product_kb.sources import (
    _normalise_metadata,
    discover_sources,
    extract_chunks,
    load_external_sources,
)


def test_internal_sources_have_unique_ids() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = discover_sources(Settings.load(root))
    ids = [source.source_id for source in sources]
    assert len(ids) == len(set(ids))
    assert "method-source-authority" in ids
    assert "case-heart-rate-template-evolution" in ids


def test_internal_markdown_can_be_chunked() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = discover_sources(Settings.load(root))
    source = next(item for item in sources if item.source_id == "method-new-product-analysis")
    chunks = extract_chunks(source)
    assert chunks
    assert all(chunk.source_id == source.source_id for chunk in chunks)


def test_external_path_must_be_allowlisted(tmp_path: Path) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text(
        "version: 1\nallow_roots:\n  - 'C:\\\\safe'\nsources:\n"
        "  - id: bad\n    path: 'C:\\\\outside\\\\file.md'\n    metadata: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="outside allow_roots"):
        load_external_sources(Settings.load(tmp_path))


def test_yaml_dates_are_json_safe() -> None:
    import datetime

    metadata = _normalise_metadata({"reviewed_at": datetime.date(2026, 9, 8)})
    assert metadata["reviewed_at"] == "2026-09-08"


def test_source_config_falls_back_to_example(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    example = tmp_path / "config" / "sources.example.yaml"
    example.write_text("version: 1\nallow_roots: []\nsources: []\n", encoding="utf-8")

    settings = Settings.load(tmp_path)

    assert settings.source_config == example
    assert load_external_sources(settings) == []
