# 工作台模块化重构修改清单

版本：V0.1 方案稿  
状态：待确认，尚未实施  
范围：保持现有产品行为不变，拆分 `workbench/app.py` 与 `workbench/static/app.js`，为后续知识库和能力热插拔准备边界。

## 1. 重构目标

- [ ] `app.py` 只负责启动、依赖组装和兼容入口，不再承载所有业务。
- [ ] `app.js` 只负责前端启动和页面编排，不再承载所有状态、渲染和功能细节。
- [ ] 现有 API、SQLite 数据结构、页面路径和任务行为保持兼容。
- [ ] 新增知识库、任务能力、工具、校验器或导出器时，不需要继续堆积到主文件。
- [ ] 每一步可以单独测试、回滚和上线，不进行一次性大重写。

## 2. 当前耦合范围

### 后端 `workbench/app.py`

| 现有范围 | 主要职责 | 目标模块 |
|---|---|---|
| 约 551–840 行 | 项目创建、更新、删除、恢复、回收站 | `services/project_service.py` |
| 约 841–940 行 | 资料、图片、资源引用 | `services/material_service.py` |
| 约 945–1219 行 | 交付物导出、项目包导入导出 | `services/export_service.py` |
| 约 1221–1517 行 | 竞品评论采集及状态 | `adapters/review_scraper.py` |
| 约 1517–1648 行 | 项目资料和 Product KB 检索 | `services/retrieval_service.py` |
| 约 1649–2243 行 | 任务、Codex、版本、批注、评审、修订、取消恢复 | `services/job_service.py` |
| 约 2262–2469 行 | HTTP Handler、路由、响应 | `api/handler.py` + `api/routes.py` |

### 前端 `workbench/static/app.js`

| 现有范围 | 主要职责 | 目标模块 |
|---|---|---|
| 约 1–151 行 | DOM、常量、请求、刷新、错误 | `modules/utils.js`、`modules/api.js` |
| 约 172–487 行 | 首页、背景、资料、任务、交付物、回收站、能力库渲染 | `render/*.js` |
| 约 489–614 行 | 新项目、导入、删除、任务准备 | `features/projects.js`、`features/tasks.js` |
| 约 615–736 行 | Markdown 渲染、图片、批注块定位 | `modules/markdown.js` |
| 约 737–862 行 | 批注、质量摘要、交付物编辑、版本 | `features/outputs.js` |
| 约 863–1078 行 | 点击事件和功能交互 | `features/*.js` + `modules/events.js` |

## 3. 第一阶段：必须做的安全准备

### R0 行为基线与迁移映射

- [ ] 记录当前启动命令、HTTP 路径、请求参数和响应结构。
- [ ] 记录项目、资料、任务、交付物、版本、批注、评审、回收站和导出等关键行为。
- [ ] 建立“旧方法 → 新模块 → 原测试”的迁移表。
- [ ] 为当前没有测试的关键异常补最小回归测试：文件不存在、项目不存在、任务取消、导入失败、导出失败、引用失效。
- [ ] 保存当前测试、语法检查和浏览器冒烟结果，作为拆分后的比较基线。
- [ ] 先不改变字段名、状态名、URL、数据库表和交付物格式。

验收：在没有新增模块前，当前测试和启动方式可重复通过。

### R1 抽取纯函数和常量

- [ ] 新增 `workbench/core/constants.py`，集中状态、任务类型、平台和文件类型常量。
- [ ] 新增 `workbench/core/text_utils.py`，迁移文本清洗、切块、引用 ID 和交付物规范化。
- [ ] 新增 `workbench/core/file_security.py`，迁移扩展名、大小、路径、ZIP 成员和安全文件名检查。
- [ ] 新增 `workbench/core/errors.py`，定义项目不存在、任务状态错误、来源失效、导入失败等统一异常。
- [ ] `app.py` 暂时继续导出旧函数名，保持现有内部调用兼容。

验收：纯函数测试通过，业务输出与拆分前逐字一致。

