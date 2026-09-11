---
id: template-f4-tracking-spec
type: template
domain: analytics-instrumentation
stage: tracking-design
platform: [android, ios]
region: [global]
evidence_level: approved-plan
status: active
source: [method-new-product-analysis, template-f2-core-prd, pattern-prd-state-closure]
reviewed_at: 2026-09-11
tags: [F4, 完整埋点, tracking-spec, 蓝湖, PRD, 可编辑]
---

# 完整埋点方案

> 本文档面向产品、研发和数据同事。默认使用中文；事件 ID、参数名、SDK 名称和枚举值使用英文。每个事件必须回答一个产品问题，不能机械记录所有按钮。

## 0. 方案范围

| 字段 | 内容 |
|---|---|
| 产品 / 版本 / 平台 | `[填写]` |
| 关联 PRD | `[填写]` |
| 原型来源 | `[蓝湖快照 / 截图 / 无]` |
| 本轮核心问题 | `[填写要通过数据回答的问题]` |
| 包含模块 | `[填写]` |
| 明确排除 | `[填写]` |

## 1. 页面与流程覆盖

| 页面 / 状态 | 用户目标 | 入口 | 成功结果 | 失败、取消、超时或重试 | 来源 |
|---|---|---|---|---|---|
| `[页面]` |  |  |  |  |  |

## 2. 埋点事件总表

> 页面完整展示使用 `_page_display`；普通按钮、返回、关闭和 Tab 合并为 `_page_click`；核心异步业务必须记录最终 `_result`，不能用点击代表成功。

| 事件 ID | 中文名称 | 事件类型 | 触发时机 | 分析问题 | 发送平台 | 优先级 | 来源页面 / 状态 |
|---|---|---|---|---|---|---|---|
| `xxx_page_display` |  | page_display | 页面完整展示后 |  | Firebase / Amplitude / Umeng | P0 |  |
| `xxx_page_click` |  | page_click | 用户点击普通操作后 |  |  | P1 |  |
| `xxx_result` |  | result | 业务或 SDK 回调结束后 |  |  | P0 |  |

## 3. 事件参数表

> 同一固定参数的每个枚举值单独一行；开放值必须写格式、范围和隐私限制。不要记录 Cookie、Token、原始用户内容、精确位置、设备地址或可识别蓝牙广播标识。

| 事件 ID | 参数名 | 参数中文名 | 类型 | 枚举值 / 开放值 | 何时上报 | 是否必填 | 隐私与实现说明 |
|---|---|---|---|---|---|---|---|
| `xxx_result` | `result` | 结果 | enum | `success` | 最终成功回调 | 是 |  |
| `xxx_result` | `result` | 结果 | enum | `fail` | 最终失败回调 | 是 |  |
| `xxx_result` | `result` | 结果 | enum | `cancel` | 用户取消或主动返回 | 是 |  |
| `xxx_result` | `result` | 结果 | enum | `timeout` | 达到业务超时 | 是 |  |

## 4. 权限、商业化与异常闭环

### 4.1 权限

| 权限流程 | 展示事件 | 点击事件 | 最终结果事件 | 参数 | 拒绝后的数据问题 |
|---|---|---|---|---|---|
| 系统权限请求 | `system_permission_request` |  | `system_permission_result`（确有分析需要时） | `permission_type`、`result` |  |
| 产品权限说明弹窗 | `permission_dialog_display` | `permission_dialog_click` |  | `permission_type`、`button` |  |

### 4.2 异常和恢复

| 异常 / 状态 | 触发事件 | 恢复动作事件 | 最终结果 | 必要参数 |
|---|---|---|---|---|
| Loading / Empty |  |  |  |  |
| Error / Timeout |  |  |  |  |
| Permission Denied |  |  |  |  |
| Interruption / Restore |  |  |  |  |

### 4.3 商业化

只有当前需求确实包含广告、订阅或 IAP 时才添加相关事件。首次核心价值前不得因为模板惯例自动增加商业化事件。

## 5. 核心漏斗与数据问题

| 漏斗步骤 | 事件 / 条件 | 成功定义 | 失败定义 | 要回答的产品问题 |
|---|---|---|---|---|
| 进入核心功能 |  |  |  |  |
| 完成关键操作 |  |  |  |  |
| 获得核心结果 |  |  |  |  |
| 再次尝试 / 复用 |  |  |  |  |

## 6. 研发验收映射

| 事件 ID | 触发页面 / 操作 | 预期日志 | 参数和值检查 | F3 QA ID | 实际日志 | 状态 |
|---|---|---|---|---|---|---|
|  |  |  |  |  | 尚未产生 | NOT_RUN |

## 7. 资料索引与缺口

| 编号 | 资料 | 类型 | 支持的页面 / 事件 | 日期 |
|---|---|---|---|---|
| S1 |  | F2 / 蓝湖快照 / 截图 / 其他 |  |  |

- 原型中没有的模块不新增事件。
- 没有明确最终回调的异步结果标记“待研发确认”，不编造 success/fail 规则。
- 方案完成前检查事件重复、参数命名漂移、枚举多值挤在一个单元格、隐私字段和页面状态遗漏。

下一步：将本方案交给研发确认 SDK、事件触发时机和参数映射；开发后在 F3 回填实际日志与复测证据。
