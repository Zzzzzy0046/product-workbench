from __future__ import annotations

import json
import re
import warnings
from pathlib import Path
from typing import Any

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models

from .config import Settings
from .models import Chunk
from .sources import discover_sources, extract_chunks, source_fingerprint


class HybridIndex:
    TYPE_BOOST = {
        "decision": 0.45,
        "method": 0.42,
        "pattern": 0.40,
        "template": 0.35,
        "case": 0.32,
        "risk": 0.32,
        "retrospective": 0.30,
        "source": 0.0,
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.index_dir.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(self.settings.index_dir / "qdrant"))
        self._dense: TextEmbedding | None = None
        self._sparse: SparseTextEmbedding | None = None

    @property
    def manifest_path(self) -> Path:
        return self.settings.index_dir / "manifest.json"

    def close(self) -> None:
        self.client.close()

    def _dense_model(self) -> TextEmbedding:
        if self._dense is None:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="The model .* now uses mean pooling instead of CLS embedding.*",
                    category=UserWarning,
                )
                self._dense = TextEmbedding(model_name=self.settings.dense_model)
        return self._dense

    def _sparse_model(self) -> SparseTextEmbedding:
        if self._sparse is None:
            self._sparse = SparseTextEmbedding(model_name=self.settings.sparse_model)
        return self._sparse

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"version": 1, "models": {}, "sources": {}}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        temp = self.manifest_path.with_suffix(".tmp")
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.manifest_path)

    def _collection_exists(self) -> bool:
        return self.client.collection_exists(self.settings.collection_name)

    def reset(self) -> None:
        if self._collection_exists():
            self.client.delete_collection(self.settings.collection_name)
        if self.manifest_path.exists():
            self.manifest_path.unlink()

    def _ensure_collection(self, dense_size: int) -> None:
        if self._collection_exists():
            return
        self.client.create_collection(
            collection_name=self.settings.collection_name,
            vectors_config={
                "dense": models.VectorParams(size=dense_size, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )

    @staticmethod
    def _sparse_vector(value: Any) -> models.SparseVector:
        return models.SparseVector(
            indices=value.indices.tolist(),
            values=value.values.tolist(),
        )

    def _upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        texts = [chunk.text for chunk in chunks]
        dense_vectors = list(self._dense_model().embed(texts))
        sparse_vectors = list(self._sparse_model().embed(texts))
        if not dense_vectors:
            return
        self._ensure_collection(len(dense_vectors[0]))
        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector={
                    "dense": dense.tolist(),
                    "sparse": self._sparse_vector(sparse),
                },
                payload=chunk.payload(),
            )
            for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors, strict=True)
        ]
        self.client.upsert(
            collection_name=self.settings.collection_name,
            points=points,
            wait=True,
        )

    def _delete_points(self, point_ids: list[str]) -> None:
        if not point_ids or not self._collection_exists():
            return
        self.client.delete(
            collection_name=self.settings.collection_name,
            points_selector=models.PointIdsList(points=point_ids),
            wait=True,
        )

    def build(self, reset: bool = False) -> dict[str, Any]:
        if reset:
            self.reset()
        manifest = self._load_manifest()
        model_settings = {
            "dense": self.settings.dense_model,
            "sparse": self.settings.sparse_model,
        }
        if manifest.get("models") not in ({}, model_settings):
            raise RuntimeError("Embedding model changed; run `product-kb index --reset`.")

        sources = {source.source_id: source for source in discover_sources(self.settings) if source.enabled}
        previous = manifest.get("sources", {})
        report: dict[str, Any] = {
            "indexed_sources": 0,
            "skipped_sources": 0,
            "removed_sources": 0,
            "indexed_chunks": 0,
            "errors": [],
        }

        removed_ids = set(previous) - set(sources)
        for source_id in sorted(removed_ids):
            self._delete_points(previous[source_id].get("chunk_ids", []))
            previous.pop(source_id, None)
            report["removed_sources"] += 1

        for source_id, source in sorted(sources.items()):
            if not source.path.exists() or not source.path.is_file():
                report["errors"].append({"source_id": source_id, "error": "source file missing"})
                continue
            try:
                fingerprint = source_fingerprint(source)
                old = previous.get(source_id)
                if old and old.get("fingerprint") == fingerprint:
                    report["skipped_sources"] += 1
                    continue
                chunks = extract_chunks(source)
                if not chunks:
                    report["errors"].append({"source_id": source_id, "error": "no extractable text"})
                    continue
                if old:
                    self._delete_points(old.get("chunk_ids", []))
                self._upsert_chunks(chunks)
                previous[source_id] = {
                    "fingerprint": fingerprint,
                    "path": str(source.path),
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                    "metadata": source.metadata,
                }
                report["indexed_sources"] += 1
                report["indexed_chunks"] += len(chunks)
            except Exception as exc:  # keep other sources indexable and report the exact source
                report["errors"].append({"source_id": source_id, "error": str(exc)})

        manifest = {"version": 1, "models": model_settings, "sources": previous}
        self._write_manifest(manifest)
        report["total_sources"] = len(previous)
        report["total_chunks"] = sum(len(item.get("chunk_ids", [])) for item in previous.values())
        return report

    def _filter(self, filters: dict[str, Any] | None = None) -> models.Filter:
        conditions: list[models.FieldCondition] = [
            models.FieldCondition(key="status", match=models.MatchValue(value="active"))
        ]
        for key, value in (filters or {}).items():
            if value in (None, "", []):
                continue
            values = value if isinstance(value, list) else [value]
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchAny(any=values))
            )
        return models.Filter(must=conditions)

    @staticmethod
    def _terms(text: str) -> set[str]:
        lowered = text.lower()
        terms = {
            token
            for token in re.findall(r"[a-z0-9_+./-]{2,}", lowered)
            if token not in {"the", "and", "for", "with"}
        }
        for sequence in re.findall(r"[\u3400-\u9fff]+", lowered):
            if len(sequence) <= 4:
                terms.add(sequence)
            for width in (2, 3, 4):
                terms.update(sequence[index : index + width] for index in range(len(sequence) - width + 1))
        return terms

    def _rerank(self, query: str, points: list[Any], top_k: int) -> list[dict[str, Any]]:
        query_terms = self._terms(query)
        ranked: list[dict[str, Any]] = []
        for point in points:
            payload = point.payload or {}
            text = str(payload.get("text", ""))
            metadata_text = " ".join(
                [
                    str(payload.get("title", "")),
                    str(payload.get("locator", "")),
                    str(payload.get("source_id", "")),
                    " ".join(str(item) for item in payload.get("tags", [])),
                ]
            )
            body_terms = self._terms(text)
            metadata_terms = self._terms(metadata_text)
            body_coverage = len(query_terms & body_terms) / max(len(query_terms), 1)
            metadata_coverage = len(query_terms & metadata_terms) / max(len(query_terms), 1)
            type_boost = self.TYPE_BOOST.get(str(payload.get("type", "")), 0.05)
            if body_coverage < 0.08 and metadata_coverage < 0.05:
                type_boost *= 0.2
            retrieval_score = float(getattr(point, "score", 0.0) or 0.0)
            adjusted = retrieval_score + (0.30 * body_coverage) + (0.20 * metadata_coverage) + type_boost
            ranked.append(
                {
                    "score": round(adjusted, 8),
                    "retrieval_score": retrieval_score,
                    "chunk_id": str(point.id),
                    **payload,
                }
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)

        diversified: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for item in ranked:
            source_id = str(item.get("source_id", ""))
            if counts.get(source_id, 0) >= 2:
                continue
            diversified.append(item)
            counts[source_id] = counts.get(source_id, 0) + 1
            if len(diversified) >= top_k:
                break
        return diversified

    def _curated_points(self) -> list[Any]:
        points: list[Any] = []
        offset: Any = None
        while True:
            batch, offset = self.client.scroll(
                collection_name=self.settings.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="status", match=models.MatchValue(value="active")
                        )
                    ],
                    must_not=[
                        models.FieldCondition(
                            key="type", match=models.MatchValue(value="source")
                        )
                    ],
                ),
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points.extend(batch)
            if offset is None:
                break
        return points

    def search(
        self,
        query: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        if not self._collection_exists():
            raise RuntimeError("Index does not exist; run `product-kb index` first.")
        dense = next(self._dense_model().query_embed(query))
        sparse = next(self._sparse_model().query_embed(query))
        candidate_limit = max(top_k * 12, 60)
        response = self.client.query_points(
            collection_name=self.settings.collection_name,
            prefetch=[
                models.Prefetch(query=dense.tolist(), using="dense", limit=candidate_limit),
                models.Prefetch(
                    query=self._sparse_vector(sparse),
                    using="sparse",
                    limit=candidate_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=self._filter(filters),
            limit=candidate_limit,
            with_payload=True,
        )
        combined: dict[str, Any] = {str(point.id): point for point in response.points}
        for point in self._curated_points():
            combined.setdefault(str(point.id), point)
        return self._rerank(query, list(combined.values()), max(1, min(top_k, 50)))

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        if not self._collection_exists():
            return None
        points = self.client.retrieve(
            collection_name=self.settings.collection_name,
            ids=[chunk_id],
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return None
        return {"chunk_id": str(points[0].id), **(points[0].payload or {})}

    def trace_source(self, source_id: str, limit: int = 20) -> dict[str, Any]:
        manifest = self._load_manifest()
        source = manifest.get("sources", {}).get(source_id)
        if source is None:
            return {"source_id": source_id, "found": False}
        points, _ = self.client.scroll(
            collection_name=self.settings.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_id", match=models.MatchValue(value=source_id)
                    )
                ]
            ),
            limit=max(1, min(limit, 100)),
            with_payload=True,
            with_vectors=False,
        )
        return {
            "source_id": source_id,
            "found": True,
            "path": source.get("path"),
            "fingerprint": source.get("fingerprint"),
            "metadata": source.get("metadata", {}),
            "chunks": [
                {
                    "chunk_id": str(point.id),
                    "title": (point.payload or {}).get("title"),
                    "locator": (point.payload or {}).get("locator"),
                }
                for point in points
            ],
        }
