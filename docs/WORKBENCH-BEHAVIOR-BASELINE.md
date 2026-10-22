# 工作台行为基线

版本：V1.1（2026-10-20，GBA 工作流复核更新）

用途：后续继续拆模块或接插件时，用这份清单判断是否意外改变现有行为。

## 1. 启动与验证

在仓库根目录执行：

```powershell
.venv\Scripts\python.exe workbench\app.py --port 8765
```

浏览器入口：`http://127.0.0.1:8765/`。

完整本地回归：

```powershell
$files = Get-ChildItem workbench -Recurse -Filter *.py | ForEach-Object FullName
python -m py_compile $files
Get-ChildItem workbench\static -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
.venv\Scripts\python.exe -m pytest -q
```

## 2. 不允许在模块化重构中改变的契约

- 页面入口、中文 UI、项目数据目录和启动命令保持兼容。
- HTTP URL、请求字段、响应字段、状态名和中文错误语义保持兼容。
- SQLite 原表继续原位使用，不迁移用户现有数据。
- F1 在界面中以 5 个顺序章节任务展开，各自保留来源快照、编辑、批注、版本和评审；完整 F1 只合并已确认章节。
- 新品业务主干为市场和竞品分析、原型图＋需求说明、初审修改、终审整理、需求评审；各阶段可直接进入，不默认自动跑完全套。业务通过由实际负责人确认，工作台交付物确认不冒充部门审批。
- F2 保留任务 ID 与历史兼容，按当前模块与原型整理需求，不以固定页数或 8,000 字裁掉完整基线；说明按业务主题组织。
- 页面说明应能独立理解用途、实际呈现、背景与区域层级、完整 UI 文案及操作结果；原型旁注与 F2 复用确认正文和稳定 ID，已有清单只补变化。
- 同轮规则变更表只维护一份，按旧口径、确认新口径及各产物确切位置核对。缺当前正文标未核对，未实际写回标待同步，不重写已有项目或替用户确认冲突。
- 产品验收三列表的原用例 ID 和预期可直接进入 F3；F3 仅增加实测字段。完整埋点负责设计，F3 复用原事件验证，不截成固定事件数。旧 QA ID 列格式继续兼容；新场景列和原事件列的 PASS 同样必须有证据。
- 公共规则、流程与页面状态、原型制作交接、评审修改、全局一致性检查、三列表产品验收用例为按需任务。完整埋点和现有 F3 开发实测清单继续保留为可选能力；F3 的实测证据与结果约束不变。
- 生成、取消、恢复、编辑、版本、定位批注、精确修订、评审和归档行为保持不变。
- Markdown、Word、PDF、Excel、CSV 以及完整项目 ZIP 的格式与入口保持不变。
- `Workbench` 的原公开方法至少保留一个版本周期，并转发给领域服务。

## 3. HTTP 路径基线

### GET

| 路径 | 主要行为 |
|---|---|
| `/`、`/app.js`、`/style.css`、`/modules/*`、`/render/*`、`/features/*` | 工作台静态资源 |
| `/api/state` | 项目、任务、资料、回收站、能力和集成状态 |
| `/api/search` | 当前项目资料检索 |
| `/api/assets/{project_id}/{asset_id}` | 读取项目图片 |
| `/api/projects/{project_id}/export` | 导出完整项目 ZIP |
| `/api/reviews/scrape/{scrape_id}` | 评论采集状态 |
| `/api/documents/{document_id}` | 读取资料详情 |
| `/api/jobs/{job_id}` | 读取任务与当前交付物 |
| `/api/jobs/{job_id}/versions[/版本号]` | 读取版本列表或指定版本 |
| `/api/jobs/{job_id}/quality` | 读取轻量质量校验 |
| `/api/jobs/{job_id}/export?format=...` | 导出交付物 |
| `/api/jobs/{job_id}/prompt`、`/download` | 下载任务包或 Markdown 正文 |

### POST

