"""Content-based upstream review hints, with no real model calls."""

import json

import pytest

from scripts.workbench_flow_smoke import SECTION_OUTPUTS
from workbench.app import Workbench


@pytest.fixture
def chain(tmp_path):
    bench = Workbench(tmp_path, runner=lambda _: "unused test fixture")
    project = bench.create_project("上游时效测试", "只测试文档来源状态，不作真实产品结论。")
    jobs = []
    for task_id, output in list(SECTION_OUTPUTS.items())[:2]:
        job = bench.prepare(project["id"], task_id, "固定测试替身")
        bench.complete(job["id"], output, "imported")
        jobs.append(bench.review(job["id"], "accepted", "确认测试替身"))
    try:
        yield bench, project, jobs
    finally:
        bench.close()


def test_upstream_content_change_warns_without_rewriting_or_revoking_review(chain):
    bench, _, (first, second) = chain
    before_sources = {item["source_id"]: item["text"] for item in second["sources"]}
    original_output = second["output"]
    bench.edit_output(first["id"], first["output"] + "\n本轮新决定 A。", "同秒改稿")
    draft_warning = bench.job(second["id"])
    assert {item["reason"] for item in draft_warning["stale_upstream"]} == {"unconfirmed"}
    bench.review(first["id"], "accepted", "确认第一章新决定")
    stale = bench.job(second["id"])
    assert {item["reason"] for item in stale["stale_upstream"]} == {"changed"}
    assert stale["review"]["decision"] == "accepted"
    assert stale["output"] == original_output
    assert stale["quality"]["errors"] == 0
    assert any(item["code"] == "upstream-changed" for item in stale["quality"]["issues"])
    assert {item["source_id"]: item["text"] for item in stale["sources"]} == before_sources
    assert stale["current_version"] == second["current_version"]


def test_reconfirm_acknowledges_current_upstream_then_warns_again_on_next_change(chain):
    bench, _, (first, second) = chain
    bench.edit_output(first["id"], first["output"] + "\n决定 A。", "变更 A")
    bench.review(first["id"], "accepted", "确认 A")
    assert bench.job(second["id"])["stale_upstream"]
    acknowledged = bench.review(second["id"], "accepted", "复核后第二章仍适用")
    assert not acknowledged["stale_upstream"]
    assert any(item.get("reviewed_upstream_digest") for item in acknowledged["sources"])
    bench.edit_output(first["id"], first["output"] + "\n决定 B。", "变更 B")
    bench.review(first["id"], "accepted", "确认 B")
    assert bench.job(second["id"])["stale_upstream"]


def test_same_content_new_version_does_not_warn(chain):
    bench, project, (first, second) = chain
    newer = bench.prepare(project["id"], first["task_id"], "同内容新任务")
    bench.complete(newer["id"], first["output"], "imported")
    bench.review(newer["id"], "accepted", "确认同内容")
    assert not bench.job(second["id"])["stale_upstream"]


def test_archived_upstream_gets_missing_not_changed_warning(chain):
    bench, _, (first, second) = chain
    bench.archive_job(first["id"], True)
    stale = bench.job(second["id"])
    assert {item["reason"] for item in stale["stale_upstream"]} == {"missing"}
    assert stale["review"]["decision"] == "accepted"


def test_legacy_full_snapshot_can_be_compared_and_acknowledged(chain):
    bench, _, (first, second) = chain
    sources = [{key: value for key, value in source.items() if key not in {"upstream_task_id", "upstream_digest", "reviewed_upstream_digest"}} for source in second["sources"]]
    with bench.db() as db:
        db.execute("UPDATE jobs SET sources=? WHERE id=?", (json.dumps(sources), second["id"]))
    assert not bench.job(second["id"])["stale_upstream"]
    bench.edit_output(first["id"], first["output"] + "\n旧快照之后的决定。", "旧格式快照测试")
    bench.review(first["id"], "accepted", "确认决定")
    assert bench.job(second["id"])["stale_upstream"]
    assert not bench.review(second["id"], "accepted", "复核旧格式来源")["stale_upstream"]


def test_assembly_warns_about_stale_chapters_until_chapters_are_reconfirmed(chain):
    bench, project, jobs = chain
    for task_id, output in list(SECTION_OUTPUTS.items())[2:]:
        job = bench.prepare(project["id"], task_id, "固定测试替身")
        bench.complete(job["id"], output, "imported")
        jobs.append(bench.review(job["id"], "accepted", "确认测试替身"))
    first = jobs[0]
    bench.edit_output(first["id"], first["output"] + "\n新决定影响后文。", "修改前章")
    bench.review(first["id"], "accepted", "确认修改")
    merged = bench.assemble_sections(project["id"])
    assert merged["status"] == "completed"
    assert merged["quality"]["errors"] == 0
    assert any(item.get("via_job_id") == jobs[1]["id"] for item in merged["stale_upstream"])
    assert bench.review(merged["id"], "accepted", "合并确认不能代替逐章复核")["stale_upstream"]
    for job in jobs[1:]:
        bench.review(job["id"], "accepted", "逐章复核后仍适用")
    assert not bench.job(merged["id"])["stale_upstream"]


def test_acknowledgement_survives_export_import_id_remap(chain):
    bench, project, (first, second) = chain
    bench.edit_output(first["id"], first["output"] + "\n确认新增规则。", "变更")
    bench.review(first["id"], "accepted", "确认")
    bench.review(second["id"], "accepted", "复核后仍适用")
    package, _ = bench.export_project(project["id"])
    imported = bench.import_project(package)
    restored = bench.job(bench.rows("SELECT id FROM jobs WHERE project_id=? AND task_id=?", (imported["id"], second["task_id"]))[0]["id"])
    assert not restored["stale_upstream"]
    assert restored["review"]["decision"] == "accepted"
    assert second["id"] not in {source["source_id"] for source in restored["sources"]}


def test_digest_normalizes_citation_numbers_but_not_business_content(chain):
    bench, project, _ = chain
    digest = bench.job_service._upstream_digest
    assert digest(project["id"], "规则 A [S1]\r\n") == digest(project["id"], "规则 A [S99]\n")
    assert digest(project["id"], "规则 A [S1]") != digest(project["id"], "规则 B [S1]")
