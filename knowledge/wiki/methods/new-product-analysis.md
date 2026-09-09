---
id: method-new-product-analysis
type: method
domain: new-product-analysis
stage: definition
platform: [android, ios]
region: [global]
evidence_level: project-validated
status: active
source:
  - source-template-audit-v1
  - source-heart-rate-original-pdf
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [新品, Heart Rate, Doc Reader, 执行基线]
---

# 新品需求分析方法

新品分析按照“市场 → 用户 → 竞品 → 定位 → MVP → 流程 → 商业化 → 政策 → 预研 → 指标 → 执行决策”推进。用户已经指定要做的品类默认跳过机会门，直接把不确定性写成假设、风险、验证任务和后续收窄条件。

正式 T1 使用 [`template-t1-new-product-analysis`](../../templates/t1-new-product-analysis.md)，保留历史 Heart Rate / Doc Reader 的 0–12 章骨架和结论先行写法；正式 T2、T3、T4 分别使用 [`template-t2-product-framework-version-plan`](../../templates/t2-product-framework-version-plan.md)、[`template-t3-prd-prototype-handoff`](../../templates/t3-prd-prototype-handoff.md)、[`template-t4-tracking-qa-acceptance`](../../templates/t4-tracking-qa-acceptance.md)。

T1–T4 是产品团队实际阅读和执行的主交付物；A0–A7 是状态、证据、Gate、风险和验收追踪层。所有正式文档默认使用中文，英文只保留必要的技术名词和 UI copy。新品分析不展开付费投放、媒体采买、投放归因、ASO 文案、商店素材或商店发布执行。

在写功能前先回答：目标用户是否具体、痛点是否真实、首次价值是否成立、问题是否自然重复、变现是否匹配价值频率、能力承诺是否符合平台政策。证据不足时先收窄范围、安排验证或设置后续 Kill Criteria，不能靠堆功能掩盖问题。只有用户明确要求机会筛选时，才使用 A1 / G1 判断是否继续。
