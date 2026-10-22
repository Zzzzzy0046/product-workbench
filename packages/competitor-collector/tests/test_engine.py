from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from competitor_collector import engine, scrapers


def request(**values):
    return {"app_id": "com.example.app", "countries": ["us"], **values}


def test_native_review_preserves_17_fields_without_pydantic():
    value = scrapers.Review("r1", "👍", original_content="👍")
    dumped = value.model_dump(mode="json")
    assert len(dumped) == 17
    assert dumped["translated_content"] is None
    assert dumped["original_content"] == "👍"


def test_native_collection_uses_local_scrapers_without_desktop(monkeypatch):
    calls = []
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: calls.append((args, kwargs)) or [scrapers.Review("r1", "works", score=5)])
    result = engine.collect(request())
    assert result["reviews"][0]["content"] == "works"
    assert calls[0][0] == ("com.example.app", ["us"])
    assert calls[0][1]["count_per_country"] == 100
    assert result["filter_stats"] == {"active": False, "fetched": 1, "kept": 1}


def test_default_never_calls_translation(monkeypatch):
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: [scrapers.Review("r1", "hello")])
    monkeypatch.setattr(engine, "_translate_items", lambda *args, **kwargs: pytest.fail("translation must be opt in"))
    assert engine.collect(request())["reviews"]


def test_listing_only_and_no_images_do_not_call_reviews_or_download(monkeypatch, tmp_path):
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: pytest.fail("not requested"))
    monkeypatch.setattr(engine, "_download_screenshots", lambda *args: pytest.fail("not requested"))
    monkeypatch.setattr(engine, "_google_listing", lambda *args: {"app_id": "com.example.app", "screenshot_urls": ["https://play-lh.googleusercontent.com/test.png"]})
    result = engine.collect(request(collect_listing=True, collect_reviews=False, download_screenshots=False, output_dir=str(tmp_path)))
    assert result["reviews"] == []
    assert result["listing"]["screenshot_files"] == []
    assert result["listing"]["collected_at"]


def test_listing_failure_retains_reviews_without_exception_secrets(monkeypatch):
    monkeypatch.setattr(engine, "_google_listing", lambda *args: (_ for _ in ()).throw(ConnectionError("https://secret:password@proxy.invalid")))
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: [scrapers.Review("r1", "hello")])
    result = engine.collect(request(collect_listing=True))
    assert result["listing"] is None and result["reviews"]
    assert "secret" not in json.dumps(result)


def test_app_store_preserves_effective_100_limit(monkeypatch):
    calls = []
    monkeypatch.setattr(scrapers, "scrape_app_store", lambda *args, **kwargs: calls.append(kwargs) or [])
    result = engine.collect(request(platform="app_store", app_id="123", count_per_country=500))
    assert calls[0]["count_per_country"] == 100
    assert calls[0]["translate"] is False
    assert any("100" in warning for warning in result["warnings"])


def test_global_expands_and_is_not_passed_to_store(monkeypatch):
    calls = []
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: calls.append(args) or [])
    result = engine.collect(request(countries=["global", "US"]))
    assert calls[0][1] == ["us", "gb", "de", "jp", "in", "id", "br", "sa"]
    assert "并非所有国家" in result["warnings"][0]


@pytest.mark.parametrize("values", [
    {"countries": []}, {"countries": ["us;rm"]}, {"count_per_country": 501},
    {"platform": "unsupported"}, {"app_id": "https://host.invalid"},
    {"sort": "random"}, {"date_from": "2026-10-21", "date_to": "2026-10-01"},
])
def test_invalid_inputs_never_fetch(values, monkeypatch):
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: pytest.fail("invalid request fetched"))
    with pytest.raises(ValueError):
        engine.collect(request(**values))


def test_explicit_invalid_root_never_falls_back_to_native(tmp_path, monkeypatch):
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: pytest.fail("fallback forbidden"))
    with pytest.raises(ValueError, match="app/scrapers.py"):
        engine.collect(request(root=str(tmp_path)))


def test_native_google_search_does_not_import_desktop_or_fetch_details(monkeypatch):
    calls = []
    fake = SimpleNamespace(search=lambda query, **kwargs: calls.append((query, kwargs)) or [{"appId": "com.example.result", "title": "Result"}], app=lambda *args: pytest.fail("no detail fanout"))
    monkeypatch.setitem(sys.modules, "google_play_scraper", fake)
    result = engine.collect({"mode": "discovery_search", "platform": "google_play", "query": "gba", "limit": 12})
    assert result["items"][0]["app_id"] == "com.example.result"
    assert len(calls) == 1


def test_native_translation_requires_explicit_provider(monkeypatch):
    monkeypatch.setattr(scrapers, "scrape_google_play", lambda *args, **kwargs: pytest.fail("must validate before network"))
    with pytest.raises(ValueError, match="translation_provider"):
        engine.collect(request(translate=True))


