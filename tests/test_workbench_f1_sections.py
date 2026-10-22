"""F1 chapter workflow and deterministic final assembly."""

import pytest

from workbench import app


SECTION_TASKS = [
    "fast/f1-category-user",
    "fast/f1-competitor-differences",
    "fast/f1-positioning-scope",
    "fast/f1-product-solution",
    "fast/f1-flow-monetization",
]


SECTION_OUTPUTS = {
    "fast/f1-category-user": """# F1-1 品类与用户

## 2. 行业与市场背景

本章品类标记 A：品类定义、市场信号与当前资料边界。

## 3. 用户分析

核心用户在具体使用场景中完成核心任务。
""",
    "fast/f1-competitor-differences": """# F1-2 竞品差异

## 4. 竞品分析与差异

本章竞品标记 B：竞品选择、单竞品流程、横向差异与评论主题。
""",
    "fast/f1-positioning-scope": """# F1-3 定位与版本范围

## 5. 产品定位与价值主张

本章定位标记 C：一句话定位、产品价值与首次价值。

## 6. 产品范围与版本边界

V0 现在必须做的能力与本阶段不做的范围已分开。
""",
    "fast/f1-product-solution": """# F1-4 功能框架与核心模块

## 7. 产品功能框架

本章功能标记 D：产品树与模块关系。

## 8. 核心功能说明

核心模块说明包含模块目标、用户入口和主操作结果。
""",
    "fast/f1-flow-monetization": """# F1-5 流程、商业化与 PRD 交接

## 9. 产品主要流程

本章流程标记 E：核心任务流程与再次使用流程。

## 10. 商业化策略

比较 Subscription、IAP 与 Ads，给出产品内商业化建议。

## 11. 进入 PRD 的交付结论

F2 需要展开核心页面、业务规则与验收标准。
""",
}


def _complete_and_accept(bench, project_id, task_id, output=None):
    job = bench.prepare(project_id, task_id, "只处理本章")
    bench.complete(job["id"], output or SECTION_OUTPUTS[task_id])
    bench.review(job["id"], "accepted", "本章已确认")
    return bench.job(job["id"])


def test_f1_capability_exposes_five_ordered_hidden_sections(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        aggregate = bench.task("fast/new-product-analysis")
        assert aggregate["assembly"] == "accepted_sections"
        assert aggregate["section_tasks"] == SECTION_TASKS
        assert aggregate["hidden"] is True
        assert bench.task(SECTION_TASKS[0]).get("required_upstream_all") is None
        assert bench.task(SECTION_TASKS[2])["required_upstream_all"] == SECTION_TASKS[:2]
        assert all(bench.task(task_id)["hidden"] for task_id in SECTION_TASKS)
    finally:
        bench.close()


def test_f1_section_requires_confirmed_upstream_chapters(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("分章依赖", "已确定要做的新品")
        with pytest.raises(ValueError, match="请先生成并确认前置章节"):
            bench.prepare(project["id"], "fast/f1-competitor-differences", "")

        first = bench.prepare(project["id"], "fast/f1-category-user", "")
        bench.complete(first["id"], SECTION_OUTPUTS["fast/f1-category-user"])
        with pytest.raises(ValueError, match="F1-1 品类与用户"):
            bench.prepare(project["id"], "fast/f1-competitor-differences", "")

        bench.review(first["id"], "accepted", "确认")
        second = bench.prepare(project["id"], "fast/f1-competitor-differences", "")
        assert second["status"] == "prepared"
        assert any(source["source_id"] == first["id"] and source["kind"] == "accepted" for source in second["sources"])
    finally:
        bench.close()


def test_f1_assembly_keeps_confirmed_chapter_text_and_order(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("分章合并", "小团队快速迭代的海外 App", platform="Android-first")
        chapter_jobs = [_complete_and_accept(bench, project["id"], task_id) for task_id in SECTION_TASKS]

        final_job = bench.assemble_sections(project["id"])
        assert final_job["status"] == "completed"
        assert final_job["review"] is None
        versions = bench.versions(final_job["id"])
        assert versions[0]["source"] == "assembled"
        assert versions[0]["note"] == "分章自动合并"
        assert "没有调用模型重写已确认正文" in final_job["output"]
        assert "| 目标平台 | Android |" in final_job["output"]
        markers = ["品类标记 A", "竞品标记 B", "定位标记 C", "功能标记 D", "流程标记 E"]
        assert [final_job["output"].index(marker) for marker in markers] == sorted(final_job["output"].index(marker) for marker in markers)
        assert all(final_job["output"].count(marker) == 1 for marker in markers)
        assert not bench.citation_issues(final_job["output"], final_job["sources"])
        assert {job["id"] for job in chapter_jobs}.issubset({source["source_id"] for source in final_job["sources"]})
    finally:
        bench.close()


def test_f1_assembly_blocks_when_any_chapter_is_unconfirmed(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("不完整合并", "")
        _complete_and_accept(bench, project["id"], SECTION_TASKS[0])
        with pytest.raises(ValueError, match="以下章节尚未确认"):
            bench.assemble_sections(project["id"])
    finally:
        bench.close()


def test_f1_assembly_drops_chapter_local_source_tables(tmp_path):
    # Each chapter numbers its own index (S1 = store listing there), but merged
    # body citations are renumbered globally (S1 = F1-1). Keeping the chapter
    # tables would point readers at the wrong source; the merged index replaces them.
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("分章索引", "已确定要做的新品")
        outputs = dict(SECTION_OUTPUTS)
        outputs["fast/f1-competitor-differences"] = outputs["fast/f1-competitor-differences"].rstrip() + """

## 资料索引

以下项目附件均保留。

| 编号 | 证据附件 | 使用边界 |
|---|---|---|
| S1 | 本章局部编号的商店信息.md | 局部编号行 |

**证据不足与最小下一步：**补一次主对标的连续操作记录。
"""
        for task_id in SECTION_TASKS:
            _complete_and_accept(bench, project["id"], task_id, outputs[task_id])
        merged = bench.assemble_sections(project["id"])["output"]
        assert merged.count("资料索引") == 1
        assert "## 1. 资料索引" in merged
        assert "本章局部编号的商店信息" not in merged
        assert "以下项目附件均保留" not in merged
        assert "**证据不足与最小下一步：**补一次主对标的连续操作记录。" in merged
    finally:
        bench.close()
