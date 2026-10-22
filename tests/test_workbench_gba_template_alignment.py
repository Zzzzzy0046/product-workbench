"""Source reuse and real-evidence checks for the GBA-derived template update."""

import pytest

from workbench import app
from workbench.validators import validate


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path, runner=lambda _: "unused")
    instance.retrieval_mode = "keyword"
    yield instance
    instance.close()


def confirm(bench, project_id, task_id, output):
    job = bench.prepare(project_id, task_id, "只处理本轮当前资料")
    bench.complete(job["id"], output)
    bench.review(job["id"], "accepted", "采用当前明确口径")
    return bench.job(job["id"])


def test_f3_receives_existing_case_ids_and_tracking_without_independent_prd(bench, monkeypatch):
    project = bench.create_project("已有用例直接实测", "只核对当前范围")
    case_text = """# 产品验收用例

| 验收场景 | 操作步骤 | 预期结果 |
|---|---|---|
| 3.2 取消后保留输入 | 在内容页输入名称并取消保存。 | 回到来源，保留已确认数据，不把未保存草稿当成成功结果。 |
"""
    cases = confirm(bench, project["id"], "fast/product-acceptance", case_text)
    events = confirm(bench, project["id"], "fast/tracking-spec", """# 完整埋点方案

| 事件 ID | 中文名称 | 事件类型 | 触发时机 | 分析问题 | 来源页面 / 状态 |
|---|---|---|---|---|---|
| content_save_result | 保存结果 | result | 实际保存完成回调 | 保存是否完成 | 内容页 |

固定参数沿用已确认方案；页面展示和点击不代表保存成功，不新增同义事件。
""")
    monkeypatch.setattr(bench, "search", lambda *args: [])
    job = bench.prepare(project["id"], "fast/acceptance", "沿用已有用例与事件")
    sources = {source["source_id"]: source for source in job["sources"]}
    assert {cases["id"], events["id"]} <= sources.keys()
    assert case_text.strip() == sources[cases["id"]]["text"].strip()
    assert "content_save_result" in sources[events["id"]]["text"]
    assert "已有已确认产品验收用例，沿用原用例及预期" in job["prompt"]
    assert "验收场景 | 操作步骤 | 预期结果 | 实测结果" in job["prompt"]
    assert "5–8 个核心事件" not in job["prompt"]
    # Preparation is not a document mutation or a claim of completed testing.
    assert bench.job(cases["id"])["output"] == cases["output"]
    assert bench.job(events["id"])["output"] == events["output"]
    assert job["output"] == "" and job["status"] == "prepared"


@pytest.mark.parametrize("evidence", ["", "尚未提供", "尚未产生", "无"])
def test_f3_scenario_column_cannot_bypass_pass_evidence(evidence):
    output = f"""# F3 开发验收清单

构建版本和设备尚未提供，实测结果及复测待补。

| 验收场景 | 操作步骤 | 预期结果 | 实测结果 | 状态 | 证据 / 修改与复测 |
|---|---|---|---|---|---|
| 3.2 原用例 | 执行保存 | 展示保存结果 | 与预期一致 | PASS | {evidence} |
"""
    codes = {issue["code"] for issue in validate("fast/acceptance", output, sources=[])}
    assert "f3-pass-without-evidence" in codes
    assert "f3-pass-row-without-evidence" in codes


def test_f3_scenario_pass_accepts_uploaded_linked_test_record():
    output = """# F3 开发验收清单

构建版本、设备与实际结果见报告，复测无新增问题。

| 验收场景 | 操作步骤 | 预期结果 | 实测结果 | 状态 | 证据 / 修改与复测 |
|---|---|---|---|---|---|
| 3.2 原用例 | 执行保存 | 展示保存结果 | 与预期一致 | 通过 | 测试报告 [S1] |
"""
    sources = [{"kind": "upload", "name": "本轮测试报告.txt", "text": "构建与设备实测记录", "citation": "S1"}]
    issues = validate("fast/acceptance", output, sources=sources)
    assert not any(issue["code"].startswith("f3-pass-") for issue in issues)


def test_f3_tracking_rows_also_need_per_row_evidence():
    output = """# F3 开发验收清单

| 原事件 ID | 来源方案 / 对应操作 | 预期触发与参数 | 实际日志 / 证据 | 状态 | 修改与复测 |
|---|---|---|---|---|---|
| content_save_result | 保存 | result=success | | PASS | 无 |
"""
    sources = [{"kind": "upload", "name": "测试报告.txt", "text": "只覆盖其他场景"}]
    codes = {issue["code"] for issue in validate("fast/acceptance", output, sources=sources)}
    assert "f3-pass-row-without-evidence" in codes


@pytest.mark.parametrize("result", ["PASS", "通过", "部分通过"])
def test_f3_new_summary_label_does_not_allow_unsubstantiated_pass(result):
    issues = validate("fast/acceptance", f"# F3\n\n本轮实测结论：{result}。\n", sources=[])
    assert any(issue["code"] == "f3-pass-without-evidence" for issue in issues)


def test_f3_partial_pass_row_also_requires_real_evidence():
    text = """# F3

| 验收场景 | 操作步骤 | 预期结果 | 实测结果 | 状态 | 证据 |
|---|---|---|---|---|---|
| 2.4 保存 | 点击保存 | 完成保存 | 一部分正常 | 部分通过 | 尚未提供 |
"""
    codes = {issue["code"] for issue in validate("fast/acceptance", text, sources=[])}
    assert {"f3-pass-without-evidence", "f3-pass-row-without-evidence"} <= codes


def test_f1_handoff_can_stop_at_prototype_instead_of_forcing_prd():
    text = """# 流程、商业化与下一步

## 产品主要流程
当前任务从已有入口继续，完成后保留结果。商业化沿用当前明确方案。

## 下一步交接
只将已确认范围交给本轮原型模块，不启动完整 PRD。
"""
    issues = validate("fast/f1-flow-monetization", text)
    assert not any(issue["code"] == "f1-section-handoff" for issue in issues)


def test_confirmed_page_body_remains_single_source_when_preparing_prd(bench, monkeypatch):
    project = bench.create_project("页面说明复用", "只处理输入与保存")
    body = """# 当前原型与需求旁注

## CONTENT-03 内容页
用途是输入和保存内容。画面为独立页面，上方标题，中间输入区，底部保存按钮。
① 输入与保存
1、输入后点击 Save；成功留在当前页并展示已保存反馈，取消不覆盖旧内容。
"""
    notes = confirm(bench, project["id"], "fast/prototype-handoff", body)
    monkeypatch.setattr(bench, "search", lambda *args: [])
    job = bench.prepare(project["id"], "fast/core-prd", "只同步 CONTENT-03，原文保留")
    source = next(item for item in job["sources"] if item["source_id"] == notes["id"])
    assert source["text"].strip() == body.strip()
    assert "CONTENT-03" in job["prompt"] and "区域位置层级" in job["prompt"]
    assert bench.job(notes["id"])["output"] == body
    assert "不再自由改写第二套" in job["prompt"]
