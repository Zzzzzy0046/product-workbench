"""Lightweight, explainable checks for workbench deliverables."""
from __future__ import annotations

import re


def _issue(code: str, severity: str, message: str, hint: str = "") -> dict:
    return {"code": code, "severity": severity, "message": message, "hint": hint}


def _has_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value.lower() in text.lower() for value in values)


def _line_for(text: str, values: tuple[str, ...]) -> int | None:
    for index, line in enumerate(str(text).splitlines(), 1):
        if _has_any(line, values):
            return index
    return None


def validate(
    task_id: str,
    output: str,
    workflow_mode: str = "fast",
    sources: list[dict] | None = None,
) -> list[dict]:
    """Return deterministic checks; warnings do not block confirmation."""
    text = str(output or "")
    issues: list[dict] = []
    if not text.strip():
        return [_issue("empty", "error", "交付物正文为空。", "请重新生成或导入完整 Markdown。")]
    if len(text) > 2_000_000:
        issues.append(_issue("length-hard", "error", "交付物超过系统允许的最大长度。", "请缩短正文后再确认。"))
    elif len(text) > 20_000:
        issues.append(_issue("length", "warning", "交付物超过推荐长度，阅读和导出可能变得拥挤。", "压缩重复背景和不影响决策的说明。"))

    if task_id == "fast/new-product-analysis":
        checks = [
            ("market", ("行业", "市场"), "行业或市场判断"),
            ("user", ("目标用户", "用户场景", "使用场景"), "目标用户或核心场景"),
            ("delta", ("竞品差异", "差异化", "竞品对比"), "竞品差异"),
            ("positioning", ("产品定位", "定位"), "产品定位"),
            ("scope", ("首版范围", "MVP", "V0", "必须做"), "首版范围"),
            ("features", ("功能框架", "核心功能", "功能结构"), "功能框架或核心功能"),
            ("flow", ("核心流程", "主要流程", "用户流程"), "核心流程"),
            ("monetization", ("商业化", "订阅", "广告", "IAP"), "商业化方向"),
        ]
        for code, words, label in checks:
            if not _has_any(text, words):
                issues.append(_issue(f"f1-{code}", "warning", f"未明显找到{label}。", f"建议补充“{label}”章节或结论。"))
        forbidden = (("机会门", "机会门章节"), ("用户访谈",), ("假设验证",), ("技术 Spike", "技术spike"))
        for words in forbidden:
            if _has_any(text, words):
                issues.append(_issue("f1-scope", "warning", f"正文出现快速模式不要求的内容：{words[0]}。", "确认是否属于本轮范围，避免文档膨胀。"))
        project_sources = [
            source for source in (sources or [])
            if isinstance(source, dict) and source.get("kind") != "knowledge"
        ]
        if project_sources and not re.search(r"\[S[1-9][0-9]*\]", text):
            issues.append(
                _issue(
                    "f1-missing-citation",
                    "warning",
                    "当前项目有资料，但正文没有看到来源编号引用。",
                    "只把项目资料支持的结论写入正文，并在相关结论旁标注 [Sx]。",
                )
            )
        metric_pattern = re.compile(
            r"(?:下载量|收入|DAU|MAU|市场规模|排名|用户比例|用户占比|转化率|留存率|评论(?:量|数量)|平均评分|评分)"
            r"[^\n]{0,36}?\d+(?:\.\d+)?\s*(?:%|万|千|K|M|美元|\$)?",
            re.IGNORECASE,
        )
        ungrounded_metrics = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if metric_pattern.search(line) and not re.search(r"\[S[1-9][0-9]*\]|https?://", line):
                ungrounded_metrics.append(line_number)
        if ungrounded_metrics:
            issues.append(
                _issue(
                    "f1-ungrounded-metric",
                    "warning",
                    f"第 {', '.join(map(str, ungrounded_metrics[:5]))} 行出现未标来源的市场/用户/竞品数字。",
                    "删除无法追溯的数字，或在同一行补充项目资料来源编号；不要把样本外推为全市场。",
                )
            )
        broad_claim_pattern = re.compile(
            r"(?:品类|市场|用户|竞品).{0,32}(?:已验证|说明需求|普遍|大多数|主要用户|核心用户|天然|必然|明确证明)",
            re.IGNORECASE,
        )
        ungrounded_claims = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if broad_claim_pattern.search(line) and not re.search(r"\[S[1-9][0-9]*\]|https?://", line):
                if not re.match(r"\s*(?:建议|本产品可|待确认|当前资料未覆盖)", line):
                    ungrounded_claims.append(line_number)
        if ungrounded_claims:
            issues.append(
                _issue(
                    "f1-ungrounded-generalization",
                    "warning",
                    f"第 {', '.join(map(str, ungrounded_claims[:5]))} 行可能把局部资料外推成市场或用户普遍结论。",
                    "改为描述当前样本/单个竞品，或补充来源；产品建议请用“建议/本产品可”措辞。",
                )
            )

    elif task_id == "fast/core-prd":
        checks = [
            ("page", ("页面", "功能"), "页面或功能定义"),
            ("entry", ("入口", "进入方式"), "入口"),
            ("state", ("Loading", "Empty", "Error", "加载", "空状态", "错误"), "状态说明"),
            ("failure", ("失败", "取消", "超时", "重试", "恢复"), "失败或恢复规则"),
            ("copy", ("英文 UI", "UI copy", "英文文案", "按钮文案"), "英文 UI copy"),
            ("acceptance", ("验收", "接受标准", "Acceptance"), "验收标准"),
        ]
        for code, words, label in checks:
            if not _has_any(text, words):
                issues.append(_issue(f"f2-{code}", "warning", f"未明显找到{label}。", f"建议补充可交给研发执行的{label}。"))

    elif task_id == "fast/tracking-spec":
        event_ids = re.findall(r"(?:event\s*id|事件\s*ID|事件ID)\s*[|：:]\s*`?([A-Za-z][A-Za-z0-9_.-]+)", text, re.IGNORECASE)
        duplicates = sorted({item for item in event_ids if event_ids.count(item) > 1})
        if duplicates:
            issues.append(_issue("tracking-duplicate-id", "error", f"埋点事件 ID 重复：{', '.join(duplicates[:8])}。", "每个业务事件只保留一个唯一 ID。"))
        if not _has_any(text, ("参数名", "参数", "properties")):
            issues.append(_issue("tracking-params", "warning", "未明显找到事件参数定义。", "补充参数名、类型和枚举值。"))
        if not _has_any(text, ("失败", "取消", "超时", "重试")):
            issues.append(_issue("tracking-terminal-states", "warning", "未明显找到失败、取消、超时或重试事件。", "根据实际异步流程补齐最终状态。"))
        sensitive = ("Cookie", "Token", "原始用户内容", "精确位置", "蓝牙广播")
        found_sensitive = [word for word in sensitive if word.lower() in text.lower()]
        if found_sensitive:
            issues.append(_issue("tracking-sensitive", "warning", f"正文出现敏感数据字段或提示：{', '.join(found_sensitive)}。", "确认这是禁止记录的说明，而不是埋点参数。"))

    elif task_id == "fast/acceptance":
        checks = [
            ("build", ("构建", "版本", "Build"), "构建版本"),
            ("device", ("设备", "机型", "测试环境"), "测试设备或环境"),
            ("expected", ("预期",), "预期结果"),
            ("actual", ("实测", "实际结果"), "实测结果"),
            ("retest", ("复测", "回归"), "复测结果"),
        ]
        for code, words, label in checks:
            if not _has_any(text, words):
                issues.append(_issue(f"f3-{code}", "warning", f"未明显找到{label}。", f"补充{label}，方便开发后验收。"))
        if not _has_any(text, ("截图", "日志", "证据")):
            issues.append(_issue("f3-evidence", "warning", "未明显找到截图、日志或证据索引。", "把实际测试证据链接或文件名写入对应验收项。"))
        if workflow_mode == "fast" and re.search(r"最终结果\s*[：:]\s*`?Conditional", text, re.IGNORECASE):
            issues.append(_issue("f3-conditional", "error", "快速模式 F3 的最终结果仍为 Conditional。", "在同一份清单中补充修改和复测，直到结果变为通过。"))

    return issues


def summarize(issues: list[dict]) -> dict:
    errors = sum(1 for issue in issues if issue.get("severity") == "error")
    warnings = sum(1 for issue in issues if issue.get("severity") == "warning")
    return {"issues": issues, "errors": errors, "warnings": warnings, "ok": errors == 0}
