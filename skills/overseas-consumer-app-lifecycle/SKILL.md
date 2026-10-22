---
name: overseas-consumer-app-lifecycle
description: "Route small-team overseas consumer-app work by the current stage: complete Chinese new-product analysis, page-first requirements, review changes and scoped handoff. PRD, tracking and real-build acceptance are optional."
---

# 小团队出海 App 工作流

## 选择当前工作

品类已决定要做，日常主干为：市场与竞品分析 → 原型图＋需求说明 → 初审修改 → 终审整理 → 需求评审。它是导航，不是必须跑完的审批链；从用户当前阶段继续，只交付本轮指定内容。

- 普通新品与快速迭代，读 [references/fast-iteration-path.md](references/fast-iteration-path.md)。完整新品分析保留 Heart Rate 产品故事，不压成定义卡，也不自动升级为正式研究。
- 选择具体产物，读 [references/artifact-router.md](references/artifact-router.md)。独立 F2、完整埋点、三列表产品验收与 F3 实测按需，不默认生成全套。
- 正式 0–12 章、立项或阶段门仅在明确要求时使用历史 T1–T4；需要 Gate 时读 [references/gates.md](references/gates.md)。
- 恢复已有项目时读 [references/manifest-contract.md](references/manifest-contract.md)，沿用已存在产物和确认，不因补交接重新立项。

模板路径均相对工作台仓库根目录。先定位当前仓库，不假设固定磁盘、产品值或外部连接可用。

## 事实与确认边界

先读当前要求、指定基线及本轮资料。用户当前确认和指定的确认基线约定业务规则；当前原型、草图或运行行为描述实际表现。二者不一致时列来源与差异，不凭日期、文件名或实现偏差擅自覆盖约定。

资料保留来源、日期及适用范围。评论只代表当前样本，截图不证明完整交互，第三方收入估算不证明广告收入或真实收益。没有资料就说明未覆盖，不硬凑画像、因果、竞品或商业数值；案例只能提供方法。

候选资料可辅助用户选用，但不自动确定最终竞品。近期下载与累计安装、商店收入与广告收入分开；保留平台、地区、周期、来源、覆盖口径及实际体验范围，未知不写 0。

## 最小维护原则

- F1 保留五章，范围集中一处；只对选中竞品深入，按“观察 → 产品含义 → 本产品取舍”表达。不套标准 App 功能树或广告顺序，不强凑竞品、模块或页面数量。
- 页面先写用途、呈现形式、区域层级、必要 UI 文案，再按业务主题说明条件、操作、结果、返回及真实需要的边界。简单状态补差异；系统接管只说明触发与返回。
- 原型旁注和 F2 共用一份已确认页面正文及稳定 ID。已有流程、索引、规则和用例时复用或引用，只补变化。
- 同轮只维护一份规则变更表，核对“旧口径 → 已确认新口径 → 各产物具体位置”。未读取标未核对，未实际写回标待同步。
- 产品验收只写场景、步骤、预期；F3 沿用原编号及预期增补实测。埋点方案负责设计，F3 引用原事件及参数验证，不另设计或压成固定数量，实际日志与状态只维护一处。

## 输出与执行

正式正文中文，必要 UI copy 和技术名词保留英文。选定的评论、截图、日志及研究资料进入资料索引并支持相关结论，不复制整份原始材料。

不默认输出访谈、假设验证、风险清单、技术 Spike、Gate、条件闭环或 F1 独立平台权限章节。付费投放、ASO 与商店发布不在本流程内。

只声明实际完成的工作。原型制作说明不等于写入 Figma/Axure，静态审查不等于真机验收，工作台确认不等于部门业务评审通过。外部工具不可用时说明边界，不虚构操作。

只有当前任务确实需要采集评论时才读 [references/competitor-review-collector.md](references/competitor-review-collector.md)，核对当前工具及翻译选项。普通分析可直接使用上传 CSV，不强制再次采集。不自动写入知识库、Notion 或 GitHub。
