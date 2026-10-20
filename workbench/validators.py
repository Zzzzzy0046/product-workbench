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


def _table_cells(line: str) -> list[str]:
    """Split a Markdown table row while keeping validation dependency-free."""
    value = str(line).strip()
    if not value or "|" not in value:
        return []
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [cell.strip() for cell in value.split("|")]


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _markdown_tables(text: str) -> list[dict]:
    """Return Markdown tables with headers, row cells and one-based line numbers."""
    lines = str(text).splitlines()
    tables: list[dict] = []
    index = 0
    while index + 1 < len(lines):
        headers = _table_cells(lines[index])
        separator = _table_cells(lines[index + 1])
        if not headers or not _is_table_separator(separator):
            index += 1
            continue
        rows = []
        cursor = index + 2
        while cursor < len(lines):
            cells = _table_cells(lines[cursor])
            if not cells:
                break
            rows.append({"cells": cells, "line": cursor + 1})
            cursor += 1
        tables.append({"headers": headers, "rows": rows})
        index = cursor
    return tables


def _normal_header(value: str) -> str:
    return re.sub(r"[\s`_*]", "", str(value)).lower()


def _column(headers: list[str], *names: str) -> int | None:
    normalized = [_normal_header(header) for header in headers]
    for name in names:
        target = _normal_header(name)
        for index, header in enumerate(normalized):
            if header == target or target in header:
                return index
    return None


def _cell(cells: list[str], index: int | None) -> str:
    return cells[index].strip() if index is not None and index < len(cells) else ""


def _plain_cell(value: str) -> str:
    return re.sub(r"[`*_]", "", str(value)).strip()


def _is_blank_cell(value: str) -> bool:
    plain = _plain_cell(value)
    return not plain or plain in {"-", "—", "[填写]", "[待填写]", "待填写", "待补", "N/A"}


def _is_prohibition_line(line: str) -> bool:
    return _has_any(line, ("不得", "禁止", "不要记录", "不记录", "排除", "不可采集", "禁止采集"))


