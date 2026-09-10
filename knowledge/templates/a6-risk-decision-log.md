---
id: template-a6-risk-decision-log
type: template
domain: risk
stage: all
platform: [android, ios]
region: [global]
evidence_level: approved-plan
status: archived
source: [source-workflow-implementation-v1]
reviewed_at: 2026-09-10
expires_at:
supersedes: []
tags: [A6, 风险, 决策, ADR, 历史正式模式, formal-only]
---

# A6 Risk & Decision Log

> 历史正式模式模板，不参与默认检索。快速流程不生成风险台账、假设验证或条件闭环。

## 风险台账

| ID | 风险 | 类型 | Impact | Confidence | 证据 | 缓解 | Owner | 截止 | 状态 |
|---|---|---|---:|---:|---|---|---|---|---|

类型包括：用户价值、市场、平台政策、权限、隐私、技术、成本、商业化、数据、质量。

## 决策记录

| ID | 日期 | Context | Decision | Alternatives | Evidence | Consequences | Revisit trigger |
|---|---|---|---|---|---|---|---|

## 假设台账

| ID | 假设 | 验证方法 | 成功阈值 | 失败阈值 | 当前证据 | 结果 |
|---|---|---|---|---|---|---|

## 条件关闭台账

| Condition ID | 条件 | Owner | 截止 | 阻塞范围 | 预期输出 | 状态 | 关闭证据 | 复核日期 |
|---|---|---|---|---|---|---|---|---|
| C-001 |  |  |  | 开发/内部测试/外部发布/不阻塞 |  | 未开始/进行中/待证据/已关闭/豁免 |  |  |

关闭或豁免必须填写证据或决策记录。没有 Owner 或截止时间的 `Conditional` 不可作为正式结论。
