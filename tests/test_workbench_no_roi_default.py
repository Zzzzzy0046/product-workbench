"""The current workflow must not impose an arbitrary payback metric or window."""

import json
from pathlib import Path
import re

import pytest

from workbench import app
from workbench.validators import validate


ROOT = Path(__file__).resolve().parents[1]
FIXED_PAYBACK_ANCHOR = re.compile(
    r"\bD7\s*(?:ROI|ROAS)\b|7\s*[天日].{0,12}(?:ROI|ROAS|回本)"
    r"|七天.{0,12}回本|7.day.{0,10}ROI",
    re.IGNORECASE,
)


def test_current_configured_templates_and_rules_have_no_fixed_payback_default():
    paths = {
        ROOT / "workbench/workflows/presets.json",
        ROOT / "workbench/core/constants.py",
        ROOT / "workbench/validators.py",
    }
    for path in sorted((ROOT / "workbench/capabilities").glob("*.json")):
        paths.add(path)
        capability = json.loads(path.read_text(encoding="utf-8"))
        for task in capability.get("tasks", []):
            if task.get("template"):
                paths.add(ROOT / task["template"])
    paths.update((ROOT / "workbench/templates").glob("*.md"))
    for path in sorted(paths):
        assert not FIXED_PAYBACK_ANCHOR.search(path.read_text(encoding="utf-8")), path


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path, runner=lambda _: "unused")
    instance.retrieval_mode = "keyword"
    yield instance
    instance.close()


@pytest.mark.parametrize("task_id", [
    "fast/f1-category-user", "fast/product-baseline", "fast/version-brief",
    "fast/core-prd", "fast/competitor-analysis", "fast/version-result",
    "fast/shared-rules", "fast/product-acceptance",
])
def test_prepared_current_tasks_do_not_inject_fixed_payback_anchor(bench, task_id):
    project = bench.create_project("本轮只做资料整理", "本轮目标：整理已选竞品的评论与截图")
    job = bench.prepare(project["id"], task_id, "只处理当前资料，不增加未指定目标")
    assert not FIXED_PAYBACK_ANCHOR.search(job["prompt"])
    assert "本轮目标：整理已选竞品的评论与截图" in job["prompt"]


def test_explicit_metric_is_preserved_without_rewriting_existing_evidence(bench):
    background = "用户本轮指定：复盘 D7 ROI，但不作为其他任务的统一目标。"
    project = bench.create_project("用户指定的指标", background)
    original = "# 原始经营记录\n\nD7 ROI 仅为用户指定的观察项，未形成实测结论。\n"
    evidence = bench.add_document(project["id"], "原始经营记录.md", original.encode("utf-8"))
    job = bench.prepare(project["id"], "fast/version-result", "只复盘明确指定项", [evidence["id"]])
    assert background in job["prompt"]
    source = next(source for source in job["sources"] if source["source_id"] == evidence["id"])
    assert original.strip() == source["text"].strip()
    assert bench.document(evidence["id"])["text"] == original
    assert bench.project(project["id"])["brief"] == background


def test_validator_does_not_require_a_payback_metric():
    text = """# 本轮产品范围

行业与市场、目标用户及使用场景以项目资料为准。
竞品差异用于产品定位。首版范围包含导入和继续游戏。
功能框架为导入与游戏；核心流程从选择文件到继续游戏。
商业化沿用已有方案，本轮不修改。
"""
    issues = validate("fast/new-product-analysis", text)
    assert not any(re.search(r"\b(?:roi|roas|d7)\b|回本", str(issue), re.IGNORECASE) for issue in issues)
