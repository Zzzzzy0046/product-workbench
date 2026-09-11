import threading

from workbench.retrieval import CompositeRetriever, public_sources


class FakeProjectIndex:
    def sync_project(self, project_id, documents):
        self.synced = (project_id, documents)

    def search_project(self, project_id, query, top_k):
        return [
            {
                "source_id": "project-doc",
                "document_kind": "upload",
                "title": "项目资料",
                "source_path": "项目资料.txt",
                "locator": "项目资料.txt",
                "chunk": 1,
                "text": "当前项目事实",
            }
        ]


class FakeGlobalIndex:
    def search(self, query, top_k):
        return [
            {
                "source_id": "knowledge-method",
                "title": "方法知识",
                "locator": "knowledge/method.md",
                "text": "可复用方法",
            }
        ]


def test_composite_retriever_prioritizes_project_evidence():
    retriever = CompositeRetriever.__new__(CompositeRetriever)
    retriever.project_index = FakeProjectIndex()
    retriever.global_index = FakeGlobalIndex()
    retriever.lock = threading.RLock()

    results = retriever.search("project-a", "当前问题", [], top_k=4)

    assert [result["source_id"] for result in results] == [
        "project-doc",
        "knowledge-method",
    ]
    assert results[0]["kind"] == "upload"
    assert results[1]["kind"] == "knowledge"


def test_public_sources_remove_internal_retrieval_metadata():
    result = public_sources(
        [
            {
                "source_id": "doc",
                "name": "资料",
                "kind": "upload",
                "location": "资料.txt",
                "chunk": 1,
                "text": "内容",
                "score": 0.91,
                "retrieval_score": 0.82,
                "chunk_id": "secret-vector-id",
                "project_id": "private-project",
            }
        ]
    )

    assert result == [
        {
            "source_id": "doc",
            "name": "资料",
            "kind": "upload",
            "location": "资料.txt",
            "chunk": 1,
            "text": "内容",
        }
    ]


def test_project_result_restores_workbench_document_id():
    result = CompositeRetriever._project_result(
        {
            "source_id": "project-a:document-a",
            "document_id": "document-a",
            "document_kind": "upload",
            "title": "截图证据",
            "source_path": "evidence.png",
            "text": "截图内容",
        }
    )

    assert result["source_id"] == "document-a"
    assert result["kind"] == "upload"
