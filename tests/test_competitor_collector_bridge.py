"""Offline compatibility tests for the old workbench worker entry point.

No real store or translation provider is contacted.  Each subprocess gets an
explicit temporary legacy backend so its behavior remains deterministic.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "workbench" / "review_scraper_worker.py"


def _load_worker():
    spec = importlib.util.spec_from_file_location("collector_bridge_compat_tests", WORKER)
    module = importlib.util.module_from_spec(spec)
    # Deliberately mirror the existing tests: the module is NOT registered in
    # sys.modules. Replacing sys.modules[__name__] alone cannot satisfy this use.
    spec.loader.exec_module(module)
    return module


def _legacy_tool(tmp_path: Path) -> Path:
    root = tmp_path / "legacy-tool"
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "scrapers.py").write_text(
        "GOOGLE_LANGS = {'us': 'en'}\n"
        "def scrape_google_play(app_id, countries, **kwargs):\n"
        "    return [{'review_id':'legacy-r1','content':'真实评论 👎 中文','score':1,'app_id':app_id,'market':countries[0]}]\n"
        "def scrape_app_store(*args, **kwargs):\n"
        "    return []\n",
        encoding="utf-8",
    )
    return root


def _run_worker(payload, cwd, *, env=None, isolated=False):
    command = [sys.executable]
    if isolated:
        command.append("-I")
    command.append(str(WORKER))
    return subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        cwd=cwd,
        env=env,
        timeout=20,
        check=False,
    )


def test_legacy_private_functions_keep_the_shim_globals(monkeypatch, tmp_path):
    worker = _load_worker()
    calls = []

    def translate(texts, root):
        calls.append((list(texts), root))
        if len(texts) > 1:
            raise ValueError("split this batch")
        return ["译文：" + texts[0]]

    monkeypatch.setattr(worker, "_translate_ai_batch", translate)
    result = worker._translate_items(
        [{"text": "First", "language": "en"}, {"text": "Second", "language": "en"}],
        tmp_path,
    )
    assert worker._translate_items.__globals__ is worker.__dict__
    assert worker._translate_resilient.__globals__ is worker.__dict__
    assert result["translations"] == ["译文：First", "译文：Second"]
    assert [values for values, _ in calls] == [["First", "Second"], ["First"], ["Second"]]


def test_legacy_discovery_private_provider_remains_patchable(monkeypatch, tmp_path):
    worker = _load_worker()
    calls = []

    def apple(endpoint, params):
        calls.append((endpoint, params))
        return {"results": [{"trackId": 123, "trackName": "测试应用", "description": "Long only"}]}

    monkeypatch.setattr(worker, "_apple_discovery_request", apple)
    result = worker._discovery(
        {"mode": "discovery_search", "platform": "app_store", "query": "test", "limit": 12},
        tmp_path,
    )
    assert worker._discovery.__globals__ is worker.__dict__
    assert result["items"][0]["title"] == "测试应用"
    assert result["items"][0]["short_description"] == ""
    assert len(calls) == 1
    assert calls[0][0] == "search"


def test_old_cli_loads_shared_core_from_a_foreign_cwd(tmp_path):
    tool = _legacy_tool(tmp_path)
    foreign = tmp_path / "unrelated-working-directory"
    foreign.mkdir()
    result = _run_worker(
        {"root": str(tool), "platform": "google_play", "app_id": "com.test.legacy", "countries": ["us"]},
        foreign,
        isolated=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    body = json.loads(result.stdout)
    assert body["reviews"][0]["review_id"] == "legacy-r1"
    assert body["reviews"][0]["content"] == "真实评论 👎 中文"
    assert body["filter_stats"] == {"active": False, "fetched": 1, "kept": 1}


def test_old_cli_keeps_utf8_json_when_parent_requests_gbk(tmp_path):
    tool = _legacy_tool(tmp_path)
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "gbk"
    result = _run_worker(
        {"root": str(tool), "platform": "google_play", "app_id": "com.test.legacy", "countries": ["us"]},
        tmp_path,
        env=environment,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert json.loads(result.stdout.decode("utf-8"))["reviews"][0]["content"] == "真实评论 👎 中文"


def test_old_entry_point_does_not_import_workbench_application(tmp_path):
    code = (
        "import importlib.util,sys; "
        "spec=importlib.util.spec_from_file_location('isolated_collector_bridge',sys.argv[1]); "
        "module=importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module); "
        "assert callable(module.main); "
        "assert not any(name=='workbench' or name.startswith('workbench.') for name in sys.modules); "
        "assert module._translate_items.__globals__ is module.__dict__"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(WORKER)],
        cwd=tmp_path,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert not result.stdout


def test_legacy_discovery_keeps_stdout_json_and_does_not_import_reviews(tmp_path):
    tool = _legacy_tool(tmp_path)
    (tool / "app" / "scrapers.py").write_text("raise AssertionError('review backend must not load')\n", encoding="utf-8")
    (tool / "google_play_scraper.py").write_text(
        "def search(query, n_hits, lang, country):\n"
        "    return [{'appId':'com.test.onlysearch','title':'结果 👌','score':4.5}]\n"
        "def app(*args, **kwargs):\n"
        "    raise AssertionError('details must not load')\n",
        encoding="utf-8",
    )
    result = _run_worker(
        {"mode": "discovery_search", "root": str(tool), "platform": "google_play", "query": "GBA", "limit": 12},
        tmp_path,
        isolated=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert json.loads(result.stdout)["items"][0]["title"] == "结果 👌"
    assert len(result.stdout.strip().splitlines()) == 1


def test_legacy_invalid_explicit_root_returns_protocol_error_without_fallback(tmp_path):
    result = _run_worker(
        {"root": str(tmp_path / "does-not-exist"), "platform": "google_play", "app_id": "com.test", "countries": ["us"]},
        tmp_path,
        isolated=True,
    )
    assert result.returncode == 1
    body = json.loads(result.stdout)
    assert body.get("error")
    assert "reviews" not in body


def test_legacy_discovery_failure_never_leaks_provider_exception(tmp_path):
    tool = _legacy_tool(tmp_path)
    (tool / "google_play_scraper.py").write_text(
        "def search(*args, **kwargs):\n"
        "    raise RuntimeError('Bearer sk-do-not-output https://user:password@private.example')\n",
        encoding="utf-8",
    )
    result = _run_worker(
        {"mode": "discovery_search", "root": str(tool), "platform": "google_play", "query": "test", "limit": 12},
        tmp_path,
        isolated=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"error_code": "store_error"}
    assert b"sk-do-not-output" not in result.stdout
    assert b"password" not in result.stdout
