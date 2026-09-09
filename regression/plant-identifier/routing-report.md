# Plant Identifier / Plant Care 第三品类回归报告

日期：2026-09-09

## 结论

- 工作流成功从 `INITIALIZATION` 路由到 `OPPORTUNITY`，先创建 A0/A1，没有提前生成 PRD。
- Product KB 没有植物识别专用案例时，没有伪造历史知识；PDF Reader 与 Heart Rate 只作为弱类比。
- 当前事实通过 Google Play、Android、Google Play Policy、Pl@ntNet API 和研究论文实时刷新。
- 产品结论为：通用 Plant Identifier 不做；Plant Rescue AI 候选楔子进入 `G1 = HOLD`，等待用户、复访和技术 Spike。
- 付费投放、ASO、商店素材和发布执行未进入工作流。

## Product KB 实际调用

| 工具 | 调用 | 结果 |
|---|---:|---|
| `kb_search` | 9 | 方法、Gate、模板、商业化与风险均命中；2 次过滤过窄为空 |
| `kb_find_similar_cases` | 2 | 仅得到两个低分弱相似案例，未迁移结论 |
| `kb_get` | 24 | 23 次返回；1 次由 Agent 报 `found:false`，后续无法复现 |
| `kb_trace` | 4 | 主方法、Gate、范围和 A1 模板均完成追溯 |

关键复用来源：

- `method-new-product-analysis` / `59e285fb-d63d-9ea1-a1b0-5e60c87cc11b`
- `method-workflow-gates` / `46bc8276-cdae-654b-340b-6bd37b915655`
- `decision-workflow-scope-2026-09-08` / `7c5ce5d7-c8ef-0924-6c92-c3f2140d648d`
- `template-a0-project-manifest` / `05d8cd10-7298-7139-2077-1ccb3a67e502`
- `template-a1-opportunity-brief` / `2cfa2122-ae50-7a9e-aede-0b7fbafc1a45`
- `pattern-monetization-task-boundary` / `3019c173-4766-58d5-0229-5575bcc60405`
- 弱相似案例：`case-pdf-reader-product-boundary`、`case-heart-rate-template-evolution`

## 验收

| 验收项 | 结果 | 说明 |
|---|---|---|
| 新品先 A0/A1，不直接 PRD | PASS | 当前停在 Opportunity |
| 当前动态事实实时核验 | PASS | 竞品、政策、Android 和技术均使用 2026-09-09 可核验来源 |
| 历史案例不覆盖当前事实 | PASS | 两个案例 retrieval score 为 0，仅迁移方法 |
| Gate 有证据、缺口、Owner、阈值和 Kill Criteria | PASS | G1 明确 HOLD |
| 排除投放与商店发布 | PASS | 仅保留约束产品的政策检查 |
| 重要 RAG 结论可追溯 | PASS | 4 个关键来源完成 trace |
| 检索效率 | FAIL → FIXED | 单次机会判断用了 39 次调用，已增加默认调用预算 |
| Search → Get 一致性 | PASS | 增加永久 round-trip 冒烟断言；问题无法复现 |

## 回归修订

1. `product-knowledge-rag` 默认预算收紧为：2 次决策搜索 + 1 次放宽、1 次相似案例、最多 6 次 get、4 次 trace。
2. 明确普通任务不得读取所有搜索结果；只有显式知识审计或具体冲突才能超预算。
3. 明确 canonical 名称是 `A0 Project Manifest` 与 `A1 Opportunity Brief`；旧盘点中的其他 A0/A1 名称只作为历史别名。
4. MCP 冒烟新增 search/get round-trip 校验，避免以后把 Agent 参数错误误判为索引损坏。

## 最终判断

第三品类回归证明当前系统已经能处理“知识库没有直接答案”的产品：它可以复用方法、拒绝硬套案例、主动补实时证据，并在证据不足时停在 HOLD。当前主要短板从“能不能跑”转为“如何控制检索成本，以及如何把新领域知识经过人工审核后沉淀回 KB”。
