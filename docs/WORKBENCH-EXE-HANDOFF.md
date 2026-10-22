# 产品工作台 Windows EXE：使用与技术交接说明

版本：v1.0｜日期：2026-10-22｜对象：负责研究、接入或继续开发的技术同事

**这份交付保留当前工作台的完整界面，便于直接体验；本次技术研究重点是评论、商店资料、指定范围实机截图，以及资料导入、确认、归档与导出。** EXE、源码、HTTP API 和采集能力说明一起交付，后续实现可按能力拆分，不必照搬当前网页结构。

## 1. 交付内容与边界

| 内容 | 用途 |
|---|---|
| `ProductWorkbench.exe` | Windows 单文件程序，内置 Python 及本包所需采集、截图处理、文件解析和文档导出依赖 |
| `source/` | 可继续研究和修改的源码；本说明后续提到的代码路径均相对于此目录 |
| `docs/WORKBENCH-EXE-HANDOFF.md` | 本使用与交接说明 |
| `docs/WORKBENCH-HTTP-API.md` | 当前本地服务的 HTTP 路由、参数、认证、异步状态与调用示例 |
| `docs/数据采集能力与数据流-同事交接说明-v1.0.md` | C01—C05 的采集输入、处理、输出、上下游和完成边界 |
| 随包验证记录 | 本次实际执行的打包和验证结果；以最终生成记录为准 |

交付从空项目开始，不附带原使用者的项目数据库、上传资料、任务历史、设备走查记录、登录凭据、Cookie、`.env`、个人 MCP 配置或 Codex 认证文件。源码中的通用方法和模板供阅读与复用，不能当成当前研究 App 的事实。

本包是供本机体验和技术研究的当前工作台。它没有多用户权限、团队部署或公网服务承诺；也不代表所有外部商店、真实 App、支付、广告、埋点和经营结果已经验证。

## 2. 第一次启动

1. 将交付包完整解压到一个目录，保留 `source/` 与 `docs/` 供研究查阅。
2. 双击 `ProductWorkbench.exe`。程序打开控制台，并自动用默认浏览器打开工作台。
3. 查看控制台中的实际访问地址和数据目录。服务仅监听 `127.0.0.1`。
4. 正常体验期间保留控制台。按 `Ctrl+C` 或关闭控制台，结束本次服务；只关闭浏览器标签不会结束服务。

默认从 **8765—8784 共 20 个端口**中选择可用端口。如果 8765 已被其他工作台占用，本次会尝试下一端口，不会停止原服务。书签、脚本及 API 调用以本次控制台打印的实际端口为准。

### 2.1 哪些环境需要另配

| 想体验的能力 | 本包内置 | 同事需要另行准备 |
|---|---|---|
| 项目、资料上传、模板、关键词检索、导入导出 | Python、解析与导出依赖、界面和模板 | Windows、可写数据目录 |
| 商店资料、评论、候选搜索 | 原生采集后端及所需依赖 | 能访问对应商店的网络；实际可采字段和数量以返回结果为准 |
| 可选评论中文翻译 | Google / `deep-translator` 依赖 | 对应翻译服务可访问；可在采集表单取消翻译 |
| 文档自动生成、修订 | 调用适配层、模板 | 本机 Codex CLI、有效登录或模型 provider 配置，以及账号可用额度 |
| Android 指定范围自动截图 | 截图 Skill 副本、受限工具桥、图片与流程整理依赖 | ADB、已授权设备、已安装目标 App，以及可用 Codex CLI/模型 |
| Hybrid 向量检索研究 | 源码中的对应实现 | 从源码安装 `pyproject.toml` 依赖，另行准备向量模型及索引 |

**运行 EXE 不需要另装 Python，也不依赖旧的桌面 `competitor-analysis-platform`。** 本包不会替同事安装或登录 Codex、配置模型 provider、安装目标 App，或完成设备的 USB 调试授权。

## 3. 建议先体验这一条采集路径

### 3.1 已知 App：采集、预览、确认、导出

