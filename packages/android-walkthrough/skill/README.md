# android-walkthrough 1.0.1

让 Claude Code / Codex 通过 ADB 走查 Android App：单步受控操作、自动关广告、按模块登记真实跳转，最后输出按模块的流程截图拼图。适合竞品流程拆解、付费墙/广告触点留证。

## 前置条件

| 项 | 要求 |
|---|---|
| Python | 3.9+，`python -m pip install -r requirements.txt`（Pillow 必需；python-docx 仅导出 Word 时需要） |
| adb | Android SDK platform-tools。放进 PATH，或装在默认 SDK 目录，或运行时用 `--adb` 指定 |
| 手机 | 开发者选项 → USB 调试；首次连接在手机上点"允许" |
| 字体 | Windows 自带微软雅黑即可；Linux 安装 `fonts-noto-cjk` |
| 网络 | 要看海外广告，手机需走目标市场网络；国内网络下广告基本不填充 |

## 安装

```bash
python install.py            # 链接到 ~/.claude/skills 和 ~/.codex/skills（存在才装）
python install.py --copy     # 复制而不是链接
python install.py --dry-run  # 只看会做什么
```

装完重启 Claude Code / Codex。已存在同名目录时脚本会停下，不会覆盖；确认后用 `--force`（原目录会先改名备份）。

## 自检

```bash
python scripts/aw.py doctor --package com.example.app
```

每个失败项都带 `fix` 提示。

## 怎么用

直接对 Claude / Codex 说，例如：

> 用 android-walkthrough 走查 com.example.weather，只看首页→城市搜索→15 天预报，以及付费墙入口，输出到 D:\work\weather-walkthrough

模型会依次：`doctor` → `init` → `launch/observe` → 单步 `act` 并登记状态 → `build` 出图。产物：

```
<输出目录>/flow_export/*_flow.png    ← 主要交付：按模块的流程拼图
<输出目录>/app-map.md                ← 模块/页面/跳转结构
<输出目录>/delivery_review.md        ← 交付检查
<输出目录>/observations/             ← 原始截图、控件树、广告/外跳证据
```

也可以手动跑命令，完整命令见 [SKILL.md](SKILL.md)，输出格式见 [references/json-contract.md](references/json-contract.md)。

## 安全边界

不安装/卸载、不清数据、不登录、不购买；购买/订阅/试用/安装/密码控件默认拦截；广告 CTA 永不点击；系统权限框和登录交给人处理。`aw anim off` 会修改手机的动画设置，用完务必 `aw anim restore`。

## 常见问题

- **`DEVICE_LOCKED`**：同一台手机同时只能跑一条命令；进程退出后 OS 自动释放锁。锁文件残留正常，不要手动删除。
- **`ui_error` / `visual_only`**：页面有持续动画（雷达、视频、游戏），uiautomator 拿不到控件树。可用 `tap-xy --view` 按截图点，或经同意 `aw anim off`。
- **`NOT_TARGET_APP`**：权限弹窗、系统选择器、登录页、其他 App 在前台。处理后再 observe；在桌面时用 `aw launch`。
- **多台设备**：`init` 时用 `--serial` 指定；每台设备用独立输出目录。

## 开发

```bash
python -m unittest discover -s tests     # 离线测试，不需要手机
```
