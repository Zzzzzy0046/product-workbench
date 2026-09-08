---
id: method-workflow-gates
type: method
domain: workflow
stage: all
platform: [android, ios]
region: [global]
evidence_level: approved-plan
status: active
source:
  - source-workflow-implementation-v1
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [Gate, G1, G2, G3, G4, G5]
---

# 工作流 Gate

- G1 机会门禁：用户、场景、痛点、首次价值和继续投入的理由是否成立。
- G2 定义门禁：竞品证据能否导出定位、差异化、留存和商业化决策。
- G3 方案门禁：MVP、主流程、状态、异常、权限、风险和验收是否闭环。
- G4 研发验收门禁：需求、原型、实现、埋点和测试是否一致，真机核心路径是否通过。
- G5 迭代门禁：仅在已有真实产品数据时判断 Continue、Iterate、Hold 或 Retire。

Gate 的输出为 `Go / Conditional Go / Hold / Stop`，并记录阻断项、负责人、补证方式和返回阶段。