## 4. 第二阶段：后端按领域拆分

### R2 项目服务

- [ ] 新增 `workbench/services/project_service.py`。
- [ ] 迁移项目创建、编辑、查询、删除确认、回收、恢复和永久删除。
- [ ] 保持删除二次确认、运行中项目保护和向量清理规则。
- [ ] `Workbench` 保留兼容方法，内部转发到 `ProjectService`。

### R3 资料与图片服务

- [ ] 新增 `workbench/services/material_service.py`。
- [ ] 迁移 Markdown、TXT、CSV、JSON、PDF、DOCX 和图片导入。
- [ ] 迁移图片资源读取、项目隔离、正文引用和来源归一化。
- [ ] 保持 12 MB 限制、真实文件类型检查和项目路径隔离。
- [ ] 后续知识源连接器只能通过资料服务写入项目资料，不得直接操作数据库。

### R4 任务与交付物服务

- [ ] 新增 `workbench/services/job_service.py`。
- [ ] 迁移任务准备、Codex 执行、取消、失败、重启恢复和归档。
- [ ] 迁移 Markdown 编辑、版本链、版本恢复、定位批注、修订和评审确认。
- [ ] 保持来源引用闭合、未处理批注阻断和 F3 Conditional 规则。
- [ ] 将 Codex 子进程改为注入的 `CodexRunner`，服务层不直接拼命令。

### R5 检索服务

- [ ] 新增 `workbench/services/retrieval_service.py`，对外只暴露项目搜索和检索状态。
- [ ] 保留 `workbench/retrieval.py` 作为底层索引实现，先不改 Hybrid 算法。
- [ ] 项目资料、已确认交付物和全局知识的优先级保持不变。
- [ ] 保留 Hybrid 失败回退关键词检索。
- [ ] 为未来 `KnowledgeConnector` 留出接口，不在服务中直接绑定单一 Product KB 实现。

### R6 外部工具适配器

- [ ] 新增 `workbench/adapters/codex_runner.py`。
- [ ] 新增 `workbench/adapters/lanhu_adapter.py`。
- [ ] 整理 `workbench/adapters/review_scraper.py`，将子进程、CSV 解析和采集状态分开。
- [ ] 外部工具失败、超时、取消和空结果统一转换为工作台错误，不污染项目数据。
- [ ] 凭证和本机配置继续留在工作台外部，不进入服务对象和任务包。

### R7 导出、导入与校验服务

- [ ] 新增 `workbench/services/export_service.py`，封装 `exporters.py`。
- [ ] 新增 `workbench/services/validation_service.py`，封装 `validators.py`。
- [ ] 导出器、校验器通过接口注入，不由项目服务直接 import 具体实现。
- [ ] 保持 Word、PDF、Excel、CSV 和项目 ZIP 的现有输出格式。
- [ ] 导出或校验失败不能改变交付物、评审或版本状态。

验收：R2–R7 每完成一个模块，原有 `Workbench` 方法仍可调用，全部既有测试通过。

## 5. 第三阶段：HTTP 层拆分

### R8 路由与响应拆分

- [ ] 新增 `workbench/api/routes.py`，只负责 URL、HTTP 方法和参数映射。
- [ ] 新增 `workbench/api/serializers.py`，统一 JSON、下载文件和错误响应。
- [ ] 新增 `workbench/api/handler.py`，保留静态文件服务和请求生命周期。
- [ ] `app.py` 只负责初始化 `Workbench`、注册路由和启动 Server。
- [ ] 所有现有 API 路径保持兼容，不趁拆分修改前端协议。
- [ ] 对每个 POST 接口保留错误码、中文错误信息和幂等/重复提交行为。

目标：`app.py` 降到约 200–400 行；超过目标时先检查是否有领域逻辑泄漏回启动文件。

## 6. 第四阶段：前端按状态、功能、渲染拆分

### R9 基础模块

