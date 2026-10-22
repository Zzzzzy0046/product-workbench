"""Selected evidence stays an explicit, project/version-scoped input snapshot."""

import copy
import json

import pytest

from workbench import app


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path, runner=lambda _: "unused")
    instance.retrieval_mode = "keyword"
    yield instance
    instance.close()


def dossier(bench, project_id, app_id="com.example.primary"):
    return bench.competitor_service.upsert(project_id, {
        "platform": "google_play", "app_id": app_id, "title": "Selected competitor",
    })


def no_automatic_search(*args, **kwargs):
    raise AssertionError("Explicit evidence must not call automatic RAG search")


def test_explicit_selection_only_includes_checked_documents(bench, monkeypatch):
    project = bench.create_project("明确选择输入", "只分析当前勾选的资料")
    selected = dossier(bench, project["id"])
    other = dossier(bench, project["id"], "com.example.other")
    checked = bench.add_document(project["id"], "已勾选资料.md", "本次明确采用的商店原文。".encode())
    unchecked = bench.add_document(project["id"], "同竞品未勾选.md", "UNCHECKED_SAME_COMPETITOR".encode())
    excluded = bench.add_document(project["id"], "其他竞品.md", "UNSELECTED_COMPETITOR".encode())
    common = bench.add_document(project["id"], "通用参考.md", "本轮明确选择的通用研究资料。".encode())
    bench.competitor_service.attach_documents(project["id"], selected["id"], [checked["id"], unchecked["id"]])
    bench.competitor_service.attach_documents(project["id"], other["id"], [excluded["id"]])
    monkeypatch.setattr(bench, "search", no_automatic_search)
    job = bench.prepare(project["id"], "fast/competitor-analysis", "按勾选内容进行比较", [checked["id"], common["id"]],
                        source_selection_mode="explicit", competitor_ids=[selected["id"]])
    assert {item["source_id"] for item in job["sources"]} == {checked["id"], common["id"]}
    assert "UNCHECKED_SAME_COMPETITOR" not in job["prompt"]
    assert "UNSELECTED_COMPETITOR" not in job["prompt"]
    record = json.loads((bench.data / "runs" / job["id"] / "执行记录.json").read_text(encoding="utf-8"))
    assert record["source_selection_mode"] == "explicit"
    assert record["selected_document_ids"] == [checked["id"], common["id"]]
    assert record["selected_competitor_ids"] == [selected["id"]]


def test_new_upload_and_dossier_changes_do_not_rewrite_prepared_snapshot(bench, monkeypatch):
    project = bench.create_project("来源快照不变", "")
    competitor = dossier(bench, project["id"])
    original = bench.add_document(project["id"], "旧批次.md", "ORIGINAL_SELECTED_BATCH".encode())
    bench.competitor_service.attach_documents(project["id"], competitor["id"], [original["id"]], material_type="store_info")
    monkeypatch.setattr(bench, "search", no_automatic_search)
    job = bench.prepare(project["id"], "fast/competitor-analysis", "只读已选批次", [original["id"]],
                        source_selection_mode="explicit", competitor_ids=[competitor["id"]])
    sources, prompt = copy.deepcopy(job["sources"]), job["prompt"]
    record_file = bench.data / "runs" / job["id"] / "执行记录.json"
    record_before = record_file.read_bytes()
    later = bench.add_document(project["id"], "新批次.md", "LATER_UPLOAD_NOT_SELECTED".encode())
    bench.competitor_service.attach_documents(project["id"], competitor["id"], [later["id"]], material_type="store_info")
    bench.competitor_service.update(project["id"], competitor["id"], {"note": "新备注不应修改旧输入"})
    current = bench.job(job["id"])
    assert current["sources"] == sources
    assert current["prompt"] == prompt
    assert record_file.read_bytes() == record_before
    assert "LATER_UPLOAD_NOT_SELECTED" not in current["prompt"]


@pytest.mark.parametrize("invalid_case", ["project", "version", "draft", "competitor", "unselected-owner", "archived"])
def test_explicit_selection_rejects_out_of_scope_or_unconfirmed_inputs(bench, monkeypatch, invalid_case):
    project = bench.create_project("本项目", "")
    other_project = bench.create_project("其他项目", "")
    current_version = bench.create_product_version(project["id"], {"name": "当前版本"})
    other_version = bench.create_product_version(project["id"], {"name": "其他版本"})
    competitor = dossier(bench, project["id"])
    selected_competitor = competitor
    version_id = current_version["id"]
    if invalid_case == "project":
        document = bench.add_document(other_project["id"], "外部资料.md", b"other project")
    elif invalid_case == "version":
        document = bench.add_document(project["id"], "其他版本.md", b"wrong version", other_version["id"])
    elif invalid_case == "draft":
        draft = bench.prepare(project["id"], "fast/version-brief", "草稿")
        bench.complete(draft["id"], "# 尚未确认\n\n这只是模型草稿，不能充当已确认输入。" * 4)
        document = {"id": draft["id"]}
    else:
        document = bench.add_document(project["id"], "本项目资料.md", b"selected data")
    if invalid_case not in {"draft", "project"}:
        bench.competitor_service.attach_documents(project["id"], competitor["id"], [document["id"]])
    if invalid_case == "competitor":
        selected_competitor = dossier(bench, other_project["id"])
    elif invalid_case == "unselected-owner":
        selected_competitor = dossier(bench, project["id"], "com.example.unrelated")
    elif invalid_case == "archived":
        bench.competitor_service.update(project["id"], competitor["id"], {"archived": True})
    count_before = len(bench.rows("SELECT id FROM jobs"))
    monkeypatch.setattr(bench, "search", no_automatic_search)
    with pytest.raises(ValueError):
        bench.prepare(project["id"], "fast/competitor-analysis", "", [document["id"]], version_id,
                      source_selection_mode="explicit", competitor_ids=[selected_competitor["id"]])
    assert len(bench.rows("SELECT id FROM jobs")) == count_before


@pytest.mark.parametrize("documents", [None, [], "not-a-list", [None], [123], ["x"] * 13])
def test_explicit_inputs_require_one_to_twelve_document_ids(bench, monkeypatch, documents):
    project = bench.create_project("输入数量校验", "")
    monkeypatch.setattr(bench, "search", no_automatic_search)
    with pytest.raises(ValueError):
        bench.prepare(project["id"], "fast/competitor-analysis", "", documents,
                      source_selection_mode="explicit", competitor_ids=[])
    assert not bench.rows("SELECT id FROM jobs")


def test_explicit_inputs_allow_twelve_and_deduplicate_existing_ids(bench, monkeypatch):
    project = bench.create_project("输入边界", "")
    docs = [bench.add_document(project["id"], f"资料{index}.md", f"独立资料{index}".encode()) for index in range(12)]
    monkeypatch.setattr(bench, "search", no_automatic_search)
    job = bench.prepare(project["id"], "fast/competitor-analysis", "", [doc["id"] for doc in docs], source_selection_mode="explicit")
    assert {source["source_id"] for source in job["sources"]} == {doc["id"] for doc in docs}
    repeated = bench.prepare(project["id"], "fast/competitor-analysis", "", [docs[0]["id"], docs[0]["id"]], source_selection_mode="explicit")
    assert [source["source_id"] for source in repeated["sources"]] == [docs[0]["id"]]
