# 产品工作台项目文件地图

盘点日期：2026-09-11  
盘点范围：项目根目录；不逐项展开 `.git/`、`.venv/`、`__pycache__/` 和 `.pytest_cache/` 内部文件。  
文件数量：除上述依赖、版本历史和缓存目录外，共 269 个文件。

## 1. 阅读标记

- `核心`：工作台或 Product KB 运行、测试、分发需要维护的文件。
- `本机`：当前电脑生成或配置的内容，不应提交 Git。
- `历史`：用于追溯设计和回归，不参与当前默认工作流。
- `生成`：可以由程序重新生成，不应手工编辑。
- `候选清理`：当前运行不依赖，可以在单独确认后归档或删除。

## 2. 根目录

- `.git/`：`本机` Git 的提交历史、分支和对象数据库；不是产品功能文件，不能手工删除其中单个文件。
- `.venv/`：`本机` Python 虚拟环境和第三方依赖；可根据 `pyproject.toml` 重建，不进入 Git。
- `.pytest_cache/`：`生成` pytest 的运行缓存；删除不会影响源码。
- `.index/`：`生成` 全局 Product KB 的 Qdrant Local 索引。
  - `manifest.json`：记录已索引来源、文件指纹、模型和 Chunk 对应关系。
  - `qdrant/.lock`：Qdrant 本地访问锁，不是知识正文。
  - `qdrant/meta.json`：Qdrant 本地实例元数据。
  - `qdrant/collection/product_kb/storage.sqlite`：全局知识向量和检索 payload 的本地存储；可重新索引生成。
- `.gitignore`：`核心` 规定虚拟环境、索引、本机配置、项目资料、工作台数据库和运行产物不提交 Git。
- `.mcp.example.json`：`核心` Claude 项目级 MCP 配置模板，可分发，不含本机真实路径。
- `.mcp.json`：`本机` 当前电脑实际 MCP 配置；可能包含本机路径，已被 Git 忽略，不应发给同事直接复用。
- `pyproject.toml`：`核心` Python 包、版本、依赖、命令入口和 pytest 路径配置。
- `README.md`：`核心` 仓库总入口，介绍 Product KB、工作台启动、MCP、索引和验证方法。
- `STATUS.md`：`历史/状态快照` 记录 2026-09-11 当时的完成情况。部分描述已经落后，例如仍写有团队资源、验证周期和旧测试数量，不能作为唯一当前事实。
- `projects/`：`本机` 当前为空；预留给具体产品项目资料，并被 Git 忽略。

## 3. `config/`：知识来源配置

- `sources.example.yaml`：`核心` 可分发的外部知识来源配置示例，说明 `allow_roots`、文件路径和来源 metadata。
- `sources.yaml`：`本机` 当前电脑真正使用的来源清单和白名单路径；不进入 Git。未来热插拔架构应把这类配置迁移到工作台“知识源”页面管理。

## 4. `docs/`：面向人阅读的文档

- `WORKBENCH-OVERVIEW.md`：`核心` 工作台产品介绍，解释使用场景、技术能力、信息流、资料、任务、版本、批注、回收站和蓝湖接入。
- `WORKFLOW-USER-MANUAL.md`：`核心` F1 新品分析、F2 核心 PRD、F3 开发验收和可选埋点的当前使用手册；已按快速迭代范围移除团队资源、验证周期和平台/权限独立章节。
- `WORKFLOW-MODIFICATION-CHECKLIST.md`：`历史` GBA 全流程后形成的 V0.2 修改记录，保留了 F1–F6、Gate、Spike 等已经取消的中间设计，不是当前操作规范。
- `WORKBENCH-NEXT-PHASE-MODIFICATION-CHECKLIST.md`：`当前实施与后置清单`，记录本轮图片、评论采集、导出、质量校验、项目迁移的完成状态，以及后置插件内核、知识候选和检索过滤。
- `PROJECT-FILE-MAP.md`：`说明文档` 当前这份文件地图。

## 5. `evals/`：RAG 检索回归题

- `questions.yaml`：`核心测试数据` 30 条检索问题及预期命中来源，用于检查 Product KB 是否能找回正确的方法、模板、规则和案例。它测试的是检索，不是模型回答质量。

## 6. `integration/`：Codex 和 Claude 接入材料