- [ ] 新增 `static/modules/api.js`，集中 `fetch`、JSON、下载和错误处理。
- [ ] 新增 `static/modules/state.js`，集中项目、资料、任务、交付物和界面状态。
- [ ] 新增 `static/modules/constants.js`，集中状态、平台、任务和评论动作名称。
- [ ] 新增 `static/modules/utils.js`，集中 HTML 转义、日期、Badge 和通用格式化。
- [ ] 新增 `static/modules/modal.js`，集中弹窗、关闭和 Toast。

### R10 Markdown 与渲染模块

- [ ] 新增 `static/modules/markdown.js`，保留正文块 ID、图片引用和批注定位行为。
- [ ] 新增 `static/render/overview.js`、`context.js`、`materials.js`、`tasks.js`、`outputs.js`、`capabilities.js`。
- [ ] 渲染函数只接收数据，不直接发请求或修改全局状态。
- [ ] 保持当前中文 UI、平台下拉选项、查找依据说明和错误提示。

### R11 功能模块

- [ ] 新增 `static/features/projects.js`：新建、导入、删除、恢复和永久删除。
- [ ] 新增 `static/features/materials.js`：上传、图片、搜索和资料勾选。
- [ ] 新增 `static/features/tasks.js`：任务准备、执行、取消和恢复。
- [ ] 新增 `static/features/outputs.js`：编辑、批注、版本、修订、评审和导出。
- [ ] 新增 `static/features/integrations.js`：蓝湖和竞品评论采集。
- [ ] 新增 `static/modules/events.js`：统一事件委托，避免每个渲染函数重复绑定监听。
- [ ] `static/app.js` 作为入口，只负责创建 API、Store、挂载渲染器和初始化事件。

目标：`app.js` 降到约 150–250 行；模块之间通过显式参数传递 `api`、`store` 和回调，不依赖隐式全局变量。

## 7. 第五阶段：为热插拔建立接口

### R12 插件契约

- [ ] 新增 `workbench/registry/contracts.py`。
- [ ] 定义 `KnowledgeConnector`：`health`、`search`、`get`、`trace`。
- [ ] 定义 `CapabilityProvider`：任务定义、模板、上游依赖、工具依赖和输出限制。
- [ ] 定义 `ToolAdapter`：配置、健康检查、执行、取消和错误转换。
- [ ] 定义 `Validator`、`Exporter` 接口和能力声明。
- [ ] 所有插件使用统一 `manifest.json`，声明 ID、版本、配置、权限和入口。

### R13 插件注册与加载

- [ ] 新增 `workbench/registry/plugin_registry.py`。
- [ ] 支持发现、校验、启用、停用和重新加载插件。
- [ ] 插件加载失败不影响项目资料和其他任务运行。
- [ ] 现有 `capabilities/*.json` 先通过兼容适配器接入，不立即改成全新格式。
- [ ] Product KB、本地目录和通用 MCP 作为首批知识源适配器。
- [ ] 默认只读，权限和密钥不进入项目包、日志和 Git。

验收：新增一个合规能力包或知识连接器时，只添加插件目录和配置，不修改 `app.py`。

### R14 外部知识库接口预留

状态：`接口现在预留，具体连接器后置`  
优先级：`P0 / 设计前置，P2 / 具体实现`  

现在不实现 Notion、钉钉、飞书或 Confluence 的完整授权流程，但必须先把它们需要的接口能力定义好。

#### 统一连接器配置

- [ ] 定义知识源配置结构：`source_id`、`adapter_id`、显示名称、连接模式、适用范围、启用状态和配置版本。
- [ ] 连接模式至少支持 `federated`（实时查询）和 `indexed`（本地缓存索引）。
- [ ] 配置中只保存连接器需要的非敏感参数；Token、OAuth refresh token 和 Cookie 存在本机安全配置中。
- [ ] 允许声明知识库、空间、数据库、文件夹或页面范围，不默认读取整个账号。
- [ ] 允许声明来源类型、平台、区域、产品和更新时间等 metadata 映射规则。
- [ ] 允许用户为知识源设置默认优先级、是否参与全局检索以及是否只对指定项目生效。

