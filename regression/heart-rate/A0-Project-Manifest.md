# A0 Project Manifest — Heart Rate 工作流回归

## 项目身份

- 项目名称：Heart Rate 历史资产工作流回归
- 目标：验证历史原始文档能否通过 Product KB RAG 正确进入新品工作流
- 工作流模式：Regression / Resume Existing Materials
- 产品方向：移动端 Heart Rate 健康工具
- 目标平台：历史材料覆盖 Android 与 iOS；当前未重新确认开发平台
- 候选区域：历史材料为 Global；当前未重新确认首发区域
- 目标执行模型：`gpt-6-astra`；本地 embedding 模型仅负责检索
- 模型验证状态：当前任务内不可热切换，需在新任务按目标模型做最终 Agent 回归

## 当前状态

- 当前阶段：`OPPORTUNITY_REVIEW`
- 工作流回归结果：`PASS`
- 当前产品 G1：`HOLD`
- G1 Hold 原因：历史材料可用于模板和案例回归，但当前市场、竞品、政策、目标区域和用户选择尚未实时复核，不能继承为当前立项结论
- 当前 Source of Truth：原始 20 页 Heart Rate PDF + 2026-09-08 模板盘点 + 当前明确的工作流范围决策

## Source of Truth

| 优先级 | Source ID | 作用 | 状态 |
|---:|---|---|---|
| 1 | `decision-workflow-scope-2026-09-08` | 当前工作流范围；排除投放和商店发布 | Active |
| 2 | `source-heart-rate-original-pdf` | Heart Rate 原始新品需求分析 | Historical source |
| 3 | `case-heart-rate-template-evolution` | 已结构化的模板演进结论 | Active case |
| 4 | `method-new-product-analysis` | 当前新品分析方法 | Active method |
| 5 | `source-template-audit-v1` | 历史模板交叉验证 | Active source |

## 交付物状态

| 编号 | 交付物 | 状态 | 证据等级 | 说明 |
|---|---|---|---|---|
| A1 | Opportunity Brief | Review | Historical source | 原始 PDF 包含对应内容，但未按当前市场实时复核 |
| A2 | Competitor Evidence Pack | Draft | Historical source | 竞品内容嵌在原始材料中，尚未形成独立当前证据包 |
| A3 | Product Definition | Draft | Historical source | 可用于模板回归，不可直接视为当前产品决策 |
| A4 | PRD | Missing | Not verified | 不在本次回归范围 |
| A5 | Prototype Handoff | Missing | Not verified | 不在本次回归范围 |
| A6 | Risk & Decision Log | Draft | Current workflow | 本 Manifest 已记录关键范围决策和证据缺口 |
| A7 | Tracking / QA / Acceptance Pack | Missing | Not verified | 不在本次回归范围 |

## 已验证的 RAG 路由

- 模板查询首位命中：`case-heart-rate-template-evolution`
- 新品范围查询首位命中：`method-new-product-analysis`
- Gate 查询命中：`method-workflow-gates`
- 原始证据回溯命中：`source-heart-rate-original-pdf`
- 当前范围命中：`decision-workflow-scope-2026-09-08`

## 阻断项

- 当前目标用户和使用场景未重新确认。
- 首发平台和首发区域未重新确认。
- 市场规模、竞品、价格和政策没有进行当前时间点的实时复核。
- 尚无本次真实产品项目的 MVP 和资源约束。

## 下一步最小动作

当 Heart Rate 作为真实新品重新启动时，先确认目标平台、区域、用户和产品方向，再刷新 A1/A2；在此之前不进入当前产品 G1 Go，也不生成 A4–A7。

最后更新：2026-09-08