| 路径组 | 主要行为 |
|---|---|
| `/api/projects`、`/api/project/update`、`/api/project/delete` | 新建、更新、删除项目 |
| `/api/projects/import` | 导入完整项目 ZIP |
| `/api/trash/restore`、`/api/trash/delete` | 回收站恢复与永久删除 |
| `/api/context`、`/api/conditions` | 项目背景与完整模式条件 |
| `/api/documents`、`/api/documents/{id}/delete` | 上传或删除资料/图片 |
| `/api/lanhu/snapshot` | 导入已脱敏的蓝湖页面快照 |
| `/api/prepare`、`/api/packs` | 准备单任务或任务包 |
| `/api/integrations/lanhu`、`/api/integrations/review-scraper` | 保存本机集成配置 |
| `/api/reviews/scrape`、`/api/reviews/scrape/{id}/cancel` | 开始或取消评论采集 |
| `/api/jobs/{id}/start`、`cancel`、`restore-cancelled` | 执行与恢复任务 |
| `/api/jobs/{id}/comments[/评论ID]` | 新增或更新定位批注 |
| `/api/jobs/{id}/review`、`revise`、`revise-comments` | 评审与修订 |
| `/api/jobs/{id}/edit`、`versions/{版本号}` | 编辑正文或恢复版本 |
| `/api/jobs/{id}/archive`、`restore`、`import` | 归档、恢复或导入外部结果 |

所有 POST 请求继续校验本机 Host、Origin（存在时）与 `X-Workbench-Token`。

## 4. 数据结构基线

本次五阶段与按需任务调整采用任务配置、模板和展示层实现，不要求迁移或重建已有项目。任务历史与已确认交付物保留原内容；新增能力不会自动重写它们。

继续使用这些 SQLite 表：

- `projects`
- `documents`
- `jobs`
- `preferences`
- `contexts`
- `reviews`
- `job_versions`
- `document_comments`
- `conditions`
- `scrapes`

项目资料、图片、运行记录、评论采集结果和回收站仍保存在 `workbench/data/`；模块化本身不改变目录结构。

## 5. 旧入口到新模块映射

| 原 `Workbench` 职责 | 当前实现模块 | 重点回归 |
|---|---|---|
| SQLite 初始化与迁移 | `services/storage_service.py` | 旧数据库可直接打开 |
| 项目、背景、条件、回收站 | `services/project_service.py` | 删除确认、运行中阻断、恢复 |
| 能力和任务定义 | `services/capability_service.py` | 任务 ID、模板和依赖不变 |
| 资料、图片、引用与蓝湖快照 | `services/material_service.py` | 文件限制、项目隔离、来源编号 |
| 项目搜索与 RAG 回退 | `services/retrieval_service.py` | Hybrid 失败回退关键词 |
| 任务、版本、批注、修订和评审 | `services/job_service.py` | 状态机、来源闭合和版本链 |
| 格式导出与项目包 | `services/export_service.py` | 导出不修改任务状态 |
| 轻量质量检查 | `services/validation_service.py` | 错误阻断确认，提示不阻断 |
| Codex、蓝湖、评论爬取 | `adapters/` | 失败、超时和取消不写伪结果 |
| HTTP 生命周期、路由和序列化 | `api/handler.py`、`api/routes.py`、`api/serializers.py` | URL 与错误码兼容 |
| 页面状态、渲染和交互 | `static/modules/`、`static/render/`、`static/features/` | 首页、任务、交付物与弹窗可用 |

## 6. 浏览器冒烟路径

每次前端结构调整至少检查：

1. 首页能够加载现有项目，切换项目正常；
2. 「项目背景」「资料」「任务」「交付物」均能打开；
3. 新品五阶段导航、F1 五章、F2 和按需任务正常显示，完整埋点与 F3 可以独立进入；
4. 交付物弹窗能渲染 Markdown、质量结果、批注和下载入口；
5. 浏览器控制台没有 JavaScript error；
6. 拆分后的 `/modules/*`、`/render/*`、`/features/*` 均返回 HTTP 200。

文档检查的新增约束：当前用户确认优先于历史资料；共享规则引用稳定 RULE ID；原型交接不声称实际外部写入；评审修改同时交付影响矩阵与修订正文；一致性检查不生成虚构审批通过；产品验收用例只输出“验收场景｜操作步骤｜预期结果”，实测继续由可选 F3 处理。

## 7. 回滚原则

- 结构重构不修改数据库和项目文件，所以可按 Git 提交回退代码。
- 不删除 `Workbench` 兼容入口；出现模块问题时可定位到单一服务或前端功能文件。
- 任何失败都不得通过清空 `workbench/data/`、重建项目或覆盖用户交付物来“修复”。
