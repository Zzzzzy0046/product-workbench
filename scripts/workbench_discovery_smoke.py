"""Isolated competitor-discovery-to-F1 HTTP smoke test.

Run with ``.venv/Scripts/python.exe -X utf8 scripts/workbench_discovery_smoke.py``.
Every candidate, comment, screenshot and generated sentence is a labelled fixture.
The test makes loopback HTTP calls only; it does NOT query an external store,
translate comments, call a model, or touch the real workbench project directory.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.app import Workbench
from workbench.api.handler import Handler


PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
CANDIDATES = [
    {
        "platform": "google_play", "app_id": "com.fixture.localreader",
        "title": "Fixture Local Reader", "developer": "Fixture Studio",
        "short_description": "FICTIONAL: local documents and rename.",
        "source_url": "https://play.google.com/store/apps/details?id=com.fixture.localreader",
        "score": 4.1, "ratings": 100, "installs": "1,000+", "free": True,
        "price": 0, "contains_ads": None, "offers_iap": None, "icon_url": "",
    },
    {
        "platform": "google_play", "app_id": "com.fixture.reference",
        "title": "Fixture Optional Reference", "developer": "Fixture Studio",
        "short_description": "FICTIONAL: an unselected reference.",
        "source_url": "https://play.google.com/store/apps/details?id=com.fixture.reference",
        "score": None, "ratings": None, "installs": "", "free": None,
        "price": None, "contains_ads": None, "offers_iap": None, "icon_url": "",
    },
]


def main() -> int:
    checks, discovery_calls, model_fixture_calls = [], [], []

    def check(name, condition, detail=""):
        if not condition:
            raise AssertionError(f"{name}: {detail}")
        checks.append({"name": name, "result": "PASS", "detail": detail})

    def fake_runner(job):
        model_fixture_calls.append(job["task_id"])
        return (
            "# F1-1 品类与用户（固定测试替身，非真实研究）\n\n"
            "## 2. 行业与市场背景\n只参考本轮人工选定的虚构竞品资料。"
            "当前测试不包含真实下载量、收入或市场规模。\n\n"
            "## 3. 用户分析\n测试设定的使用场景为本地阅读与重命名；不代表用户研究结论。\n"
        )

    with tempfile.TemporaryDirectory(prefix="workbench-discovery-smoke-") as temporary:
        bench = Workbench(Path(temporary) / "data", runner=fake_runner)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.app = bench
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        origin = f"http://127.0.0.1:{server.server_port}"

        def request(path, payload=None, expected=200):
            data = None if payload is None else json.dumps(payload).encode("utf-8")
            headers = {"Origin": origin, "X-Workbench-Token": bench.token}
            if data is not None:
                headers["Content-Type"] = "application/json"
            operation = urllib.request.Request(origin + path, data=data, headers=headers)
            try:
                with urllib.request.urlopen(operation, timeout=10) as response:
                    status, body = response.status, response.read()
                    is_json = "application/json" in response.headers.get("Content-Type", "")
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read()
                is_json = "application/json" in exc.headers.get("Content-Type", "")
            if status != expected:
                raise AssertionError(f"HTTP {path}: expected {expected}, got {status}: {body[:500]!r}")
            return json.loads(body) if is_json else body

        def fake_discovery(request_data):
            discovery_calls.append(dict(request_data))
            if request_data.get("query") == "failure-fixture":
                raise ValueError("测试替身：商店暂时无法连接，请稍后重试。")
            if request_data["mode"] == "discovery_detail":
                return {"listing": {
                    **deepcopy(CANDIDATES[0]), "market": request_data["country"].upper(),
                    "long_description": "FICTIONAL LONG DESCRIPTION: local files only.",
                    "screenshot_urls": [],
                }, "warnings": []}
            return {"items": [] if request_data.get("query") == "empty-fixture" else deepcopy(CANDIDATES), "warnings": []}

        def fake_collection(scrape_id):
            scrape = bench.scrape(scrape_id)
            collection_request = json.loads(scrape["request"])
            directory = bench.review_scraper._collection_directory(scrape)
            shots = directory / "screenshots"
            shots.mkdir(parents=True, exist_ok=True)
            (shots / "fixture.png").write_bytes(PIXEL)
            listing = {
                **deepcopy(CANDIDATES[0]), "market": collection_request["countries"][0].upper(),
                "language": "en", "short_description": "FICTIONAL SHORT DESCRIPTION.",
                "long_description": "FICTIONAL LONG DESCRIPTION: local files only.",
                "screenshot_files": ["fixture.png"], "screenshot_urls": ["https://play-lh.googleusercontent.com/fixture.png"],
            }
            result = {"listing": listing, "reviews": [{
                "review_id": "fixture-review-1", "content": "Fictional rename retry failed.",
                "original_content": "Fictional rename retry failed.", "translated_content": "虚构评论：重命名重试失败。",
                "score": 1, "market": "US", "language": "en", "platform": "google_play",
                "app_id": scrape["app_id"], "published_at": "2026-01-01T00:00:00",
            }], "warnings": [], "filter_stats": {"fetched": 1, "kept": 1}}
            bench.review_scraper._stage_collection_result(scrape, collection_request, result, directory)
            bench._update_scrape(scrape_id, status="ready", review_count=1, warning_count=0)

        object.__setattr__(bench.competitor_discovery, "_worker_request", fake_discovery)
        object.__setattr__(bench.review_scraper, "_run_review_scrape", fake_collection)
        try:
            check("data-isolated", not bench.data.is_relative_to(ROOT / "workbench" / "data"))
            project = request("/api/projects", {"name": "竞品发现链路测试（非真实研究）", "brief": "本地阅读与重命名。", "platform": "Android"}, 201)
            pid = project["id"]
            version = request("/api/product-versions", {"project_id": pid, "name": "V0 Fixture"}, 201)
            search = {"project_id": pid, "version_id": version["id"], "query": "local reader fixture", "platform": "google_play", "country": "us", "lang": "en", "limit": 12}
            found = request("/api/competitors/search", search)
            check("search-two-fixture-candidates", len(found["items"]) == 2 and not found["cached"])
            check("search-does-not-auto-select", all(not item.get("selected") and not item.get("role") for item in found["items"]))
            check("search-no-collection-or-document", not bench.scrapes(pid) and not bench.rows("SELECT id FROM documents WHERE project_id=?", (pid,)))
            cached = request("/api/competitors/search", search)
            check("search-cache-hit", cached["cached"] is True and len(discovery_calls) == 1)
            request("/api/competitors/search", {**search, "refresh": True})
            check("search-refresh-fetches-again", len(discovery_calls) == 2)
            empty = request("/api/competitors/search", {**search, "query": "empty-fixture"})
            check("empty-search-remains-empty", empty["items"] == [])
            failure = request("/api/competitors/search", {**search, "query": "failure-fixture"}, 400)
            check("failed-search-human-readable", "无法连接" in failure["error"])
            before_retry = len(discovery_calls)
            request("/api/competitors/search", {**search, "query": "failure-fixture"}, 400)
            check("failed-search-not-cached", len(discovery_calls) == before_retry + 1)
            invalid = request("/api/competitors/search", {**search, "query": ""}, 400)
            check("empty-keyword-rejected", bool(invalid["error"]))
            detail_payload = {"project_id": pid, "version_id": version["id"], "platform": "google_play", "country": "us", "lang": "en", "app_id": CANDIDATES[0]["app_id"]}
            detail = request("/api/competitors/detail", detail_payload)
            check("detail-on-demand", "FICTIONAL LONG" in detail["listing"]["long_description"])
            check("detail-no-import-side-effect", not bench.scrapes(pid) and not bench.rows("SELECT id FROM documents WHERE project_id=?", (pid,)))

            collect = {"project_id": pid, "version_id": version["id"], "entries": [], "countries": ["us"], "count_per_country": 1, "translate": False}
            rejected = request("/api/competitors/collect", collect, 400)
            check("unselected-cannot-collect", bool(rejected["error"]) and not bench.scrapes(pid))
            selected = {"platform": "google_play", "app_id": CANDIDATES[0]["app_id"], "title": CANDIDATES[0]["title"], "role": "feature", "note": "只参考重命名失败恢复；不是全量主对标。", "source_url": CANDIDATES[0]["source_url"], "query": search["query"]}
            invalid_role = request("/api/competitors/collect", {**collect, "entries": [CANDIDATES[0]["source_url"]], "selections": [{**selected, "role": "automatic-choice"}]}, 400)
            check("invalid-role-cannot-start-collection", bool(invalid_role["error"]) and not bench.scrapes(pid))
            wrong_selection = request("/api/competitors/collect", {**collect, "entries": [CANDIDATES[0]["source_url"]], "selections": [{**selected, "app_id": CANDIDATES[1]["app_id"]}]}, 400)
            check("mismatched-selection-cannot-start-collection", bool(wrong_selection["error"]) and not bench.scrapes(pid))
            batch = request("/api/competitors/collect", {**collect, "entries": [CANDIDATES[0]["source_url"]], "selections": [selected]}, 202)
            check("only-user-selected-candidate-collected", batch["count"] == 1 and len(bench.scrapes(pid)) == 1)
            sid = batch["items"][0]["id"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                staged = request(f"/api/reviews/scrape/{sid}")
                if staged["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)
            check("collected-is-staged-ready", staged["status"] == "ready", staged.get("error", staged["status"]))
            check("unconfirmed-not-in-library", not bench.rows("SELECT id FROM documents WHERE project_id=?", (pid,)))
            selection = json.loads(staged["request"]).get("selection", {})
            check("manual-role-preserved", selection.get("role") == "feature" and selection.get("app_id") == CANDIDATES[0]["app_id"])
            check("descriptions-preserved-before-import", "FICTIONAL SHORT" in staged["listing"]["short_description"] and "FICTIONAL LONG" in staged["listing"]["long_description"])
            check("staged-screenshot-count", staged["screenshot_count"] == 1)
            check("preview-original-and-translated-comments", staged["review_samples"][0]["original_content"] == "Fictional rename retry failed." and staged["review_samples"][0]["translated_content"] == "虚构评论：重命名重试失败。")
            check("preview-screenshot-url-available", staged["screenshot_preview_urls"] == ["https://play-lh.googleusercontent.com/fixture.png"])
            confirmed = request(f"/api/reviews/scrape/{sid}/confirm", {})
            check("explicit-confirm-imports", confirmed["status"] == "completed" and len(confirmed["document_ids"]) == 3)
            documents = bench.rows("SELECT id,name,text FROM documents WHERE project_id=?", (pid,))
            check("library-has-listing-review-and-image", len(documents) == 3 and any(row["name"].endswith(".csv") for row in documents) and any(row["name"].endswith(".png") for row in documents))
            duplicate = request(f"/api/reviews/scrape/{sid}/confirm", {}, 400)
            check("repeat-confirm-does-not-duplicate", bool(duplicate["error"]) and len(bench.rows("SELECT id FROM documents WHERE project_id=?", (pid,))) == 3)
            listing_doc = next(row for row in documents if row["name"].endswith(".md"))
            check("selection-purpose-in-research-source", "功能参考" in listing_doc["text"] and "重命名失败恢复" in listing_doc["text"])
            prepared = request("/api/prepare", {"project_id": pid, "task": "fast/f1-category-user", "version_id": version["id"], "document_ids": confirmed["document_ids"], "instruction": "只使用本轮测试证据，不补造事实。"}, 201)
            check("confirmed-collection-to-f1-sources", set(confirmed["document_ids"]) <= {item["source_id"] for item in prepared["sources"]})
            check("f1-awaits-user-start", prepared["status"] == "prepared" and not model_fixture_calls)
            request(f"/api/jobs/{prepared['id']}/start", {})
            worker = bench.threads.get(prepared["id"])
            if worker:
                worker.join(5)
            output = request(f"/api/jobs/{prepared['id']}")
            check("f1-fixed-fixture-completes", output["status"] == "completed" and model_fixture_calls == ["fast/f1-category-user"])
            review = request(f"/api/jobs/{prepared['id']}/review", {"decision": "accepted", "note": "仅确认固定测试替身的流程状态。"})
            check("f1-human-confirmed", review["review"]["decision"] == "accepted")
            package = request(f"/api/projects/{pid}/export")
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                check("project-package-valid", {"data.json", "manifest.json"} <= set(archive.namelist()))
            imported = request("/api/projects/import", {"content": base64.b64encode(package).decode("ascii")}, 201)
            new_pid = imported["id"]
            check("import-creates-isolated-copy", new_pid != pid)
            restored = bench.scrapes(new_pid)
            check("import-preserves-completed-collection", len(restored) == 1 and restored[0]["status"] == "completed")
            restored_item = request(f"/api/reviews/scrape/{restored[0]['id']}")
            check("import-preserves-collection-preview", restored_item["listing"].get("title") == CANDIDATES[0]["title"])
            check("import-preserves-review-preview", restored_item["review_samples"][0]["translated_content"] == "虚构评论：重命名重试失败。")
            restored_doc_ids = {row["id"] for row in bench.rows("SELECT id FROM documents WHERE project_id=? AND kind='upload'", (new_pid,))}
            check("import-remaps-collection-document-ids", set(restored_item["document_ids"]) == restored_doc_ids and not restored_doc_ids.intersection(confirmed["document_ids"]), f"preview={restored_item['document_ids']}; imported={sorted(restored_doc_ids)}")
            restored_selection = json.loads(restored_item["request"]).get("selection", {})
            check("import-preserves-user-role", restored_selection.get("role") == "feature")
            png_id = next(row["id"] for row in bench.rows("SELECT id,name FROM documents WHERE project_id=?", (new_pid,)) if row["name"].endswith(".png"))
            check("import-image-remains-readable", request(f"/api/assets/{new_pid}/{png_id}") == PIXEL)
            print(json.dumps({"result": "PASS", "checks": len(checks), "discovery_fixture_calls": len(discovery_calls), "model_fixture_calls": len(model_fixture_calls), "network_scope": "loopback only", "real_model_calls": 0, "details": checks}, ensure_ascii=False, indent=2))
            return 0
        finally:
            server.shutdown()
            server.server_close()
            serving.join(5)
            bench.close()


if __name__ == "__main__":
    raise SystemExit(main())
