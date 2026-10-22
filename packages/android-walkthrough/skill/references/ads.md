# 广告与外跳

广告是商业化证据，但不能卡住流程：**先截图存证，再安全关闭，回到目标流程**。

## 自动处理（默认开启，`--no-auto-dismiss` 关闭）

每次 observe/act 前最多 3 轮：

| 前台 | 动作 | 记录 `kind` |
|---|---|---|
| 目标包内的广告 SDK Activity（AdMob、Meta Audience Network、AppLovin、Unity、ironSource、Vungle/Liftoff、Pangle、Mintegral、InMobi、Chartboost、DT/Fyber、Yandex、myTarget、Bigo、Moloco 等，按类名前缀识别） | 截图 → 返回键；仍在则点精确的 close/skip（含西/葡/印尼/越/泰/俄语） | `ad` |
| Play 商店、常见浏览器、Google 搜索 | 截图 → 返回键 | `external_jump` |
| 桌面（仅当本次关广告导致 App 退出） | 重启 App | `app_exited` |
| 其他外部 App、系统权限框、选择器 | 不处理 → `NOT_TARGET_APP` | — |

额外允许自动返回的外部包：`--return-pkg <包名>`（可重复）。

识别不到的情况：很多 App 把开屏广告包在自家 Splash Activity 里，或用 native 广告伪装成列表项，这类不会被自动关闭，需要你看画面识别、在状态标题里注明"含广告"。

## 外跳不一定是广告

`external_jump` 只说明跳去了 Play/浏览器。评分请求、隐私政策、"更多应用"、Play 结算弹窗都会外跳。用 `ads_closed[].pkg` 和截图判断来源；结论里写清楚。

## 人工处理

自动处理关闭或失败时：看 view → 找 close/skip/倒计时结束后的关闭 → 用 act 点击；关闭按钮常延迟出现，等 3–5 秒再 observe，最多尝试 2 次。仍关不掉记为"广告阻断主流程"，停止该路径。

## 禁止

- 不点广告 CTA（Install/Download/Open/Play now/Learn more）。
- 不在 Play/浏览器里继续浏览落地页，不安装、不注册、不授权。
- 不为关广告乱点屏幕。

## 广告曝光为 0 时

国内网络下 AdMob、Pangle 等海外 SDK 基本不填充。没看到广告 ≠ 没有广告位。需要判断广告策略时，让设备走目标市场网络复跑，并在结论里标注本轮网络环境。

## 总结时写清楚

出现时机（启动/返回前台/功能入口/完成任务/导出/返回首页）、形式（app open/插屏/激励/banner/native/playable）、能否关闭、是否打断核心任务、是否外跳或诱导误触。对留存/收入的影响只能写推断。
