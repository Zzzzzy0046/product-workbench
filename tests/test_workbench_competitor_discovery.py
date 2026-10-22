"""Discovery is lightweight/read-only; collection requires explicit selection."""

import importlib.util
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from workbench.app import Workbench
from workbench.adapters.competitor_discovery import CompetitorDiscoveryAdapter
from workbench.adapters import competitor_discovery as discovery_module
from workbench.core.competitor_markets import GLOBAL_MARKETS


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("discovery_worker_tests", ROOT / "workbench" / "review_scraper_worker.py")
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


@pytest.fixture
def setup(tmp_path):
    bench = Workbench(tmp_path / "data", runner=lambda _: "not called")
    project = bench.create_project("搜索测试", "仅测试，不是真实研究")
    yield bench, project
    bench.close()


def test_search_cache_read_only_and_copy_isolation(setup, monkeypatch):
    bench, project = setup
    calls = []
    def provider(request):
        calls.append(request)
        return {"items": [{"app_id": "com.example.test", "title": "Test", "platform": "google_play"}], "warnings": ["测试替身"]}
    object.__setattr__(bench.competitor_discovery, "_worker_request", provider)
    request = {"query": "GBA", "country": "us", "lang": "en", "limit": 12}
    first = bench.search_competitors(project["id"], request)
    assert first["cached"] is False
    first["items"][0]["title"] = "mutated"
    second = bench.search_competitors(project["id"], request)
    assert second["cached"] is True
    assert second["items"][0]["title"] == "Test"
    assert len(calls) == 1
    bench.search_competitors(project["id"], {**request, "country": "gb"})
    bench.search_competitors(project["id"], {**request, "refresh": True})
    assert len(calls) == 3
    assert bench.rows("SELECT id FROM scrapes") == []
    assert bench.rows("SELECT id FROM documents") == []
    assert bench.rows("SELECT id FROM jobs") == []


