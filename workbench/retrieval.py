"""Hybrid retrieval for the local product workbench.

The global Product KB remains a read-only canonical index. Project material is
indexed separately so private project evidence cannot leak into global
knowledge or into another project. The composite retriever keeps the existing
keyword path as a safe fallback while the local embedding model is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from product_kb.chunking import chunk_markdown
from product_kb.config import Settings
from product_kb.index import HybridIndex


class ProjectHybridIndex(HybridIndex):
    """A Qdrant Local index owned by the workbench for project evidence."""

    COLLECTION = "workbench_project_documents"

    def __init__(self, data_dir: Path, root: Path | None = None):
        settings = Settings.load(root)
        project_index_dir = (data_dir / "index").resolve()
        super().__init__(replace(settings, index_dir=project_index_dir, collection_name=self.COLLECTION))
        self.project_index_dir = project_index_dir
        self.project_manifest_path = project_index_dir / "project-manifest.json"
        self.lock = threading.RLock()

    def _load_project_manifest(self) -> dict[str, Any]:
        if not self.project_manifest_path.exists():
            return {"version": 1, "models": {}, "documents": {}}
        try:
            value = json.loads(self.project_manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"version": 1, "models": {}, "documents": {}}
        return value if isinstance(value, dict) and isinstance(value.get("documents"), dict) else {"version": 1, "models": {}, "documents": {}}

    def _write_project_manifest(self, manifest: dict[str, Any]) -> None:
        temporary = self.project_manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.project_manifest_path)

    def _delete_document_points(self, point_ids: Iterable[str]) -> None:
        self._delete_points([str(point_id) for point_id in point_ids])

    @staticmethod
    def _document_fingerprint(document: dict[str, Any]) -> str:
        digest = hashlib.sha256()
        for value in (document.get("id"), document.get("name"), document.get("kind"), document.get("text")):
            digest.update(str(value or "").encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    def sync_project(self, project_id: str, documents: list[dict[str, Any]]) -> dict[str, int]:
        """Incrementally index eligible documents for one project.

        ``documents`` are already project-scoped by Workbench. Only uploads
        and accepted deliverables are eligible for default retrieval.
        """
        eligible = {
            str(document["id"]): document
            for document in documents
            if document.get("kind") in {"upload", "accepted"}
        }
        with self.lock:
            manifest = self._load_project_manifest()
            model_settings = {
                "dense": self.settings.dense_model,
                "sparse": self.settings.sparse_model,
            }
            if manifest.get("models") not in ({}, model_settings):
                raise RuntimeError("Project embedding model changed; rebuild the project index.")
            manifest["models"] = model_settings
            stored = manifest["documents"]
            prefix = f"{project_id}:"
            current_keys = {key for key in stored if key.startswith(prefix)}
            indexed = skipped = removed = 0

            for key in sorted(current_keys - {f"{prefix}{document_id}" for document_id in eligible}):
                self._delete_document_points(stored[key].get("chunk_ids", []))
                stored.pop(key, None)
                removed += 1

            for document_id, document in sorted(eligible.items()):
                key = f"{project_id}:{document_id}"
                fingerprint = self._document_fingerprint(document)
                previous = stored.get(key)
                if previous and previous.get("fingerprint") == fingerprint:
                    skipped += 1
                    continue
                if previous:
                    self._delete_document_points(previous.get("chunk_ids", []))

                source_chunks = chunk_markdown(
                    f"{project_id}:{document_id}",
                    str(document.get("text") or ""),
                    str(document.get("name") or document_id),
                    {
                        "scope": "project",
                        "project_id": project_id,
                        "document_id": document_id,
                        "document_kind": document.get("kind", "upload"),
                        "document_version": 1,
                        "review_state": "accepted" if document.get("kind") == "accepted" else "unreviewed",
                        "type": "project-document",
                        "status": "active",
                        "evidence_level": "project-input",
                        "created_at": document.get("created", ""),
                        "fingerprint": document.get("sha") or fingerprint,
                        "source_path": str(document.get("name") or ""),
                    },
                )
                for number, chunk in enumerate(source_chunks, 1):
                    chunk.metadata["chunk"] = number
                self._upsert_chunks(source_chunks)
                stored[key] = {
                    "project_id": project_id,
                    "document_id": document_id,
                    "fingerprint": fingerprint,
                    "chunk_ids": [chunk.chunk_id for chunk in source_chunks],
                }
                indexed += 1

            self._write_project_manifest(manifest)
            return {"indexed": indexed, "skipped": skipped, "removed": removed}

    def remove_project(self, project_id: str) -> int:
        with self.lock:
            manifest = self._load_project_manifest()
            stored = manifest["documents"]
            keys = [key for key in stored if key.startswith(f"{project_id}:")]
            for key in keys:
                self._delete_document_points(stored[key].get("chunk_ids", []))
                stored.pop(key, None)
            self._write_project_manifest(manifest)
            return len(keys)

    def search_project(self, project_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
        if not self._collection_exists():
            return []
        return self.search(query, top_k, {"scope": "project", "project_id": project_id})

    def status(self) -> dict[str, Any]:
        manifest = self._load_project_manifest()
        documents = manifest.get("documents", {})
        return {
            "index": self.project_manifest_path.is_file(),
            "sources": len(documents),
            "chunks": sum(len(item.get("chunk_ids", [])) for item in documents.values()),
            "updated_at": self.project_manifest_path.stat().st_mtime if self.project_manifest_path.is_file() else None,
            "models": manifest.get("models", {}),
        }


class CompositeRetriever:
    """Combine project evidence and global knowledge with safe fallbacks."""

    def __init__(self, data_dir: Path, root: Path | None = None):
        self.data_dir = Path(data_dir).resolve()
        self.root = Path(root or self.data_dir).resolve()
        self.project_index = ProjectHybridIndex(self.data_dir, self.root)
        self.global_index: HybridIndex | None = None
        self.lock = threading.RLock()
        settings = Settings.load(self.root)
        if (settings.index_dir / "qdrant").is_dir() and (settings.index_dir / "manifest.json").is_file():
            self.global_index = HybridIndex(settings)

    def close(self) -> None:
        with self.lock:
            self.project_index.close()
            if self.global_index is not None:
                self.global_index.close()

    def remove_project(self, project_id: str) -> int:
        """Remove every vector and manifest entry owned by one project."""
        with self.lock:
            return self.project_index.remove_project(project_id)

    @property
    def global_available(self) -> bool:
        return self.global_index is not None

    def status(self) -> dict[str, Any]:
        project = self.project_index.status()
        global_stats: dict[str, Any] = {
            "index": False,
            "sources": 0,
            "chunks": 0,
            "updated_at": None,
            "models": {},
        }
        if self.global_index is not None:
            manifest = self.global_index._load_manifest()
            global_stats = {
                "index": True,
                "sources": len(manifest.get("sources", {})),
                "chunks": sum(len(item.get("chunk_ids", [])) for item in manifest.get("sources", {}).values()),
                "updated_at": self.global_index.manifest_path.stat().st_mtime if self.global_index.manifest_path.is_file() else None,
                "models": manifest.get("models", {}),
            }
        return {
            "mode": "hybrid",
            "global_index": self.global_available,
            "project_index": project["index"],
            "global": global_stats,
            "project": project,
        }

    @staticmethod
    def _project_result(result: dict[str, Any]) -> dict[str, Any]:
        value = dict(result)
        # The vector source id is project-scoped to prevent collisions. The
        # workbench-facing source id remains the original document id so
        # pinning, image lookup and citation lineage continue to work.
        value["source_id"] = value.get("document_id") or value.get("source_id", "")
        value["kind"] = value.get("document_kind", "upload")
        value["name"] = value.get("title") or value.get("name") or value.get("document_id", "项目资料")
        value["location"] = value.get("source_path") or value.get("name", "")
        value["chunk"] = value.get("chunk", 1)
        return value

    @staticmethod
    def _global_result(result: dict[str, Any]) -> dict[str, Any]:
        value = dict(result)
        value["kind"] = "knowledge"
        value["name"] = value.get("title") or value.get("source_id", "知识条目")
        value["location"] = value.get("source_path") or value.get("locator") or value["name"]
        value["chunk"] = value.get("chunk", value.get("locator", 1))
        return value

    def search(
        self,
        project_id: str,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        with self.lock:
            self.project_index.sync_project(project_id, documents)
            project_budget = max(1, top_k // 2)
            project_results = [
                self._project_result(item)
                for item in self.project_index.search_project(project_id, query, max(project_budget * 3, 6))
            ]
            global_results: list[dict[str, Any]] = []
            if self.global_index is not None:
                global_results = [
                    self._global_result(item)
                    for item in self.global_index.search(query, max(top_k * 3, 8))
                ]

            result: list[dict[str, Any]] = []
            seen: set[tuple[str, str, str]] = set()

            def add(items: list[dict[str, Any]], limit: int | None = None) -> None:
                for item in items:
                    key = (
                        str(item.get("source_id", "")),
                        str(item.get("locator", item.get("chunk", ""))),
                        str(item.get("text", "")),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append(item)
                    if limit is not None and len(result) >= limit:
                        return

            add(project_results, project_budget)
            add(global_results, top_k)
            add(project_results, top_k)
            return result[:top_k]


def public_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove retrieval internals before sources reach the browser or prompt."""
    allowed = {
        "source_id",
        "name",
        "kind",
        "location",
        "chunk",
        "text",
        "truncated",
        "citation",
        "image_path",
        "draft",
    }
    return [{key: value for key, value in source.items() if key in allowed} for source in sources]
