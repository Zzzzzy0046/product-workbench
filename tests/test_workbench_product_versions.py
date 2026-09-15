"""Product-version routing, workflow presets and portability."""

import io
import json
import zipfile
from pathlib import Path

from workbench import app


def test_fast_state_exposes_light_daily_workflows(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("个人 PM 工作台", "验证四个工作入口")
        state = bench.state(project["id"])
        assert [item["id"] for item in state["workflows"]] == [
            "new-product", "version-iteration", "competitor-research", "version-review",
        ]
        new_product = state["workflows"][0]
        assert [step["task"] for step in new_product["steps"]] == [
            "fast/new-product-analysis", "fast/core-prd", "fast/tracking-spec", "fast/acceptance",
        ]
        assert new_product["steps"][2]["optional"] is True
        core_prd = bench.task("fast/core-prd")
        assert core_prd["recommended_upstream_any"] == [
            "fast/new-product-analysis", "fast/version-brief",
        ]
    finally:
        bench.close()


def test_full_mode_keeps_task_view_without_fast_presets(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("完整研究", "", workflow_mode="full")
        assert bench.state(project["id"])["workflows"] == []
    finally:
        bench.close()


def test_task_knowledge_allowlist_keeps_project_evidence(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("竞品工作流", "只验证知识路由")
        evidence = bench.add_document(project["id"], "竞品说明.txt", "竞品 A 有再次尝试入口。".encode())

        class FakeRetriever:
            def search(self, *args, **kwargs):
                return [
                    {"source_id": "irrelevant-runtime-playbook", "name": "运行时说明", "kind": "knowledge", "location": "playbook.md", "chunk": 1, "text": "无关内容"},
                    {"source_id": evidence["id"], "name": "竞品说明.txt", "kind": "upload", "location": "竞品说明.txt", "chunk": 1, "text": "竞品 A 有再次尝试入口。"},
                    {"source_id": "external-opos-03-templates-competitor-analysis-template-c-end-overseas", "name": "竞品分析模板", "kind": "knowledge", "location": "template.md", "chunk": 1, "text": "横向比较方法。"},
                    {"source_id": "external-opos-03-templates-prd-template-c-end-overseas", "name": "PRD 模板", "kind": "knowledge", "location": "prd.md", "chunk": 1, "text": "不应进入。"},
                ]

            def close(self):
                pass

        bench.retrieval_mode = "hybrid"
        bench.retriever = FakeRetriever()
        job = bench.prepare(project["id"], "fast/competitor-analysis", "")
        source_ids = {source["source_id"] for source in job["sources"]}
        assert evidence["id"] in source_ids
        assert "external-opos-03-templates-competitor-analysis-template-c-end-overseas" in source_ids
        assert "external-opos-03-templates-prd-template-c-end-overseas" not in source_ids
        assert "irrelevant-runtime-playbook" not in source_ids
        baseline = bench.prepare(project["id"], "fast/product-baseline", "")
        assert {source["source_id"] for source in baseline["sources"]} == {evidence["id"]}
    finally:
        bench.close()


def test_selected_product_version_isolates_automatic_evidence(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("版本隔离", "")
        v1 = bench.create_product_version(project["id"], {"name": "V1"})
        v2 = bench.create_product_version(project["id"], {"name": "V2"})
        global_doc = bench.add_document(project["id"], "产品级.txt", "产品长期背景".encode())
        v1_doc = bench.add_document(project["id"], "V1.txt", "V1 需求".encode(), v1["id"])
        v2_doc = bench.add_document(project["id"], "V2.txt", "V2 需求".encode(), v2["id"])

        class FakeRetriever:
            def search(self, *args, **kwargs):
                docs = [global_doc, v1_doc, v2_doc]
                return [
                    {"source_id": item["id"], "name": item["name"], "kind": "upload", "location": item["name"], "chunk": 1, "text": item["name"]}
                    for item in docs
                ]

            def close(self):
                pass

        bench.retrieval_mode = "hybrid"
        bench.retriever = FakeRetriever()
        job = bench.prepare(project["id"], "fast/version-brief", "", version_id=v1["id"])
        source_ids = {source["source_id"] for source in job["sources"]}
        assert global_doc["id"] in source_ids
        assert v1_doc["id"] in source_ids
        assert v2_doc["id"] not in source_ids
        product_job = bench.prepare(project["id"], "fast/version-brief", "")
        product_source_ids = {source["source_id"] for source in product_job["sources"]}
        assert product_source_ids == {global_doc["id"]}
    finally:
        bench.close()


def test_product_version_survives_project_copy_and_trash_restore(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("版本链路", "一个项目代表一个产品。")
        version = bench.create_product_version(project["id"], {
            "name": "V1.2.0", "version_type": "feature", "status": "planning",
            "goal": "验证版本链路", "target_date": "2026-09-20",
        })
        evidence = bench.add_document(project["id"], "版本证据.md", "版本证据内容。".encode(), version["id"])
        job = bench.prepare(project["id"], "fast/version-brief", "整理增量版本", [evidence["id"]], version["id"])
        bench.complete(job["id"], "# 版本简报\n\n" + "这是用于验证的完整版本交付内容。" * 8, "imported")
        state = bench.state(project["id"])
        assert state["versions"][0]["job_count"] == 1
        assert state["versions"][0]["document_count"] == 2
        assert state["jobs"][0]["version_name"] == "V1.2.0"

        package, _ = bench.export_project(project["id"])
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            exported = json.loads(archive.read("data.json"))
        assert exported["schema_version"] == 2
        assert len(exported["product_versions"]) == 1
        assert len(exported["version_documents"]) == 2
        copied = bench.import_project(package)
        copied_state = bench.state(copied["id"])
        assert copied_state["versions"][0]["name"] == "V1.2.0"
        assert copied_state["jobs"][0]["version_id"] == copied_state["versions"][0]["id"]

        deleted = bench.delete_project(project["id"], "版本链路")
        restored = bench.restore_project(Path(deleted["backup"]).name)
        restored_state = bench.state(restored["id"])
        assert restored_state["versions"][0]["id"] == version["id"]
        assert restored_state["documents"][0]["versions"][0]["name"] == "V1.2.0"
    finally:
        bench.close()
