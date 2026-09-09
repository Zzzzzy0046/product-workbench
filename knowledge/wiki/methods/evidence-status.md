---
id: method-evidence-status
type: method
domain: evidence
stage: all
platform: [cross-platform]
region: [global]
evidence_level: project-validated
status: active
source:
  - source-historical-workflow-v1
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [事实, 推断, 假设, 验证]
---

# 证据状态

- `[事实]`：有可追溯的来源、数据、原型或真实行为。
- `[推断]`：由事实推导，必须写清推导链。
- `[假设]`：尚未验证，不得包装成行业结论。
- `[决策]`：影响目标、范围、资源或实现的明确选择。
- `[风险]`：可能影响价值、采用、可行性、商业或合规。
- `[待确认]`：当前缺失但不阻断其余工作的输入。

证据强度分层：指导性规则、静态文件验证、本地 Mock、真实构建、真机行为、真实 API 或真实数据。低层证据不能冒充高层验证。

## 新鲜度字段

- `reviewed_at` 只表示知识条目被检查的时间，不自动刷新来源中的事实。
- 用户、市场、竞品、价格、政策和平台能力类结论，应独立记录 `source_observed_at`、`fact_valid_through` 与 `requires_live_refresh`。
- 缺少事实有效期时，按“待刷新”处理，不能据此继承历史 Gate 结论。
