# Product KB MVP

本项目是出海 C 端产品工作流的本地知识底座：Markdown 是事实源，Qdrant Local 保存生成索引，MCP 向 Codex 和 Claude 提供只读检索。

## 本地产品工作台

已提供可运行的单人工作台：创建项目、维护背景、导入资料、准备任务包、调用 Codex 生成、评审与修订、导出中文 Markdown。

```powershell
.venv\Scripts\python.exe workbench\app.py
```

启动后打开 `http://127.0.0.1:8765`。安装、使用方式、扩展机制和明确边界见 [工作台使用手册](workbench/README.md)。工作台当前使用关键词检索；下方 Product KB Hybrid RAG 仍为独立能力。

## 工作流使用手册

以下手册是完整交付体系的参考；日常在工作台按需选择任务，不必每次跑完全部阶段。

完整的 A0–A7 / T1–T4 交付体系、Gate、跳转规则和项目目录见：

[《出海 C 端新品工作流使用手册》](docs/WORKFLOW-USER-MANUAL.md)

正式产品文档模板位于 `knowledge/templates`：`t1-new-product-analysis.md`、
`t2-product-framework-version-plan.md`、`t3-prd-prototype-handoff.md`、
`t4-tracking-qa-acceptance.md`。T1–T4 是面向产品、设计、研发、数据和 QA 的主交付物，
A0–A7 是状态、证据、Gate、风险和验收追踪层。用户已经指定要做的品类默认跳过 G1 Opportunity Gate，直接进入 T1 → G2 Definition；A1/G1 仅在明确要求机会筛选时启用。

## 当前范围

- 支持 Markdown、TXT 和文本型 PDF。
- 支持 dense + sparse Hybrid Search 与 metadata filter。
- 支持外部来源白名单、增量指纹和来源追踪。
- 正式检索默认只返回 `status: active` 的知识。
- `knowledge/00_inbox` 不进入索引；正式知识不提供 MCP 写操作。
- 不收录付费投放、媒体采买、商店素材和商店发布执行内容。

## 本地运行

在 Windows PowerShell 中：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\product-kb.exe doctor
.venv\Scripts\product-kb.exe index --reset
.venv\Scripts\product-kb.exe search "Heart Rate 新品模板的核心写法是什么"
.venv\Scripts\product-kb.exe eval
```

第一次建立索引会下载本地 embedding 模型；之后只处理发生变化的来源。

首次使用外部资料时，把 `config/sources.example.yaml` 复制为
`config/sources.yaml`，再登记本机资料路径。`sources.yaml`、生成索引和虚拟环境
都不会进入 Git。

## MCP 启动

```powershell
.venv\Scripts\product-kb-mcp.exe
```

Claude 项目配置参考 `.mcp.example.json`；Codex 配置参考
`integration/codex-config-snippet.example.toml`。复制为本地配置后，把
`C:\\PATH\\TO\\product-kb` 替换成实际克隆目录。

工作流使用任务当前选择的 Agent 模型，不锁定特定型号。Agent 模型与本项目的
本地 embedding 模型是两套独立配置，切换 Agent 模型不会重建检索索引。

## 只读工具

- `kb_search`：混合检索，可按 product、stage、platform、region、domain、type 过滤。
- `kb_get`：按不可变 chunk ID 获取正文和元数据。
- `kb_trace`：追踪来源路径、指纹和切块位置。
- `kb_find_similar_cases`：只检索正式案例。

## 内容维护

1. 外部原始文档在本机 `config/sources.yaml` 中显式登记，并且必须位于 `allow_roots`。
2. 结构化知识放入 `knowledge` 的正式目录并使用 YAML frontmatter。
3. 待审核内容放入 `knowledge/00_inbox`，不会进入索引。
4. 用户明确授权沉淀后，再移动候选知识并运行增量 `index`。
5. `reviewed_at` 只表示知识条目被检查的时间，不代表其中的市场事实仍然有效。
6. 用户、市场、竞品、价格、政策和平台能力类资料应同时维护
   `source_observed_at`、`fact_valid_through` 和 `requires_live_refresh`。
7. 更新索引后重启正在运行的 MCP 客户端，使其重新读取只读运行时快照。

## 验证

`product-kb eval` 会运行 `evals/questions.yaml` 中的 30 个真实检索问题。第一版验收要求：全部问题至少在 Top 5 命中一个预期来源，并能通过 `kb_trace` 回溯原文。

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\mcp_smoke.py
.venv\Scripts\python.exe scripts\mcp_concurrency_smoke.py
```

并发冒烟会同时启动 3 个 MCP 进程，验证多个 Codex 任务读取同一份知识库时不会争用 Qdrant Local 的 canonical index。
