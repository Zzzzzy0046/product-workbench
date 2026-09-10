---
id: template-t4-tracking-qa-acceptance
type: template
domain: acceptance
stage: acceptance
platform: [android, ios]
region: [global]
evidence_level: approved-plan
status: superseded
source: [template-a7-tracking-qa-acceptance, pattern-prd-state-closure]
reviewed_at: 2026-09-09
tags: [T4, 埋点, QA, 验收, 中文]
---

# T4 埋点、测试与验收

> 历史兼容模板。快速项目使用一份持续更新的 `F3 开发验收清单`。

## 0. 文档信息

| 字段 | 内容 |
|---|---|
| 产品名称 | `[填写]` |
| 关联 T3 / PRD | `[链接或文件]` |
| 构建版本 | `[填写]` |
| 测试日期 | `[填写]` |
| 目标设备 | `[填写]` |

## 1. 指标与埋点

| 事件 ID | 事件名称 | 触发时机 | 参数 | 值域 | 平台 | 对应指标 |
|---|---|---|---|---|---|---|
| E-001 |  |  |  |  | 共用 / Android / iOS |  |

禁止采集内容：

- `[填写]`

## 2. 测试矩阵

| 测试 ID | 场景 | 前置条件 | 操作 | 预期结果 | 实际结果 | 状态 | 证据 |
|---|---|---|---|---|---|---|---|
| QA-001 | 主流程 |  |  |  |  | 通过 / 失败 / 阻塞 |  |
| QA-002 | Loading |  |  |  |  |  |  |
| QA-003 | Empty |  |  |  |  |  |  |
| QA-004 | Error |  |  |  |  |  |  |
| QA-005 | Timeout |  |  |  |  |  |  |
| QA-006 | Permission Denied |  |  |  |  |  |  |
| QA-007 | Interruption / Restore |  |  |  |  |  |  |
| QA-008 | 免费 / 付费 |  |  |  |  |  |  |

## 3. 埋点验收

| 事件 | ID 是否一致 | 参数是否一致 | 值域是否一致 | 时机是否一致 | 结果 |
|---|---|---|---|---|---|
| `[填写]` |  |  |  |  | 通过 / 失败 |

## 4. 设备与质量验收

| 平台 | 系统版本 | 设备 | 核心流程 | 权限 | 性能 | 崩溃 / ANR | 结果 |
|---|---|---|---|---|---|---|---|
| Android |  |  |  |  |  |  |  |
| iOS |  |  |  |  |  |  |  |

## 5. 残余问题

| 问题 | 严重程度 | 影响 | Owner | 处理计划 | 是否阻塞验收 |
|---|---|---|---|---|---|
| `[填写]` | P0 / P1 / P2 |  |  |  | 是 / 否 |

## 6. G4 验收结论

- 核心价值路径：
- PRD、原型、实现一致性：
- 埋点一致性：
- 权限、订阅、广告和恢复行为：
- 异常恢复：
- 性能、崩溃和兼容性：
- 最终结果：`Accepted / Conditional / Rejected`；
- 条件或阻塞项：
