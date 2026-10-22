from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from competitor_collector import cli, engine
from competitor_collector.exports import REVIEW_FIELDS, write_evidence
from competitor_collector.request_spec import GLOBAL_MARKETS, normalize_request


def request(**values):
    return {"entries": ["com.example.app"], **values}


def test_normalization_detects_platform_and_deduplicates_without_search():
    result = normalize_request(request(entries="com.example.app\nhttps://play.google.com/store/apps/details?id=com.example.app&gl=gb\nhttps://apps.apple.com/us/app/example/id123?l=en\n123"))
    assert result["entries"] == [
        {"platform": "google_play", "app_id": "com.example.app", "source_url": "https://play.google.com/store/apps/details?id=com.example.app"},
        {"platform": "app_store", "app_id": "123", "source_url": "https://apps.apple.com/app/id123"},
    ]
    assert result["translate"] is False


def test_normalization_drops_paths_credentials_and_unknown_keys():
    result = normalize_request(request(root="C:/private/tool", output_dir="C:/private", api_key="secret", password="secret", unknown=True))
    assert not {"root", "output_dir", "api_key", "password", "unknown"} & result.keys()


def test_global_market_scope_explicit_and_deduplicated():
    result = normalize_request(request(countries=["GLOBAL", "US", "ca"]))
    assert result["countries"] == [*GLOBAL_MARKETS, "ca"]
    assert result["requested_countries"] == ["global", "us", "ca"]
    assert result["collection_scope"] == "global_multi_market"


@pytest.mark.parametrize("values", [
    {"entries": []}, {"entries": [f"com.example.app{i}" for i in range(21)]},
    {"entries": ["https://evil.invalid/app?id=hello"]},
    {"entries": ["https://user:secret@play.google.com/store/apps/details?id=x"]},
    {"countries": ["xx"]}, {"countries": ["uk"]}, {"countries": []},
    {"count_per_country": 0}, {"count_per_country": 501}, {"count_per_country": True},
    {"ratings": [6]}, {"ratings": [True]}, {"date_from": "bad"},
    {"date_from": "2026-10-21", "date_to": "2026-01-01"},
    {"sort": "random"}, {"reply_filter": "yes"}, {"min_thumbs_up": -1},
    {"include_keywords": ["x" * 81]}, {"translate": "false"},
    {"translate": True}, {"translate": True, "translation_provider": "unknown"},
    {"collect_listing": False, "collect_reviews": False, "download_screenshots": False},
])
def test_invalid_request_rejected(values):
    with pytest.raises(ValueError):
        normalize_request(request(**values))


def test_screenshots_enable_listing_and_translation_only_explicit_provider():
    result = normalize_request(request(collect_listing=False, download_screenshots=True, translate=True, translation_provider="google"))
    assert result["collect_listing"] is True
    assert result["translation_provider"] == "google"


def test_review_filters_keep_strict_types_and_casefold_dedupe():
    result = normalize_request(request(ratings="1,3,3", include_keywords="ads, ADS,crash", exclude_keywords=["boring"], reply_filter="unreplied", version_filter=" 1.2 ", min_thumbs_up=5))
    assert result["ratings"] == [1, 3]
    assert result["include_keywords"] == ["ads", "crash"]
    assert result["version_filter"] == "1.2"


