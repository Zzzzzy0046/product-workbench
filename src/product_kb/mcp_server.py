from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .index import HybridIndex


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = Settings.load(PROJECT_ROOT)
mcp = FastMCP("product-kb", instructions="Read-only product knowledge retrieval with source traceability.")


def _with_index(callback: Any) -> Any:
    index = HybridIndex(SETTINGS)
    try:
        return callback(index)
    finally:
        index.close()


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
