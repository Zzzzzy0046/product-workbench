# 按模块采集协议

本协议用于真实 Android App 走查。脚本负责受控操作、证据绑定和地图维护；模块含义、页面身份和下一步动作仍由操作者根据真实画面判断。不是输入包名后无人值守跑完整 App 的爬虫。

## 1. 准备与范围

先用现有 ADB `devices -l` 核对设备，确认目标应用已安装及其版本。只查看包信息，不安装、清数据、修改系统设置。每个包名/serial 使用独立输出目录；不同版本的大改动另开目录，不能把旧版本地图当本轮证据。

已有目标前台就直接观察。需要启动目标 App 时，可以使用旧 helper 的 `start`，但不要用带固定等待的旧 `session` 来重复初始化每个模块。账号登录、购买、授权或外部系统页面由用户处理。新接口不启动应用，不处理系统弹窗。

看到首页和导航后，列出本轮要回答的问题、暂定模块及预算。例如：只采集“游戏库→导入→回到库”和“游戏中菜单”；每模块最多 10 次动作或 3 分钟，重复失败最多两次。这个数字是任务预算，不是速度承诺。模块可以调整，但不能把暂定架构当已观察事实。

## 2. 观察与单步操作

将占位符换成已确认的路径、包名和设备。PowerShell 示例：

```powershell
$PY = "<可用的 python.exe>"
$C = "C:\Users\simon\.codex\skills\android-app-screenshot\scripts\capture_session.py"
$M = "C:\Users\simon\.codex\skills\android-app-screenshot\scripts\research_map.py"
$OUT = "<本轮输出目录>"
$ADB = "<adb.exe>"
$SERIAL = "<已核对的 serial>"
$PACKAGE = "<目标包名>"
& $PY $C observe --adb $ADB --serial $SERIAL --package $PACKAGE --out-dir $OUT
```

标准输出是 JSON：`ok`、`observation`、`adb_calls`。观察记录的 `id` 为本次 observation_id；`files` 为输出目录下的相对路径。打开对应 PNG 看画面，结合 `nodes` 的父子结构及 `clickables` 选择元素。不要只按文字猜页面或重复请求同一份 XML。

```powershell
& $PY $C act-observe --adb $ADB --serial $SERIAL --package $PACKAGE --out-dir $OUT `
  --observation-id "<最新 obs-...>" --action tap --index 2
# 返回、滑动也必须绑定最新观察；每次执行后先看新观察，再决定下一动作。
& $PY $C act-observe --adb $ADB --serial $SERIAL --package $PACKAGE --out-dir $OUT `
  --observation-id "<最新 obs-...>" --action back
& $PY $C act-observe --adb $ADB --serial $SERIAL --package $PACKAGE --out-dir $OUT `
  --observation-id "<最新 obs-...>" --action swipe --swipe 500 1400 500 500
```

不要连着照抄三条动作；示例不是动作队列。`index` 仅在对应 observation 有效。动作前会再次读取前台和 UI 指纹；任何变化均拒绝旧操作，重新 observe 后再选元素。当前指纹包含全部控件文本，因此倒计时等动态内容也可能触发拒绝；不能为省时间直接关闭保护。tap/back/swipe 以外的动作不接受，也不接受任意 shell。购买/订阅/安装/试用等明显控件会检查整个点击子树后拦截；此保护并非能识别所有语言与无文字按钮，仍须人工语义核对。

### 状态与恢复

- 正常页面通常只 dump 一次，截图前后核对前台包名和 Activity。仅信任唯一有效的 mCurrentFocus，旧设备只返回 mFocusedApp 时安全暂停。XML 与截图是先后采集，不是同帧原子快照；`stable: null` 表示没有宣称持续稳定，不代表稳定性测试通过。
- XML 出现 ProgressBar 时做短轮询；`--settle-timeout` 默认 8 秒、范围 0.2–30 秒，只约束这一段 UI 等待，不是整条命令总时限。ADB 其他阶段各有超时。
- XML 失败：保留视觉截图，`status: visual_only`，`actionable: false`。加载未结束则为 `loading`，不按旧元素继续操作。游戏/Canvas/地图截图可保留，但本接口不为其捏造控件；需要实际交互时人工接管，再重新观察。
- 前台变成权限弹窗、系统选择器、广告外跳：暂停，不冒充目标 App。人工处理后重新 observe。不要因暂停而重开、清空整个采集目录。
- 动作发出前会将 checkpoint 标记 pending_action 并使旧观察失效。返回错误若有 `action_may_have_run: true`，说明动作可能已执行但后续观察失败；旧 observation 无法重用。只观察当前位置，不能重发上次 tap。恢复会保留 unresolved_action 及 checkpoint.unresolved_actions，不自动连成确定跳转。
- 同一 serial 有互斥锁。异常退出遗留锁时，先确认确实没有采集进程，再只处理对应设备的锁文件；不批量删临时目录。

每条 observation 的 PNG/XML/JSON 同名保存；不要改名破坏绑定。断点保存在 `capture-session.json`。续跑总是先新观察，不沿用中断前 index 或坐标。

## 3. 模块、页面、状态与跳转

在同一个输出目录维护一份地图，不从 UI 节点层级直接推导业务架构：

```powershell
$MAP = Join-Path $OUT "research-map.json"
& $PY $M --map $MAP init --package $PACKAGE --serial $SERIAL
& $PY $M --map $MAP module --id M01 --title "游戏库与导入"
& $PY $M --map $MAP page --id P01 --module M01 --title "游戏库" --kind page
& $PY $M --map $MAP attach --observation (Join-Path $OUT "observations/<obs-id>.json") `
  --module M01 --page P01 --state S01 --title "未导入游戏"
```

