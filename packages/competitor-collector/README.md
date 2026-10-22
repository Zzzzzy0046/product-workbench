# 竞品资料采集器

从产品工作台剥离的独立小工具。提供「商店资料采集」和「App 实机截图」两个入口，不需要启动原工作台、桌面旧竞品工具或 Codex。商店采集不需要 ADB；实机截图需要本机 ADB 和已连接、已授权调试的 Android 测试设备。

## 启动

Windows 双击本目录的 **启动采集器.cmd**。

1. 首次启动会在本工具目录建立独立 `.venv` 并安装依赖，需要 Python 3.11–3.13 和网络。
2. 首次使用在本机终端设置管理员用户名和密码。密码输入不显示，没有默认账号或默认密码，也没有网页注册入口。
3. 浏览器打开 `http://127.0.0.1:8766/`，用刚设置的账号登录。

保持终端运行；停止时在该终端按 Ctrl+C。8766 被占用时不会停掉其他程序，可运行 `start.ps1 -Port 8768` 另选端口。原工作台的 8765 不受影响。

已手动安装依赖时：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[translation]"
.\.venv\Scripts\python.exe -m competitor_collector init-admin
.\.venv\Scripts\python.exe -m competitor_collector serve --open
```

忘记管理员密码：在本工具目录运行 `.\.venv\Scripts\python.exe -m competitor_collector recover-admin`，在本机重新输入密码。恢复只处理已有管理员，不创建或提权；禁用状态不会自动解除。

## 使用

1. 每行填写一个 Google Play / App Store 官方 HTTPS 链接或应用 ID，可混合两平台，每批最多 20 个，由你决定竞品，不自动搜索或替你选择。
2. 从下拉框选择国家或地区；可多选。全球选项是 **US、GB、DE、JP、IN、ID、BR、SA 八个市场的样本**，不是所有国家或全球榜单。
3. 按需勾选商店资料、评论、商店截图。截图需要先取商店资料，工具会一起开启。
4. 评论可筛评分、关键词、日期、回复、版本和最低点赞数。Google Play 每市场 1–500 条；App Store 当前每市场实际最多 100 条。筛选作用于已抓取样本，不能保证筛完仍有指定条数。
5. 点击采集，查看每个竞品的状态、长短描述、截图和评论表格。可以分别下载文件或下载本批次 ZIP。

评论翻译默认关闭。明确开启后会把评论原文发送到 Google 翻译；原文和中文分列保存，失败保留原文。没有翻译依赖时页面禁用此项；不自动切到付费模型。Python API/CLI 另可显式选择 OpenAI-compatible provider，但不在网页输入或暴露 API Key。

## App 实机截图

这是有人工选择的半自动采集，不是无人值守的全 App 爬虫。页面不会自动启动设备采集，也不需要把截图发送到外部模型。

1. 用 USB 连接 Android 测试手机（或启动已配置的模拟器），在设备上自行开启 USB 调试并确认调试授权。采集器不会自动修改系统设置或替你授权。
2. 登录后进入 **App 实机截图**，点击查找设备，选择设备及已安装的目标 App；可按包名筛选。工具不自动下载或安装 APK。
3. 创建截图任务，明确点击打开目标 App，再采集当前屏幕。手机已有登录、权限或订阅弹窗时，先在手机上人工处理。
4. 查看截图，为本页填写模块名、页面名和状态名并保存。例如「游戏库与导入 / 游戏库 / 空状态」。同一模块和页面可以保存多个状态。
5. 根据当前观察返回的控件选择下一步，或使用返回、滑动。每次操作后自动截图；页面已变化时拒绝旧控件，先重新观察。你也可以直接在手机上操作后重新截图，此时不会假装已知两张图之间的操作关系。
6. 点击生成流程拼图，按模块导出 PNG；可以直接预览、单张下载，也可以下载整包。只有已保存的页面/状态会进入流程图；没有真实跳转记录的截图单列，不按时间顺序猜箭头。
7. 暂停时释放设备；恢复任务后先重新观察。服务中断或重启不会自动继续点击。

ADB 优先读取本机 `COLLECTOR_ADB_PATH`，再检查 PATH、Android SDK 和已支持的本地 scrcpy 工具目录。没有找到时，页面会给出准备说明，不自动安装未知程序。ADB 路径只能由本机配置，不能通过网页请求指定任意可执行文件。

同一设备只允许一个活动任务，防止两人互相操作。成员只看自己的记录；管理员可查看全部资料，并可释放他人任务的设备占用，但不能替别人点击或截图。创建任务不等于截图已完成，文件导出成功也不等于目标 App 全部路径已覆盖。

购买、试用、安装等明显敏感控件会被拦截，但控件文字保护不是完整语义识别器。请使用测试设备和测试账号；不要在含私人聊天、支付资料等敏感内容的页面采集。登录、系统权限、外跳广告和无法识别的 Canvas 交互需人工接管；不绕过账号、订阅或系统权限。

## 账号与权限

| 操作 | 未登录 | 成员 | 管理员 |
| --- | --- | --- | --- |
| 登录、读取首次初始化提示 | 可以 | 可以 | 可以 |
| 发起采集 | 不可以 | 可以 | 可以 |
| 查看任务、预览、单文件与 ZIP 下载 | 不可以 | 仅本人 | 全部任务 |
| 控制实机截图任务对应设备 | 不可以 | 仅本人任务，且取得设备占用 | 仅本人任务，且取得设备占用 |
| 释放截图任务的设备占用（不操作手机） | 不可以 | 仅本人 | 可以释放全部任务 |
| 修改本人密码 | 不可以 | 可以 | 可以 |
| 创建、停用、启用、重置账号密码 | 不可以 | 不可以 | 可以 |

权限由后端和下载接口校验，不靠隐藏按钮。账号禁用、密码或角色变更会撤销该账号旧会话；管理员不能自停用/自降权，系统保留至少一个可用管理员。会话默认 8 小时，登录失败有持久化限流。

密码使用随机盐和 scrypt 哈希，数据库只保存会话 token 摘要；Cookie 为 HttpOnly、SameSite=Strict，写接口另验来源和 CSRF token。设计参考 [OWASP 密码存储](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[会话管理](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)及 [CSRF 防护](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。这不是第三方安全认证。

当前仅监听本机 `127.0.0.1`，不直接对局域网或公网开放。账号权限已经实现，但同事通过网络共用同一实例仍需部署 HTTPS、反向代理和访问控制；不能把本机 HTTP 地址当已上线团队服务。登录和权限不保护有本机文件系统权限的管理员直接读取磁盘。

## 输出

```text
data/
  auth.sqlite3                 本工具自己的账号/会话，不随资料导出
  captures.sqlite3             实机截图任务与设备占用，不随资料导出
  captures/<截图任务 ID>/
    research-map.json          模块、页面、状态及有证据的跳转
    app-map.md                 从地图派生的结构说明
    capture-session.json       最新观察与断点
    timings.jsonl              ADB 调用与阶段耗时
    observations/              原始 PNG / XML / JSON
    flow_export/               按模块生成的流程 PNG 与说明
  runs/<任务 ID>/
    job.json                   任务状态与归属，重启后保留
    <竞品项 ID>/
      store-listing.json
      store-listing.md          中文标题，商店长短描述保留原文
      reviews.csv               UTF-8 BOM，兼容 Excel
      result.json               原文、译文分列
      manifest.json             采集参数、统计与缺口
      screenshots/              商店宣传截图
