"""Frozen builds use the bundled collector without inheriting a developer's tool path."""

import json
import sys
from types import SimpleNamespace

import pytest

from workbench import app
from workbench.adapters import competitor_discovery as discovery_module
from workbench.adapters import review_scraper as scraper_module


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path / "data", runner=lambda _: "unused")
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def builtin(tmp_path, monkeypatch):
    package_root = tmp_path / "bundle" / "packages" / "competitor-collector"
    source = package_root / "competitor_collector"
    source.mkdir(parents=True)
    for filename in ("engine.py", "scrapers.py"):
        (source / filename).write_text("# synthetic resource\n", encoding="utf-8")
    monkeypatch.setattr(scraper_module, "ROOT", tmp_path / "bundle")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("WORKBENCH_REVIEW_SCRAPER_ROOT", raising=False)
    return package_root


def save_preferences(bench, value):
    with bench.db() as db:
        db.execute("INSERT OR REPLACE INTO preferences VALUES(?,?)", (scraper_module.REVIEW_SCRAPER_CONFIG_KEY, json.dumps(value)))


def test_frozen_without_explicit_legacy_root_uses_bundled_collector(bench, builtin):
    settings = bench.review_scraper_settings()
    assert settings["backend"] == "builtin"
    assert settings["root"] == str(builtin)
    assert settings["worker_root"] == ""
    assert settings["python"] == sys.executable
    assert settings["ready"] is True
    assert settings["enabled"] is True
    save_preferences(bench, {"enabled": False})
    assert bench.review_scraper_settings()["enabled"] is False


def test_frozen_incomplete_collector_resources_are_not_ready(bench, builtin):
    (builtin / "competitor_collector" / "scrapers.py").unlink()
    settings = bench.review_scraper_settings()
    assert settings["backend"] == "builtin"
    assert settings["ready"] is False
    assert "不完整" in settings["message"]


def test_frozen_form_settings_round_trip_keeps_builtin_backend(bench, builtin):
    result = bench.save_review_scraper_settings({'root': str(builtin), 'enabled': True})
    assert result['backend'] == 'builtin'
    saved = json.loads(bench.rows('SELECT value FROM preferences WHERE key=?', (scraper_module.REVIEW_SCRAPER_CONFIG_KEY,))[0]['value'])
    assert saved == {'enabled': True}
    assert bench.save_review_scraper_settings({'enabled': False})['enabled'] is False


@pytest.mark.parametrize("source", ["saved", "environment"])
def test_explicit_legacy_root_still_takes_precedence_in_frozen_build(bench, builtin, tmp_path, monkeypatch, source):
    legacy = tmp_path / "legacy"
    (legacy / "app").mkdir(parents=True)
    (legacy / "app" / "scrapers.py").write_text("# legacy provider\n", encoding="utf-8")
    if source == "saved":
        save_preferences(bench, {"root": str(legacy), "python": sys.executable})
    else:
        monkeypatch.setenv("WORKBENCH_REVIEW_SCRAPER_ROOT", str(legacy))
    settings = bench.review_scraper_settings()
    assert settings["backend"] == "legacy"
    assert settings["root"] == settings["worker_root"] == str(legacy.resolve())
    assert settings["ready"] is True


def test_nonfrozen_mode_keeps_legacy_settings(bench, builtin, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False)
    legacy = tmp_path / "legacy"
    (legacy / "app").mkdir(parents=True)
    (legacy / "app" / "scrapers.py").write_text("# legacy provider\n", encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_REVIEW_SCRAPER_ROOT", str(legacy))
    assert bench.review_scraper_settings()["backend"] == "legacy"


@pytest.mark.parametrize("translate", [False, True])
def test_frozen_collection_worker_uses_native_root_and_explicit_free_translation(bench, builtin, monkeypatch, translate):
    project = bench.create_project("可移植采集", "")
    scrape_id = "c" * 32
    request = {"platform": "google_play", "app_id": "com.example.synthetic", "countries": ["us"], "translate": translate}
    with bench.db() as db:
        db.execute(
            "INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (scrape_id, project["id"], "google_play", request["app_id"], json.dumps(request), "queued", "", "2026-10-22", "2026-10-22", "", ""),
        )
    calls = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            calls.append({"command": command, "cwd": kwargs["cwd"]})

        def communicate(self, content, timeout):
            calls[-1]["payload"] = json.loads(content)
            return json.dumps({"reviews": [{"review_id": "r1", "content": "Original review", "original_content": "Original review", "translated_content": "中文译文" if translate else "", "score": 4}], "warnings": []}).encode(), b""

    monkeypatch.setattr(scraper_module.subprocess, "Popen", Process)
    bench.review_scraper._run_review_scrape(scrape_id)
    assert calls[0]["cwd"] == str(builtin)
    assert calls[0]["command"][0] == sys.executable
    payload = calls[0]["payload"]
    assert payload["root"] == ""
    assert payload["translate"] is translate
    assert payload.get("translation_provider") == ("google" if translate else None)
    result = bench.scrape(scrape_id)
    assert result["status"] == "completed"
    document = bench.document(result["result_doc_id"])
    assert "Original review" in document["text"]
    assert ("中文译文" in document["text"]) is translate


def test_frozen_explicit_retranslation_uses_google_and_keeps_original_items(bench, builtin, monkeypatch):
    items = [{"text": "Original review", "language": "en"}]
    calls = []

    def run(command, **kwargs):
        calls.append({"command": command, "cwd": kwargs["cwd"], "payload": json.loads(kwargs["input"])})
        return SimpleNamespace(returncode=0, stdout=json.dumps({"translations": ["中文译文"], "provider": "google"}).encode(), stderr=b"")

    monkeypatch.setattr(scraper_module.subprocess, "run", run)
    result = bench.review_scraper._translate_items(items)
    assert result["provider"] == "google"
    assert calls[0]["cwd"] == str(builtin)
    assert calls[0]["payload"]["root"] == ""
    assert calls[0]["payload"]["translation_provider"] == "google"
    assert calls[0]["payload"]["items"] == items == [{"text": "Original review", "language": "en"}]


def test_frozen_discovery_worker_uses_native_root_and_bundle_cwd(bench, builtin, monkeypatch):
    calls = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            self.output = kwargs["stdout"]
            calls.append({"command": command, "cwd": kwargs["cwd"]})

        def communicate(self, content, timeout):
            calls[-1]["payload"] = json.loads(content)
            self.output.write(b'{"items":[],"warnings":[]}')

    monkeypatch.setattr(discovery_module.subprocess, "Popen", Process)
    result = bench.competitor_discovery._worker_request({"mode": "discovery_search", "platform": "google_play", "query": "synthetic"})
    assert result == {"items": [], "warnings": []}
    assert calls[0]["command"][0] == sys.executable
    assert calls[0]["cwd"] == str(builtin)
    assert calls[0]["payload"]["root"] == ""
    assert "translation_provider" not in calls[0]["payload"]