- `claude-project-setup.md`：`核心说明` Claude Code 如何加载项目级 Product KB MCP。
- `codex-config-snippet.example.toml`：`核心` 可分发的 Codex MCP 配置示例，路径为占位符。
- `codex-config-snippet.toml`：`本机` 当前电脑的 Codex 配置片段，包含真实本机路径，已被 Git 忽略。
- `skill-install-map.md`：`核心说明` 两个 Skill 的源码目录，以及安装到 Codex、Claude 用户目录的位置和覆盖规则。

## 7. `schemas/`：知识数据格式约束

- `knowledge-entry.schema.json`：`核心` 规定正式知识条目的 id、类型、状态、平台、区域、证据级别、时效和来源等字段。
- `source-registry.schema.json`：`核心` 规定外部知识来源配置的路径白名单和 metadata 格式。

## 8. `scripts/`：独立验证脚本

- `mcp_smoke.py`：`核心测试` 启动真实 MCP 子进程，验证 initialize、工具列表以及 search → get → trace 的调用闭环。
- `mcp_concurrency_smoke.py`：`核心测试` 同时启动多个 MCP 客户端，检查多个任务读取本地 Qdrant 快照时是否发生锁冲突。

## 9. `src/product_kb/`：Product KB 核心代码

- `__init__.py`：`核心` Python 包入口和版本标识。
- `models.py`：`核心` 定义来源文档和 Chunk 的数据对象，以及写入索引的 payload。
- `config.py`：`核心` 读取知识目录、来源配置、索引目录、Collection 和 embedding 模型设置。
- `frontmatter.py`：`核心` 解析 Markdown YAML frontmatter，并拒绝未闭合或格式错误的头部。
- `sources.py`：`核心` 发现内部知识与外部白名单文件，规范 metadata、解析文件并计算指纹。
- `chunking.py`：`核心` 按 Markdown 标题和 PDF 页面切块，生成稳定 Chunk ID。
- `index.py`：`核心` Qdrant Local Hybrid Index，实现构建、增量更新、dense/sparse 检索、过滤、去重、重排、get 和 trace。
- `cli.py`：`核心` `product-kb` 命令行入口，提供 doctor、index、search、get、trace 和 eval。
- `mcp_server.py`：`核心` 只读 MCP 服务，暴露 `kb_search`、`kb_get`、`kb_trace`、`kb_find_similar_cases`。

## 10. `knowledge/`：仓库内置知识库

### `knowledge/00_inbox/`

- `README.md`：`核心规则` 待审核知识候选的存放规则；该目录默认不进入正式索引。

### `knowledge/cases/`

- `heart-rate-template-evolution.md`：`active` Heart Rate 新品文档模板如何演进的案例，是当前 F1 结构的重要历史依据。
- `pdf-reader-product-boundary.md`：`active` PDF Reader 为什么采用 Reader-first、如何处理 Android 文件打开和权限边界的案例。

### `knowledge/decisions/`

- `knowledge-writeback-policy.md`：`active` 知识候选、人工确认、敏感信息和禁止自动写回的决策规则。
- `workflow-scope.md`：`active` 当前工作流包含什么、不包含投放和商店发布什么，以及快速模式边界。

### `knowledge/wiki/methods/`

- `evidence-status.md`：`active` 事实、推断、假设、决策、风险和证据新鲜度的历史方法；快速正文目前不要求显示这些标签。
- `new-product-analysis.md`：`active` 当前新品分析方法，说明从资料到 F1、F2、F3 的轻量路径。
- `source-authority.md`：`active` 当前用户确认、当前原型、当前 PRD和历史资料发生冲突时的优先级。
- `workflow-gates.md`：`active 但非默认流程` 历史正式模式的 G1–G5 Gate 定义；快速工作台不展示 Gate。

### `knowledge/wiki/patterns/`

- `monetization-task-boundary.md`：`active` 广告、订阅和 IAP 不应打断核心任务的产品模式。
- `prd-state-closure.md`：`active` PRD 必须覆盖 Loading、Empty、Error、取消、失败和恢复等状态闭环。

### `knowledge/templates/` 当前模板

- `a0-project-manifest.md`：`active` 项目身份、资料、交付物状态和当前事项的项目清单模板；工作台界面已有部分同类数据。
- `a5-prototype-handoff.md`：`active` 左侧页面效果、右侧中文需求和美术标注的原型交接模板。
- `f1-new-product-analysis.md`：`active/核心` 当前快速模式新品需求分析模板。
- `f2-core-prd.md`：`active/核心` 当前页面级核心 PRD 模板。
- `f3-development-acceptance.md`：`active/核心` 当前开发前预期、开发后实测、问题和复测共用的验收模板。
- `f4-tracking-spec.md`：`active/核心` 可选完整埋点方案模板，中文说明配英文事件和参数标识。
- `knowledge-candidate.md`：`active` 将项目经验提炼为待人工审核知识候选时使用的模板。

