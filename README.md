# Product KB MVP

本项目是出海 C 端产品工作流的本地知识底座：Markdown 是事实源，Qdrant Local 保存生成索引，MCP 向 Codex 和 Claude 提供只读检索。

## 本地产品工作台

已提供可运行的单人工作台：创建项目、导入文档和截图、调用桌面竞品评论采集器，按当前阶段调用 Codex 整理分析、原型需求与评审交接，支持编辑、批注和修订，并导出中文 Markdown / Word / PDF / Excel / CSV 或完整项目包。

```powershell
.venv\Scripts\python.exe workbench\app.py
```

启动后打开 `http://127.0.0.1:8765`。安装、使用方式、扩展机制和明确边界见 [工作台使用手册](workbench/README.md)。工作台已接入双索引 Hybrid RAG：当前项目资料独立索引，全局 Product KB 只读补充方法知识；不可用时自动回退关键词检索。

资料页也可直接使用「Android 实机截图走查」：指定已安装 App 和范围，调用已有截图 skill 自动走查并按模块输出流程 PNG；遇到需人工处理的页面暂停，确认后再入库。使用方式与边界见 [实机截图功能说明](docs/WORKBENCH-ANDROID-CAPTURE.md)。

## 工作流使用手册

日常新品主干为“市场和竞品分析 → 原型图＋需求说明 → 初审修改 → 终审整理 → 需求评审”，从当前阶段继续，每轮明确范围与交付点。F1 保留五章分步生成与 Heart Rate 式完整分析；原型阶段准备公共规则、功能流程与页面状态、原型制作交接和中文需求旁注，实际原型在外部工具制作并回传。需求评审阶段按需补充独立 F2 PRD、完整埋点和 F3 开发实测清单，产品验收用例使用三列表。AI 自查和工作台确认不等于部门业务评审通过。

竞品评论 CSV、政策来源、技术日志、截图和研究资料进入资料索引，相关结论引用它们，不复制整份原始数据。流程不默认生成用户访谈、假设验证、风险清单、技术 Spike、Gate 或条件闭环。

本轮目标由用户输入决定，不预设固定回收周期、收益目标或放行门槛。已提供的经营指标仍可按本轮需要使用；既有项目资料和历史交付物保留原文，不自动重写。

完整使用方式、资料规则和历史正式模式见：

[《出海 C 端新品工作流使用手册》](docs/WORKFLOW-USER-MANUAL.md)

正式模板位于 `knowledge/templates`。F1 与 F2 使用已有模板，新增按需模板为 `shared-rules.md`、`flow-pages.md`、`prototype-handoff.md`、`review-changes.md`、`consistency-review.md`、`product-acceptance.md`；`f3-development-acceptance.md` 保留开发实测用途。历史 T1–T4 仅在明确要求 0–12 章正式研究或大型跨团队材料时按文件路径使用，不参与默认 RAG 检索。

本轮提炼依据、使用变化与原型执行边界见 [GBA 工作流更新说明](docs/WORKBENCH-GBA-WORKFLOW-UPDATE.md)。本仓库只保留可复用方法，不复制具体项目业务值与私有原型定位。

## 当前范围

- 工作台支持 Markdown、TXT、CSV、JSON、文本型 PDF、DOCX 和 PNG/JPG/WEBP 截图。
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
