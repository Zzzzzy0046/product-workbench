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
reviewed_at: 2026-10-21
expires_at:
supersedes: []
tags: [Source of Truth, 冲突, 当前事实]
---

# Source of Truth 优先级

发生冲突时使用以下优先级：

1. 当前用户明确确认。
2. 用户指定采用的当前已确认基线，包括原型旁注、公共规则和项目文档。
3. 当前源文件、原型或真实运行状态中实际可观察的表现。
4. 有来源和时间信息的历史项目知识。
5. 通用模板和通用方法。

历史模板只能提供结构和检查方法，不能覆盖当前产品事实。原型、草图和实现用于描述实际表现，确认基线用于说明约定行为：二者不一致时保留差异，不能把新上传的草图、实现偏差或文件名为“最终”的材料自动当成新决定。已有明确用户确认时按该口径整理，同时如实记录哪些外部对象尚未同步；没有确认时列为待决定项。

检索结果出现冲突时必须同时返回冲突条目、时间和证据等级，不得静默选择更旧内容。
