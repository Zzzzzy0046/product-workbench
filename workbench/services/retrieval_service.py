"""Project retrieval, Product KB access and keyword fallback."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class RetrievalService(BoundService):
    def __init__(self, workbench):
        super().__init__(workbench)
        object.__setattr__(self, "_knowledge_cache", None)

    def knowledge(self):
        """Active knowledge cards; parsing is cached by file mtime/size."""
        from product_kb.frontmatter import parse_markdown
        paths = [path for path in sorted((ROOT / "knowledge").rglob("*.md")) if "00_inbox" not in path.parts]
        signature = []
        for path in paths:
            try:
                stat = path.stat()
            except OSError:
                continue
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        signature = tuple(signature)
        cached = self._knowledge_cache
        if cached and cached[0] == signature:
            return [dict(item) for item in cached[1]]
        result = []
        for path in paths:
            meta, text = parse_markdown(path)
            if meta.get("status") != "active":
                continue
            result.append({"id":meta.get("id", path.stem),"name":path.stem,"text":text,"path":str(path.relative_to(ROOT)),"kind":"knowledge"})
        object.__setattr__(self, "_knowledge_cache", (signature, [dict(item) for item in result]))
        return result

    def _keyword_search(self, project_id, query, limit=8):
        self.project(project_id)
        if not query.strip():
            return []
        words = tokens(query)
        candidates = []
        docs = self.rows("SELECT id,name,text,kind FROM documents WHERE project_id=?", (project_id,))
        # Draft generations are not retrieved automatically. They may be pinned
        # explicitly and are then carried with a prominent draft warning.
        for doc in [d for d in docs if d['kind'] in {'upload','accepted'}] + self.knowledge():
            for number, text in enumerate(chunks(doc["text"]), 1):
                matched = words & tokens(doc["name"] + " " + text)
                if not matched:
                    continue
                score = sum(1.5 if len(w)>2 else 1 for w in matched) / math.sqrt(max(1,len(words)))
                candidate = {"source_id":doc["id"],"name":doc["name"],"kind":doc["kind"],"location":doc.get("path",doc["name"]),"chunk":number,"text":text,"score":round(score,3)}
                if doc["kind"] == "upload" and Path(doc["name"]).suffix.lower() in IMAGE_SUFFIXES:
                    image_path = self.upload_path(project_id, doc["id"], doc["name"])
                    if image_path.is_file():
                        candidate["image_path"] = str(image_path)
                candidates.append(candidate)
        candidates.sort(key=lambda c:c["score"], reverse=True)
        # Reserve room for project evidence as well as reusable methods.
        project_hits = [c for c in candidates if c["kind"] != "knowledge"][:max(1,limit//2)]
        rest = [c for c in candidates if c not in project_hits]
        return (project_hits + rest)[:limit]

    def _hybrid(self):
        with self.lock:
            if self.retriever is None:
                try:
                    from workbench.retrieval import CompositeRetriever
                except ModuleNotFoundError:
                    from retrieval import CompositeRetriever
                self.retriever = CompositeRetriever(self.data, ROOT)
            return self.retriever

    def _with_image_paths(self, project_id, sources):
        for source in sources:
            if source.get("kind") != "upload" or Path(source.get("name", "")).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            image_path = self.upload_path(project_id, source.get("source_id", ""), source.get("name", ""))
            if image_path.is_file():
                source["image_path"] = str(image_path)
        return sources

    def retrieval_status(self):
        if self.retrieval_mode == "keyword":
            return {
                "mode": "keyword",
                "retrieval": "关键词片段检索（测试或手动回退模式）",
                "hybrid_available": False,
                "global_index": False,
                "project_index": False,
                "fallback": False,
            }
        try:
            status = self._hybrid().status()
            return {
                **status,
                "mode": self.retrieval_mode,
                "retrieval": "Hybrid RAG：项目证据优先 + 全局方法知识补充"
                + ("（上次检索异常，已回退关键词）" if self.retrieval_error else ""),
                "hybrid_available": True,
                "fallback": bool(self.retrieval_error),
            }
        except Exception as exc:
            self.retrieval_error = str(exc)[:300]
            return {
                "mode": self.retrieval_mode,
                "retrieval": "关键词片段检索（Hybrid RAG 当前不可用，已自动回退）",
                "hybrid_available": False,
                "global_index": False,
                "project_index": False,
                "fallback": True,
            }

    def search(self, project_id, query, limit=8):
        self.project(project_id)
        query = str(query)
        if not query.strip():
            return []
        if self.retrieval_mode in {"hybrid", "shadow"}:
            documents = self.rows(
                "SELECT id,name,text,kind,sha,created FROM documents WHERE project_id=?",
                (project_id,),
            )
            try:
                from workbench.retrieval import public_sources
            except ModuleNotFoundError:
                from retrieval import public_sources
            try:
                hybrid_sources = public_sources(
                    self._hybrid().search(project_id, query, documents, limit)
                )
                self.retrieval_error = ""
                if self.retrieval_mode == "hybrid" and hybrid_sources:
                    return self._with_image_paths(project_id, hybrid_sources)
            except Exception as exc:
                self.retrieval_error = str(exc)[:300]
        return self._with_image_paths(
            project_id,
            self._keyword_search(project_id, query, limit),
        )

    def _remove_project_index(self, project_id):
        manifest = self.data / "index" / "project-manifest.json"
        if self.retriever is None and not manifest.is_file():
            return 0
        try:
            removed = self._hybrid().remove_project(project_id)
            self.retrieval_error = ""
            return removed
        except Exception as exc:
            # Project deletion must remain recoverable even if a local vector
            # index is temporarily locked. A stale entry remains isolated by
            # project_id and is removed on the next successful cleanup.
            self.retrieval_error = str(exc)[:300]
            return 0
