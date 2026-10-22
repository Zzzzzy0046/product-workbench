# Windows EXE：本轮构建与验证记录

日期：2026-10-22。当前交付版本已更新为 `ProductWorkbench 2026.10.22.3`。下方先列本次重新打包结果，再保留早前版本的历史记录；历史文件标识不能用于校验新包。

## 当前交付：2026.10.22.3

- 文件大小：42,130,402 字节。
- SHA-256：`1338ece208711eaa26f69a3623c9d247aee2017a0df1e43136589f65d346a9cc`。
- `--version` 实际返回 `ProductWorkbench 2026.10.22.3 / android-walkthrough 1.0.1`。
- 当前 EXE 的 118 个项目资源逐字节匹配工作区源文件，没有发现 `.env`、`.mcp.json` 或项目数据库条目。
- 对此最终文件重新执行独立启动与导出 16 项、截图 MCP 握手 8 项、FakeAdb 受控流程 21 项检查，全部通过。三份 JSON 报告都绑定上述 SHA-256；所属测试进程树与端口均已清理。
- 打包、前端资料页、公共资料任务衔接及明确输入/导入导出等相关 Python 回归组合共 42 项通过。该组合不是全仓测试，不能与其他历史组合的数量累加。
- 资料页已统一；使用说明、API 说明、竞品档案说明和文件清单同步生成。API 文档包括竞品档案、公共资料的明确选择以及 schema 3 项目包兼容关系。
- 本轮未调用真实商店、翻译服务、手机或模型，未做全新 Windows 虚拟机与同事电脑验证。

本次报告位于 `work/repackage-20261022-v3/`，交付包仅附其已通过的 JSON 报告，不附测试数据、FakeAdb、账号或项目资料。对比与回退说明见 `WORKBENCH-REPACKAGE-20261022.md`。

## 历史记录：2026.10.22.2

以下为早前技术研究版的实际检查，仅保留追溯，不代表当前 EXE 的大小与校验值。

## 1. 最终 EXE 身份

| 项目 | 本轮值 |
|---|---|
| 文件 | `ProductWorkbench.exe`，Windows 单文件技术研究版 |
| 程序版本 | `ProductWorkbench 2026.10.22.2` |
| 截图后端 | `android-walkthrough 1.0.1` |
| 大小 | **42,093,073 字节** |
| SHA-256 | `52991e32355e5716d0ad4043fcf26ac193ca758718771c4679033e2ab91dd5a4` |

主线程已实际读取冻结归档：其中 23 个截图运行源码文件逐字节匹配 1.0.1 manifest，未包含作者的项目 data、私有 index、cases 或 decisions；实际执行 `--version` 得到上表版本。两项截图 smoke 也独立计算了 EXE 大小与 SHA-256，与上表一致。

随包使用 `packages/android-walkthrough/skill/`，包含 `SKILL.md` 及 `references/walkthrough.md`、`ads.md`、`delivery.md`、`json-contract.md`。冻结版只使用随包完整 Skill，不依赖作者个人 Skill 目录。

默认检索为 keyword。Codex CLI、登录与模型连接、ADB 和手机环境另行准备；没有打入作者的账号、设备记录或既有业务项目。

## 2. 最终冻结文件的实际检查

三份脚本按下表顺序串行执行，全部使用临时空用户配置及独立数据目录；未启用 `--live-store`，没有访问外部商店、翻译服务、真实 ADB、手机或模型。

| 检查脚本 | 本次实际结果 | 证据范围 |
|---|---|---|
| `smoke_workbench_exe.py` | **16 / 16 个检查通过** | 独立启动、实际 HTTP、资料与文档导出、项目包导入导出、进程树与监听清理 |
| `smoke_capture_worker.py` | **8 / 8 个检查通过** | 最终 EXE 的真实 MCP 握手、12 工具契约、新版随包协议读取与只读上下文 |
| `smoke_walkthrough_exe.py` | **21 / 21 个检查通过** | 最终 EXE 工具使用 FakeAdb 完成合成截图流程，工作台读取成果并确认入库 |

这里的数量是各脚本报告中的检查项数量，不是覆盖全 App 的页面数、独立用户场景数或真实设备测试次数。

### 2.1 独立启动、资料与导出

实际将最终 EXE 复制到独立目录运行。PATH 只保留 Windows System32，使用空用户配置和独立数据目录；无须从原项目 cwd 启动，也不要求 PATH 中存在 Python。

本次通过的路径包括：

- 真实 `--self-test`：冻结依赖、随包资源与方法模板可读取。
- 新数据空间的项目列表为空；原生采集后端为 `builtin` 且准备就绪。
- 实际 HTTP 返回 HTML 与采集 JavaScript；缺少本进程 token 的 POST 返回 403。
- 合成 UTF-8 Markdown 上传、下载字节一致。
- 合成正文实际导出 DOCX、PDF、XLSX、CSV，并核对格式标识。
- 合成截图 JSON 文件可通过实际 HTTP 读取。
- 完整项目 ZIP 校验通过，导入创建新的项目副本。
- 服务、PyInstaller 子进程和本次监听端口完整停止。

导出内容为合成正文，没有调用生成模型；本次未逐页验收这些文档的视觉排版。公开商店联网采集未执行，不沿用旧 EXE 的 Google Play 或 App Store 结果。

