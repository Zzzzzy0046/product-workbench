# 广告处理规则

用于处理 Android App 走查过程中出现的广告、插屏、激励视频、playable ad、native ad、banner、外跳广告。

广告是竞品体验和商业化证据的一部分，但不能让广告把流程卡死。原则是：**先截图记录，再安全关闭，继续回到目标流程**。

## 广告类型

- Banner：页面顶部/底部常驻广告。
- Native ad：伪装成列表项、推荐卡、工具卡的广告。
- App open ad：启动或回到前台时出现的全屏广告。
- Interstitial：流程中突然出现的全屏插屏。
- Rewarded video / playable ad：视频广告或可试玩广告。
- External jump：跳到 Google Play、浏览器、广告落地页或其它 App。

## 处理顺序

1. 复用当前 observation 的 Activity、截图和可见内容；不为同一画面重复 dump→screenshot→clickables。
2. 如果广告在目标 App 内，保留当前图文证据，并在地图状态标题注明广告及触发场景。旧目录模式可用以下文件名；新 observation 文件不要改名：
   - `ad_app_open_after_launch.png`
   - `ad_interstitial_after_import.png`
   - `home_banner_ad.png`
   - `ad_playable_before_close.png`
3. 记录广告触发时机：启动、返回前台、点击功能、完成任务、导出、返回首页等。
4. 尝试关闭广告：
   - 优先找 `X`、`Close`、`Skip`、`No thanks`、倒计时结束后的关闭按钮。
   - 必要时等待 3-5 秒后重新 observe；关闭按钮可能延迟出现，不用旧 index 连点，也不要为了等广告每秒重复完整截图。
   - 最多尝试 2 次关闭。
5. act-observe 已返回关闭后的图文证据，核对回到目标流程再继续，不额外重复 dump。

## 禁止操作

- 不要点击广告 CTA，例如 `Install`、`Download`、`Open`、`Play now`、`Continue`，除非用户明确要求分析广告落地页。
- 不要在 Google Play 或浏览器里继续探索广告落地页。
- 不要完成安装、注册、购买、授权。
- 不要为了关闭广告随意连点屏幕。

## 外跳处理

如果广告跳到 Google Play、浏览器或其它 App：

1. 新运行器检测到前台包名不符会暂停，不会把外部页登记成目标 App 观察。
2. 记录外跳发生在上次哪一步；如需要外部截图，先核对前台，仅用旧截图 helper 留独立标注证据，不挂成目标 App 页面。
3. 人工接管后安全返回目标 App，再重新 observe。不能把旧 observation 传给 act-observe 强行操纵外部页。
4. 如已获准只读走查，可单步用旧 helper Back 一次返回；仍不能返回时仅启动原目标 App。不探索、提交或授权外部页面。
5. 记录这是广告外跳，不把外部页面当成目标 App 功能；旧脚本也不因此获得安装/购买授权。

## 无法关闭

如果广告无法关闭：

1. 截图记录阻断页。
2. 等待 5 秒后再 observe 一次，并重新确认关闭控件。
3. 再尝试一次关闭。
4. 仍然失败时，记录为“广告阻断主流程”，不要继续盲点。
5. 如果该广告阻断关键路径，在最终报告里说明路径未完成和阻断原因。

## Banner 和 Native Ad

Banner 和 native ad 通常不需要关闭，但必须记录：

- 出现页面。
- 是否遮挡主要操作。
- 是否和内容/工具入口混淆。
- 是否影响首屏可用面积。

截图命名示例：

```text
10_home_tabs\home_banner_ad.png
20_features\tool_list_native_ad.png
40_paywalls\ad_after_export_interstitial.png
```

## 产品总结写法

广告不是只写“有广告”，要写清楚：

- 出现时机。
- 广告类型。
- 是否可关闭。
- 是否打断核心任务。
- 是否诱导外跳或误触。
- 可见的体验摩擦；对留存、转化、评分的影响只能作为推断，不能仅凭截图宣称已测得收入或指标变化。