#### 统一连接器能力

- [ ] 所有连接器至少实现 `health`、`search`、`get`、`trace`。
- [ ] 支持分页、游标、限流、超时、重试和部分结果返回。
- [ ] `search` 支持 query、top_k、来源范围、类型、平台、日期和标签过滤。
- [ ] `get` 支持读取页面、块、文档或条目的可核对原文。
- [ ] `trace` 返回外部系统 URL、空间/数据库/页面层级、更新时间和权限范围。
- [ ] `sync`、增量游标和本地缓存作为可选能力，不要求所有连接器实现。
- [ ] `writeback` 默认关闭；只有连接器声明且用户显式确认后才允许回写。
- [ ] 连接器必须返回统一的权限不足、未找到、限流、网络失败和内容已删除错误。

#### 预留适配器目录

- [ ] 预留 `workbench/adapters/knowledge/notion.py`。
- [ ] 预留 `workbench/adapters/knowledge/dingtalk.py`。
- [ ] 预留 `workbench/adapters/knowledge/feishu.py`。
- [ ] 预留 `workbench/adapters/knowledge/confluence.py`。
- [ ] 预留 `workbench/adapters/knowledge/generic_mcp.py` 作为没有专用适配器时的通用入口。
- [ ] 预留 `workbench/connectors/knowledge-source.schema.json`，供设置页校验不同连接器的配置表单。
- [ ] 未实现的适配器不能显示为“可用”，只能显示为“接口已预留”。

#### 未来接入验收标准

- [ ] 新增 Notion 连接器时，只新增适配器、manifest 和授权配置，不修改 `retrieval_service.py`、任务服务或前端任务逻辑。
- [ ] Notion 不可用或权限过期时，任务可以继续使用项目资料和其他知识源。
- [ ] 同一条知识在不同连接器返回时，可以依据 canonical URL、外部 ID 和更新时间去重。
- [ ] 历史任务保存实际使用的连接器、来源 URL 和原文快照，连接器停用后仍可追溯。
- [ ] 外部知识库的凭证不会进入项目导出包、任务包、日志或 Git。

## 8. 测试、发布和回滚

- [ ] 每个阶段单独提交，提交说明标记为“结构重构，不改行为”。
- [ ] 每次提交运行 Python 语法检查、`node --check`、pytest 和 `git diff --check`。
- [ ] 每次前端拆分后实际打开 `http://127.0.0.1:8765/` 验证首页、项目、任务和交付物。
- [ ] 每次后端拆分后验证启动、上传、检索、生成、编辑、批注、评审和导出。
- [ ] 保留 `Workbench` 兼容层至少一个版本周期，不立即删除旧入口。
- [ ] 新模块异常时可以通过配置开关回退到旧实现。
- [ ] 确认新模块稳定后，再删除重复旧代码和兼容分支。

## 9. 暂时不做

- [ ] 不更换 FastAPI、React、Vue 或数据库。
- [ ] 不拆微服务，不引入消息队列和远程服务发现。
- [ ] 不在重构期间重设计 UI。
- [ ] 不同时修改工作流规则、模板正文和数据库 schema。
- [ ] 不把每个函数拆成一个文件。
- [ ] 不把热插拔误解为任意知识库零配置兼容。
- [ ] 不在没有回归测试的情况下删除 `Workbench` 兼容方法。

## 10. 完成定义

- [ ] 现有所有测试和浏览器核心路径通过。
- [ ] `app.py` 只保留启动、组装和兼容入口。
- [ ] `app.js` 只保留前端初始化和模块挂载。
- [ ] 项目、资料、任务、检索、外部工具、导出和校验均有独立边界。
- [ ] 至少一个知识库连接器和一个任务能力包通过统一注册机制加载。
- [ ] 连接器停用后，任务不再使用该来源；历史任务仍保留来源快照。
- [ ] 故障、取消、导入失败和回滚不会破坏已有项目数据。

本清单只描述模块化重构，不代表上述项目已经实施。
