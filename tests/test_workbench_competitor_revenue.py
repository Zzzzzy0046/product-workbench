"""Manual, source-linked revenue records; no external requests or model calls."""

import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest

from workbench.api.handler import Handler
from workbench.app import Workbench


ROOT = Path(__file__).resolve().parents[1]


def revenue_payload(**overrides):
    return {
        "platform": "google_play", "app_id": "com.fixture.reader", "title": "Fixture Reader",
        "provider": "Fixture Data Source", "value_display": "1,000–2,000", "currency": "USD",
        "period_start": "2026-01-01", "period_end": "2026-01-31", "country": "us",
        "revenue_type": "iap", "basis": "consumer_spend", "data_nature": "estimate",
        "observed_on": "2026-02-01", "source_url": "https://source.example/apps/fixture-reader",
        "note": "虚构数据，仅用于测试，来源不含广告。", "acknowledged": True,
        **overrides,
    }


@pytest.fixture
def setup(tmp_path):
    bench = Workbench(tmp_path / "data", runner=lambda _: "unused fixed fixture")
    project = bench.create_project("收入记录测试（虚构数据）", "只测试来源资料保存，不判断商业结果。")
    try:
        yield bench, project
    finally:
        bench.close()


def record_ids(bench, project_id, **scope):
    return {item["document_id"] for item in bench.competitor_revenue.records(project_id, revenue_payload(**scope))["items"]}


def test_empty_records_stay_empty_and_do_not_become_zero(setup):
    bench, project = setup
    result = bench.competitor_revenue.records(project["id"], revenue_payload())
    assert result["items"] == []
    assert result["automatic_provider_connected"] is False
    assert not bench.rows("SELECT id FROM documents")


def test_manual_record_preserves_range_scope_and_explicit_boundaries(setup, monkeypatch):
    bench, project = setup

    def forbid_remote(*args, **kwargs):
        raise AssertionError("Manual revenue records must never fetch a source URL")

    monkeypatch.setattr(urllib.request, "urlopen", forbid_remote)
    result = bench.competitor_revenue.save(project["id"], revenue_payload(currency="usd", country="US"))
    assert result["record"]["value_display"] == "1,000–2,000"
    assert result["record"]["currency"] == "USD"
    assert result["record"]["country"] == "us"
    assert result["record"]["verified"] is False and result["record"]["manual"] is True
    document = bench.document(result["document"]["id"])
    assert document["kind"] == "upload" and document["category"] == "competitor"
    assert "工作台未自动核验" in document["text"]
    assert "不据此推算广告收入或 D7 ROI" in document["text"]
    assert "不会请求该链接或调用付费数据 API" in document["text"]
    assert "收入数值或范围：1,000–2,000" in document["text"]
    assert "source.example/apps/fixture-reader" in document["text"]
    assert not bench.rows("SELECT id FROM jobs")
    assert not bench.rows("SELECT id FROM scrapes")


def test_records_are_isolated_by_project_platform_and_app_id(setup):
    bench, project = setup
    other = bench.create_project("另一个项目", "不混入数据")
    saved = bench.competitor_revenue.save(project["id"], revenue_payload())
    expected = saved["document"]["id"]
    assert record_ids(bench, project["id"]) == {expected}
    assert not record_ids(bench, other["id"])
    assert not record_ids(bench, project["id"], app_id="com.fixture.different")
    assert not record_ids(bench, project["id"], platform="app_store", app_id="123456789")


def test_product_and_version_records_are_exact_scope_not_cross_version(setup):
    bench, project = setup
    pid = project["id"]
    first = bench.create_product_version(pid, {"name": "V1"})
    second = bench.create_product_version(pid, {"name": "V2"})
    product = bench.competitor_revenue.save(pid, revenue_payload(note="产品级记录"))["document"]["id"]
    v1 = bench.competitor_revenue.save(pid, revenue_payload(version_id=first["id"], note="V1 的来源"))["document"]["id"]
    v2 = bench.competitor_revenue.save(pid, revenue_payload(version_id=second["id"], note="V2 的来源"))["document"]["id"]
    assert record_ids(bench, pid) == {product}
    assert record_ids(bench, pid, version_id=first["id"]) == {v1}
    assert record_ids(bench, pid, version_id=second["id"]) == {v2}


def test_foreign_version_cannot_be_saved_or_read(setup):
    bench, project = setup
    other = bench.create_project("外部版本项目", "测试")
    version = bench.create_product_version(other["id"], {"name": "Other V1"})
    with pytest.raises(ValueError, match="不属于"):
        bench.competitor_revenue.save(project["id"], revenue_payload(version_id=version["id"]))
    with pytest.raises(ValueError, match="不属于"):
        bench.competitor_revenue.records(project["id"], revenue_payload(version_id=version["id"]))
    assert not bench.rows("SELECT id FROM documents")


