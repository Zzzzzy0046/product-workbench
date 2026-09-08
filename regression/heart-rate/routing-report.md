# Heart Rate RAG 与工作流路由回归报告

## 结论

工作流回归通过。系统能够从原始 Heart Rate PDF、模板盘点、结构化方法和当前范围决策中检索正确上下文，并能区分“历史模板可复用”与“当前产品结论尚未验证”。

产品 G1 被正确判定为 Hold，而不是因为找到了历史文档就自动 Go。这是预期行为。

## 输入识别

- 输入类型：历史新品原始文档 + 衍生模板 + 当前工作流方案。
- 模式：Resume Existing Materials / Regression。
- 应生成：A0 Manifest 与路由/Gate 结论。
- 不应生成：未经当前验证的完整新品立项结论、投放方案或商店发布材料。

## RAG 结果

| 查询 | 关键命中 | 用途 |
|---|---|---|
| Heart Rate 应复用什么模板结构和写法 | `case-heart-rate-template-evolution`、`method-new-product-analysis` | 选择 Doc Reader 骨架 + Heart 写法 |
| 健康类新品首次价值、留存、商业化和政策风险 | `method-new-product-analysis`、`source-heart-rate-original-pdf` | 恢复历史产品判断框架 |
| 进入产品定义前需要哪些证据 | `method-workflow-gates` | 执行 G1/G2，而不是直接进入 PRD |
| 当前工作流做什么、不做什么 | `decision-workflow-scope-2026-09-08` | 排除投放、ASO 和商店发布 |

## 正确继承

- Heart Rate 的结论先行和完整产品故事写法。
- Doc Reader 0–12 章结构作为当前新品分析骨架。
- Printer 的政策、信任和版本优先级检查作为工具类增强。
- Heart 页面需求结构作为方案确认后的展开方式。
- 事实、推断、假设和决策必须分层。

## 禁止继承

- 历史市场规模、下载、收入和竞品结论。
- 历史价格、平台政策和系统能力结论。
- 历史目标区域和用户分群。
- 历史功能、SKU 和优先级。
- 任何投放或商店发布执行内容。

## Gate 结果

### 工作流回归

- 结果：PASS
- 证据：查询命中正确结构化知识、原始来源和范围决策；A0 已生成。

### 当前产品 G1

- 结果：HOLD
- 原因：缺少当前用户确认和实时外部证据。
- 返回阶段：Opportunity。
- 下一步：确认平台、区域、Beachhead 用户和目标结果，然后刷新市场与竞品证据。