### `knowledge/templates/` 历史或被替代模板

- `a1-opportunity-brief.md`：`archived` 历史机会分析和 G1 模板；用户给出的品类默认要做，因此不进入默认流程。
- `a2-competitor-evidence-pack.md`：`archived` 历史正式竞品证据包；当前竞品差异已并入 F1。
- `a3-product-definition.md`：`archived` 历史产品定义模板；当前定位、范围、框架已并入 F1。
- `a4-prd.md`：`archived` 历史完整 PRD；当前用更轻的 `f2-core-prd.md`。
- `a6-risk-decision-log.md`：`archived` 历史风险、假设和决策台账；当前快速流程不生成。
- `a7-tracking-qa-acceptance.md`：`archived` 历史大一统埋点/QA/验收包。
- `f2-competitor-delta-pack.md`：`superseded` 已被 F1 竞品差异章节替代。
- `f3-spike-condition-plan.md`：`superseded` 快速模式已取消技术 Spike 和条件闭环。
- `t1-new-product-analysis.md`：`archived` 历史 0–12 章正式新品分析模板。
- `t2-product-framework-version-plan.md`：`archived` 历史独立产品框架和版本计划模板。
- `t3-prd-prototype-handoff.md`：`archived` 历史 PRD 与原型交接模板。
- `t4-acceptance-run.md`：`superseded` 历史真实构建验收记录，现并入 F3。
- `t4-tracking-qa-acceptance.md`：`superseded` 历史 T4 埋点、测试和验收模板。

这些 archived/superseded 文件由索引状态过滤，不应参与当前默认 RAG；它们存在的价值主要是历史追溯。

## 11. `skills/`：可安装给 Agent 的能力说明

### `skills/overseas-consumer-app-lifecycle/`

- `SKILL.md`：`核心` 出海消费类 App 工作流路由入口，规定默认走 F1 → F2 → F3，正式研究仅在明确要求时启用。
- `agents/openai.yaml`：`核心元数据` OpenAI/Codex 对该 Skill 的展示名、说明和调用提示；它不是工作流正文模板。
- `references/artifact-router.md`：交付物、模板和其他 Skill 的选择规则。
- `references/competitor-review-collector.md`：竞品评论采集器什么时候调用、输入输出和失败边界。
- `references/fast-iteration-path.md`：F1、F2、F3 快速路径、长度预算和排除项。
- `references/gates.md`：仅供历史正式模式使用的 Gate 定义。
- `references/manifest-contract.md`：A0 项目清单的快速和正式字段约定。

### `skills/product-knowledge-rag/`

- `SKILL.md`：`核心` 要求 Agent 在相关产品任务中真正调用 Product KB，而不是把文件搜索冒充 RAG。
- `agents/openai.yaml`：`核心元数据` OpenAI/Codex 对 Product KB Skill 的展示和触发说明。
- `references/retrieval-contract.md`：四个 MCP 工具的参数、返回值、调用预算和查询示例。
- `references/governance.md`：知识状态、证据级别、新鲜度、冲突和人工回写规则。

## 12. `tests/`：自动化测试

- `test_frontmatter.py`：测试 Markdown frontmatter 正常解析和错误拒绝。
- `test_chunking.py`：测试标题定位、稳定 Chunk ID 和长内容拆分。
- `test_sources.py`：测试来源唯一性、外部路径白名单、日期序列化和配置回退。
- `test_index.py`：测试索引分页、类型过滤、active 状态防御和结果筛选。
- `test_workbench_retrieval.py`：测试项目证据优先、全局知识组合、内部检索字段脱敏和 ID 恢复。
- `test_workbench.py`：工作台主回归，覆盖项目、上传、检索、蓝湖、任务、编辑、版本、批注、评审、取消、恢复、删除和 HTTP 接口。
- `test_workbench_expansions.py`：测试新增的图片引用、多格式导出、项目包迁移、评论采集桥接和质量校验。

## 13. `workbench/`：产品工作台程序

### 后端与运行文件

