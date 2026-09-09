# PDF Reader Product KB 回归报告

日期：2026-09-09

## 结论

- 两个 Skill 在独立新任务中成功发现并完整读取。
- 四个 Product KB MCP 工具均通过 stdio 协议真实调用。
- 六项工作流验收全部通过。
- 当前阶段为 `OPPORTUNITY`，G1 为 `HOLD`。
- 历史 `Android Conditional Go / iOS Hold` 未被错误继承为当前决定。

## MCP 实际调用

| 工具 | 结果 | 证据 |
|---|---|---|
| `kb_search` | PASS | 6 组决策型检索成功 |
| `kb_get` | PASS | 7 个高影响 Chunk 完整读取 |
| `kb_trace` | PASS | 6 个来源的路径、指纹、元数据和 locator 核实 |
| `kb_find_similar_cases` | PASS | 回归发现并修复 curated results 绕过 cases-only 过滤的问题；修复后仅返回 `case` 类型 |

## 关键追溯

| 主题 | Source ID | Chunk ID | Locator |
|---|---|---|---|
| Reader-first 边界 | `case-pdf-reader-product-boundary` | `57ef3de7-6538-2023-1d8e-978f643876f5` | PDF Reader 的产品边界 |
| Android 文件入口 | `source-pdf-reader-heart-template` | `d7f9b436-c175-ba01-9e1f-1cc25193f053` | 新品 PDF Reader > 10、预研需求 > 1. Android 文件入口 |
| 新品分析方法 | `method-new-product-analysis` | `59e285fb-d63d-9ea1-a1b0-5e60c87cc11b` | 新品需求分析方法 |
| Gate | `method-workflow-gates` | `46bc8276-cdae-654b-340b-6bd37b915655` | 工作流 Gate |
| 当前范围 | `decision-workflow-scope-2026-09-08` | `7c5ce5d7-c8ef-0924-6c92-c3f2140d648d` | 完整工作流的范围边界 |
| A0 模板 | `template-a0-project-manifest` | `05d8cd10-7298-7139-2077-1ccb3a67e502` | A0 Project Manifest > 输入与交付物 |

## 六项验收

| 验收项 | 结果 |
|---|---|
| 先 A0，不直接 PRD | PASS |
| 正确调用方法与模板 | PASS |
| 区分历史与当前事实 | PASS |
| 重要结论可追溯 | PASS |
| 排除付费投放与商店发布 | PASS |
| 证据不足时明确 HOLD | PASS |

## 回归发现与处理

1. Curated results 绕过 `type=case`：检索层改为对 curated points 应用同一 metadata filter，并增加自动化断言。
2. 多 MCP 进程争用 embedded Qdrant：每个 MCP 进程改为读取私有运行时快照；进程内复用一个 client 并串行调用。
3. `reviewed_at` 容易被误解为事实有效期：新增 `source_observed_at`、`fact_valid_through`、`requires_live_refresh`。
4. 历史动作与当前授权范围冲突：A0 Manifest 契约新增 `Not Applicable / Deferred` 规则。
5. Desktop 当前进程的原生工具目录不会热刷新：已用全新 Codex CLI 进程和默认 `gpt-5.6-sol` 原生调用 `kb_search`，返回 `MCP_OK case-pdf-reader-product-boundary`；未使用 GPT-6。

## 修复后验证

- 单元测试：11/11。
- RAG 回归：30/30。
- 索引：27 个有效来源，322 个切块。
- MCP stdio 冒烟：四个工具可发现，类似案例结果仅含 `case`。
- MCP 并发冒烟：3 个并发进程全部通过，无 Qdrant 锁冲突。
