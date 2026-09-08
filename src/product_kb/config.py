from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    knowledge_dir: Path
    source_config: Path
    index_dir: Path
    collection_name: str
    dense_model: str
    sparse_model: str

    @classmethod
    def load(cls, root: Path | None = None) -> "Settings":
        resolved_root = (root or Path(os.environ.get("PRODUCT_KB_ROOT", Path.cwd()))).resolve()
        local_source_config = resolved_root / "config" / "sources.yaml"
        example_source_config = resolved_root / "config" / "sources.example.yaml"
        return cls(
            root=resolved_root,
            knowledge_dir=resolved_root / "knowledge",
            source_config=(
                local_source_config if local_source_config.exists() else example_source_config
            ),
            index_dir=resolved_root / ".index",
            collection_name=os.environ.get("PRODUCT_KB_COLLECTION", "product_kb"),
            dense_model=os.environ.get(
                "PRODUCT_KB_DENSE_MODEL",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            ),
            sparse_model=os.environ.get("PRODUCT_KB_SPARSE_MODEL", "Qdrant/bm25"),
        )