### 2.2 新版截图 MCP 握手

最终 EXE 用一个不存在的 `workbench/capture_mcp.py` 路径作为固定 worker 选择器，成功进入内置模块，未执行用户提供的脚本。真实完成 initialize、tools/list 和一次 capture_context。

- 工具集合为最终约定的 12 项，包含 `view_observation`，没有任意 shell 或文件执行工具。
- act_observe 的新参数与精简返回契约可读取。
- `skill_source=bundled`、`backend=android-walkthrough`、`backend_version=1.0.1`。
- Skill 正文与四份新版 references 全部从包内读取，报告保存其 SHA-256。
- `actions_used=0`、观察数为 0；未调用观察、设备动作或 finish，没有生成设备截图。
- worker 所属进程树清理后成员为空。

这项检查证明冻结 stdio 分派与随包协议可用。设备动作和成果产出由下一项合成测试单独验证。

### 2.3 冻结 FakeAdb 完整流程

本脚本在自己的输出目录临时编译 FakeAdb.exe。它不调用其他程序，只对白名单固定命令返回合成设备、App 版本、UI XML 和生成的 PNG。FakeAdb 和测试数据不应加入交付包。

实际执行顺序为：

`工作台创建合成项目和会话 → 冻结 MCP launch_app → 读取已有缩略图 → 登记首页状态 → act_observe 点击 → 登记详情状态与自动跳转 → 模块覆盖确认 → export_flows / build → finish → 工作台 HTTP 读取 PNG / ZIP → 确认入库 → 重复确认与项目资料读取`

| 项目 | 本次结果 |
|---|---|
| 合成 App | `test.frozen.walkthrough` |
| 设备 | `SYNTHETIC-FAKE-ADB-ONLY`，仅 FakeAdb 返回 |
| 最终结果 | `completed`，证据 review 通过 |
| 观察与动作 | 2 次页面观察、2 个动作预算记录；分别为启动和一次点击 |
| 模块成果 | 1 张模块流程 PNG，来自本次合成首页到详情的已记录证据 |
| PNG 人工检查 | 主线程实际打开最终合成模块 PNG，确认中文、页号、箭头方向和 Continue 动作正确，无裁切 |
| 默认观察 | MCP 只返回精简 JSON |
| 按需看图 | `view_observation` 返回已保存 JPEG；前后 FakeAdb 命令日志不变，未再次操作设备 |
| 跳转 | attach_observation 自动登记真实测试动作；重复 add_transition 返回已有边 |
| 工作台闭环 | HTTP 可读取 PNG、导出当前证据 ZIP、确认进入项目资料，并验证重复确认不重复入库 |

**此脚本仅模拟模型 runner 将 finish 的 completed 结果回填会话 ready 状态这一步。** 页面观察、原图、缩略图、地图、动作、拼图、review 和 finish 均由最终 EXE 内置工具实际生成，未用预制交付结果替代。该测试不证明真实模型可以自主完成同一范围，也不把合成 PNG 称为真实手机证据。

## 3. 进程树与端口清理

验证脚本先以 CREATE_SUSPENDED 创建进程，将自身 Popen 句柄绑定到专属 Windows Job Object，再恢复主线程。PyInstaller 派生进程及测试子进程都在本测试 Job 内；清理只作用于持有的 Job 和自己创建的进程句柄，不按进程名称或历史 PID 扫描结束其他服务。

| 运行 | 本次清理结果 |
|---|---|
| HTTP 自检进程树 | `remaining_owned_pids=[]` |
| HTTP 服务，端口 60092 | 所属进程为空，`listener_remaining=false`，端口可重新绑定 |
| MCP 握手 worker | 所属进程为空 |
| FakeAdb 编译器 | 所属进程为空 |
| FakeAdb 流程 worker | 所属进程为空 |
| FakeAdb 工作台服务，端口 53196 | 所属进程为空，`listener_remaining=false`，端口可重新绑定 |

全部测试结束后，另行再次探测 60092 与 53196，均无监听。用户自己另行打开的旧版工作台保持运行；本次测试没有借用或停止它的窗口。

修复后的清理逻辑还实际验证过“父进程提前退出、监听子进程仍存活”的合成情况：所属后代仍可被本测试 Job 完整清理，监听消失且端口可重新绑定。

## 4. 复现记录与未覆盖范围

构建工作区保留的原始报告：

- `work/exe-walkthrough-1.0.1-http/verification.json`
- `work/exe-walkthrough-1.0.1-capture.json`
- `work/exe-walkthrough-1.0.1-flow/verification.json`

对应脚本位于 `source/scripts/packaging/`；使用方法见交接说明。临时输出中的测试二进制、合成项目和数据库不属于交付资料。

本轮在当前 Windows 主机的隔离目录与配置中完成，没有在干净 Windows 虚拟机或同事电脑上验证。未验证真实 Codex 自动规划、任何真实 App、设备授权、外部翻译成功、支付、广告 SDK、埋点或经营结果；没有安装器、代码签名或多用户部署承诺。

冻结文件或相关源码变化后必须重新运行检查。上面的 SHA-256 和交付 manifest 用于识别本次产物，不能将旧报告套用于之后的构建。