- `app.py`：`核心` 当前单体后端和 HTTP Server；负责数据库、项目、资料、任务、Codex 执行、版本、批注、评审、回收站、蓝湖、爬虫、导入导出和 API。它过大，也是下一阶段拆插件内核的主要对象。
- `retrieval.py`：`核心` 工作台双索引检索；项目资料写入项目隔离索引，再与全局 Product KB 结果组合，异常时由 `app.py` 回退关键词检索。
- `exporters.py`：`核心` 将 Markdown 渲染为 DOCX、PDF、XLSX、CSV，并生成项目 ZIP。
- `validators.py`：`核心` F1、F2、埋点、F3 的轻量确定性检查和严重级别汇总。
- `review_scraper_worker.py`：`核心适配器` Google Play 评论采集子进程，将评论转换成工作台约定的结构化输出。
- `smoke_codex.py`：`测试辅助` 用假 Codex 输出验证工作台执行链，不调用真实模型。
- `start.ps1`：`核心入口` Windows 下启动工作台的 PowerShell 脚本。
- `README.md`：`核心技术手册` 工作台安装、启动、操作、配置、数据目录、接口和边界。
- `DESIGN.md`：`核心设计说明` 当前架构、检索、版本批注规则，以及未来热插拔目标。
- `VERIFICATION.md`：`验证记录` 已运行过的自动化和人工冒烟项目、场景及结果。

### `workbench/capabilities/`

- `fast.json`：`核心` 默认快速模式任务包：F1 新品需求分析、F2 核心 PRD、可选完整埋点、F3 开发验收。
- `product.json`：`历史正式能力` T1–T4/完整研究模式任务定义，只在用户主动切换完整模式时出现。
- `reviews.json`：`可选且默认关闭` 大批评论的独立分析任务；普通项目直接把评论 CSV 交给 F1。

### `workbench/templates/`

- `review-analysis.md`：`可选模板` 独立竞品评论分析的输出约束，要求说明样本范围、避免把局部样本伪装成总体比例。

### `workbench/fixtures/`

- `reviews.csv`：`测试夹具` 极小的示例评论数据，只用于测试解析和采集桥接，不能当真实竞品研究证据。

### `workbench/static/`

- `index.html`：`核心前端` 单页应用的 HTML 外壳和资源引用。
- `app.js`：`核心前端` 项目、资料、任务、编辑、批注、版本、导出、回收站、蓝湖和爬虫界面的全部浏览器逻辑；当前体积较大。
- `style.css`：`核心前端` 工作台布局、表单、卡片、编辑器、批注和响应式样式。

### `workbench/.runtime/`

- `server.out.log`：`本机生成` 工作台标准输出日志。
- `server.err.log`：`本机生成` 工作台错误日志。

### `workbench/data/`

- `workbench.sqlite3`：`本机核心数据` 当前项目、资料元数据、任务、版本、批注、评审、条件、爬取任务等记录。删除会丢失工作台内项目状态。
- `index/project-manifest.json`：`生成` 项目索引来源、指纹和 Chunk 对照。
- `index/qdrant/.lock`：`生成` 项目 Qdrant 访问锁。
- `index/qdrant/meta.json`：`生成` 项目索引实例元数据。
- `index/qdrant/collection/workbench_project_documents/storage.sqlite`：`生成` 当前项目资料和已确认交付物的向量存储，可从原资料重建。
- `uploads/26ea5bdaf11d440fa805704b91fe1df1/c794fd45343b424898ad5038ba718e25.md`：`本机项目资料` 某个当前项目上传的 Markdown 原文件，目录名是项目 ID、文件名是资料 ID。
- `uploads/26ea5bdaf11d440fa805704b91fe1df1/f50b8b007fd3457f82db67f17fd73e0e.csv`：`本机项目资料` 同一项目上传或评论采集生成的 CSV。

### `workbench/data/runs/` 当前任务运行目录

每个 UUID 目录对应一个任务。目录内文件含义一致：

- `任务包.md`：发送给模型前冻结的项目、要求、模板和来源上下文。
- `执行记录.json`：任务 ID、来源、模型、时间和运行参数。
- `model-output.md`：模型原始输出。
- `交付物.md`：工作台当前版本正文。
- `交付物-v000N.md`：不可变历史版本快照。

当前共有以下任务目录：