def test_cache_is_bounded_expires_and_detail_separate(setup, monkeypatch):
    bench, project = setup
    adapter = bench.competitor_discovery
    clock = [100.0]
    # Check cache expiry, not whether SQLite/CI completes the next request in
    # ten real milliseconds. Keep the fake clock local to this adapter module.
    monkeypatch.setattr(discovery_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    object.__setattr__(adapter, "CACHE_LIMIT", 2)
    object.__setattr__(adapter, "TTL", 0.01)
    object.__setattr__(adapter, "_worker_request", lambda request: {"listing": {"app_id": request.get("app_id"), "screenshot_urls": []}} if request["mode"] == "discovery_detail" else {"items": []})
    for query in ("one", "two", "three"):
        bench.search_competitors(project["id"], {"query": query})
    assert len(adapter._cache) == 2
    result = bench.competitor_detail(project["id"], {"app_id": "com.example.test"})
    assert result["cached"] is False
    assert bench.competitor_detail(project["id"], {"app_id": "com.example.test"})["cached"] is True
    clock[0] += 0.02
    assert bench.competitor_detail(project["id"], {"app_id": "com.example.test"})["cached"] is False


@pytest.mark.parametrize("payload", [
    {"query": ""}, {"query": "x" * 161}, {"query": "x\nfoo"},
    {"query": "GBA", "platform": "https://evil.example"},
    {"query": "GBA", "country": "usa"}, {"query": "GBA", "lang": "../../"},
    {"query": "GBA", "limit": 31}, {"query": "GBA", "limit": True},
    {"query": "GBA", "limit": 2.5}, {"query": "GBA", "refresh": "yes"},
])
def test_invalid_search_requests_rejected_without_network(setup, monkeypatch, payload):
    bench, project = setup
    object.__setattr__(bench.competitor_discovery, "_worker_request", lambda _: pytest.fail("must not call provider"))
    with pytest.raises(ValueError):
        bench.search_competitors(project["id"], payload)


def test_project_and_version_scope_checked(setup, monkeypatch):
    bench, project = setup
    other = bench.create_project("另一项目", "")
    version = bench.create_product_version(other["id"], {"name": "v1"})
    object.__setattr__(bench.competitor_discovery, "_worker_request", lambda _: pytest.fail("must not call provider"))
    with pytest.raises(ValueError):
        bench.search_competitors(project["id"], {"query": "GBA", "version_id": version["id"]})
    with pytest.raises(ValueError):
        bench.search_competitors("nonexistent", {"query": "GBA"})
    with pytest.raises(ValueError, match="数字"):
        bench.competitor_detail(project["id"], {"platform": "app_store", "app_id": "com.bad"})


def test_search_concurrency_and_failed_results_not_cached(setup, monkeypatch):
    bench, project = setup
    adapter = bench.competitor_discovery
    adapter._slots.acquire()
    adapter._slots.acquire()
    with pytest.raises(ValueError, match="两个"):
        bench.search_competitors(project["id"], {"query": "GBA"})
    adapter._slots.release()
    adapter._slots.release()
    object.__setattr__(adapter, "_worker_request", lambda _: {"items": "invalid"})
    with pytest.raises(ValueError, match="候选列表"):
        bench.search_competitors(project["id"], {"query": "GBA"})
    assert len(adapter._cache) == 0


def test_worker_google_search_has_no_detail_reviews_or_ai_fanout(tmp_path):
    root = tmp_path / "tool"
    (root / "app").mkdir(parents=True)
    (root / "app" / "scrapers.py").write_text("raise RuntimeError('do not import review pipeline')", encoding="utf-8")
    (root / "google_play_scraper.py").write_text(
        "def search(query, n_hits, lang, country):\n"
        "    assert (query,n_hits,lang,country)==('GBA',12,'en','us')\n"
        "    return [{'appId':'com.test.gba','title':'测试 👌','summary':'Play games','score':4.5,'free':True}]\n"
        "def app(*args, **kwargs):\n"
        "    raise RuntimeError('search must not fetch details')\n",
        encoding="utf-8",
    )
    payload = {"mode": "discovery_search", "root": str(root), "platform": "google_play", "query": "GBA", "limit": 12, "country": "us", "lang": "en"}
    result = subprocess.run([sys.executable, str(ROOT / "workbench" / "review_scraper_worker.py")], input=json.dumps(payload).encode(), capture_output=True, timeout=10)
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["items"][0]["title"] == "测试 👌"
    assert value["items"][0]["ratings"] is None
    assert value["items"][0]["contains_ads"] is None
    assert value["items"][0]["offers_iap"] is None
    assert value["items"][0]["free"] is True


def test_worker_capability_error_does_not_expose_exception(tmp_path):
    root = tmp_path / "tool"
    (root / "app").mkdir(parents=True)
    (root / "app" / "scrapers.py").write_text("", encoding="utf-8")
    module = root / "google_play_scraper.py"
    module.write_text("other = 1", encoding="utf-8")
    request = {"mode": "discovery_search", "root": str(root), "platform": "google_play", "query": "GBA", "limit": 12}
    result = subprocess.run([sys.executable, str(ROOT / "workbench" / "review_scraper_worker.py")], input=json.dumps(request).encode(), capture_output=True, timeout=10)
    assert json.loads(result.stdout) == {"error_code": "unsupported_capability"}
    module.write_text("def search(*args, **kwargs):\n    raise RuntimeError('Bearer sk-secret-token https://user:password@proxy.example')", encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "workbench" / "review_scraper_worker.py")], input=json.dumps(request).encode(), capture_output=True, timeout=10)
    assert json.loads(result.stdout) == {"error_code": "store_error"}
    assert b"secret" not in result.stdout


def test_apple_search_and_detail_do_not_guess_missing_fields(monkeypatch, tmp_path):
    calls = []
    def apple(endpoint, params):
        calls.append((endpoint, params))
        return {"results": [{"trackId": 123, "trackName": "Test", "description": "Only long description", "price": 0, "screenshotUrls": ["https://is1-ssl.mzstatic.com/test.png"]}]}
    monkeypatch.setattr(worker, "_apple_discovery_request", apple)
    result = worker._discovery({"mode": "discovery_search", "platform": "app_store", "query": "emulator", "limit": 12}, tmp_path)
    assert result["items"][0]["short_description"] == ""
    assert result["items"][0]["contains_ads"] is None
    assert result["items"][0]["installs"] == ""
    detail = worker._discovery({"mode": "discovery_detail", "platform": "app_store", "app_id": "123"}, tmp_path)
    assert detail["listing"]["long_description"] == "Only long description"
    assert detail["listing"]["short_description"] == ""
    assert detail["listing"]["screenshot_urls"] == ["https://is1-ssl.mzstatic.com/test.png"]
    assert [call[0] for call in calls] == ["search", "lookup"]


