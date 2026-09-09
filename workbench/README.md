# 本地产品工作台

这是可以本地运行的单人工作台，建立在现有 Product KB 之上。它围绕项目背景和一次交付组织工作，不要求从头跑完 T1–T4。

## 启动

先按仓库根目录 README 建好 Python 3.12 虚拟环境并安装依赖。在仓库根目录运行：

```powershell
.venv\Scripts\python.exe workbench\app.py
```

打开 **http://127.0.0.1:8765**。也可以运行 `workbench/start.ps1`。

已有 Product KB 环境不需要额外安装前端依赖；不依赖 CDN，离线可以管理资料和准备任务包。模型生成需要联网与本机 Codex 登录。

```powershell
codex login status
```

默认绑定 `127.0.0.1`，只供本机使用。换端口：`--port 8766`。服务运行期间保持终端进程存活，按 Ctrl+C 关闭。

## 第一次使用

1. 新建项目，写明产品方向与已经确定的内容。
2. 在「项目背景」填长期背景，以及当前目标和已确认决策。未知项可以留空。
3. 在「资料与检索」上传已有文档。支持 MD、TXT、CSV、JSON、文本 PDF、DOCX；单文件最大 12 MB。扫描 PDF 需先 OCR。
4. 在「任务」选择这次的交付物，补充具体要求，按需指定重点资料。
5. 点击「生成任务包」，检查完整模板、项目背景和检索片段。此步骤不调用模型。
6. 点击「开始生成」，使用本机 Codex 账号执行。任务结束后展示中文 Markdown，可下载原文。
7. 检查关键事实、核心场景和异常边界，点击确认或记录修改意见。需要修改时，可「按意见准备修订版」，检查后再运行。

如果不想从工作台调用模型，可下载任务包，在已有 AI 对话完成，再点击「导入已有结果」。结果同样先是待评审草稿。

## 当前功能与边界

| 能力 | 当前实现 |
|---|---|
| 项目与背景 | SQLite 持久化；长期背景、当前工作、单次任务三层上下文 |
| 文档上传 | 原文件保存、文本解析、SHA-256 去重、原文查看 |
| 项目检索 | 仅当前项目的上传资料及已确认产物；不会串入其他项目 |
| 方法检索 | 只读仓库 knowledge 中 active 条目；不读取 inbox |
| RAG | 中文双字 / 英文词的关键词片段检索；不是向量 Hybrid Search |
| 模板 | 复用现有 T1 0–12 章、T2、T3、T4，另有可启用的评论分析 |
| 执行 | Codex CLI 后台运行，一次一个任务，状态更新、停止、超时、失败恢复 |
| 追溯 | 任务输入、模板、上下文、模型名称、资料快照和输出分别保存 |
| 评审 | 待评审、已确认、需修改；可根据评审意见生成新任务，保留旧版 |
| 导出 | Markdown；不是 Word / Excel / Axure / Figma 成品 |
| 评论爬取 | 支持导入采集器 CSV；尚未自动调用桌面爬虫 |
| 扩展 | JSON 注册任务和模板；新执行工具需编写适配器 |

生成完成表示引擎返回了文档，不表示事实已经核验或质量合格。未经评审的生成稿不会自动进入后续任务的检索。项目内确认不会自动写入全局知识库。

已有 Product KB 的向量索引、Hybrid Search 和 MCP 继续独立可用，未改动其运行方式。工作台暂只检索仓库内知识，没有自动展开 `sources.yaml` 中全部外部来源。

## 数据保存位置

```text
workbench/data/                # 已被 Git 忽略
  workbench.sqlite3           # 项目、资料文本、任务、评审与能力开关
  uploads/<项目ID>/           # 原始上传文件，使用内部ID命名
  runs/<任务ID>/
    任务包.md
    执行记录.json
    model-output.md           # Codex 返回原文
    交付物.md
```

本地文件不加密，按电脑文件权限保护。备份时先停止服务，再复制整个 data 目录；恢复时替换为完整备份，避免只复制部分数据。项目材料、数据库、模型任务记录、虚拟环境和本机配置均不上传 GitHub。

资料上传和检索在本机完成。只有启动生成才会向模型服务发送任务包内容，并消耗现有账号额度。工作台不读取或展示登录 token。

## 模型配置

工作台寻找本机 Codex CLI，Windows 优先使用 npm 安装的 `@openai/codex/bin/codex.js` 和 Node。它读取 Codex 配置中的模型名称，但不载入用户的全套 MCP 和外部集成配置。使用 `--ignore-user-config`、`--ephemeral`、`read-only` 运行，认证仍由 Codex 自身处理。

任务准备时记录模型名称，执行时使用该快照。文档执行器关闭 shell、子 Agent、插件、应用连接器、浏览器控制与记忆能力，只围绕任务包生成，可使用网页检索核实时效性事实。修改模型后，请重新准备任务包。当前已验证 Codex CLI 0.153.4；较旧版本需先升级。

可选环境变量：

- `WORKBENCH_MODEL`：显式选择可用模型；省略则使用本机 Codex 配置中的模型名称。
- `WORKBENCH_CODEX_JS`：自定义 Codex JS 启动文件的绝对路径。
- `WORKBENCH_DATA`：自定义工作台数据目录的绝对路径。

通过自定义 provider 接入的模型尚未适配。当前生成适配器面向已登录 ChatGPT 的标准 Codex CLI；不把默认模型写死为 GPT-6。

## 扩展一个新任务

在 `workbench/capabilities/` 增加一个 JSON 文件，引用仓库内已有的 Markdown 模板。刷新页面即可加载，无需修改前端。

```json
{
  "id": "research",
  "name": "用户研究",
  "description": "从项目访谈资料整理用户需求。",
  "enabled": false,
  "tasks": [{
    "id": "interview-summary",
    "name": "访谈整理",
    "description": "根据已上传访谈整理发现与反例。",
    "template": "workbench/templates/interview-summary.md",
    "output": "访谈分析",
    "tools": ["project-search", "knowledge-search", "codex"],
    "query": "访谈 用户场景 痛点"
  }]
}
```

先创建上例所引用的模板，才会通过校验。ID 仅允许小写字母、数字、短横线；模板必须位于本仓库内。能力开关保存在本机数据库，不修改能力定义文件。

`tools` 是已实现能力的声明与校验；不能通过随便填入一个命令来运行工具。接入新爬虫或文档导出器，需要在 `app.py` 中实现受控的适配器、错误处理及测试，再登记工具。

## 验证

```powershell
.venv\Scripts\python.exe -m pytest -q
node --check workbench\static\app.js
```

`tests/test_workbench.py` 的模型执行使用可控测试替身，不消耗额度。浏览器实测与真实模型验收记录见 `VERIFICATION.md`。

## 设计参考

参考 [ai-pm-workflow](https://github.com/hy459229090-lang/ai-pm-workflow) 的上下文分层、任务资料路由、渐进建设与重点评审理念。实现映射和当前取舍见 [DESIGN.md](DESIGN.md)。