```

ZIP 仅包含本任务的竞品资料，不包含账号数据库、会话、配置或其他账号的任务。`data/`、`.venv/`、`.env` 均已排除版本控制。发给同事应发送本工具源码，不要发送整份运行数据或本机凭证。

服务重启不会悄悄重试未完成采集；未完成项会标记失败，需要你重新发起。单应用后台进程最多运行 10 分钟；批次中一个应用失败不覆盖其他应用已保存的资料。网络、商店下架/地区限制或返回字段变化会造成部分失败，页面会保留警告。

## 能力边界

- 包含：商店标题、开发者、长短描述、评分等公开信息、评论与筛选、商店截图下载、可选评论翻译、Android 实机受控截图、模块流程拼图、文件导出、登录和账号管理。
- 不包含：自动选择竞品、收入/广告收入查询、评论分析/竞品对比结论、PRD、原型、iOS 实机截图、无人值守全 App 探索、安装或登录第三方 App。
- App Store 接口未返回 Subtitle 时短描述留空，不拿 Promotional Text 或长描述冒充；未知字段不使用模型补写。
- 商店安装量不是月下载，商店宣传图不是 App 内实测证据；跨市场去重的评论市场不代表评论作者国家。
- 评论分页有上限，不是完整历史数据。网站和翻译接口可能限流或变化，不保证每次能取满。

## 给其他程序调用

```python
from competitor_collector import collect

result = collect({
    "platform": "google_play",
    "app_id": "it.dbtecno.pizzaboygba",
    "countries": ["us"],
    "count_per_country": 20,
    "collect_listing": True,
    "collect_reviews": True,
    "download_screenshots": False,
    "translate": False,
})
```

原工作台的 `workbench/review_scraper_worker.py` 现在是薄兼容入口，调用本包的共享核心，不另维护第二套爬取实现。只有明确提供 legacy `root` 的调用才使用桌面旧采集后端；独立页面不接受这个参数。

## 技术与来源

Python 标准库 HTTP 服务、SQLite 账号会话、纯 HTML/CSS/JavaScript 页面；采集依赖 requests、google-play-scraper、Pillow，可选 deep-translator。无 Node 构建、无外部前端 CDN、无额外云服务。

实机采集复用了当前 `android-app-screenshot` skill 的观察、单步操作、模块地图和 PNG 拼图核心，代码随工具内置于 `capture_runtime/`，运行时不依赖用户目录下另装 skill。保留观察绑定、前台校验及支付等操作拦截；不使用旧 Axure 拼接模板，也不把商店图混进实机证据。

核心从当前工作台 worker 和本机 `competitor-analysis-platform` 的纯采集部分抽取并适配；没有复制其 UI、分析 pipeline、配置、数据或凭证。原本机项目没有可见的开源许可声明，本工具不擅自为原代码声明 MIT/Apache，也不在此宣称第三方接口授权或商用保障。
