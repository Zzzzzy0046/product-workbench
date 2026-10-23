"""F1 prompts ask for decisions, not repeated disclaimers, and F1-5 must plan ad placements."""
from pathlib import Path

import pytest

from workbench import app
from workbench.validators import validate


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path, runner=lambda _: "unused")
    instance.retrieval_mode = "keyword"
    yield instance
    instance.close()


def test_f1_prompt_asks_for_decisions_not_hedging(bench):
    project = bench.create_project("写法规则", "已决定要做的新品")
    prompt = bench.prepare(project["id"], "fast/f1-category-user", "")["prompt"]
    assert "先给结论，再给依据" in prompt
    assert "只在第一次出现时说一次" in prompt
    for removed in ("必须使用“建议/本产品可/待确认”等方案措辞", "当前资料未覆盖，暂不下结论", "结尾写明证据不足"):
        assert removed not in prompt


def test_f1_flow_monetization_template_requires_ad_plan(bench):
    template = bench.task("fast/f1-flow-monetization")
    text = (Path(__file__).resolve().parents[1] / template["template"]).read_text(encoding="utf-8")
    assert "首版广告位方案" in text and "回本假设与验证" in text
    issues = {item["code"] for item in validate("fast/f1-flow-monetization", "## 9. 产品主要流程\n核心任务流程\n## 10. 商业化\n## 11. 本轮交接\n", "fast", [])}
    assert {"f1-section-ad-placements", "f1-section-payback"} <= issues