def _has_actual_test_evidence(sources: list[dict] | None) -> bool:
    evidence_words = (
        "测试报告", "测试记录", "验收记录", "实测", "复测", "设备结果", "构建日志",
        "技术日志", "运行日志", "崩溃日志", "截图", "录像", "录屏", "抓包",
    )
    evidence_suffixes = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".log", ".apk", ".aab")
    for source in sources or []:
        if not isinstance(source, dict) or source.get("kind") != "upload":
            continue
        name = str(source.get("name") or source.get("location") or "")
        sample = f"{name}\n{str(source.get('text') or '')[:1200]}"
        if name.lower().endswith(evidence_suffixes) or _has_any(sample, evidence_words):
            return True
    return False


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

    elif task_id in {
        "fast/f1-category-user",
        "fast/f1-competitor-differences",
        "fast/f1-positioning-scope",
        "fast/f1-product-solution",
        "fast/f1-flow-monetization",
    }:
        section_checks = {
            "fast/f1-category-user": [
                ("market", ("品类", "行业", "市场"), "品类或市场背景"),
                ("user", ("用户分层", "目标用户", "核心用户"), "用户分层"),
                ("scene", ("使用场景", "核心场景", "触发场景"), "核心使用场景"),
            ],
            "fast/f1-competitor-differences": [
                ("competitors", ("竞品选择", "单竞品", "竞品 A"), "竞品范围"),
                ("delta", ("横向差异", "竞品差异", "与竞品的差异"), "竞品差异"),
                ("reviews", ("评论主题", "用户不满", "用户喜欢"), "评论或口碑结论"),
            ],
            "fast/f1-positioning-scope": [
                ("positioning", ("一句话定位", "产品定位"), "产品定位"),
                ("value", ("首次价值", "产品价值"), "首次价值"),
                ("scope", ("V0", "现在必须做", "本阶段不做"), "V0 范围"),
            ],
            "fast/f1-product-solution": [
                ("framework", ("产品树", "功能框架"), "产品功能框架"),
                ("modules", ("核心功能", "核心模块", "模块目标"), "核心模块说明"),
            ],
            "fast/f1-flow-monetization": [
                ("flow", ("主要流程", "核心任务流程", "再次使用流程"), "产品主要流程"),
                ("monetization", ("商业化", "Subscription", "IAP", "Ads"), "商业化方案"),
                ("handoff", ("进入 PRD", "F2 需要", "PRD 交接"), "F2 交接范围"),
            ],
        }
        for code, words, label in section_checks[task_id]:
            if not _has_any(text, words):
                issues.append(_issue(f"f1-section-{code}", "warning", f"本章未明显找到{label}。", f"只补充当前章节需要的{label}。"))
        for word in ("机会门", "用户访谈", "假设验证", "技术 Spike", "平台与权限"):
            if word.lower() in text.lower():
                issues.append(_issue("f1-section-scope", "warning", f"本章出现快速模式不需要的内容：{word}。", "删除无关段落，保留当前章节的产品判断。"))
        project_sources = [source for source in (sources or []) if isinstance(source, dict) and source.get("kind") != "knowledge"]
        if project_sources and not re.search(r"\[S[1-9][0-9]*\]", text):
            issues.append(_issue("f1-section-missing-citation", "warning", "当前章节有项目资料，但正文没有看到来源编号引用。", "只在资料支持的结论旁标注 [Sx]。"))

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

        permission_claim = re.compile(
            r"(?:相机|摄像头|麦克风|通知|定位|位置|蓝牙|存储|相册|照片|文件|媒体)\s*(?:权限|授权)",
            re.IGNORECASE,
        )
        permission_lines = [
            line for line in text.splitlines()
            if permission_claim.search(line) and not _is_blank_cell(line.split(":", 1)[-1])
        ]
        recovery_rule = re.compile(
            r"(?:拒绝|未授权|Denied|不允许).{0,40}(?:重试|再次申请|重新授权|系统设置|设置页|继续使用|返回|降级|提示|不阻塞|恢复)",
            re.IGNORECASE,
        )
        if permission_lines and not recovery_rule.search(text):
            issues.append(
                _issue(
                    "f2-permission-recovery",
                    "warning",
                    "正文要求了系统权限，但没有找到用户拒绝后的继续、重试或恢复路径。",
                    "在对应页面写清拒绝后用户看到什么、还能做什么，以及如何再次授权；不确定的系统行为标记“待研发确认”。",
                )
            )

        concrete_value = re.compile(
            r"(?:\d+(?:\.\d+)?\s*(?:ms|毫秒|秒|分钟|小时|天|次|个|KB|MB|GB|%|美元|美金)|[$￥€]\s*\d+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        rule_cue = re.compile(r"(?:最多|至少|超过|少于|每隔|间隔|等待|限制|上限|下限|默认|连续|保留|缓存|超时|价格|订阅)")
        unlabelled_rules = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not concrete_value.search(line) or not rule_cue.search(line):
                continue
            if re.search(r"\[S[1-9][0-9]*\]|https?://", line):
                continue
            if _has_any(line, ("待研发确认", "本轮方案", "本轮拟定", "建议", "示例")):
                continue
            unlabelled_rules.append(line_number)
        if unlabelled_rules:
            issues.append(
                _issue(
                    "f2-unlabelled-specific-rule",
                    "warning",
                    f"第 {', '.join(map(str, unlabelled_rules[:5]))} 行出现无来源、也未标为本轮拟定的具体阈值或价格。",
                    "有资料依据时补 [Sx]；属于产品方案时写“本轮拟定”；依赖实现的数值写“待研发确认”。",
                )
            )

    elif task_id == "fast/tracking-spec":
        tables = _markdown_tables(text)
        event_rows: list[dict] = []
        parameter_rows: list[dict] = []
        for table in tables:
            headers = table["headers"]
            if _column(headers, "事件 ID", "event id") is None:
                continue
            if _column(headers, "参数名", "property") is not None:
                parameter_rows.extend({**row, "headers": headers} for row in table["rows"])
            elif _column(headers, "事件类型", "中文名称", "分析问题") is not None:
                event_rows.extend({**row, "headers": headers} for row in table["rows"])

        event_ids = []
        for row in event_rows:
            raw_id = _plain_cell(_cell(row["cells"], _column(row["headers"], "事件 ID", "event id")))
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]+", raw_id):
                event_ids.append(raw_id)
        event_ids.extend(
            re.findall(
                r"(?:event\s*id|事件\s*ID|事件ID)\s*[：:]\s*`?([A-Za-z][A-Za-z0-9_.-]+)",
                text,
                re.IGNORECASE,
            )
        )
        duplicates = sorted({item for item in event_ids if event_ids.count(item) > 1})
        if duplicates:
            issues.append(_issue("tracking-duplicate-id", "error", f"埋点事件 ID 重复：{', '.join(duplicates[:8])}。", "每个业务事件只保留一个唯一 ID。"))

        bad_suffix_lines = []
        click_as_success_lines = []
        missing_question_lines = []
        missing_source_lines = []
        for row in event_rows:
            headers, cells, line_number = row["headers"], row["cells"], row["line"]
            event_id = _plain_cell(_cell(cells, _column(headers, "事件 ID", "event id")))
            event_type = _plain_cell(_cell(cells, _column(headers, "事件类型"))).lower()
            event_name = _plain_cell(_cell(cells, _column(headers, "中文名称")))
            trigger = _plain_cell(_cell(cells, _column(headers, "触发时机")))
            question = _cell(cells, _column(headers, "分析问题"))
            source = _cell(cells, _column(headers, "来源页面", "来源页面 / 状态", "来源"))
            if event_id and not re.search(r"_(?:display|click|select|result)$", event_id):
                bad_suffix_lines.append(line_number)
            if (event_id.endswith("_click") or "click" in event_type) and (
                re.search(r"(?:成功|完成|结果|回调).{0,8}(?:后|时|返回)", trigger)
                or re.search(r"(?:成功|完成|结果)", event_name)
            ):
                click_as_success_lines.append(line_number)
            if _is_blank_cell(question):
                missing_question_lines.append(line_number)
            if _is_blank_cell(source):
                missing_source_lines.append(line_number)
        if bad_suffix_lines:
            issues.append(
                _issue(
                    "tracking-event-suffix",
                    "warning",
                    f"第 {', '.join(map(str, bad_suffix_lines[:8]))} 行的事件 ID 未按 display/click/select/result 语义收口。",
                    "展示用 _display，点击用 _click，选择用 _select，异步最终结果用 _result。",
                )
            )
        if click_as_success_lines:
            issues.append(
                _issue(
                    "tracking-click-as-success",
                    "error",
                    f"第 {', '.join(map(str, click_as_success_lines[:8]))} 行把点击事件当成成功、完成或结果回调。",
                    "保留 _click 表示意图；真实业务结果由 SDK/业务回调触发独立 _result。",
                )
            )
        if missing_question_lines:
            issues.append(
                _issue(
                    "tracking-missing-question",
                    "warning",
                    f"第 {', '.join(map(str, missing_question_lines[:8]))} 行没有说明事件要回答的产品问题。",
                    "不能回答产品问题的事件应删除；保留事件时补充分析问题。",
                )
            )
        if missing_source_lines:
            issues.append(
                _issue(
                    "tracking-missing-source",
                    "warning",
                    f"第 {', '.join(map(str, missing_source_lines[:8]))} 行没有映射到 PRD、原型页面或页面状态。",
                    "补充来源页面/状态；来源中不存在的模块不要新增事件。",
                )
            )

        multi_enum_lines = []
        for row in parameter_rows:
            headers, cells = row["headers"], row["cells"]
            value_type = _plain_cell(_cell(cells, _column(headers, "类型"))).lower()
            enum_value = _plain_cell(_cell(cells, _column(headers, "枚举值", "枚举值 / 开放值")))
            if "enum" in value_type and re.search(r"\S\s*(?:/|、|,|，)\s*\S", enum_value):
                multi_enum_lines.append(row["line"])
        if multi_enum_lines:
            issues.append(
                _issue(
                    "tracking-multi-enum-cell",
                    "warning",
                    f"第 {', '.join(map(str, multi_enum_lines[:8]))} 行把多个固定枚举值写在同一个单元格。",
                    "固定枚举一值一行，分别说明各自上报时机。",
                )
            )
        if not _has_any(text, ("参数名", "参数", "properties")):
            issues.append(_issue("tracking-params", "warning", "未明显找到事件参数定义。", "补充参数名、类型和枚举值。"))
        if not _has_any(text, ("失败", "取消", "超时", "重试")):
            issues.append(_issue("tracking-terminal-states", "warning", "未明显找到失败、取消、超时或重试事件。", "根据实际异步流程补齐最终状态。"))
        sensitive = ("Cookie", "Token", "原始用户内容", "精确位置", "设备地址", "蓝牙广播")
        sensitive_lines = []
        for row in parameter_rows:
            line = " | ".join(row["cells"])
            if not _is_prohibition_line(line) and _has_any(line, sensitive):
                sensitive_lines.append(row["line"])
        found_sensitive = sorted({
            word
            for row in parameter_rows
            for word in sensitive
            if word.lower() in " | ".join(row["cells"]).lower()
            and not _is_prohibition_line(" | ".join(row["cells"]))
        })
        if found_sensitive:
            issues.append(_issue("tracking-sensitive", "warning", f"第 {', '.join(map(str, sensitive_lines[:8]))} 行把敏感数据写进参数表：{', '.join(found_sensitive)}。", "删除敏感参数；禁止记录的规则说明可以保留在正文。"))

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

        pass_claim_lines = []
        passed_rows_without_evidence = []
        for table in _markdown_tables(text):
            headers = table["headers"]
            if _column(headers, "QA ID") is None or _column(headers, "状态") is None:
                continue
            status_index = _column(headers, "状态")
            evidence_index = _column(headers, "日志/截图/录像/报告", "证据")
            for row in table["rows"]:
                status = _plain_cell(_cell(row["cells"], status_index)).upper()
                if status in {"PASS", "PASSED", "通过", "已通过"}:
                    pass_claim_lines.append(row["line"])
                    if _is_blank_cell(_cell(row["cells"], evidence_index)):
                        passed_rows_without_evidence.append(row["line"])
        for line_number, line in enumerate(text.splitlines(), 1):
            plain = _plain_cell(line)
            if re.search(r"核心流程\s*[：:]\s*(?:PASS|通过|已通过)(?:\s|$|；|。)", plain, re.IGNORECASE):
                pass_claim_lines.append(line_number)
            if re.search(r"可以进入内部测试\s*[：:]\s*是(?:\s|$|；|。)", plain):
                pass_claim_lines.append(line_number)
        pass_claim_lines = sorted(set(pass_claim_lines))
        if pass_claim_lines and not _has_actual_test_evidence(sources):
            issues.append(
                _issue(
                    "f3-pass-without-evidence",
                    "error",
                    f"第 {', '.join(map(str, pass_claim_lines[:8]))} 行宣称通过，但本任务没有实际测试证据附件。",
                    "没有构建、设备测试、日志、截图、录像或测试报告时，实测结果保持“尚未测试”，状态保持 NOT_RUN。",
                )
            )
        if passed_rows_without_evidence:
            issues.append(
                _issue(
                    "f3-pass-row-without-evidence",
                    "error",
                    f"第 {', '.join(map(str, passed_rows_without_evidence[:8]))} 行标记通过，但该 QA 行没有关联日志、截图、录像或报告。",
                    "在对应 QA 行填写实际证据文件名或 [Sx]，再标记 PASS。",
                )
            )
        if workflow_mode == "fast" and re.search(r"最终结果\s*[：:]\s*`?Conditional", text, re.IGNORECASE):
            issues.append(_issue("f3-conditional", "error", "快速模式 F3 的最终结果仍为 Conditional。", "在同一份清单中补充修改和复测，直到结果变为通过。"))

    return issues


def summarize(issues: list[dict]) -> dict:
    errors = sum(1 for issue in issues if issue.get("severity") == "error")
    warnings = sum(1 for issue in issues if issue.get("severity") == "warning")
    return {"issues": issues, "errors": errors, "warnings": warnings, "ok": errors == 0}
