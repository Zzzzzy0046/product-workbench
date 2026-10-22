"""Product handoff checks keep scenario specs distinct from execution records."""

from workbench.validators import summarize, validate


def test_product_acceptance_uses_three_columns_without_execution_fields():
    output = """# 产品验收用例

## 1 内容管理

| 验收场景 | 操作步骤 | 预期结果 |
|---|---|---|
| 1.1 取消编辑 | 修改名称后取消，重新进入页面。 | 返回来源页，保留已保存的名称。 |
"""
    assert validate("fast/product-acceptance", output) == []

    execution_record = output.replace("操作步骤 | 预期结果 |", "操作步骤 | 预期结果 | 状态 |")
    result = summarize(validate("fast/product-acceptance", execution_record))
    assert result["ok"] is False
    assert any(issue["code"] == "product-acceptance-columns" for issue in result["issues"])


def test_product_acceptance_does_not_turn_expected_success_into_tested_pass():
    output = """| 验收场景 | 操作步骤 | 预期结果 |
|---|---|---|
| 1.1 保存 | 输入有效名称，点击保存。 | 校验通过后返回列表。 |
"""
    assert validate("fast/product-acceptance", output) == []
    issues = validate("fast/product-acceptance", output + "\n验收结论：已通过\n")
    assert any(issue["code"] == "product-acceptance-execution" for issue in issues)


def test_page_ids_are_unique_definitions_but_can_be_referenced_again():
    output = """# 功能流程与页面状态清单

首页 M01 → 编辑 M02 → 保存后返回 M01。

| 稳定 ID / 中文名 | 类型 | 进入来源 | 退出/返回去向 |
|---|---|---|---|
| M01 首页 | 页面 | 启动 | M02 |
| M02 编辑 | 页面 | M01 | M01 |
"""
    assert validate("fast/flow-pages", output) == []
    duplicated = output + "| M02 确认弹窗 | 弹窗 | M02 | M01 |\n"
    issues = validate("fast/flow-pages", duplicated)
    assert any(issue["code"] == "flow-duplicate-page-id" and issue["severity"] == "error" for issue in issues)


def test_prototype_handoff_does_not_claim_external_write_from_document_generation():
    pending = "# 原型交接\n\n页面与旁注已整理，待同步至 Figma。\n"
    assert validate("fast/prototype-handoff", pending) == []
    claimed = "# 原型交接\n\n已更新 Figma 页面与旁注。\n"
    issues = validate("fast/prototype-handoff", claimed)
    assert any(issue["code"] == "document-external-write-claim" for issue in issues)


def test_page_state_ids_keep_full_alphanumeric_suffixes():
    output = """# 功能流程与页面状态清单

M01 → M02-S01 → M02-S02。

| 稳定 ID / 中文名 | 类型 | 进入来源 | 退出/返回去向 |
|---|---|---|---|
| M01 列表 | 页面 | 启动 | M02-S01 |
| M02 编辑 | 页面 | M01 | M01 |
| M02-S01 编辑中 | 状态 | M02 | M02-S02 |
| M02-S02 保存中 | 状态 | M02-S01 | M01 |
"""
    assert validate("fast/flow-pages", output) == []
    duplicate = output + "| M02-S01 再次定义 | 状态 | M02 | M01 |\n"
    issues = validate("fast/flow-pages", duplicate)
    assert any(issue["code"] == "flow-duplicate-page-id" and "M02-S01" in issue["message"] for issue in issues)


def test_review_and_consistency_tasks_require_their_own_inputs_and_comparison():
    assert any(issue["code"] == "review-missing-request" for issue in validate("fast/review-changes", "# 修订\n\n全部完成。"))
    assert any(issue["code"] == "consistency-comparison" for issue in validate("fast/consistency-review", "# 终审整理\n\n全部完成。"))
    compared = "# 一致性核对\n\n当前 PRD 与验收用例存在冲突，未给出采用依据，保持待决定。"
    assert validate("fast/consistency-review", compared) == []