- `0651fc795c09452a8e4cc64d57fa84e2/`：仅任务包和执行记录，说明任务未形成交付物或尚未完成。
- `5316386fc98f43d69b9adaca20e4d9c7/`：任务包、执行记录、原始输出、当前交付物及 2 个版本。
- `5d7fd8f78f6746548729997267a1081a/`：仅任务包和执行记录。
- `6ed199a890994f7e99b947df3bc961d6/`：完整输出链及 1 个历史版本。
- `6ffe8f7fb0f14171bc7f78bb620ca048/`：完整输出链及 3 个历史版本。
- `7971c69c70504973b5b5eb6f99b057c6/`：完整输出链及 2 个历史版本。
- `90ab4764f4f74778b6674395f9141382/`：完整输出链及 2 个历史版本。
- `949e7d6fc2354db984e5a9da6db9c726/`：完整输出链及 5 个历史版本。
- `981b3762dbdc43448df07b65a970143a/`：仅任务包和执行记录。
- `c945130d5b84455c831995d74f25371b/`：仅任务包和执行记录。

这些目录和 SQLite 记录共同构成任务证据链，不能只删除其中一个文件。

### `workbench/data/trash/` 项目回收站

每个目录名由删除时间和随机 ID 组成。`project-export.json` 是项目数据库快照；`runs/` 保存被删除项目的任务文件；`uploads/` 保存其原始资料。当前有：

- `20260910-152852-1ecee760815f4f8fa88cf96e8021f393/`：1 个项目快照文件。
- `20260910-155156-b79037b07be14bb6bbd99fccd1d9a68a/`：项目快照、2 个任务的任务包/记录/输出/交付物，以及 1 个 CSV，共 10 个文件。
- `20260910-155202-d346d3b9d4a64d59acf13d3c5ced8845/`：项目快照、4 个任务的任务文件和 4 个 Markdown 上传资料，共 21 个文件。
- `20260910-155206-6466ede71c07454f9712c30c713e21c6/`：项目快照和 1 个任务的 4 类文件，共 5 个文件。
- `20260910-155211-a0289682ffcd4c479c6e927f52d9f580/`：项目快照和 3 个任务的 4 类文件，共 13 个文件。
- `20260910-155215-cfb68fe1b68e46119a372fbe7a7f1e9f/`：项目快照、1 个任务的 4 类文件和 1 张 PNG，共 6 个文件。
- `20260911-102611-a6464998fe7d48db95160eea5bebf148/`：项目快照和 1 个 Markdown 上传资料。
- `20260911-102730-5588ab54ad0141939e1bea0d5b063e53/`：项目快照和 1 个 Markdown 上传资料。

回收站支持工作台恢复。只有在确认不再恢复项目后，才应从界面永久删除，不应在资源管理器里零散删除。

## 14. `archive/`：历史、审计和临时材料

### `archive/audit/logic-2026-09-10/logic-2026-09-10/`

- `01-task-and-deliverable-list.png`：任务与交付物列表逻辑的人工走查截图。
- `02-cancelled-task-recovery.png`：取消任务恢复逻辑截图。
- `03-full-mode-task-selection.png`：完整模式任务选择截图。
- `04-review-with-open-comment.png`：存在未处理批注时评审阻断截图。
- `05-project-mode-and-delete.png`：项目模式和删除逻辑截图。

这 5 张图属于 `历史验证证据`，不参与运行。

### `archive/demo/product-workbench-demo/`

- `product-workbench-demo.html`：`历史原型` 早期单文件 Demo；当前真实工作台不依赖它。

### `archive/projects/gba-emulator/`

- `00-project-manifest.md`：GBA Emulator 历史项目清单。
- `01-new-product-analysis-gba-emulator.md`：历史新品分析。
- `02-product-framework-version-plan-gba-emulator.md`：历史产品框架和版本计划。
- `03-product-definition-gba-emulator.md`：历史产品定义。

### `archive/projects/`

- `GBA-FULL-PIPELINE-AUDIT-2026-09-10.md`：GBA 全流程运行后记录的内容漏洞、流程偏重和修改建议。

### `archive/qa/regression/heart-rate/`

- `A0-Project-Manifest.md`：Heart Rate 历史 RAG/工作流回归项目清单。
- `routing-report.md`：Heart Rate 模板、来源优先级和路由是否正确的回归报告。

### `archive/qa/regression/pdf-reader/`

- `A0-Project-Manifest.md`：PDF Reader 历史跨品类回归清单。
- `routing-report.md`：Product KB MCP 调用、来源追踪和 Reader-first 结论的回归报告。

