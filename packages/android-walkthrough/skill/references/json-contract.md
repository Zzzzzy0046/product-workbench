# 输出协议 v1（供工作台 / 脚本对接）

每条命令在 stdout 输出**一行** JSON（UTF-8；加全局 `--ascii` 输出 ASCII 转义）。退出码：成功 0，失败 1。所有输出都带 `"v": 1`。

当前脚本 1.0.1；缺参数、未知命令和参数类型错误同样返回 `BAD_ARGS` JSON 与退出码 1。`--help` / `--version` 是例外，输出普通帮助/版本文本并成功退出。

## 成功：observe / act / launch（精简版）

```json
{"v":1,"ok":true,"obs":"obs-3f9a…","status":"observed","activity":".MainActivity",
 "view":"<绝对路径>/observations/obs-3f9a….view.jpg","screen":[1080,2340],
 "controls":[[0,"Settings","iv_setting",[970,170]],[1,"Search","et_search",[540,360],"edit*"]],
 "controls_more":12,
 "ads_closed":[{"kind":"ad","pkg":"com.x","by":"back","shot":"observations/ad-….png"}],
 "ui_error":"…","unresolved_action":{…},
 "state":"S05","edge":"T04","edge_note":"…","map_error":"…"}
```

- `status`：`observed` / `loading`（等待超时仍在转圈，仍可操作）/ `visual_only`（无控件树）。
- `controls` 行：`[序号, 文字(≤30字), 短 resource-id, [中心x, 中心y], 类型?]`；类型缺省=可点击，`edit`/`edit*`（已获焦点）/`scroll`。
- `state/edge` 仅在传了 `--as` 时出现；`map_error` 表示观察已保存但登记失败。
- `--full` 输出完整观察记录（含节点树），与 `observations/<obs>.json` 相同。

## 失败

```json
{"v":1,"ok":false,"code":"UI_CHANGED","message":"…","acted":false,"next":"choose_again",
 "observation":{…精简观察…}}
```

| code | next | 说明 |
|---|---|---|
| BAD_ARGS | fix_args | 参数错误 |
| NOT_INITIALIZED | init | 目录未 init |
| WORKSPACE_MISMATCH | use_new_out_dir | 目录属于其他包名/设备 |
| ADB_NOT_FOUND / DEVICE_NOT_FOUND / DEVICE_AMBIGUOUS / PACKAGE_NOT_INSTALLED | 见 next | 环境问题 |
| ADB_FAILED / ADB_TIMEOUT / FOCUS_UNKNOWN / SCREENSHOT_INVALID | observe | 设备侧失败 |
| DEVICE_LOCKED | wait | 同设备并发；等待持有者，不删除锁文件 |
| NOT_TARGET_APP | launch / manual_then_observe | 附 `foreground`、`activity` |
| FOREGROUND_CHANGED / UI_CHANGED / AD_CLEARED | choose_again | 请求动作未执行，附新 `observation`；UI_CHANGED 包括目标语义、焦点或可操作结构变化 |
| STALE_OBSERVATION | observe | 非最新观察 |
| NOT_ACTIONABLE | use_tap_xy_or_back | 无控件树 |
| BLOCKED_SENSITIVE | manual_or_confirm | 购买/订阅/密码类控件 |
| NO_FOCUSED_INPUT | tap_input_first | text 前未聚焦输入框 |
| ACTION_UNCERTAIN | observe | 动作可能已执行，`acted:true` |
| MAP_ERROR | fix_map | 地图操作被拒 |

`acted: true` 表示设备上可能已经执行了输入：调用方只能重新观察，不能重放。

## 其他命令

- `doctor` → `{"ok", "checks":[{"name","ok","required","detail","fix"?}], "devices":[…]}`
- `init` → `{"ok","config":{package, serial, adb, model, app_version, …}}`
- `map … show` → 模块/页面/状态/跳转的紧凑数组，`last_observation`
- `build` → `{"ok","review":"PASS|FAIL","issues","warnings","flow_pngs","app_map","report"}`
- `anim restore` → `{"ok":true,"animations":"restored","values":{…},"changed":true|false}`；无备份时 `changed:false`，不写设备设置

## 目录结构

```
<out>/
  aw.json                 包名、serial、adb、机型、App 版本、缓存
  capture-session.json    断点（最新观察、待确认动作）
  research-map.json       模块/页面/状态/跳转（唯一结构源）
  observations/           <obs>.png/.xml/.json/.view.jpg，ad-*.png，jump-*.png
  timings.jsonl           每条命令的耗时与 ADB 调用
  app-map.md  flow_export/  delivery_review.md      build 产物
```
