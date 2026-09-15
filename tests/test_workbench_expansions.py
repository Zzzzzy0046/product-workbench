import base64
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("workbench_app_expansions", ROOT / "workbench" / "app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)
WORKER_SPEC = importlib.util.spec_from_file_location("review_scraper_worker_tests", ROOT / "workbench" / "review_scraper_worker.py")
review_worker = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(review_worker)


PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_export_formats_and_inline_image(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    project = bench.create_project("导出项目", "快速验证")
    image = bench.add_document(project["id"], "页面.png", PIXEL)
    job = bench.prepare(project["id"], "fast/new-product-analysis", "", [image["id"]])
    output = (
        f"# 新品分析\n\n![页面截图](asset://{image['id']})\n\n"
        "市场与用户：海外阅读用户。\n\n竞品差异：更快。\n\n"
        "产品定位、MVP 首版范围、功能框架、核心流程和商业化。"
    )
    bench.complete(job["id"], output, "imported")

    exports = {fmt: bench.export_job(job["id"], fmt)[0] for fmt in ("docx", "pdf", "xlsx", "csv")}
    assert exports["docx"].startswith(b"PK")
    assert exports["pdf"].startswith(b"%PDF")
    assert exports["xlsx"].startswith(b"PK")
    assert exports["csv"].startswith(b"\xef\xbb\xbf")


def test_inline_image_must_belong_to_project(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    project = bench.create_project("图片校验", "")
    job = bench.prepare(project["id"], "fast/new-product-analysis", "")
    with pytest.raises(ValueError, match="不存在的项目图片"):
        bench.complete(job["id"], "# 正文\n\n![外部图片](asset://0123456789abcdef0123456789abcdef)", "imported")


def test_project_package_roundtrip_remaps_inline_images(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    project = bench.create_project("迁移项目", "图片和版本")
    image = bench.add_document(project["id"], "页面.png", PIXEL)
    job = bench.prepare(project["id"], "fast/new-product-analysis", "", [image["id"]])
    output = f"# 交付物\n\n![页面](asset://{image['id']})\n\n这是完整交付物正文，包含市场、用户、竞品差异、定位、MVP、功能、流程和商业化。"
    bench.complete(job["id"], output, "imported")
    package, _ = bench.export_project(project["id"])
    imported = bench.import_project(package)
    imported_job = bench.rows("SELECT id,output FROM jobs WHERE project_id=?", (imported["id"],))[0]
    asset_id = re.search(r"asset://([a-f0-9]{16,64})", imported_job["output"]).group(1)
    assert asset_id != image["id"]
    assert bench.asset(imported["id"], asset_id)[0].is_file()
    assert "asset://" + image["id"] not in imported_job["output"]


def test_project_package_does_not_export_machine_bound_image_paths(tmp_path):
    bench = app.Workbench(tmp_path / "data", runner=lambda _: "unused")
    project = bench.create_project("可迁移路径", "")
    image = bench.add_document(project["id"], "页面.png", PIXEL)
    job = bench.prepare(project["id"], "fast/new-product-analysis", "", [image["id"]])
    package, _ = bench.export_project(project["id"])
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        payload = b"".join(archive.read(name) for name in archive.namelist() if name.endswith((".json", ".md")))
    assert str(bench.data).encode() not in payload
    assert b"image_path" not in payload
    assert job["id"].encode() in payload


def test_unreferenced_image_can_be_deleted_but_referenced_image_is_protected(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    project = bench.create_project("图片管理", "")
    image = bench.add_document(project["id"], "未引用.png", PIXEL)
    path = bench.asset(project["id"], image["id"])[0]
    assert bench.delete_image(project["id"], image["id"])["deleted"] is True
    assert not path.exists()
    assert not bench.rows("SELECT id FROM documents WHERE id=?", (image["id"],))

    image = bench.add_document(project["id"], "已引用.png", PIXEL)
    job = bench.prepare(project["id"], "fast/new-product-analysis", "", [image["id"]])
    bench.complete(job["id"], f"# 新品分析\n\n![截图](asset://{image['id']})\n\n市场、用户、竞品差异、定位、MVP、功能、流程和商业化。", "imported")
    with pytest.raises(ValueError, match="不能删除"):
        bench.delete_image(project["id"], image["id"])


def test_review_scraper_bridge_imports_csv(tmp_path):
    tool = tmp_path / "competitor-tool"
    (tool / "app").mkdir(parents=True)
    (tool / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tool / "app" / "scrapers.py").write_text(
        "def scrape_google_play(*args, **kwargs):\n"
        "    return [{'review_id':'r1','content':'good 👎 中文','score':5,'published_at':'2026-09-11','market':'us','language':'en','version':'1','source':'google-play:us/en','platform':'google_play','app_id':'com.test'}]\n"
        "def scrape_app_store(*args, **kwargs):\n"
        "    return []\n",
        encoding="utf-8",
    )
    bench = app.Workbench(tmp_path / "data", runner=lambda _: "unused")
    bench.save_review_scraper_settings({"root": str(tool), "python": sys.executable})
    project = bench.create_project("评论项目", "")
    scrape = bench.start_review_scrape(
        project["id"],
        {"platform": "google_play", "app_id": "com.test", "countries": ["us"], "count_per_country": 1},
    )
    for _ in range(100):
        scrape = bench.scrape(scrape["id"])
        if scrape["status"] not in {"queued", "running"}:
            break
        time.sleep(0.02)
    assert scrape["status"] == "completed"
    document = bench.rows("SELECT name,kind,text FROM documents WHERE id=?", (scrape["result_doc_id"],))[0]
    assert document["kind"] == "upload"
    assert "review_id" in document["text"]


def test_review_csv_document_returns_structured_preview_and_original(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("评论阅读", "")
        content = (
            "review_id,content,score,published_at,market,language,version,source,platform,app_id,thumbs_up_count,user_name,reply_content,reply_at\r\n"
            "r1,\"Great app, easy to use\",5,2026-09-14,US,en,2.3.11,google-play:us/en,google_play,com.test,3,Alice,,\r\n"
            "r2,\"Line one\nLine two\",2,2026-09-13,GB,en,2.3.10,google-play:gb/en,google_play,com.test,0,Bob,Please retry,2026-09-14\r\n"
        ).encode("utf-8")
        document = bench.add_document(project["id"], "reviews.csv", content)
        preview = bench.document(document["id"])
        assert preview["csv_preview"]["kind"] == "reviews"
        assert preview["csv_preview"]["total_rows"] == 2
        assert preview["csv_preview"]["rows"][0][1] == "Great app, easy to use"
        assert preview["csv_preview"]["rows"][1][1] == "Line one\nLine two"
        original, name = bench.document_file(document["id"])
        assert original == content
        assert name == "reviews.csv"
    finally:
        bench.close()


def test_review_csv_can_fill_chinese_translation_without_replacing_original(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("评论翻译", "")
        content = (
            "review_id,content,score,published_at,language,translated_content\n"
            "r1,The app would not load,1,2026-09-14,en,\n"
            "r2,Already translated,5,2026-09-13,en,已有译文\n"
            "r3,很好用,5,2026-09-12,zh-CN,\n"
        ).encode("utf-8")
        document = bench.add_document(project["id"], "reviews.csv", content)
        calls = []

        def fake_translate(items):
            calls.extend(items)
            return {
                "translations": ["应用无法加载"],
                "translated_count": 1,
                "failed_count": 0,
                "provider": "test",
                "warnings": [],
            }

        object.__setattr__(bench.review_scraper, "_translate_items", fake_translate)
        result = bench.translate_review_document(document["id"])
        assert result["newly_translated"] == 1
        assert result["remaining_count"] == 0
        assert calls == [{"text": "The app would not load", "language": "en"}]

        preview = bench.document(document["id"])["csv_preview"]
        assert preview["translation"] == {"total": 2, "translated": 2, "missing": 0}
        headers = preview["headers"]
        rows = preview["rows"]
        assert rows[0][headers.index("content")] == "The app would not load"
        assert rows[0][headers.index("translated_content")] == "应用无法加载"
        assert rows[1][headers.index("translated_content")] == "已有译文"
        stored = bench.rows("SELECT text FROM documents WHERE id=?", (document["id"],))[0]["text"]
        assert "应用无法加载" in stored
    finally:
        bench.close()


def test_review_translation_splits_malformed_batches_and_keeps_alignment(tmp_path, monkeypatch):
    calls = []

    def fake_ai(texts, _root):
        calls.append(list(texts))
        if len(texts) > 1:
            raise ValueError("malformed batch")
        return [f"译文：{texts[0]}"]

    monkeypatch.setattr(review_worker, "_translate_ai_batch", fake_ai)
    result = review_worker._translate_items(
        [
            {"text": "First", "language": "en"},
            {"text": "Second", "language": "en"},
            {"text": "First", "language": "en"},
            {"text": "👍", "language": "en"},
        ],
        tmp_path,
        batch_size=20,
    )
    assert result["translations"] == ["译文：First", "译文：Second", "译文：First", ""]
    assert result["translated_count"] == 3
    assert result["skipped_count"] == 1
    assert result["failed_count"] == 0
    assert calls == [["First", "Second"], ["First"], ["Second"]]


def test_review_scraper_worker_is_safe_with_gbk_stdio(tmp_path):
    tool = tmp_path / "competitor-tool"
    (tool / "app").mkdir(parents=True)
    (tool / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tool / "app" / "scrapers.py").write_text(
        "def scrape_google_play(*args, **kwargs):\n"
        "    return [{'review_id':'r1','content':'emoji 👎 中文','score':1}]\n"
        "def scrape_app_store(*args, **kwargs):\n"
        "    return []\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "gbk"
    request = {
        "root": str(tool),
        "platform": "google_play",
        "app_id": "com.test",
        "countries": ["us"],
        "count_per_country": 1,
    }
    completed = subprocess.run(
        [sys.executable, str(ROOT / "workbench" / "review_scraper_worker.py")],
        input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tool,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    payload = json.loads(completed.stdout.decode("utf-8"))
    assert payload["reviews"][0]["content"] == "emoji 👎 中文"


def test_batch_competitor_collection_waits_for_confirmation(tmp_path):
    class ImageHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PIXEL)))
            self.end_headers()
            self.wfile.write(PIXEL)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), ImageHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    tool = tmp_path / "competitor-tool"
    (tool / "app").mkdir(parents=True)
    (tool / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tool / "app" / "scrapers.py").write_text(
        "GOOGLE_LANGS = {'us': 'en'}\n"
        "def scrape_google_play(package_id, *args, **kwargs):\n"
        "    return [{'review_id':'r1','content':'真实评论','score':5,'market':'US','platform':'google_play','app_id':package_id}]\n"
        "def scrape_app_store(*args, **kwargs):\n"
        "    return []\n",
        encoding="utf-8",
    )
    (tool / "google_play_scraper.py").write_text(
        "def app(app_id, lang='en', country='us'):\n"
        "    return {'title':'Test Emulator','summary':'Original short description','description':'Original long description','developer':'Test Studio','genre':'Tools','score':4.5,'ratings':10,'reviews':8,'installs':'1,000+','version':'1.0','lastUpdatedOn':'2026-09-15','url':'https://play.google.com/store/apps/details?id='+app_id,'screenshots':['http://127.0.0.1:%d/shot.png']}\n"
        % server.server_port,
        encoding="utf-8",
    )
    bench = app.Workbench(tmp_path / "data", runner=lambda _: "unused")
    try:
        bench.save_review_scraper_settings({"root": str(tool), "python": sys.executable})
        project = bench.create_project("批量竞品资料", "")
        version = bench.create_product_version(project["id"], {"name": "V1.0.0"})
        batch = bench.start_competitor_collection(project["id"], {
            "entries": ["https://play.google.com/store/apps/details?id=com.test.emulator"],
            "countries": ["us"],
            "count_per_country": 1,
            "version_id": version["id"],
        })
        assert batch["count"] == 1
        scrape_id = batch["items"][0]["id"]
        for _ in range(200):
            item = bench.scrape(scrape_id)
            if item["status"] not in {"queued", "running"}:
                break
            time.sleep(0.02)
        assert item["status"] == "ready"
        assert item["listing"]["short_description"] == "Original short description"
        assert item["listing"]["long_description"] == "Original long description"
        assert item["screenshot_count"] == 1
        assert item["translation_requested"] is True
        assert bench.rows("SELECT id FROM documents WHERE project_id=?", (project["id"],)) == []

        confirmed = bench.confirm_competitor_collection(scrape_id)
        assert confirmed["status"] == "completed"
        documents = bench.rows("SELECT id,name,text FROM documents WHERE project_id=? ORDER BY name", (project["id"],))
        assert len(documents) == 3
        listing = next(document for document in documents if document["name"].startswith("竞品商店信息-"))
        assert "Original short description" in listing["text"]
        assert "Original long description" in listing["text"]
        assert any(document["name"].startswith("竞品评论-") for document in documents)
        assert any(document["name"].startswith("竞品截图-") for document in documents)
        links = bench.rows("SELECT document_id,relation FROM version_documents WHERE version_id=?", (version["id"],))
        assert len(links) == 3
        assert {item["relation"] for item in links} == {"competitor-listing", "review-evidence", "competitor-screenshot"}
    finally:
        bench.close()
        server.shutdown()
        server.server_close()


def test_quality_rules_block_duplicate_tracking_ids():
    from workbench.validators import summarize, validate

    result = summarize(
        validate(
            "fast/tracking-spec",
            "事件 ID：scan_start\n事件 ID：scan_start\n参数名：mode",
        )
    )
    assert result["errors"] == 1
    assert result["ok"] is False
