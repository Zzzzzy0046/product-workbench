"""Dossiers preserve provenance and never silently broaden analysis inputs."""

import base64
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from workbench.app import Workbench
from workbench.core.runtime import now, uid
from workbench.api.handler import Handler


PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


@pytest.fixture
def setup(tmp_path):
    bench = Workbench(tmp_path, runner=lambda _: "unused")
    project = bench.create_project("竞品档案测试", "仅测试")
    yield bench, project["id"]
    bench.close()


def competitor(bench, project_id, app_id="example.app", **kwargs):
    return bench.competitor_service.upsert(project_id, {"platform": "google_play", "app_id": app_id, **kwargs})


def stage(bench, project_id, status="ready", app_id="example.app", documents=None, listing=None, **request):
    identifier, stamp = uid(), now()
    with bench.db() as db:
        db.execute("INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (identifier, project_id, "google_play", app_id, json.dumps(request), status, "", stamp, stamp, "", ""))
    row = bench.rows("SELECT * FROM scrapes WHERE id=?", (identifier,))[0]
    directory = bench.review_scraper._collection_directory(row)
    directory.mkdir(parents=True)
    manifest = {"listing": listing or {"title": "Example", "platform": "google_play", "app_id": app_id}, "document_ids": documents or []}
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return row, directory


def test_identity_upsert_does_not_overwrite_user_notes_or_merge_platforms(setup):
    bench, project_id = setup
    first = competitor(bench, project_id, "123", title="我的竞品名称", role="primary", note="只参考首页")
    again = competitor(bench, project_id, "123", title="商店新标题", note="被覆盖？")
    apple = bench.competitor_service.upsert(project_id, {"platform": "app_store", "app_id": "123"})
    assert first["id"] == again["id"]
    assert again["title"] == "我的竞品名称" and again["note"] == "只参考首页"
    assert apple["id"] != first["id"]
    assert again["source_url"] == "https://play.google.com/store/apps/details?id=123"


def test_blank_title_is_upgraded_only_from_structured_source(setup):
    bench, project_id = setup
    first = competitor(bench, project_id)
    assert competitor(bench, project_id, title="商店标题")["title"] == "商店标题"
    assert first["id"] == competitor(bench, project_id)["id"]


def test_shared_document_associations_keep_file_id_and_only_unlink(setup):
    bench, project_id = setup
    a, b = competitor(bench, project_id), competitor(bench, project_id, "example.two")
    document = bench.add_document(project_id, "截图.png", PIXEL, competitor_id=a["id"], material_type="device_screenshot")
    duplicate = bench.add_document(project_id, "同一截图.png", PIXEL, competitor_id=b["id"], material_type="store_screenshot")
    assert duplicate["id"] == document["id"]
    assert len(bench.competitor_service.document_links(project_id)) == 2
    bench.competitor_service.unlink_documents(project_id, a["id"], [document["id"]])
    assert bench.document_file(document["id"])[0] == PIXEL
    assert bench.competitor_service.detail(project_id, a["id"])["documents"] == []
    assert bench.competitor_service.detail(project_id, b["id"])["documents"][0]["material_type"] == "store_screenshot"


def test_cross_project_upload_is_rejected_before_creating_any_file(setup):
    bench, project_id = setup
    other = bench.create_project("另外一个项目", "")["id"]
    item = competitor(bench, other)
    with pytest.raises(ValueError, match="不属于当前项目"):
        bench.add_document(project_id, "错误.txt", b"should not persist", competitor_id=item["id"])
    assert bench.rows("SELECT id FROM documents WHERE project_id=?", (project_id,)) == []


def test_archive_is_reversible_and_never_deletes_evidence(setup):
    bench, project_id = setup
    item = competitor(bench, project_id)
    doc = bench.add_document(project_id, "笔记.md", b"real note", competitor_id=item["id"], material_type="note")
    bench.competitor_service.update(project_id, item["id"], {"archived": True})
    assert bench.competitor_service.detail(project_id, item["id"])["archived"] == 1
    with pytest.raises(ValueError, match="已归档"):
        bench.competitor_service.resolve_inputs(project_id, "", [item["id"]], [doc["id"]])
    bench.competitor_service.update(project_id, item["id"], {"archived": False})
    assert bench.competitor_service.resolve_inputs(project_id, "", [item["id"]], [doc["id"]])["document_ids"] == [doc["id"]]


def test_explicit_inputs_never_auto_include_dossier_or_other_version(setup):
    bench, project_id = setup
    a = competitor(bench, project_id)
    v1 = bench.create_product_version(project_id, {"name": "V1"})
    v2 = bench.create_product_version(project_id, {"name": "V2"})
    common = bench.add_document(project_id, "公共.md", b"common", competitor_id=a["id"], material_type="store_info")
    one = bench.add_document(project_id, "V1.md", b"version1", v1["id"], competitor_id=a["id"], material_type="reviews")
    two = bench.add_document(project_id, "V2.md", b"version2", v2["id"], competitor_id=a["id"], material_type="note")
    selected = bench.competitor_service.resolve_inputs(project_id, v1["id"], [a["id"]], [one["id"]])
    assert selected["document_ids"] == [one["id"]]
    assert selected["sources"][0]["sha"]
    assert bench.competitor_service.resolve_inputs(project_id, v1["id"], [a["id"]], [])["document_ids"] == []
    assert {doc["id"] for doc in bench.competitor_service.detail(project_id, a["id"], v1["id"])["documents"]} == {common["id"], one["id"]}
    with pytest.raises(ValueError, match="版本范围"):
        bench.competitor_service.resolve_inputs(project_id, v1["id"], [a["id"]], [two["id"]])
    with pytest.raises(ValueError, match="勾选的竞品不一致"):
        bench.competitor_service.resolve_inputs(project_id, v1["id"], [], [one["id"]])


def test_unassigned_evidence_allowed_but_generated_drafts_are_not(setup):
    bench, project_id = setup
    common = bench.add_document(project_id, "自己的想法.md", b"project context")
    assert bench.competitor_service.resolve_inputs(project_id, "", [], [common["id"]])["document_ids"] == [common["id"]]
    with bench.db() as db:
        db.execute("UPDATE documents SET kind='deliverable' WHERE id=?", (common["id"],))
    with pytest.raises(ValueError, match="未确认入库"):
        bench.competitor_service.resolve_inputs(project_id, "", [], [common["id"]])


def test_pending_batch_is_visible_but_not_an_input_document(setup):
    bench, project_id = setup
    item = competitor(bench, project_id)
    stage(bench, project_id)
    detail = bench.competitor_service.detail(project_id, item["id"])
    assert detail["pending_count"] == 1 and detail["documents"] == []
    assert detail["scrapes"][0]["status"] == "ready"
    with pytest.raises(ValueError, match="未确认入库"):
        bench.competitor_service.resolve_inputs(project_id, "", [item["id"]], [detail["scrapes"][0]["id"]])


def test_collection_uses_only_selected_dossiers_and_checked_capabilities(setup, monkeypatch):
    bench, project_id = setup
    a, b = competitor(bench, project_id), competitor(bench, project_id, "example.two")
    monkeypatch.setattr(bench.review_scraper, "_run_collection_batch", lambda _: None)
    batch = bench.start_competitor_collection(project_id, {"competitor_ids": [a["id"]], "countries": ["us"], "collect_listing": False, "collect_reviews": True, "collect_screenshots": False, "translate": False})
    assert batch["count"] == 1
    request = json.loads(batch["items"][0]["request"])
    assert request["competitor_id"] == a["id"] and request["app_id"] != b["app_id"]
    assert not request["collect_listing"] and not request["download_screenshots"] and request["collect_reviews"]


def test_collection_accepts_per_competitor_overrides(setup, monkeypatch):
    bench, project_id = setup
    a, b = competitor(bench, project_id), competitor(bench, project_id, "example.two")
    monkeypatch.setattr(bench.review_scraper, "_run_collection_batch", lambda _: None)
    batch = bench.start_competitor_collection(project_id, {"competitor_ids": [a["id"], b["id"]], "countries": ["us"], "collect_listing": False, "collect_reviews": True, "collect_screenshots": False, "collection_options": {b["id"]: {"collect_reviews": False, "collect_screenshots": True}}})
    requests = {json.loads(item["request"])["competitor_id"]: json.loads(item["request"]) for item in batch["items"]}
    assert requests[a["id"]]["collect_reviews"]
    assert not requests[b["id"]]["collect_reviews"] and requests[b["id"]]["download_screenshots"]
    assert requests[b["id"]]["collect_listing"] and not requests[b["id"]]["save_listing"]


def test_unchecked_collection_cannot_queue(setup, monkeypatch):
    bench, project_id = setup
    item = competitor(bench, project_id)
    monkeypatch.setattr(bench.review_scraper, "_run_collection_batch", lambda _: None)
    with pytest.raises(ValueError, match="至少勾选"):
        bench.start_competitor_collection(project_id, {"competitor_ids": [item["id"]], "countries": ["us"], "collect_listing": False, "collect_reviews": False, "collect_screenshots": False})
    assert bench.scrapes(project_id) == []


def test_screenshot_only_confirm_excludes_unchecked_listing_and_reviews(setup):
    bench, project_id = setup
    row, directory = stage(bench, project_id, save_listing=False, collect_reviews=False, download_screenshots=True)
    (directory / "store-listing.md").write_text("this must not enter library", encoding="utf-8")
    (directory / "reviews.csv").write_text("content\nunselected", encoding="utf-8")
    screenshots = directory / "screenshots"
    screenshots.mkdir()
    (screenshots / "01.png").write_bytes(PIXEL)
    confirmed = bench.confirm_competitor_collection(row["id"])
    assert confirmed["status"] == "completed" and len(confirmed["document_ids"]) == 1
    items = bench.competitor_service.list(project_id)["competitors"]
    detail = bench.competitor_service.detail(project_id, items[0]["id"])
    assert detail["counts"]["store_screenshot"] == 1 and detail["counts"]["store_info"] == 0 and detail["counts"]["reviews"] == 0


def test_startup_migrates_every_structured_scrape_without_filename_guessing(tmp_path):
    bench = Workbench(tmp_path, runner=lambda _: "unused")
    project_id = bench.create_project("旧项目", "")["id"]
    a = bench.add_document(project_id, "竞品商店信息-共同名字.md", b"listing A")
    b = bench.add_document(project_id, "竞品评论-共同名字.csv", b"content\nB")
    manual = bench.add_document(project_id, "竞品截图-example.app.md", b"unknown provenance")
    stage(bench, project_id, status="completed", documents=[a["id"]])
    stage(bench, project_id, status="completed", app_id="example.two", documents=[b["id"]])
    stage(bench, project_id, status="ready", app_id="example.pending")
    with bench.db() as db:
        db.execute("DELETE FROM preferences WHERE key LIKE 'migration:competitor-dossiers-v1:%'")
    bench.close()
    second = Workbench(tmp_path, runner=lambda _: "unused")
    try:
        dossiers = second.competitor_service.list(project_id)["competitors"]
        assert {item["app_id"] for item in dossiers} == {"example.app", "example.two", "example.pending"}
        links = second.competitor_service.document_links(project_id)
        assert {link["document_id"] for link in links} == {a["id"], b["id"]}
        assert manual["id"] not in {link["document_id"] for link in links}
        owner = next(link["competitor_id"] for link in links if link["document_id"] == a["id"])
        second.competitor_service.unlink_documents(project_id, owner, [a["id"]])
        second.competitor_service.migrate_project(project_id)
        assert a["id"] not in {link["document_id"] for link in second.competitor_service.document_links(project_id)}
        assert second.document_file(a["id"])[0] == b"listing A"
    finally:
        second.close()


def test_reading_dossiers_is_read_only_and_state_has_associations(setup):
    bench, project_id = setup
    item = competitor(bench, project_id)
    doc = bench.add_document(project_id, "体验笔记.md", b"notes", competitor_id=item["id"], material_type="note")
    before = bench.rows("SELECT * FROM competitors")
    links = bench.competitor_service.document_links(project_id)
    bench.competitor_service.list(project_id)
    bench.competitor_service.detail(project_id, item["id"])
    assert bench.rows("SELECT * FROM competitors") == before
    assert bench.competitor_service.document_links(project_id) == links
    state = bench.state(project_id)
    assert state["documents"][0]["id"] == doc["id"]
    assert state["documents"][0]["competitor_ids"] == [item["id"]]
    assert state["documents"][0]["competitor_material_types"] == {item["id"]: "note"}


def test_migration_uses_confirmed_android_ids_and_structured_revenue(setup):
    bench, project_id = setup
    screenshot = bench.add_document(project_id, "实机截图-example.android-01.png", PIXEL)
    flow = bench.add_document(project_id, "模块流程-example.android-import.md", b"fixture flow metadata")
    revenue = bench.add_document(project_id, "竞品收入-example.revenue-2026-01.md", ("# 竞品收入资料（人工记录）\n\n- 平台：google_play\n- 应用 ID：example.revenue\n- 应用名称：收入竞品\n").encode())
    directory = bench.android_capture._project_root(project_id) / ("android-" + uid())
    directory.mkdir(parents=True)
    record = {"id": uid(), "project_id": project_id, "package": "example.android", "title": "实机竞品", "status": "confirmed", "document_ids": [screenshot["id"], flow["id"]], "created": now()}
    bench.android_capture._write(directory, record)
    with bench.db() as db:
        db.execute("DELETE FROM preferences WHERE key=?", (bench.competitor_service.MIGRATION + ":" + project_id,))
    bench.competitor_service.migrate_project(project_id)
    dossiers = {item["app_id"]: item for item in bench.competitor_service.list(project_id)["competitors"]}
    android = bench.competitor_service.detail(project_id, dossiers["example.android"]["id"])
    assert android["counts"]["device_screenshot"] == 1 and android["counts"]["module_flow"] == 1
    assert bench.competitor_service.detail(project_id, dossiers["example.revenue"]["id"])["documents"][0]["id"] == revenue["id"]


def test_image_delete_cleans_dossier_relation_without_dangling_export(setup):
    bench, project_id = setup
    item = competitor(bench, project_id)
    image = bench.add_document(project_id, "图片.png", PIXEL, competitor_id=item["id"], material_type="device_screenshot")
    bench.delete_image(project_id, image["id"])
    assert bench.competitor_service.document_links(project_id) == []
    assert bench.rows("SELECT * FROM competitor_documents") == []


def test_http_dossier_create_upload_scope_and_input_routes(setup):
    bench, project_id = setup
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.app = bench
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"

    def request(path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json", "Origin": root, "X-Workbench-Token": bench.token}
        with urlopen(Request(root + path, data=body, headers=headers), timeout=10) as response:
            return json.load(response)

    try:
        item = request("/api/competitors", {"project_id": project_id, "platform": "google_play", "app_id": "example.http"})
        version = bench.create_product_version(project_id, {"name": "HTTP V1"})
        doc = request("/api/documents", {"project_id": project_id, "name": "HTTP笔记.md", "content": base64.b64encode(b"notes").decode(), "competitor_id": item["id"], "material_type": "note", "version_id": version["id"]})
        assert request(f"/api/competitors?project_id={project_id}&version_id=")["competitors"][0]["counts"]["documents"] == 0
        assert request(f"/api/competitors/{item['id']}?project_id={project_id}&version_id={version['id']}")["documents"][0]["id"] == doc["id"]
        selected = request("/api/competitors/inputs", {"project_id": project_id, "version_id": version["id"], "competitor_ids": [item["id"]], "document_ids": [doc["id"]]})
        assert selected["document_ids"] == [doc["id"]]
        with pytest.raises(HTTPError) as missing_owner:
            request("/api/competitors/inputs", {"project_id": project_id, "version_id": version["id"], "document_ids": [doc["id"]]})
        assert missing_owner.value.code == 400
        request(f"/api/competitors/{item['id']}/unlink", {"project_id": project_id, "document_ids": [doc["id"]]})
        assert request(f"/api/competitors/{item['id']}?project_id={project_id}")["documents"] == []
        assert bench.document_file(doc["id"])[0] == b"notes"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
