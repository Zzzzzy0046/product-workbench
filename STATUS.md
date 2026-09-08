# Product KB V0.1 状态

日期：2026-09-08

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
- 8 个代码测试全部通过。
- 30 个 RAG 回归问题全部通过。
- MCP stdio 真实进程冒烟测试通过。
- `product-knowledge-rag` Skill 包创建并校验通过。
- `overseas-consumer-app-lifecycle` Skill 包创建并校验通过。
- Claude 项目级 `.mcp.example.json` 和 Codex 配置示例。
- Heart Rate 第一次工作流回归通过。
- GitHub 交付内容已改为 portable examples；本机来源路径、索引和客户端配置不入库。
- 后续正式 Agent 回归模型锁定为 `gpt-6-astra`（新任务生效）。

## 当前索引

- 发现来源：28 个。
- 有效索引来源：27 个。
- 禁用来源：1 个旧版待改造 Skill。
- 索引切块：321 个。
- RAG 测试：30/30。

## 尚未执行

- 未修改含既有配置和第三方凭证的全局 Codex 配置。
- 未把两个 Skill 覆盖安装到用户级 Codex/Claude 目录。
- 当前已经运行的 Codex 会话不会动态出现新 MCP 工具，也不能由任务内热切换模型；需要配置后新任务加载 `gpt-6-astra`。
- 尚未用第二个真实项目做跨品类回归。
- 尚未建立正式知识候选的人工审核命令。

## 下一阶段

1. 安全安装 MCP 与两个 Skill 到目标客户端。
2. 新任务使用 `gpt-6-astra` 验证能直接调用 Product KB。
3. 使用 PDF Reader 做第二次跨品类回归。
4. 根据两次回归修订后发布 V1.0。
