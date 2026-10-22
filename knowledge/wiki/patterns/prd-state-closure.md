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
reviewed_at: 2026-10-21
expires_at:
supersedes: []
tags: [PRD, 状态, 异常, AC]
---

# PRD 状态闭环

页面需求先说明用途、呈现形式、所属背景、区域位置与层级、必要的完整文案及默认状态，再写条件、操作和结果。弹窗、菜单、气泡、Toast 与局部状态按实际形态说明，不能一律写成独立页面。简单状态只补变化；Loading、Empty、Fail、Timeout、权限拒绝、中断恢复和重复操作仅在本轮真实涉及时检查。

每项当前核心能力应有可判断的预期。业务口径以用户当前确认及指定基线为准；原型和实现记录实际表现，已确认文档记录约定，出现冲突必须列明，不把文件类型、新旧或实现偏差当成自动裁决。

页面旁注和独立 PRD 复用一份确认正文及稳定 ID，公共规则集中维护，流程和验收引用同一口径。发生变更时核对旧口径、新确认和所有受影响位置；只报告实际核对与落实范围。
