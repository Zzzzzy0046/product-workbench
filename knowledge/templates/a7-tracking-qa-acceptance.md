---
id: template-a7-tracking-qa-acceptance
type: template
domain: acceptance
stage: acceptance
platform: [android, ios]
region: [global]
evidence_level: approved-plan
status: active
source: [source-historical-workflow-v1]
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [A7, 埋点, QA, 真机, G4]
---

# A7 Tracking / QA / Acceptance Pack

## 埋点设计

- 产品问题和漏斗：
- 事件 ID、触发时机、参数、类型和值域：
- Success / Fail / Cancel / Timeout：
- 隐私和禁止采集内容：

## 测试矩阵

| Case ID | 平台/设备 | 前置条件 | 操作 | 预期 | 实际 | 证据等级 | 结果 |
|---|---|---|---|---|---|---|---|

覆盖主路径、权限拒绝、网络异常、订阅/恢复、广告 No Fill、后台恢复、通知、重复操作和降级。

## 实机埋点验收

- PASS：事件 ID、参数和值、触发时机全部匹配；无需截图。
- FAIL：记录差异并附必要截图。
- BLOCKED / NOT_RUN：记录原因，不伪装为通过。

## G4 研发验收

- 核心价值路径在目标设备通过：
- PRD、原型、实现、埋点和测试一致：
- 订阅、广告、权限和异常路径符合需求：
- Crash、性能、兼容性和降级已检查：
- 未关闭问题、Owner 和处理期限：
- 结论：Accepted / Conditional / Rejected
