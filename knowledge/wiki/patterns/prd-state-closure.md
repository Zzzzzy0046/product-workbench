---
id: pattern-prd-state-closure
type: pattern
domain: prd
stage: solution
platform: [android, ios]
region: [global]
evidence_level: project-validated
status: active
source:
  - source-historical-workflow-v1
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [PRD, 状态, 异常, AC]
---

# PRD 状态闭环

页面需求不能只描述正常点击路径。至少检查进入条件、展示、交互、数据、离开、Loading、Empty、Fail、Timeout、Permission denied、Interrupted、Restore 和重复操作。

每项 P0 能力必须有验收标准。原型负责表达页面和交互，PRD 是业务规则的 Source of Truth；关键规则不能只藏在原型标注或口头说明中。