def test_selection_validation_and_confirmed_listing_metadata(setup, tmp_path):
    bench, project = setup
    entries = [{"platform": "google_play", "app_id": "com.test.gba"}]
    selection = {"platform": "google_play", "app_id": "com.test.gba", "role": "feature", "note": "仅参考存档模块", "query": "GBA emulator"}
    adapter = bench.review_scraper
    assert adapter._selection_metadata([selection], entries)[("google_play", "com.test.gba")]["role"] == "feature"
    for invalid in ([], [selection, selection], [{**selection, "app_id": "com.other"}], [{**selection, "role": "auto"}], [{**selection, "note": "x" * 1001}]):
        with pytest.raises(ValueError):
            adapter._selection_metadata(invalid, entries)
    listing = {"platform": "google_play", "app_id": "com.test.gba", "title": "Test", "short_description": "Short", "long_description": "Long"}
    markdown = adapter._listing_markdown(listing, selection)
    assert "功能参考" in markdown
    assert "仅参考存档模块" in markdown
    assert "GBA emulator" in markdown
    assert "人工选用信息" in markdown


def test_selection_discovery_market_kept_separate_from_collection_market(setup):
    bench, _ = setup
    entries = [{"platform": "google_play", "app_id": "com.test.gba"}]
    selection = {"platform": "google_play", "app_id": "com.test.gba", "role": "primary", "query": "GBA", "search_country": "US"}
    normalized = bench.review_scraper._selection_metadata([selection], entries)[("google_play", "com.test.gba")]
    assert normalized["search_country"] == "us"
    markdown = bench.review_scraper._listing_markdown({"platform": "google_play", "app_id": "com.test.gba", "market": "GB"}, normalized)
    assert "- 市场：GB" in markdown
    assert "- 发现市场：US" in markdown
    assert "实际采集市场以本页“市场”字段为准" in markdown
    for invalid in ("usa", "../us", "1s"):
        with pytest.raises(ValueError, match="发现市场"):
            bench.review_scraper._selection_metadata([{**selection, "search_country": invalid}], entries)
    old = bench.review_scraper._selection_metadata([{key: value for key, value in selection.items() if key != "search_country"}], entries)
    assert "search_country" not in old[("google_play", "com.test.gba")]


def test_review_and_screenshot_preview_bounded_and_safe(setup):
    bench, project = setup
    scrape = {"project_id": project["id"], "id": "test"}
    directory = bench.review_scraper._collection_directory(scrape)
    directory.mkdir(parents=True)
    (directory / "reviews.csv").write_bytes(bench._review_csv([{"content": f"original {i}", "translated_content": f"译文 {i}", "score": 5} for i in range(20)]))
    rows = bench.review_scraper._review_samples(scrape)
    assert len(rows) == 5
    assert rows[0]["original_content"] == "original 0"
    assert rows[0]["translated_content"] == "译文 0"
    urls = bench.review_scraper._screenshot_preview_urls({"screenshot_urls": ["http://127.0.0.1/private", "https://evil.example/screenshot.png", "https://user:secret@is1-ssl.mzstatic.com/foo.png", "https://is1-ssl.mzstatic.com/ok.png", "https://play-lh.googleusercontent.com/ok.png"]})
    assert urls == ["https://is1-ssl.mzstatic.com/ok.png", "https://play-lh.googleusercontent.com/ok.png"]


def test_worker_timeout_stops_process_and_clears_registry(setup, monkeypatch):
    bench, _ = setup
    stopped = []
    monkeypatch.setattr(bench, "review_scraper_settings", lambda: {"ready": False, "enabled": False, "root": "", "python": ""})
    class Process:
        def __init__(self, *args, **kwargs):
            assert "-X" in args[0]
            assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        def communicate(self, *args, **kwargs):
            raise subprocess.TimeoutExpired("test", 35)
        def wait(self, timeout):
            return 0
        def kill(self):
            stopped.append(self)
    monkeypatch.setattr(discovery_module.subprocess, "Popen", Process)
    with pytest.raises(ValueError, match="35 秒"):
        bench.competitor_discovery._worker_request({"mode": "discovery_search", "platform": "app_store", "query": "test"})
    assert len(stopped) == 1
    assert bench.processes == {}


@pytest.mark.parametrize("body,code,match", [
    (b'{"error_code":"missing_dependency","error":"Bearer sk-private"}', 1, "依赖"),
    (b'{"error_code":"network_error","error":"https://user:secret@proxy.example"}', 1, "网络"),
    (b'not JSON sk-private', 0, "格式"),
    (b'[]', 0, "格式"),
])
def test_worker_protocol_errors_are_safe(setup, monkeypatch, body, code, match):
    bench, _ = setup
    monkeypatch.setattr(bench, "review_scraper_settings", lambda: {"ready": False, "enabled": False, "root": "", "python": ""})
    class Process:
        def __init__(self, *args, **kwargs):
            self.returncode = code
            kwargs["stdout"].write(body)
            kwargs["stderr"].write(b"Bearer sk-private")
        def communicate(self, *args, **kwargs):
            return None, None
    monkeypatch.setattr(discovery_module.subprocess, "Popen", Process)
    with pytest.raises(ValueError, match=match) as error:
        bench.competitor_discovery._worker_request({"mode": "discovery_search", "platform": "app_store", "query": "test"})
    assert "sk-private" not in str(error.value)
    assert "secret" not in str(error.value)
    assert bench.processes == {}


