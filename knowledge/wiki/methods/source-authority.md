---
id: method-source-authority
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
tags: [Source of Truth, 冲突, 当前事实]
---

# Source of Truth 优先级

发生冲突时使用以下优先级：

1. 当前用户明确确认。
2. 当前源文件、原型或真实运行状态。
3. 当前项目已经确认的文档。
4. 有来源和时间信息的历史项目知识。
5. 通用模板和通用方法。

历史模板只能提供结构和检查方法，不能覆盖当前产品事实。当当前原型与旧需求文档不一致时，优先采用当前原型中已经确认的事实，并把旧需求标记为冲突或待更新；如果原型本身尚未确认，则不能擅自覆盖，应把差异列为待决策项。

检索结果出现冲突时必须同时返回冲突条目、时间和证据等级，不得静默选择更旧内容。
