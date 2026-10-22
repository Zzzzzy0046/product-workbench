"""Do not fill a short description from a different store field."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from competitor_collector import engine
from competitor_collector.exports import write_evidence


def test_apple_promotion_is_not_subtitle(monkeypatch):
    response = SimpleNamespace(raise_for_status=lambda: None,
        json=lambda: {'results': [{'trackName': 'Fixture', 'promotionalText': 'Promo only', 'description': 'Long only'}]})
    monkeypatch.setitem(sys.modules, 'requests', SimpleNamespace(get=lambda *args, **kwargs: response))
    warnings = []
    listing = engine._app_store_listing('12345', 'us', warnings)
    assert listing['short_description'] == ''
    assert listing['promotional_text'] == 'Promo only'
    assert listing['long_description'] == 'Long only'
    assert warnings
    assert engine._candidate({'trackId': 12345, 'promotionalText': 'Promo only'}, 'app_store', 'us')['short_description'] == ''


def test_google_missing_summary_not_filled_from_long_description():
    assert engine._candidate({'appId': 'com.fixture', 'description': 'Long only'}, 'google_play', 'us')['short_description'] == ''


def test_excel_whitespace_formula_is_escaped_without_changing_source(tmp_path):
    text = '\t =HYPERLINK("https://example.com")'
    write_evidence(tmp_path, {'reviews': [{'content': text, 'original_content': text}]}, {'app_id': 'com.fixture'})
    assert b"'\t =HYPERLINK" in (tmp_path / 'reviews.csv').read_bytes()
    assert json.loads((tmp_path / 'result.json').read_text(encoding='utf-8'))['reviews'][0]['original_content'] == text


def test_cli_shows_safe_password_rule_without_creating_user(tmp_path, monkeypatch, capsys):
    from competitor_collector import cli
    from competitor_collector.auth import AuthStore
    monkeypatch.setattr(cli.getpass, 'getpass', lambda prompt: 'short')
    assert cli.main(['init-admin', '--username', 'new_admin', '--data-dir', str(tmp_path)]) == 1
    assert '10–128' in capsys.readouterr().err
    assert AuthStore(tmp_path / 'auth.sqlite3').has_users() is False