def test_worker_response_size_limit(setup, monkeypatch):
    bench, _ = setup
    monkeypatch.setattr(bench, "review_scraper_settings", lambda: {"ready": False, "enabled": False, "root": "", "python": ""})
    object.__setattr__(bench.competitor_discovery, "MAX_RESULT_BYTES", 10)
    class Process:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            kwargs["stdout"].write(b"x" * 11)
        def communicate(self, *args, **kwargs):
            return None, None
    monkeypatch.setattr(discovery_module.subprocess, "Popen", Process)
    with pytest.raises(ValueError, match="过大"):
        bench.competitor_discovery._worker_request({"mode": "discovery_search", "platform": "app_store", "query": "test"})


def test_global_search_round_robin_dedup_and_country_metadata(setup):
    bench, project = setup
    calls, active, peak = [], 0, 0
    lock = threading.Lock()
    def provider(request):
        nonlocal active, peak
        country = request["country"]
        assert country != "global"
        assert 0 < request["_timeout_seconds"] <= 12
        with lock:
            calls.append(country)
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return {"items": [{"platform": "google_play", "app_id": f"com.{country}.first", "score": 4.1}, {"platform": "google_play", "app_id": "com.shared", "score": 4.7}, {"platform": "google_play", "app_id": f"com.{country}.third"}], "warnings": []}
    object.__setattr__(bench.competitor_discovery, "_worker_request", provider)
    result = bench.search_competitors(project["id"], {"query": "GBA", "country": "global", "limit": 12})
    assert result["scope"] == "global_multi_market"
    assert result["countries"] == list(GLOBAL_MARKETS)
    assert result["successful_countries"] == list(GLOBAL_MARKETS)
    assert result["failed_countries"] == []
    assert result["attempted_countries"] == list(GLOBAL_MARKETS)
    assert [item["app_id"] for item in result["items"][:8]] == [f"com.{country}.first" for country in GLOBAL_MARKETS]
    shared = next(item for item in result["items"] if item["app_id"] == "com.shared")
    assert shared["observed_countries"] == list(GLOBAL_MARKETS)
    assert shared["lookup_country"] == "us"
    assert len(result["items"]) == 12
    assert peak <= 2
    assert set(calls) == set(GLOBAL_MARKETS)
    again = bench.search_competitors(project["id"], {"query": "GBA", "country": "global", "limit": 12})
    assert again["cached"] is True
    assert len(calls) == 8
    assert bench.rows("SELECT id FROM documents") == []
    assert bench.rows("SELECT id FROM scrapes") == []


def test_global_partial_success_empty_success_and_all_failures(setup):
    bench, project = setup
    calls = []
    def partial(request):
        calls.append(request["country"])
        if request["country"] != "jp":
            raise ValueError("private proxy password must not be exposed")
        return {"items": [], "warnings": []}
    object.__setattr__(bench.competitor_discovery, "_worker_request", partial)
    result = bench.search_competitors(project["id"], {"query": "empty", "country": "global"})
    assert result["items"] == []
    assert result["successful_countries"] == ["jp"]
    assert result["failed_countries"] == [country for country in GLOBAL_MARKETS if country != "jp"]
    assert result["cached"] is False
    assert "private" not in json.dumps(result)
    assert "password" not in json.dumps(result)
    bench.search_competitors(project["id"], {"query": "empty", "country": "global"})
    assert calls.count("jp") == 1  # successful concrete-market cache reused
    assert calls.count("us") == 2  # failed markets retried, not cached for 24h
    object.__setattr__(bench.competitor_discovery, "_worker_request", lambda _: (_ for _ in ()).throw(ValueError("secret")))
    with pytest.raises(ValueError, match="全部失败.*未回退美国"):
        bench.search_competitors(project["id"], {"query": "allfail", "country": "global"})