先按实际观察添加页面，再挂 observation。一个业务页的空/加载/正常/结果等状态挂在同一 page_id 下；明显不同用途的页才新增页面。弹窗可用独立 page 并设置 `--kind dialog`。同一页面只有一个主要 module_id，跨模块引用已有状态即可，不复制截图假装多个页面。

中间观察不一定要挂成独立页面状态，但原始 JSON/PNG/XML 必须保留。在提供 root 的维护接口或 CLI attach 下，会从同一研究目录补登记缺失的原始祖先观察，校验应用/设备与路径；不会替它们创建页面、状态或跳转。不能删掉中间观察后假装两个不相邻状态有一步直达关系。

字段结构：

```text
modules: id / title / status / reason
pages: id / module_id / title / kind
states: id / page_id / title / observation_id / screenshot / ui_xml
transitions: id / from_state / to_state / action / evidence_observation_ids
observations: 完整的观察记录（含包名、设备、Activity、时间及文件）
```

跳转必须来自真实动作：目标 observation 的 `previous_observation_id` 对应源 observation，`action` 必须原样使用采集返回值。不能因文件相邻、名称相似或属于同一模块就连边。为了避免 Windows 命令行 JSON 转义，推荐在调用脚本的 Python 代码中直接使用保存的动作对象：

```python
# scripts 目录加入 sys.path 后，可调用 research_map 的维护接口。
from pathlib import Path
import json
import research_map as rm

map_path = Path(output_dir) / "research-map.json"
data = rm.load_map(map_path)
target = json.loads((Path(output_dir) / "observations" / (target_id + ".json")).read_text(encoding="utf-8"))
# 两端 S01、S02 已分别 attach；source_id 为 S01 绑定的观察 id。
rm.add_transition(data, "T01", "S01", "S02", target["action"], [source_id, target_id])
rm.save_map(map_path, data)
```

CLI 同样支持 `transition --id T01 --from S01 --to S02 --action <原样 JSON> --evidence <源obs> <目标obs>`；不要手写一个“看起来合理”的动作替代证据。

## 4. 覆盖与交付

模块状态为 `pending`、`partial`、`complete`、`blocked`、`skipped`。只有本轮所选关键路径确实看过，才手动标 complete 并写清覆盖范围；截图数量、文件验证通过都不会自动完成模块。登录/订阅/设备限制等写 blocked；尚未选中的入口写 skipped 或留待补。

```powershell
& $PY $M --map $MAP status --module M01 --status partial --reason "已看到游戏库空态；系统文件选择器待人工处理，尚未观察导入结果"
& $PY $M --map $MAP check
& $PY $M --map $MAP render
& $PY "C:\Users\simon\.codex\skills\android-app-screenshot\scripts\build_flow_montages.py" --input-dir $OUT --title "<App 名称>"
& $PY "C:\Users\simon\.codex\skills\android-app-screenshot\scripts\review_delivery.py" --input-dir $OUT --require-flow
```

`render` 默认生成同目录 `app-map.md`，按模块展示页面、状态和有证据的 Mermaid 跳转。`check` 做结构校验并报告缺文件，缺文件可能仅为警告；最终交付检查会把丢失截图/引用当错误处理。两种脚本都不能证明实际覆盖充分或 App 功能已通过验收。

模块地图是结构源；流程 PNG/Markdown/报告为派生物。截图后按模块的真实跳转统一拼图，规则见 screenshot-flow.md；不使用 Axure 模板，不生成网页。可按一个已采集批次导出，不必等整个 App 结束。未采集处明确留空，不从其他模块补图。用户只要图片时不额外生成 Word 和长分析。

## 5. 耗时口径

`timings.jsonl` 记录每条命令总耗时、ADB 调用次数与阶段耗时（foreground、ui、screenshot、tap 等）。它不包含调用之间的模型判断、人工选择和广告自然等待；单独记录这些时间，才能解释全流程耗时。

比较优化前后必须同一 App 版本、设备、起始状态、路径和覆盖范围；分别记录采集时间、判断时间、广告/网络等待、导出时间和失败重试。FakeAdb 测试只能证明调用逻辑与恢复机制，不是实际提速数据。禁止把减少调用次数直接换算成总耗时下降百分比。
