---
id: template-t4-acceptance-run
type: template
domain: acceptance
stage: implementation-acceptance
platform: [android, ios]
region: [global]
evidence_level: direct
status: superseded
source: [template-f3-development-acceptance, template-a7-tracking-qa-acceptance]
reviewed_at: 2026-09-10
tags: [T4-Run, 真实构建, QA, 复测]
---

# T4-Run 真实构建验收记录（快速流程已并入 F3 开发验收清单）

> 只有导入真实构建、设备、日志、截图或录像证据后才可使用本模板。没有执行证据的项目必须标记 `NOT_RUN` 或 `BLOCKED`，不能标记通过。

## 0. 验收批次

| 字段 | 内容 |
|---|---|
| 产品/版本 | `[填写]` |
| 构建 ID/文件 | `[填写]` |
| 测试日期 | `[填写]` |
| 测试设备 | `[填写]` |
| 关联 T4-Plan/F5 | `[填写]` |

## 1. 实际测试结果

| QA ID | 设备/系统 | 实际步骤 | 实际结果 | PASS/FAIL/BLOCKED/NOT_RUN | 证据 | 缺陷 ID | Owner | 复测版本/结果 |
|---|---|---|---|---|---|---|---|---|
| QA-001 |  |  |  | NOT_RUN |  |  |  |  |

## 2. 埋点实际验收

| 事件 ID | 实际事件/参数/值域 | 触发时机 | 去重 | 数据最小化 | 日志/抓包证据 | 结果 |
|---|---|---|---|---|---|---|
| E-001 |  |  |  |  |  | NOT_RUN |

## 3. 残余问题与条件关闭

| Condition/缺陷 ID | 影响 | 阻塞范围 | Owner | 截止 | 关闭证据 | 状态 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

## 4. G4 结论

- 核心闭环实测：
- PRD/原型/实现一致性：
- 异常恢复：
- 崩溃、性能和兼容性：
- 埋点一致性：
- 最终结果：`Accepted / Conditional / Rejected`；
- 结论证据：
- 下一次复核日期：