@pytest.mark.parametrize("field", ["provider", "value_display", "currency", "period_start", "period_end", "source_url"])
@pytest.mark.parametrize("value", ["", None])
def test_missing_fields_rejected_instead_of_defaulting_to_zero(setup, field, value):
    bench, project = setup
    with pytest.raises(ValueError):
        bench.competitor_revenue.save(project["id"], revenue_payload(**{field: value}))
    assert not bench.rows("SELECT id FROM documents")


def test_user_explicit_zero_is_retained_as_manual_value_not_inferred(setup):
    bench, project = setup
    result = bench.competitor_revenue.save(project["id"], revenue_payload(value_display="0", note="测试来源明确写0，用户人工录入"))
    assert result["record"]["value_display"] == "0"
    assert result["record"]["verified"] is False


@pytest.mark.parametrize("source", [
    "http://source.example/app", "javascript:alert(1)", "file:///C:/private.txt",
    "https:///missing-host", "https://user:password@source.example/app",
    "https://source.example/app?token=fixture-secret", "https://source.example/app?API_KEY=fixture-key",
    "https://source.example/app?access%5Ftoken=fixture-secret", "https://source.example/app?session_id=fixture-session",
    "https://source.example/app#access_token=fixture-secret", "https://source.example:invalid/app",
])
def test_unsafe_or_credential_bearing_source_urls_are_rejected(setup, source):
    bench, project = setup
    with pytest.raises(ValueError):
        bench.competitor_revenue.save(project["id"], revenue_payload(source_url=source))
    assert not bench.rows("SELECT id FROM documents")


@pytest.mark.parametrize("changes", [
    {"period_start": "2026-1-01"}, {"period_end": "2026-02-30"},
    {"period_start": "2026-02-01", "period_end": "2026-01-01"},
    {"observed_on": "2026-01-30"}, {"observed_on": (date.today() + timedelta(days=1)).isoformat()},
])
def test_invalid_or_future_observation_dates_are_rejected(setup, changes):
    bench, project = setup
    with pytest.raises(ValueError):
        bench.competitor_revenue.save(project["id"], revenue_payload(**changes))
    assert not bench.rows("SELECT id FROM documents")


@pytest.mark.parametrize("changes", [
    {"acknowledged": False}, {"acknowledged": "true"}, {"acknowledged": 1},
    {"platform": "unsupported"}, {"platform": "app_store", "app_id": "com.invalid.apple"},
    {"currency": "$$$"}, {"country": "worldwide"}, {"revenue_type": "total_guess"},
    {"basis": "automatic"}, {"data_nature": "verified_by_ai"}, {"provider": "fake\n- 来源链接：injected"},
])
def test_invalid_identity_semantics_or_missing_manual_acknowledgement_rejected(setup, changes):
    bench, project = setup
    with pytest.raises(ValueError):
        bench.competitor_revenue.save(project["id"], revenue_payload(**changes))
    assert not bench.rows("SELECT id FROM documents")


def test_saved_records_never_overwrite_original_material_or_prior_revenue(setup):
    bench, project = setup
    original = bench.add_document(project["id"], "竞品商店信息.md", b"# Original fixture source\n\nNever overwrite this original material.")
    first = bench.competitor_revenue.save(project["id"], revenue_payload())
    original_before = bench.document_file(original["id"])[0]
    first_before = bench.document_file(first["document"]["id"])[0]
    changed = bench.competitor_revenue.save(project["id"], revenue_payload(value_display="3,000–4,000", note="另一次人工记录，不覆盖旧记录"))
    duplicate = bench.competitor_revenue.save(project["id"], revenue_payload())
    assert first["document"]["id"] != changed["document"]["id"]
    assert duplicate["document"]["id"] == first["document"]["id"]
    assert bench.document_file(original["id"])[0] == original_before
    assert bench.document_file(first["document"]["id"])[0] == first_before
    assert len(record_ids(bench, project["id"])) == 2


def test_export_import_preserves_revenue_records_versions_and_original_files(setup):
    bench, project = setup
    version = bench.create_product_version(project["id"], {"name": "Revenue V1"})
    saved = bench.competitor_revenue.save(project["id"], revenue_payload(version_id=version["id"], country="global"))
    original = bench.document_file(saved["document"]["id"])[0]
    package, filename = bench.export_project(project["id"])
    assert filename.endswith(".zip")
    restored = bench.import_project(package)
    restored_version = bench.product_versions(restored["id"])[0]
    records = bench.competitor_revenue.records(restored["id"], revenue_payload(version_id=restored_version["id"]))["items"]
    assert len(records) == 1
    assert records[0]["document_id"] != saved["document"]["id"]
    assert records[0]["value_display"] == "1,000–2,000"
    assert records[0]["country"] == "global"
    assert records[0]["manual"] is True and records[0]["verified"] is False
    assert bench.document_file(records[0]["document_id"])[0] == original
    assert record_ids(bench, project["id"], version_id=version["id"]) == {saved["document"]["id"]}