1. **新建项目。** 填写项目名称和简单背景。只研究资料时可按产品级工作保存，无须先建立产品版本。
2. **打开指定竞品资料采集。** 直接粘贴商店链接、Google Play 包名或 App Store ID；每行一个，本批最多 8 个。尚未选好 App 时可先使用“找竞品”，由人选择后再采集。
3. **先缩小范围。** 第一轮建议只选一个 App、一个市场，并减少每国评论上限，便于观察请求与返回结果。日期、评分、关键词等筛选在抓取后、翻译前执行，最终数量可能少于抓取上限。
4. **检查翻译开关。** 当前界面的“生成简体中文译文”默认勾选。只研究采集链路时，建议第一次取消勾选，减少外部请求和等待时间。
5. **开始采集，等待预览。** 商店文案、宣传截图和评论先进入待确认区。查看实际市场、数量、原文与译文样本、截图及缺口，不把“已受理”当成采集完成。
6. **确认进入项目资料。** 确认后材料才成为项目内可引用资料；这一步表示采用该资料，不代表已经完成评论分析或竞品判断。
7. **查看与导出。** 可在资料入口查看或下载已保存资料；需要完整迁移时使用项目 ZIP 导出。已生成的文档交付物可按对应入口导出 Word、PDF、Excel 或 CSV。

“全球”当前是 US、GB、DE、JP、IN、ID、BR、SA 八个预设市场的组合，不代表全部国家。描述和宣传图通常对应一个具体市场；评论会按本次勾选市场采集。市场之间的字段、返回数量和可访问性可能不同。

### 3.2 本包翻译实际使用什么

在 EXE 的内置采集后端中，启用翻译时使用 **Google / `deep-translator`**，译文单独保存，原评论保留；不会自动转用付费模型。每个 App 最多翻译筛选后前 500 条，其余仍保留原文，失败项以结果提示为准。

评论翻译开关不控制工作台的文档生成或 Android 自动走查。后两项会调用同事自己配置的 Codex/模型，额度与费用取决于其账号及 provider。

如果明确切换到旧桌面采集工具，其依赖和翻译配置按该 legacy 工具处理，不能再套用本包内置后端的说明。第一次研究本包时，保留随包采集器设置即可。

### 3.3 导入已有资料

在项目资料入口上传已有文档、截图、评论 CSV 或数据文件。当前支持范围包括 MD、TXT、CSV、JSON、文本 PDF、DOCX 及 PNG/JPG/WEBP 等图片，实际单文件与项目包大小限制见 API 说明。

上传前确认资料归属项目和产品版本。扫描 PDF 只有图片时需要先做 OCR，不能把没有提取到文字理解为没有内容。字段未知、来源不清或口径不同的数据应保留说明，不能自动填成 0。

外部留存、画像、下载、收入和投放数据以用户提供的文件、记录或明确来源为输入；本包没有自动连接这些经营数据平台，也不会从商店宣传图推算真实收入或回收效果。

## 4. Android 截图能力怎么体验

1. 在本机准备 `adb.exe`，连接设备并完成 USB 调试授权，确保目标 App 已安装。
2. 在本机准备并登录 Codex CLI；如果使用自定义模型 provider，由同事自行配置。只有 Codex 桌面 App 不一定代表 CLI 已能被发现。
3. 在工作台 Android 截图入口配置 ADB，检测并选择设备，填写目标包名和明确范围，例如“只走首页到设置，记录返回路径，跳过登录和购买”。
4. 核对设备和 App 版本后开始。Agent 通过受限工具观察真实页面，逐步操作、归档原始截图与页面状态，并整理模块流程 PNG。
5. 出现范围外登录、授权、系统页面、购买等需要人工处理的状态时，查看暂停原因，在设备上完成本轮允许的处理后再手动续跑。续跑先重新观察当前位置；不要将失败动作直接重复执行。
6. 查看已覆盖、未覆盖、阻塞原因、原图及流程成果，确认需要的成果后加入项目资料或导出。

自动走查依赖设备状态、页面可读性、网络、模型与预算，可以交付部分覆盖。模块流程 PNG 只整理已有真实证据，不保证穷尽全 App。截图和模型结束也不能证明支付成功、广告收入、埋点入库或多设备稳定性。

当前实际执行过哪些验证、是否对某个真实 App 完成指定路径，以随包验证记录为准。不能用依赖自检、合成测试或工具握手代替真实业务路径验证。

本轮截图后端使用随包 `android-walkthrough` Skill。工具默认返回精简页面状态；需要看图时读取当前会话已保存的 JPEG 缩略图，原始 PNG 仍保留用于交付。读取已有缩略图不再次操作设备。模块登记、实际跳转、构建与 finish 的结果仍需要经过证据检查，不会因为工具握手成功就自动视为走查完成。

## 5. 数据目录与多实例

默认数据目录：

```text
%LOCALAPPDATA%\ProductWorkbenchResearch\data
```

本机项目、上传文件、任务、资料及截图会在运行后写入该目录。删除或替换 EXE 不等于删除这份数据；重新运行默认会继续使用它。需要分享研究结果时优先导出项目包，交付前检查其中是否包含不应共享的资料。