### `archive/qa/regression/plant-identifier/`

- `A0-Project-Manifest.md`：Plant Identifier 历史跨品类回归清单。
- `A1-Opportunity-Brief.md`：当时使用旧机会门方式形成的历史分析。
- `routing-report.md`：检索无直接案例时避免伪造结论的回归报告。

### `archive/workflow-history/source-archive/`

- `历史新品需求文档模板盘点与选型-v1.0.md`：早期 Heart Rate 等模板的盘点和选型依据。
- `历史资产盘点与出海产品完整工作流-v1.0.md`：早期把资产组合成完整工作流的方案。
- `全量资产盘点（Codex+Claude）与工作流修订建议-v2.0.md`：Codex 与 Claude 历史 Skill/模板的较大范围盘点。
- `完整工作流搭建实施方案-v1.0.md`：早期 A0–A7/Gate 型实施方案。

这些文件解释了“为什么最终收缩为轻量 F1–F3”，但内容不是当前执行规则。

### `archive/tmp/20260911-before-cleanup/`

- `bluetooth-device-finder-research.md`：清理前保留的 Bluetooth Device Finder 临时研究材料。
- `bluetooth-device-finder-reviews.csv`：对应的临时竞品评论样本。
- `scrape_bluetooth_reviews.py`：一次性评论抓取脚本，已被正式 worker 取代或作为历史参考。
- `tracking-inspect/inspect_template.mjs`：一次性埋点模板检查脚本。
- `pdfs/heart-rate-template-review/page-1.png`
- `pdfs/heart-rate-template-review/page-8.png`
- `pdfs/heart-rate-template-review/page-10.png`
- `pdfs/heart-rate-template-review/page-14.png`
- `pdfs/heart-rate-template-review/page-17.png`
- `pdfs/heart-rate-template-review/page-18.png`
- `pdfs/heart-rate-template-review/page-20.png`

这些 PNG 是 Heart Rate 模板 PDF 的指定页面截图，全部属于清理前临时验证证据。

### `archive/workbench-backups/20260910-pre-logic-fixes/`

- `workbench.sqlite3`：逻辑修复前的完整数据库备份。
- `runs/0651fc.../`、`531638.../`、`5d7fd8.../`、`90ab47.../`、`981b37.../`、`c94513.../`：逻辑修复前对应任务的任务包、执行记录、原始输出或交付物快照；不同任务完成程度不同。

该目录用于防止逻辑修复破坏旧数据，当前运行不读取它，并已被 Git 忽略。确认新逻辑稳定且不再需要恢复旧状态后，它是可清理候选。

## 15. 当前结构判断

### 当前真正的产品核心

1. `workbench/` 中除 `.runtime/`、`data/`、`fixtures/` 外的源码和说明；
2. `src/product_kb/`；
3. `knowledge/` 中 active 方法、决策、案例和当前模板；
4. `skills/`；
5. `schemas/`、`tests/`、`scripts/`、`evals/`；
6. 根目录 `pyproject.toml`、`README.md`、`.gitignore` 和可分发配置示例。

### 本机数据，不应作为产品源码分发

1. `.mcp.json`、`config/sources.yaml`、`integration/codex-config-snippet.toml`；
2. `.index/`；
3. `workbench/.runtime/`；
4. `workbench/data/`；
5. `.venv/`、`.pytest_cache/`；
6. `projects/` 中未来产生的具体项目资料。

### 最明显的结构问题

1. `workbench/app.py` 和 `workbench/static/app.js` 过大，多种能力耦合在单文件中；
2. 当前知识库绑定仓库内 `knowledge/` 和本机 `sources.yaml`，还不是真正可插拔；
3. `STATUS.md` 仍是历史快照；当前使用方法以已更新的 `WORKFLOW-USER-MANUAL.md` 和实施清单为准；
4. active、archived、superseded 模板仍放在同一个模板目录，靠 metadata 过滤，阅读时容易误用；
5. `archive/`、当前文档和运行数据共处一个仓库，第一次接触项目的人不容易分清哪些是产品、哪些是历史证据；
6. 当前“已实现能力”和 `WORKBENCH-NEXT-PHASE-MODIFICATION-CHECKLIST.md` 的“待实施”状态可能不一致，需要在正式开工前重新核验一次。

本文件只做解释和结构判断，没有删除、移动或改写上述项目文件。
