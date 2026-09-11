import base64
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("workbench_app_expansions", ROOT / "workbench" / "app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


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