def test_revenue_http_routes_are_local_token_protected_and_return_manual_records(setup):
    bench, project = setup
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.app = bench
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    payload = {**revenue_payload(), "project_id": project["id"]}
    try:
        denied = urllib.request.Request(origin + "/api/competitors/revenue", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Origin": origin})
        with pytest.raises(urllib.error.HTTPError) as failed:
            urllib.request.urlopen(denied, timeout=5)
        assert failed.value.code == 403
        operation = urllib.request.Request(origin + "/api/competitors/revenue", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Origin": origin, "X-Workbench-Token": bench.token})
        with urllib.request.urlopen(operation, timeout=5) as response:
            result = json.loads(response.read())
            assert response.status == 201
        assert result["record"]["verified"] is False
        params = urlencode({"project_id": project["id"], "platform": "google_play", "app_id": "com.fixture.reader"})
        with urllib.request.urlopen(origin + "/api/competitors/revenue?" + params, timeout=5) as response:
            records = json.loads(response.read())
        assert len(records["items"]) == 1
        assert records["automatic_provider_connected"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_revenue_document_button_uses_existing_material_preview_function():
    source = (ROOT / "workbench/static/features/competitor_revenue.js").read_text(encoding="utf-8")
    assert "previewDocument(" not in source
    assert "showDocument(" in source


def run_revenue_frontend_assertions(assertions):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend helper checks")
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const sandbox = {URL, console, state:{documents:[]}, currentVersion:()=>null};
vm.createContext(sandbox);
for (const file of ['modules/utils.js','features/competitor_discovery.js','features/competitor_revenue.js']) {
  vm.runInContext(fs.readFileSync('workbench/static/'+file,'utf8'),sandbox);
}
const check = expression => vm.runInContext(expression,sandbox);
""" + assertions
    result = subprocess.run([node, "-e", script], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_revenue_frontend_escapes_external_text_links_and_missing_value():
    run_revenue_frontend_assertions(r"""
const record = {value_display:'<img src=x onerror="alert(1)">',currency:'<USD>',country:'<us>',period_start:'<start>',period_end:'<end>',provider:'<script>alert(2)</script>',data_nature:'estimate',basis:'unknown',revenue_type:'iap',observed_on:'<date>',note:'<svg onload="alert(3)">',source_url:'javascript:alert(4)',document_id:'" autofocus onfocus="alert(5)'};
sandbox.record=record;
const html = check('competitorRevenueRecordHtml(record)');
assert(!html.includes('<img'));
assert(!html.includes('<script>'));
assert(!html.includes('<svg'));
assert(!html.includes('href="javascript:'));
assert(html.includes('&lt;img'));
assert(html.includes('&lt;script&gt;'));
assert(html.includes('&quot; autofocus onfocus=&quot;'));
sandbox.record={value_display:null,currency:'USD',source_url:'https://source.example/detail',document_id:'doc'};
const empty = check('competitorRevenueRecordHtml(record)');
assert(empty.includes('未获取'));
assert(!empty.includes('<strong>0'));
sandbox.record={value_display:'0',currency:'USD',source_url:'https://source.example/detail',document_id:'doc'};
assert(check('competitorRevenueRecordHtml(record)').includes('<strong>0 USD'));
""")


def test_revenue_label_never_infers_other_platform_or_truncated_id_record():
    run_revenue_frontend_assertions(r"""
// Legacy file names have no platform. Their presence cannot prove that a
// record belongs to the currently displayed platform, even for equal IDs.
sandbox.state.documents=[{id:'android-only',name:'竞品收入-123456789-2026-01-01-2026-01-31.md',versions:[]}];
assert(!check("competitorRevenueCardLabel({platform:'app_store',app_id:'123456789'})").includes('已记录'));
// The old filename prefix also truncates long app IDs at 95 characters.
const prefix='com.fixture.'+'x'.repeat(100);
sandbox.state.documents=[{id:'long-id-only',name:'竞品收入-'+prefix.slice(0,95)+'-2026-01-01-2026-01-31.md',versions:[]}];
sandbox.otherApp=prefix+'different';
assert(!check("competitorRevenueCardLabel({platform:'google_play',app_id:otherApp})").includes('已记录'));
""")