可用 `--data-dir` 创建独立研究环境。多个实例并行研究时，使用不同数据目录，避免两个进程同时操作同一份数据库和任务文件。空闲端口自动选择只解决网络端口冲突，不代表数据已自动隔离。

### 5.1 启动参数

以下在 PowerShell 中从 EXE 所在目录执行：

```powershell
# 使用默认行为：自动选端口、打开浏览器
.\ProductWorkbench.exe

# 固定端口，并使用独立数据目录
.\ProductWorkbench.exe --port 8875 --data-dir ".\research-data"

# 不自动开浏览器，按控制台地址手动访问
.\ProductWorkbench.exe --port 8875 --data-dir ".\research-data" --no-browser

# 离线检查内置资源与依赖，不启动服务
.\ProductWorkbench.exe --self-test
```

指定 `--port` 后，如果该端口不可用会报错，不会停止占用者或自动切换端口。`--self-test` 输出资源和依赖检查结果；它不检测商店访问、Codex 登录、设备授权或真实走查效果。

EXE 默认使用 `keyword` 关键词检索，内置方法与模板仍可使用；没有打入 embedding 向量模型和预建向量索引。默认数据路径可通过 `--data-dir` 覆盖；明确设置的 `WORKBENCH_DATA` 环境变量也会影响未传此参数时的路径。

## 6. 技术研究从哪里看

### 6.1 推荐阅读顺序

1. 阅读 `docs/数据采集能力与数据流-同事交接说明-v1.0.md`，先确认 C01—C05 的职责与资料包含义。
2. 阅读 `docs/WORKBENCH-HTTP-API.md`，围绕一个临时项目调用已实现接口。调用时使用控制台实际端口，先读 `/api/state` 获取本次进程 token，再按说明发送 POST。
3. 在 `source/` 中沿下面的入口追踪请求、worker、归档和确认逻辑。
4. 按同一 App 与范围对照界面、API 返回和导出资料，不把“接口返回成功”扩展为采集覆盖或分析结论成立。

### 6.2 源码定位

下表路径均相对于 `source/`：

| 想研究什么 | 入口 |
|---|---|
| Windows 启动、内置资源定位、固定 worker 分派、自检 | `scripts/packaging/workbench_launcher.py` |
| EXE 构建及资源白名单 | `scripts/packaging/build_workbench_exe.py` |
| 本次构建依赖锁定 | `scripts/packaging/requirements-build.lock` |
| 主服务与能力组合 | `workbench/app.py` |
| HTTP 请求校验与路由 | `workbench/api/handler.py`、`workbench/api/routes.py` |
| 商店/评论采集的工作台适配、预览及确认 | `workbench/adapters/review_scraper.py` |
| 候选搜索 | `workbench/adapters/competitor_discovery.py` |
| 可独立复用的采集后端 | `packages/competitor-collector/competitor_collector/engine.py`、`scrapers.py` |
| 现有 worker 兼容入口 | `workbench/review_scraper_worker.py` |
| Android 会话及模型 runner | `workbench/services/android_capture_service.py`、`workbench/adapters/android_capture_runner.py` |
| Android 受限工具与 MCP | `workbench/capture_tools.py`、`workbench/capture_mcp.py` |
| 截图 Skill 协议与脚本副本 | `packages/android-walkthrough/skill/`，包含 `SKILL.md` 及 `references/walkthrough.md`、`ads.md`、`delivery.md`、`json-contract.md` |
| 资料、项目包及文档导出 | `workbench/services/material_service.py`、`export_service.py`、`workbench/exporters.py` |
| 当前网页界面、能力及任务模板 | `workbench/static/`、`workbench/capabilities/`、`knowledge/templates/` |

完整工作台界面保留了新品分析、原型说明、PRD、埋点及验收等入口。这些属于后续文档任务；本次采集能力交接的终点是资料可追溯、可确认、可导出，不要求先调用全部文档流程。

独立采集器项目的网页服务与本工作台不是同一套 API。源码中保留其实现供研究，但本次 EXE 启动的是工作台，不会额外启动或提供一个已冻结的 8766 独立采集器服务。

### 6.3 源码运行与重新构建

EXE 使用者不需要安装 Python；修改或重建源码时需要对应 Python 开发环境。项目要求 Python 3.11—3.13，构建环境以锁定清单和最终构建记录为准。

在 `source/` 根目录创建独立环境并安装锁定依赖后，使用：

```powershell
python scripts\packaging\build_workbench_exe.py --output dist
```

构建脚本生成单文件 `ProductWorkbench.exe`。依赖版本、资源白名单及 worker 分派都应纳入修改后的复核，不能只验证网页首页能打开。