def test_native_google_translation_deduplicates_and_preserves_alignment(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "_translate_google", lambda text: calls.append(text) or "你好")
    monkeypatch.setattr(engine, "_translate_ai_batch", lambda *args: pytest.fail("wrong provider"))
    result = engine.collect({"mode": "translate", "translation_provider": "google", "items": [{"text": "hello"}, {"text": "hello"}, {"text": "中文", "language": "zh"}]})
    assert result["translations"] == ["你好", "你好", ""]
    assert calls == ["hello"]
    assert result["provider"] == "google"


def test_native_openai_failure_never_sends_to_google_or_leaks_error(monkeypatch):
    monkeypatch.setattr(engine, "_translate_ai_batch", lambda *args: (_ for _ in ()).throw(RuntimeError("private-api-key")))
    monkeypatch.setattr(engine, "_translate_google", lambda *args: pytest.fail("cross provider fallback forbidden"))
    result = engine.collect({"mode": "translate", "translation_provider": "openai", "items": [{"text": "hello"}]})
    assert result["failed_count"] == 1
    assert "private" not in json.dumps(result)


class Response:
    def __init__(self, content=b"", *, status=200, headers=None, chunks=None):
        self.content = content
        self.status_code = status
        self.headers = headers or {}
        self.chunks = chunks
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http failed")

    def iter_content(self, chunk_size):
        yield from self.chunks if self.chunks is not None else [self.content]

    def close(self):
        self.closed = True


def png():
    from PIL import Image
    stream = io.BytesIO()
    Image.new("RGB", (4, 8), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_screenshot_stream_validates_pixels_and_closes_response(monkeypatch):
    import requests
    response = Response(png(), headers={"Content-Type": "text/html"})
    calls = []
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: calls.append((url, kwargs)) or response)
    content, extension = engine._read_screenshot("https://play-lh.googleusercontent.com/image")
    assert content == png() and extension == ".png"
    assert calls[0][1]["stream"] is True and calls[0][1]["allow_redirects"] is False
    assert response.closed


@pytest.mark.parametrize("url", [
    "http://play-lh.googleusercontent.com/x", "https://127.0.0.1/x",
    "https://play-lh.googleusercontent.com.evil.invalid/x",
    "https://user:password@play-lh.googleusercontent.com/x",
    "https://play-lh.googleusercontent.com:8443/x",
])
def test_screenshot_url_rejected_before_network(url, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: pytest.fail("untrusted URL fetched"))
    with pytest.raises(ValueError):
        engine._read_screenshot(url)


def test_redirect_to_untrusted_host_never_followed(monkeypatch):
    import requests
    calls = []
    response = Response(status=302, headers={"Location": "https://127.0.0.1/secret"})
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: calls.append(args) or response)
    with pytest.raises(ValueError, match="origin"):
        engine._read_screenshot("https://is1.mzstatic.com/x")
    assert len(calls) == 1 and response.closed


def test_stream_size_limit_even_without_content_length(monkeypatch):
    import requests
    response = Response(chunks=[b"x" * (6 * 1024 * 1024)] * 3)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="too_large"):
        engine._read_screenshot("https://is1.mzstatic.com/x")
    assert response.closed


def test_html_disguised_as_image_never_saved(monkeypatch, tmp_path):
    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response(b"<html>no</html>", headers={"Content-Type": "image/png"}))
    warnings = []
    assert engine._download_screenshots({"screenshot_urls": ["https://is1.mzstatic.com/x"]}, tmp_path, warnings) == []
    assert not list(tmp_path.iterdir()) and warnings


def test_download_limit_and_isolated_failure(monkeypatch, tmp_path):
    calls = []
    def read(url):
        calls.append(url)
        if len(calls) == 2:
            raise ValueError("contains-private-secret")
        return png(), ".png"
    monkeypatch.setattr(engine, "_read_screenshot", read)
    warnings = []
    result = engine._download_screenshots({"screenshot_urls": [f"https://is1.mzstatic.com/{i}" for i in range(30)]}, tmp_path, warnings)
    assert len(calls) == 20 and len(result) == 19
    assert "02.png" not in result and "20.png" in result
    assert "secret" not in json.dumps(warnings)


def test_all_filters_preserve_original_fields():
    rows = [{"content": "freeze", "score": 1, "version": "1.2", "thumbs_up_count": 5, "reply_content": "hi"}, {"content": "good", "score": 5}]
    result, stats = engine._filter_reviews(rows, {"ratings": [1], "include_keywords": ["FREEZE"], "exclude_keywords": ["ads"], "reply_filter": "replied", "version_filter": "1.2", "min_thumbs_up": 3})
    assert result == rows[:1]
    assert stats == {"active": True, "fetched": 2, "kept": 1}


@pytest.mark.parametrize("error", [ValueError("https://username:password@proxy.invalid"), RuntimeError("private-api-key")])
def test_safe_exception_never_prints_arbitrary_provider_details(error):
    result = engine._safe_exception_message(error)
    assert "password" not in result and "api-key" not in result


def test_safe_exception_retains_deliberate_validation_message():
    assert engine._safe_exception_message(ValueError("需要有效的应用 ID。")) == "需要有效的应用 ID。"
