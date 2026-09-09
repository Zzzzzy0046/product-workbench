# Product KB V0.1 状态

日期：2026-09-09

## 本地工作台首版

- 新增 `workbench/` 可运行工作台，复用当前 Product KB 和 T1–T4 中文模板。
- 项目持久化、三层上下文、六类资料导入、项目隔离检索、任务输入快照、Codex 生成、Markdown 导出、评审和修订已实现。
- 能力包通过 JSON 定义加载；评论分析可启用，自动爬取仍未接入。
- 工作台检索为关键词片段检索，原有 Hybrid RAG / MCP 独立保留。
- 使用方式与功能边界见 `workbench/README.md`；设计参考见 `workbench/DESIGN.md`；验收记录见 `workbench/VERIFICATION.md`。
- 本机项目资料、工作台数据库及运行记录不进入 Git。

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
- 已整理《出海 C 端新品工作流使用手册》，明确 A0–A7 控制交付物、T1–T4 产品交付物、Gate、已验证项目跳转规则和最小交付标准。
- 工作流已调整为“交付物优先”：完整新品请求默认产出 T1 0–12 全文；A0/A2/A6 作为控制和追踪层；A1/G1 仅在明确要求机会评估时启用。
- 新增流程约定：用户指定的品类默认视为要做，不再用机会门阻断；T1 负责把不确定性转化为假设、风险、验证任务、范围收窄条件和 T2 进入条件，默认首个阻断 Gate 为 G2 Definition Gate。
- 桌面版“竞品信号工坊”已定义为可选竞品证据采集环节：默认只抓取和核验评论，不调用 DeepSeek，不自动写入 Product KB。
- 已建立正式中文 T1–T4 模板，并将方法、Router、生命周期 Skill 和使用手册统一到同一组模板 ID。
- 已清理新品分析模板中的付费投放、媒体采买、投放归因、ASO 文案、商店素材和商店发布执行内容；仍保留平台能力、政策、权限、订阅和广告等产品约束。
- 已激活当前新品工作流 Skill 作为本地 RAG 来源，并验证 T1–T4 模板可被检索。

## 当前索引

- 发现来源：32 个。
- 有效索引来源：32 个。
- 禁用来源：0 个。
- 索引切块：400 个。
- RAG 测试：30/30。

## 尚未执行

- 尚未建立正式知识候选的人工审核命令。
- Claude 仅保留项目级配置示例，未安装到 Claude 全局目录。

## 下一阶段

1. 建立知识候选的人工审核命令，形成“提取—审核—发布—重建索引”闭环。
2. 根据三次回归结果定义并发布 V1.0。
3. 在第一个正式新品项目中使用 V1.0，并记录实际节省时间、返工率和 Gate 误判率。
