from __future__ import annotations

import atexit
import shutil
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .index import HybridIndex


SETTINGS = Settings.load()
mcp = FastMCP("product-kb", instructions="Read-only product knowledge retrieval with source traceability.")

_INDEX_LOCK = threading.RLock()
_RUNTIME_TEMP: tempfile.TemporaryDirectory[str] | None = None
_RUNTIME_INDEX: HybridIndex | None = None


def _create_runtime_index() -> HybridIndex:
    global _RUNTIME_TEMP
    canonical_qdrant = SETTINGS.index_dir / "qdrant"
    canonical_manifest = SETTINGS.index_dir / "manifest.json"
    if not canonical_qdrant.is_dir() or not canonical_manifest.is_file():
        raise RuntimeError("Index does not exist; run `product-kb index` first.")

    _RUNTIME_TEMP = tempfile.TemporaryDirectory(prefix="product-kb-mcp-")
    runtime_index_dir = Path(_RUNTIME_TEMP.name) / ".index"
    shutil.copytree(canonical_qdrant, runtime_index_dir / "qdrant")
    shutil.copy2(canonical_manifest, runtime_index_dir / "manifest.json")
    return HybridIndex(replace(SETTINGS, index_dir=runtime_index_dir))


def _runtime_index() -> HybridIndex:
    global _RUNTIME_INDEX
    if _RUNTIME_INDEX is None:
        _RUNTIME_INDEX = _create_runtime_index()
    return _RUNTIME_INDEX


def _close_runtime_index() -> None:
    global _RUNTIME_INDEX, _RUNTIME_TEMP
    if _RUNTIME_INDEX is not None:
        _RUNTIME_INDEX.close()
        _RUNTIME_INDEX = None
    if _RUNTIME_TEMP is not None:
        _RUNTIME_TEMP.cleanup()
        _RUNTIME_TEMP = None


atexit.register(_close_runtime_index)


def _with_index(callback: Any) -> Any:
    # Qdrant Local is embedded and single-writer. Each MCP process reads from a
    # private 2 MB runtime snapshot, while calls inside that process share one
    # client and a serial lock. This keeps multiple Codex tasks from competing
    # for the canonical index directory.
    with _INDEX_LOCK:
        return callback(_runtime_index())


@mcp.tool()
def kb_search(
    query: str,
    top_k: int = 8,
    product: str | None = None,
    stage: str | None = None,
    platform: str | None = None,
    region: str | None = None,
    domain: str | None = None,
    knowledge_type: str | None = None,
) -> list[dict[str, Any]]:
    """Search active knowledge using hybrid semantic and keyword retrieval."""
    filters = {
        "product": product,
        "stage": stage,
        "platform": platform,
        "region": region,
        "domain": domain,
        "type": knowledge_type,
    }
    return _with_index(lambda index: index.search(query, top_k, filters))


@mcp.tool()
def kb_get(chunk_id: str) -> dict[str, Any]:
    """Read one indexed knowledge chunk by its immutable chunk id."""
    result = _with_index(lambda index: index.get_chunk(chunk_id))
    return result or {"found": False, "chunk_id": chunk_id}


@mcp.tool()
def kb_trace(source_id: str) -> dict[str, Any]:
    """Trace a knowledge source to its path, fingerprint, metadata, and indexed chunks."""
    return _with_index(lambda index: index.trace_source(source_id))


@mcp.tool()
def kb_find_similar_cases(
    query: str,
    product: str | None = None,
    platform: str | None = None,
    region: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Find active reusable cases similar to the current product problem."""
    filters = {
        "type": "case",
        "product": product,
        "platform": platform,
        "region": region,
    }
    return _with_index(lambda index: index.search(query, top_k, filters))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
