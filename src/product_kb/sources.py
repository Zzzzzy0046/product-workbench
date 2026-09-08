from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from pypdf import PdfReader

from .chunking import chunk_markdown, chunk_pdf_pages
from .config import Settings
from .frontmatter import parse_markdown
from .models import Chunk, SourceDocument


SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _normalise_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalised = _json_safe(dict(metadata))
    for key in ("tags", "platform", "region"):
        value = normalised.get(key)
        if value is None:
            normalised[key] = []
        elif isinstance(value, str):
            normalised[key] = [value]
    normalised.setdefault("status", "active")
    normalised.setdefault("evidence_level", "unverified")
    return normalised


def _is_within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def load_external_sources(settings: Settings) -> list[SourceDocument]:
    if not settings.source_config.exists():
        return []
    config = yaml.safe_load(settings.source_config.read_text(encoding="utf-8-sig")) or {}
    roots = [Path(item).expanduser().resolve() for item in config.get("allow_roots", [])]
    sources: list[SourceDocument] = []
    for item in config.get("sources", []):
        path = Path(item["path"]).expanduser().resolve()
        if not _is_within(path, roots):
            raise ValueError(f"Source path is outside allow_roots: {path}")
        metadata = _normalise_metadata(item.get("metadata", {}))
        metadata["source_path"] = str(path)
        sources.append(
            SourceDocument(
                source_id=item["id"],
                path=path,
                metadata=metadata,
                enabled=bool(item.get("enabled", True)),
            )
        )
    return sources


def load_internal_sources(settings: Settings) -> list[SourceDocument]:
    sources: list[SourceDocument] = []
    for path in settings.knowledge_dir.rglob("*.md"):
        relative = path.relative_to(settings.knowledge_dir)
        if relative.parts and relative.parts[0] == "00_inbox":
            continue
        metadata, _ = parse_markdown(path)
        source_id = str(metadata.get("id") or f"kb:{relative.as_posix()}")
        metadata = _normalise_metadata(metadata)
        metadata["source_path"] = str(path.resolve())
        metadata.setdefault("type", "knowledge")
        sources.append(SourceDocument(source_id, path.resolve(), metadata, True))
    return sources


def discover_sources(settings: Settings) -> list[SourceDocument]:
    by_id: dict[str, SourceDocument] = {}
    for source in [*load_internal_sources(settings), *load_external_sources(settings)]:
        if source.source_id in by_id:
            raise ValueError(f"Duplicate source id: {source.source_id}")
        by_id[source.source_id] = source
    return list(by_id.values())


def source_fingerprint(source: SourceDocument) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(source.metadata, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    digest.update(b"\0")
    digest.update(source.path.read_bytes())
    return digest.hexdigest()


def extract_chunks(source: SourceDocument) -> list[Chunk]:
    suffix = source.path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported source type: {source.path}")
    title = str(source.metadata.get("title") or source.path.stem)
    if suffix == ".md":
        file_metadata, body = parse_markdown(source.path)
        metadata = _normalise_metadata({**source.metadata, **file_metadata})
        metadata["source_path"] = str(source.path)
        return chunk_markdown(source.source_id, body, title, metadata)
    if suffix == ".txt":
        body = source.path.read_text(encoding="utf-8-sig")
        return chunk_markdown(source.source_id, body, title, source.metadata)

    reader = PdfReader(str(source.path))
    pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
    return chunk_pdf_pages(source.source_id, pages, title, source.metadata)
