---
id: decision-knowledge-writeback-policy
type: decision
domain: knowledge-governance
stage: knowledge-foundation
platform: [cross-platform]
region: [global]
evidence_level: project-validated
status: active
source:
  - source-workflow-inventory-v2
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [RAG, 回写, 授权, 安全]
---

# 知识回写规则

检索接口只读。任务结束时可以生成知识候选，但不得直接修改正式知识库。

只有用户明确说“沉淀”“归档”“保存到知识库”或同等明确表达后，候选知识才能通过校验并进入正式目录。同步到 Notion 需要单独的明确授权。

API Key、Token、Cookie、账号凭证、浏览器数据、私人账号信息、未脱敏公司敏感数据、重复截图和无结论中间分析禁止进入知识库。