需要研究 Hybrid RAG 时，从源码安装 `pyproject.toml` 中的依赖并准备相关模型、索引；配置和实现见 `src/product_kb/`、`workbench/retrieval.py`。向量检索不是本 EXE 包的默认验证范围，也不应复制原使用者的向量索引来代替初始化。

### 6.4 修改后的离线冻结验证

先完成最终 EXE 构建，再从源码目录用开发 Python 环境执行：

```powershell
python scripts\packaging\smoke_workbench_exe.py --exe ".\ProductWorkbench.exe" --output ".\work\http-smoke-new"
python scripts\packaging\smoke_capture_worker.py --exe ".\ProductWorkbench.exe" --report ".\work\capture-handshake-new.json"
python scripts\packaging\smoke_walkthrough_exe.py --exe ".\ProductWorkbench.exe" --output ".\work\walkthrough-smoke-new"
```

输出目录必须使用尚不存在的新路径。默认不访问外部商店，不调用真实 ADB、手机或模型；第一个脚本的 `--live-store` 是另行明确选择的联网检查，不属于上述离线验证。

第三个脚本用 Windows .NET Framework 编译器临时生成 FakeAdb.exe，并生成合成 PNG/XML，再调用真实冻结工具完成操作、地图、拼图和 finish，最后通过真实工作台 HTTP API 读取并确认入库。它仅模拟模型 runner 将完成结果回填会话状态这一步，不能证明真实模型能够自主完成相同流程。FakeAdb、临时项目和运行数据只留在验证输出目录，不应加入交付包。此脚本使用开发环境的 Pillow 和系统编译器，不增加 EXE 使用者的运行依赖。

验证脚本先将自己创建的进程绑定到专属 Windows Job Object，再允许它运行；结束时清理该对象中的进程树，并检查本次监听端口已停止。它不按程序名称或端口结束其他工作台。是否清理成功以实际 JSON 报告中的 `process_cleanup` / `server_process_cleanup` 为准；测试失败也要保留错误记录，不能只关闭 PyInstaller 父进程就认为服务已停止。

## 7. 故障排查与已知边界

| 现象 | 先检查什么 |
|---|---|
| 双击后浏览器没打开 | 控制台是否仍在运行、是否打印实际地址；手动访问该地址；确认没有使用 `--no-browser` |
| 访问了错误或旧工作台 | 对照本次控制台端口；默认自动选择的端口可能不是 8765；API URL 也要同步修改 |
| 提示端口不可用 | 换一个 `--port` 或不指定端口让程序自动选择；程序不会结束旧服务 |
| 每次像是新项目，或两个实例互相看到资料 | 核对 `--data-dir`、`WORKBENCH_DATA` 及控制台数据目录；需要隔离时给每个实例独立目录 |
| 随包采集器不完整或自检依赖缺失 | 保留 `--self-test` 输出并核对交付文件；不要通过填写原开发者桌面路径绕过 |
| 某市场采集失败、条数不足或筛选后为空 | 查看任务缺口、市场、日期及过滤条件；先用单 App、单市场、少量评论定位问题；保留成功部分 |
| 翻译为空或等待较久 | 确认是否勾选翻译、Google 翻译服务是否可访问、评论数量及失败提示；需要时关闭翻译先取原文 |
| Codex 不可用 | 确认 CLI 可被本机发现、登录/provider 配置与额度；必要时使用 `WORKBENCH_CODEX_BIN` 指定真实原生可执行文件路径，不能填命令参数 |
| ADB 检测不到设备 | 检查 `adb.exe` 路径、连接、USB 调试和设备授权；多设备时明确 serial；目标 App 必须已安装 |
| 截图暂停或只有部分流程 | 先看范围、当前页面、版本及阻塞原因；处理后手动续跑，不把未覆盖路径写成已经走查 |
| API POST 返回 403 | 从当前进程 `/api/state` 重取 token，核对实际端口、Host、Origin 与 `X-Workbench-Token`；重启后旧 token 失效 |
| 文档导出或图片处理异常 | 先保留触发材料与错误信息，用小样本重试并运行自检；自检通过仍不能代替该文件格式的实际导出与打开检查 |

商店资料是公开展示，评论是样本中的用户表达，实机截图是特定设备与版本当时的观察。三类资料可互相对照，但不能互相替代。资料包交接时保留来源、采集条件、实际覆盖、失败项与未确认事项。

需要反馈问题时，提供 EXE 版本/文件标识、启动参数、实际端口、操作路径、错误提示及必要的脱敏样本；不要附带个人登录文件、Cookie、token 或无关项目资料。以随包验证记录区分依赖自检、合成回归、真实工具连接与真实业务流程结果。