def test_export_preserves_original_translation_and_guarded_csv(tmp_path):
    rows = [{"review_id": "r1", "content": "=HYPERLINK(\"evil\")", "original_content": "原文 👍", "translated_content": "译文", "score": 5}]
    result = write_evidence(tmp_path, {"listing": {"title": "测试应用", "short_description": "原短描述", "long_description": "原长描述"}, "reviews": rows}, {"app_id": "com.example", "root": "secret-path", "api_key": "secret-key", "output_dir": "private"})
    raw = (tmp_path / "reviews.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    csv_rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert tuple(csv_rows[0]) == REVIEW_FIELDS
    assert csv_rows[0]["content"].startswith("'=")
    assert csv_rows[0]["original_content"] == "原文 👍"
    assert csv_rows[0]["translated_content"] == "译文"
    snapshot = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert snapshot["reviews"][0]["content"].startswith("=")
    manifest = (tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert "secret-path" not in manifest and "secret-key" not in manifest and "private" not in manifest
    markdown = (tmp_path / "store-listing.md").read_text(encoding="utf-8")
    assert "原短描述" in markdown and "原长描述" in markdown
    assert result["review_count"] == 1 and result["status"] == "completed"


def test_export_screenshots_are_owned_relative_files_only(tmp_path):
    directory = tmp_path / "item"
    (directory / "screenshots").mkdir(parents=True)
    (directory / "screenshots" / "01.png").write_bytes(b"fixture")
    outside = tmp_path / "private.png"
    outside.write_bytes(b"private")
    result = write_evidence(directory, {"listing": {"title": "App", "screenshot_files": ["01.png", "01.png", "../private.png", str(outside), "missing.png", "01.png:secret", "https://host/1.png"]}, "reviews": []}, {})
    assert result["screenshots"] == [{"name": "01.png", "relative_path": "screenshots/01.png"}]
    assert result["listing"]["screenshot_files"] == ["screenshots/01.png"]
    assert result["screenshot_count"] == 1 and result["status"] == "partial"


def test_export_empty_results_are_failed_not_success(tmp_path):
    result = write_evidence(tmp_path, {"listing": None, "reviews": []}, {})
    assert result["status"] == "failed" and result["warnings"]
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_export_samples_bounded_and_unknown_metadata_secrets_dropped(tmp_path):
    result = write_evidence(tmp_path, {"listing": {"title": "App", "api_key": "private", "source_url": "https://play.google.com/store/apps/details?id=x&api_key=hidden"}, "reviews": [{"review_id": str(i), "content": "hi", "private_key": "secret"} for i in range(25)], "api_key": "private", "warnings": ["https://user:pass@proxy.invalid token=hidden"]}, {})
    assert len(result["review_samples"]) == 20
    text = (tmp_path / "result.json").read_text(encoding="utf-8")
    assert "private" not in text and "hidden" not in text and "user:pass" not in text


def test_cli_serve_imports_on_demand_and_passes_explicit_arguments(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setitem(sys.modules, "competitor_collector.server", SimpleNamespace(serve=lambda **kwargs: calls.append(kwargs)))
    assert cli.main(["serve", "--data-dir", str(tmp_path), "--port", "9876", "--open"]) == 0
    assert calls == [{"data_dir": tmp_path.resolve(), "host": "127.0.0.1", "port": 9876, "open_browser": True}]


def test_cli_account_password_is_getpass_only(monkeypatch, tmp_path, capsys):
    calls = []
    class Auth:
        def __init__(self, path):
            calls.append(("path", path))
        def bootstrap_admin(self, username, password):
            calls.append(("bootstrap", username, password))
        def recover_admin(self, username, password):
            calls.append(("recover", username, password))
    monkeypatch.setitem(sys.modules, "competitor_collector.auth", SimpleNamespace(AuthStore=Auth))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "nonexported-pass")
    assert cli.main(["init-admin", "--username", "simon", "--data-dir", str(tmp_path)]) == 0
    assert calls[1] == ("bootstrap", "simon", "nonexported-pass")
    assert "nonexported-pass" not in capsys.readouterr().out


def test_cli_mismatched_password_does_not_change_account(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "competitor_collector.auth", SimpleNamespace(AuthStore=lambda *args: pytest.fail("must not open auth DB")))
    values = iter(["password-one", "password-two"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(values))
    assert cli.main(["init-admin", "--username", "simon", "--data-dir", str(tmp_path)]) == 1


def test_cli_collect_calls_native_engine_and_exports(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(engine, "collect", lambda payload: calls.append(payload) or {"listing": {"title": "Mock"}, "reviews": []})
    assert cli.main(["collect", "--app", "com.example.app", "--countries", "us", "gb", "--count", "10", "--out", str(tmp_path)]) == 0
    assert "root" not in calls[0] and calls[0]["countries"] == ["us", "gb"]
    output = json.loads(capsys.readouterr().out)
    assert Path(output["directory"]).is_dir()
    assert (Path(output["items"][0]["directory"]) / "manifest.json").is_file()


def test_copied_package_runs_from_unrelated_folder_without_workbench(tmp_path):
    copied = tmp_path / "portable"
    copied.mkdir()
    shutil.copytree(PACKAGE / "competitor_collector", copied / "competitor_collector", ignore=shutil.ignore_patterns("__pycache__"))
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import competitor_collector.cli as cli; "
        "assert 'workbench' not in sys.modules; "
        "assert 'competitor_collector.engine' not in sys.modules; "
        "assert str(cli.default_data_dir()) == sys.argv[2]; "
        "raise SystemExit(cli.main(['--help']))"
    )
    completed = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", code, str(copied), str(copied / "data")], cwd=cwd, capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr.decode("utf-8")
    assert b"init-admin" in completed.stdout and b"serve" in completed.stdout
