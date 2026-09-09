# Product KB V0.1 状态

日期：2026-09-09

## 已完成

- 本地 Markdown 知识库目录与 YAML Schema。
- A0–A7 标准模板和知识候选模板。
- 外部来源白名单与敏感信息边界。
- Markdown、TXT、文本型 PDF 解析。
- 标题语义切块和稳定 Chunk ID。
- Qdrant Local dense + sparse Hybrid Search。
- 结构化知识优先、来源去重和查询覆盖重排。
- 文件指纹和增量索引。
- `kb_search`、`kb_get`、`kb_trace`、`kb_find_similar_cases` 四个只读 MCP 工具。
- 11 个代码测试全部通过。
- 30 个 RAG 回归问题全部通过。
- MCP stdio 真实进程冒烟测试通过。
- `product-knowledge-rag` Skill 包创建并校验通过。
- `overseas-consumer-app-lifecycle` Skill 包创建并校验通过。
- Claude 项目级 `.mcp.example.json` 和 Codex 配置示例。
- Heart Rate 第一次工作流回归通过。
- PDF Reader 第二次跨品类回归通过，6 项验收标准全部 PASS；当前阶段为 `OPPORTUNITY`，G1 结论为 `HOLD`。
- Plant Identifier / Plant Care 第三次跨品类回归完成：通用识别方向不建议做，Plant Rescue AI 候选楔子为 `G1 = HOLD`，等待用户、复访和真实照片 Spike。
- 第三次回归验证了“无直接案例时不伪造答案”；两个弱相似案例仅迁移方法，没有迁移产品结论。
- `product-knowledge-rag` 增加默认调用预算，修复单次机会判断过度检索问题。
- MCP 冒烟增加 search → get 往返一致性校验。
- `kb_find_similar_cases` 已强制只返回 `case` 类型，并增加防御性过滤与回归测试。
- MCP 已改为每进程私有 Qdrant 快照，3 个并发客户端冒烟测试通过，无本地索引锁冲突。
- 知识条目增加事实时效字段，明确区分评审日期、事实观察日期、有效期和是否要求实时刷新。
- Product KB MCP 与两个 Skill 已安装到用户级 Codex 配置，并完成安装副本一致性校验。
- Codex CLI 已升级到 0.153.4；使用默认 `gpt-5.6-sol` 原生直连 `kb_search` 成功，未使用 GPT-6。
- GitHub 交付内容已改为 portable examples；本机来源路径、索引和客户端配置不入库。
- 后续正式 Agent 回归使用任务当前默认模型，不锁定特定型号。

## 当前索引

- 发现来源：28 个。
- 有效索引来源：27 个。
- 禁用来源：1 个旧版待改造 Skill。
- 索引切块：322 个。
- RAG 测试：30/30。

## 尚未执行

- 尚未建立正式知识候选的人工审核命令。
- Claude 仅保留项目级配置示例，未安装到 Claude 全局目录。

## 下一阶段

1. 建立知识候选的人工审核命令，形成“提取—审核—发布—重建索引”闭环。
2. 根据三次回归结果定义并发布 V1.0。
3. 在第一个正式新品项目中使用 V1.0，并记录实际节省时间、返工率和 Gate 误判率。