def test_global_reuses_single_market_cache_and_detail_requires_concrete_country(setup):
    bench, project = setup
    calls = []
    def provider(request):
        calls.append(request)
        return {"listing": {"app_id": request.get("app_id")}} if request["mode"] == "discovery_detail" else {"items": []}
    object.__setattr__(bench.competitor_discovery, "_worker_request", provider)
    single = bench.search_competitors(project["id"], {"query": "cached", "country": "gb"})
    assert single["scope"] == "single_market"
    bench.search_competitors(project["id"], {"query": "cached", "country": "global"})
    assert len(calls) == 8
    with pytest.raises(ValueError, match="lookup_country"):
        bench.competitor_detail(project["id"], {"country": "global", "app_id": "com.test.gba"})
    result = bench.competitor_detail(project["id"], {"country": "global", "lookup_country": "JP", "app_id": "com.test.gba"})
    assert result["lookup_country"] == "jp"
    assert calls[-1]["country"] == "jp"


def test_global_closed_and_duplicate_batches_rejected(setup):
    bench, project = setup
    adapter = bench.competitor_discovery
    adapter._global_slots.acquire()
    with pytest.raises(ValueError, match="多市场搜索"):
        bench.search_competitors(project["id"], {"query": "test", "country": "global"})
    adapter._global_slots.release()
    object.__setattr__(adapter, "_worker_request", lambda request: (adapter.close() or {"items": []}))
    result = bench.search_competitors(project["id"], {"query": "test", "country": "global"})
    assert len(result["successful_countries"]) <= 2
    assert result["failed_countries"]
    with pytest.raises(ValueError, match="关闭"):
        bench.search_competitors(project["id"], {"query": "after close", "country": "us"})


def test_global_collection_expansion_and_selection_provenance(setup, monkeypatch):
    bench, project = setup
    # Queue only: do not run the collector, network, screenshots, translation or AI.
    monkeypatch.setattr(threading.Thread, "start", lambda _: None)
    result = bench.start_competitor_collection(project["id"], {
        "entries": ["com.test.gba", "123"], "countries": ["global", "us", "gb"], "count_per_country": 150,
        "selections": [{"platform": "google_play", "app_id": "com.test.gba", "role": "primary", "search_country": "global", "lookup_country": "jp", "observed_countries": ["jp", "us", "jp"]}, {"platform": "app_store", "app_id": "123", "role": "feature"}],
    })
    assert result["countries"] == list(GLOBAL_MARKETS)
    assert result["total_review_fetch_limit"] == 8 * (150 + 100)
    assert any("不是所有国家" in warning for warning in result["warnings"])
    google_request = json.loads(next(item for item in result["items"] if item["platform"] == "google_play")["request"])
    assert google_request["countries"] == list(GLOBAL_MARKETS)
    assert "global" not in google_request["countries"]
    assert google_request["requested_countries"] == ["global", "us", "gb"]
    assert google_request["selection"]["search_country"] == "global"
    assert google_request["selection"]["observed_countries"] == ["jp", "us"]
    text = bench.review_scraper._listing_markdown({"platform": "google_play", "market": "US"}, google_request["selection"])
    assert "非所有国家或全球榜" in text
    assert "候选详情参考市场：JP" in text


@pytest.mark.parametrize("metadata", [
    {"lookup_country": "global"}, {"observed_countries": ["global"]},
    {"observed_countries": "us"}, {"lookup_country": "jp", "observed_countries": ["us"]},
])
def test_global_selection_provenance_rejects_bad_countries(setup, metadata):
    bench, _ = setup
    entry = {"platform": "google_play", "app_id": "com.test.gba"}
    with pytest.raises(ValueError):
        bench.review_scraper._selection_metadata([{**entry, "role": "primary", **metadata}], [entry])


@pytest.mark.parametrize("selection,countries,expected", [
    ({"lookup_country": "jp", "observed_countries": ["br", "jp"]}, ["us", "jp", "br"], "jp"),
    ({"lookup_country": "jp", "observed_countries": ["jp"]}, ["us", "br"], "us"),
    ({"observed_countries": ["br"]}, ["us", "br", "jp"], "br"),
    ({}, ["us", "br", "jp"], "us"),
    ({"lookup_country": "jp", "observed_countries": ["br", "jp"]}, ["us", "br"], "br"),
    ({"lookup_country": "global", "observed_countries": ["global", "JP"]}, ["us", "jp"], "jp"),
])
def test_listing_country_uses_only_selected_markets_without_changing_review_scope(selection, countries, expected):
    unchanged = list(countries)
    assert worker._listing_country({"selection": selection}, countries) == expected
    assert countries == unchanged
    assert expected in countries


def test_listing_country_rejects_global_without_concrete_selected_country():
    with pytest.raises(ValueError, match="具体国家"):
        worker._listing_country({"selection": {"lookup_country": "us"}}, ["global"])
