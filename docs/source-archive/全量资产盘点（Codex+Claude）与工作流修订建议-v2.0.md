# 全量资产盘点（Codex + Claude）与工作流修订建议 v2.0

## 0. 结论先行

上一版实施方案的方向没有错，但盘点范围不够完整，主要漏了五类资产：

1. Claude 的方法论知识库与 72 条带来源 claims；
2. Claude 插件仓库中尚未进入 Codex 的 3 个高价值 PM Skill；
3. 原始《新品 Heart Rate》PDF、AI Resume、监控品类、Stellara 等需求文档变体；
4. 《竞品分析通用工作流》代表的独立竞品证据与交付审查环节；
5. 从“文档意图”到“代码实现”和“研发验收”的交付闭环。

因此，完整工作流不应继续停留在“1 个主控 + 7 个专项 Skill + T1-T4”。修订后的推荐结构是：

> **1 个主控 Skill + 9 类产出物路由 + 12 个核心专项能力 + 5 道 Gate + 1 份 Manifest + 1 个显式授权的知识回流环。**

范围修订：付费获客、媒体采买和商店发布不属于本工作流。对已有产品数据，只保留产品指标、留存、商业化表现和版本迭代分析。

本文件仍然是资产盘点和搭建依据，不代表这些 Skill 已经安装、改写或连通。

---

## 1. 本轮实际盘点范围

### 1.1 Codex

- 当前 Skill 根目录：`C:\Users\simon\.codex\skills`
- Memory Skill：`C:\Users\simon\.codex\memories\skills`
- Shared Agent Skill：`C:\Users\simon\.agents\skills`
- GitHub 同步副本：`C:\Users\simon\Documents\codex-sync\codex\skills`
- Codex 历史项目、输出物和 Memory 注册表

### 1.2 Claude

- 用户级 Skill：`C:\Users\simon\.claude\skills`
- Commands：`C:\Users\simon\.claude\commands`
- Agents：`C:\Users\simon\.claude\agents`
- Plans：`C:\Users\simon\.claude\plans`
- Plugin 注册表和本地 marketplace checkout
- 方法论知识库：`D:\claude-workspace\knowledge`
- 产品与竞品项目：`D:\claude-workspace\projects`

### 1.3 历史产品资料

对 `C:\Users\simon\Documents` 下的 `.md`、`.docx`、`.pdf`、`.xlsx`、`.html` 做了文件级扫描：

- 扫描到 1,451 个候选文件；
- 其中 704 个文件名命中“新品、需求、PRD、竞品、原型、埋点、订阅、广告、Heart、Reader、Printer”等产品关键词；
- 704 个命中并不代表 704 份独立方法论，其中大量是 Axure 导出页、同一版本的 HTML 页面、备份、截图、临时文件和交付物副本；
- 盘点时将“原始文档、当前模板、衍生文档、生成物、证据、备份”分开处理。

### 1.4 安全边界

- 未读取或输出 `.credentials.json`、token、Cookie、API Key 等凭证；
- 未修改 Codex 或 Claude 的现有 Skill；
- 未安装 Claude 插件；
- 未同步 Notion 或 GitHub；
- 未执行任何竞品订阅、许可、签名或付费能力绕过。

---

## 2. Codex 侧资产盘点

### 2.1 数量与来源

当前 `C:\Users\simon\.codex\skills` 共发现 **110 个 `SKILL.md` 入口**。通过 SHA-256 与 Claude 用户 Skill、Claude PM marketplace、Shared Agent Skill 对比：

| 来源状态 | 数量 | 判断 |
|---|---:|---|
| 与 Claude PM marketplace 完全相同 | 65 | 通用 PM 方法库，已被复制到 Codex |
| 与 Claude 用户 Skill 完全相同 | 19 | 两端共用或同步过的能力 |
| Codex 独有或内容已修改 | 26 | 包含系统 Skill、角色 Skill 和产品工作流专项 Skill |
| 合计 | 110 | 当前 Codex Skill 入口总数 |

### 2.2 当前最重要的产品工作流专项 Skill

| Skill | 当前职责 | 在完整工作流中的位置 |
|---|---|---|
| `overseas-consumer-app-workflow` | 海外 C 端新品完整分析 | Discovery → Go/Hold |
| `android-app-screenshot` | ADB 走查、竞品证据、截图、商业化观察、交付报告 | Competitor Evidence |
| `prd-prototype-standard` | 中文 PRD + 原型交付标准 | Solution Definition |
| `prototype-requirement-writer` | 页面级需求、状态、异常、交互和标注 | Prototype Handoff |
| `lead-review` | 负责人视角交付前审查 | G2 / G3 / G4 前置检查 |
| `tracking-spec-from-prototype` | PRD/原型 → 研发可执行埋点表 | Instrumentation Design |
| `tracking-implementation-validator` | 真机埋点工具验收 | Implementation Acceptance |

### 2.3 Memory 中存在、但未作为普通安装 Skill 暴露的能力

| Skill | 状态 | 建议 |
|---|---|---|
| `lanhu-prototype-inspection` | 位于 Memory Skill；明确了 Lanhu MCP-first、list → analyze 路由 | 应整理后提升为正式专项 Skill |
| `codex-thread-index-recovery` | 位于 Memory Skill；用于 Codex 任务恢复和 Provider 诊断 | 保留为运维 Skill，不进入产品生命周期主干 |

### 2.4 通用 PM Skill 库

Codex 已有较完整的通用方法库，覆盖：

- 市场与竞争：`market-sizing`、`market-segments`、`competitor-analysis`、`porters-five-forces`、`pestle-analysis`、`swot-analysis`；
- 用户与机会：`user-personas`、`user-segmentation`、`customer-journey-map`、`job-stories`、`opportunity-solution-tree`；
- 假设与实验：`identify-assumptions-*`、`prioritize-assumptions`、`brainstorm-experiments-*`；
- 战略与定位：`product-strategy`、`positioning-ideas`、`value-proposition`、`lean-canvas`、`business-model`；
- MVP 与执行：`prioritize-features`、`create-prd`、`user-stories`、`wwas`、`sprint-plan`、`pre-mortem`；
- 商业化与增长：`monetization-strategy`、`pricing-strategy`、`growth-loops`、`gtm-strategy`、`gtm-motions`；
- 数据与复盘：`metrics-dashboard`、`north-star-metric`、`ab-test-analysis`、`cohort-analysis`、`retro`；
- 内容与语言：`grammar-check`、`localization-specialist`、`content-strategist`。`aso-copy` 与 `release-notes` 只作为已安装资产记录，不进入本工作流路由。

判断：这些 Skill 是“工具箱”，不能全部硬串成固定流水线。主控应按 Task Type 和 Stage 选择其中少数几个，否则一次小需求会被升级成冗长的全套分析。

### 2.5 Codex 同步副本状态

`C:\Users\simon\Documents\codex-sync\codex\skills` 当前有 87 个 Skill，而实际安装目录有 110 个：

- 同步副本少 23 个入口；
- `android-app-screenshot` 与当前安装版内容不同；
- `tracking-spec-from-prototype` 与当前安装版内容不同；
- `tracking-implementation-validator` 尚未进入同步副本；
- 同步副本没有比当前安装目录多出的 Skill。

因此：

> **当前 `C:\Users\simon\.codex\skills` 才是 Skill Source of Truth；`codex-sync` 只能视为过期备份，不能反向覆盖。**

---

## 3. Claude 侧资产盘点

### 3.1 用户级 Skill

`C:\Users\simon\.claude\skills` 共发现 **29 个 `SKILL.md` 入口**。

#### 两端已有重复或近似能力

- `android-app-screenshot`
- `apple-hig-designer`
- `aso-copy`
- `prompt-builder`
- `prototype-requirement-writer`
- `umeng-cli`
- DingTalk 系列 Skill
- `excel`、`ppt` 在 Codex 已有更正式的文档/表格/演示文稿运行时能力，不需要原样迁移

其中：

- `apple-hig-designer`、`aso-copy`、`prompt-builder`、`umeng-cli` 两端入口文件完全一致；
- `prototype-requirement-writer` 只有换行/字节层差异，正文逻辑没有实质性差异；
- `android-app-screenshot` 的 Codex 版明显更完整，增加了快速/标准/深度模式、双设备、Axure 拼版、Word 报告和交付审查，应以 Codex 版为准。

### 3.2 Claude 独有 Skill 的处理结论

| Claude Skill | 价值判断 | 是否进入正式工作流 |
|---|---|---|
| `device-verification` | 有价值：真机状态轮询、弹窗状态机、循环触发、截图 + logcat 交叉证据 | **可吸收，但必须做安全裁剪** |
| `ad-strategy-teardown` | 有价值部分：SDK 识别、广告位结构、触发机制、配置 vs 实测报告 | **只吸收静态/公开/授权设备分析部分** |
| `apk-install-bypass` | 混合了正常 split APK 安装诊断和许可校验绕过 | **只保留合法安装诊断；绕过部分不纳入** |
| `adapty-subscription-bypass` | 直接修改竞品 premium/订阅判断 | **隔离，不纳入** |
| `premium-bypass` | 订阅解锁、签名校验规避、运行时 hook 等 | **隔离，不纳入** |
| `serenity-skill` | 投资产业链研究，不属于 C 端出海产品主流程 | 不纳入主干，可独立保留 |
| `excel` / `ppt` | 办公文件操作包装 | 使用 Codex 内置文档能力替代 |

正式工作流的边界应写死：

> 竞品分析允许商店信息、公开资料、授权设备上的正常使用、静态结构观察和行为取证；不允许绕过付费、订阅、许可、签名校验或访问控制。

### 3.3 Claude Commands

发现 5 个快捷命令：

| Command | 意图 | 工作流处理 |
|---|---|---|
| `/aso` | 商店文案 | 范围外，不进入本工作流 |
| `/competitor` | 竞品分析 | 转换为 `COMPETITOR_AUDIT` |
| `/paywall` | 订阅/Paywall | 转换为 `MONETIZATION_DESIGN` |
| `/prd` | 快速 PRD | 转换为 `FEATURE_PRD` |
| `/ui-review` | UI 评审 | 转换为 `DESIGN_REVIEW` |

判断：这五个命令适合作为主控的“快捷意图别名”，不需要再维护五套独立模板。

### 3.4 Claude Agents

发现 12 个角色 Agent：

- `market-researcher`
- `growth-strategist`
- `design-director`
- `content-strategist`
- `data-analyst`
- `tech-architect`
- `frontend-developer`
- `backend-developer`
- `devops-engineer`
- `localization-specialist`
- `qa-engineer`
- `financial-researcher`

其中前 11 个已经在 Codex 有同名或同职责 Skill；`financial-researcher` 属于投资研究，不进入本产品工作流。

这些 Agent 真正值得继承的不是“自动开很多子 Agent”，而是职责分工：市场、增长、设计、内容、数据、架构、前端、后端、DevOps、本地化、QA。主控需要保留角色路由，但不应为了形式而强制多 Agent。

### 3.5 Claude Plugin 状态

`installed_plugins.json` 登记了 10 个插件：

- `pm-data-analytics@pm-skills`
- `pm-execution@pm-skills`
- `pm-go-to-market@pm-skills`
- `pm-market-research@pm-skills`
- `pm-marketing-growth@pm-skills`
- `pm-product-discovery@pm-skills`
- `pm-product-strategy@pm-skills`
- `pm-toolkit@pm-skills`
- `frontend-design@claude-plugins-official`
- `claude-hud@claude-hud`

但注册表内 10 个 `installPath` 当前全部不存在。因此，“注册为已安装”不等于“当前 cache 路径仍可直接调用”。好消息是 marketplace checkout 仍存在，可作为源码盘点来源。

### 3.6 Claude PM marketplace 的关键发现

本地 `pm-skills` marketplace 共发现 **68 个 PM Skill**：

- 其中 65 个已经以完全相同内容进入 Codex；
- 还有 3 个没有进入当前 Codex Skill 清单，而且对完整工作流很重要。

#### 1. `strategy-red-team`

用途：对 PRD、路线图或策略的承重假设进行攻击，输出：

- Fails if；
- 本周需要获取的证据；
- Kill Criterion；
- Cheapest Test；
- 哪些部分经得住攻击。

它和 `pre-mortem` 不重复。`pre-mortem` 是假设已经失败后回看原因；`strategy-red-team` 是现在就攻击最关键假设。建议放在 G1 方向门禁和 G2 方案门禁前。

#### 2. `shipping-artifacts`

用途：为代码项目建立可审查的意图文档：

- `architecture.md`
- `flows.md`
- `permissions.md`
- `variables.md`
- `tests.md`
- 条件性 `emails.md`、`cron.md`、`seo.md`、`automation.md`

这补上了 PRD/原型与研发仓库之间的断层。建议放在 READY_FOR_DEV → BUILD → DEVELOPMENT_ACCEPTANCE。

#### 3. `intended-vs-implemented`

用途：逐条比较文档意图与代码实现，要求每个发现同时具备：

- 文档中“应该怎样”的证据；
- 代码中“实际怎样”的证据；
- 影响的 actor / data / cost / trust boundary；
- 具体修复建议。

这补上了“文档写完了，但代码到底有没有照做”的核心缺口。建议作为 G3 开发交付门禁的重要审查能力。

---

## 4. Claude 方法论知识库

### 4.1 结构与数量

知识库：`D:\claude-workspace\knowledge`

- 72 个 claim 文件；
- 46 个方法论 claim；
- 13 个竞品分析 claim；
- 13 个产品决策 claim；
- 每条 claim 原则上带来源和判断背景；
- `index.md` 是完整注册表；
- `方法论总纲.md` 将 72 条 claim 组织为七个框架；本产品工作流只采用其中六个，获客执行类框架列为范围外资产。

### 4.2 纳入产品工作流的六个方法论框架

#### 框架一：变现结构判断法

品类付费意愿决定变现上限；先定 subscription / IAP / ads / hybrid 结构，再定付费和广告时机，最后才做局部优化。

#### 框架二：版本数据分析法

先拆公式归因，再分广告位，最后拆长期指标。典型拆法：

`ARPU ≈ IPU × eCPM`

同时区分广告 ARPU、Total ARPU、留存放大和数据口径。

#### 框架三：品类立项评估法

以“高频 / 高焦虑 / 高损失 + 中部竞品空间 + 自然变现”筛选机会；下载量不是立项结论，收入、集中度、技术天花板和 beachhead 才是。

#### 框架四：审核合规风控法

把 Google Play / App Store 审核视为商业成本和账户资产风险，不把合规当文案附录。

#### 框架五：产品体验验证法

先状态机后方案、先价值后付费、先找漏斗最深的洞；竞品走查采用 quick / standard / deep 三档。

#### 框架六：知识管理法

知识系统服务于决策流：保留原文、结构化沉淀、来源可追溯、记录决策背景，并定期用实际结果复盘。

### 4.3 对工作流的意义

原工作流覆盖了新品分析、PRD、原型和埋点，但没有充分覆盖“已有产品数据诊断”和“知识回流”。因此需要增加：

- `MONETIZATION_DIAGNOSIS`
- `PRODUCT_ITERATION_REVIEW`
- `DECISION_RETRO`

知识回流不能自动执行。只有用户明确说“沉淀、归档、保存、同步”时，才写入知识库或 Notion。

---

## 5. Claude 项目资产

`D:\claude-workspace\projects` 发现 7 个项目：

| 项目 | 可复用部分 | 处理意见 |
|---|---|---|
| `IAA重仓决策论证` | 决策报告、支持证据 + 限制证据、产品组合矩阵、行动时间线 | 只吸收商业化决策结构，不纳入获客执行内容 |
| `docx-reader-teardown` | 竞品广告报告结构、配置 vs 实测、产品启示 | 只吸收报告结构和合法证据规范 |
| `flight-tracker-teardown` | 广告位架构、订阅阶梯、API 成本、待验证清单 | 纳入竞品商业化分析参考 |
| `aitutor-teardown` | AI 成本控制、免费额度、订阅 + 广告、技术栈 | 纳入 AI 产品专项检查 |
| `alldoc-reader-teardown` | 启动流程、现在做/后置/不做 | 纳入竞品路径比较 |
| `claude-obsidian` | 知识库机制 | 只借鉴轻量知识回流，不引入重依赖 |
| `adapty-premium-unlocker` | 付费能力绕过 | 隔离，不进入工作流 |

需要特别说明：部分 teardown 报告包含非公开配置、改包或绕过方法。工作流只能复用其“报告结构、证据分级、配置 vs 实测、待验证”思想，不能把高风险获取手段固化进去。

---

## 6. 历史需求与模板资产

### 6.1 原始《新品 Heart Rate》已找到

原文件：

`C:\Users\simon\Documents\xwechat_files\z837965210_36a6\msg\file\2026-08\新品Heart Rate .pdf`

已验证：

- 20 页；
- 可提取正文；
- 已抽查第 1、10、18、20 页渲染；
- 不是此前找到的 PDF Reader 衍生版；
- 原始结构为 10 个主要章节。

原始 Heart Rate 结构：

1. 行业与市场背景分析；
2. 用户分析；
3. 竞品分析；
4. 产品定位；
5. 产品范围 / 边界；
6. 产品功能框架；
7. 产品功能详述；
8. 产品主要流程；
9. 商业化策略；
10. 预研需求。

它最值得保留的不是章节编号，而是叙事顺序：

> 市场信号 → 用户真实缺口 → 竞品空位 → 一句话定位 → 范围边界 → 功能与流程 → 商业化 → 技术预研。

### 6.2 已验证的需求文档谱系

| 文档 | 结构特点 | 适用阶段 |
|---|---|---|
| 原始 Heart Rate PDF | 10 章，叙事强，定位与商业化判断清晰 | 新品方向与产品定义 |
| `新品需求分析_PDF Reader_V0.3_Heart模板版.md` | Heart 结构在 Android Reader 上的应用，补 Kill Criteria 和最终决策 | 历史回归样本 |
| `新品Printer分析文档.md` | 12 章，补平台政策、信任风险、版本优先级 | 工具型 Android 新品 |
| `新品需求分析-Doc Reader.md` | 0-12 完整结构，补来源、假设、指标、平台差异和 Go/Hold | 当前最完整 T1 母版 |
| `Skill测试-新品需求分析-SharedPetCare.md` | 对完整新品 Skill 的测试样本，含假设台账、Kill Criteria、权限和 Metrics Tree | 主控回归测试样本 |
| `监控品类新品可行性分析报告.md` | 市场/产品/技术/商业化/增长/合规六维可行性 | 立项前 T0 可行性 |
| `新品AI简历需求分析-参考HeartRate写法.md` | 14 章，补 AI 接口、隐私、埋点、研发拆分、验收 | AI 新品分析 + 初步规格 |
| `AI简历MVP研发需求文档.md` | 20 章，页面、接口、AI schema、订阅、埋点、NFR、验收完整 | 独立研发 PRD |
| `Stellara-PRD-v1.0.md` | 内容产品、Design Constitution、CMS、叙事引擎 | 内容/订阅产品 PRD 变体 |

### 6.3 Axure 与原型资产家族

已发现并确认存在以下原型/导出家族：

- iOS Heart Rate 新品；
- Weather 新品；
- Airtag / Bluetooth Finder；
- Smart Printer；
- PDF Reader / Doc Reader / All Docs；
- Heart Rate AI Insight 与数据导出 Demo；
- AI Resume 与其他 Q3 方向文档。

Axure 导出的单页 HTML 是页面状态和历史交互的证据，不应直接当成新品母版。母版应来自原始需求文档，页面级细节再回查 Axure 页面。

### 6.4 竞品分析工作流

原文件：

- `C:\Users\simon\Documents\Q3 OKR\竞品分析通用工作流.md`
- `C:\Users\simon\Documents\xwechat_files\z837965210_36a6\msg\file\2026-07\竞品分析通用工作流.pdf`

PDF 已验证为 9 页，并抽查第 1、7、8 页渲染。其核心是：

1. 定义包名、版本、设备、市场和日期；
2. 商店物料、用户评论、App 实测三路证据；
3. 固定截图分类；
4. 分析首页优先级、核心路径和商业化入口；
5. 记录广告、订阅、评分弹窗的触发时机；
6. 做“商店主推 × 用户需求 × App 内承接”三方一致性校验；
7. 交付前检查截图、Word、结论和证据。

这应独立成为 A2 竞品证据包，不应埋在新品分析正文里。

---

## 7. 现有模板体系为什么需要从 T1-T4 升级

原来的 T1-T4：

- T1 新品需求分析；
- T2 产品框架/版本方案；
- T3 页面/功能 PRD；
- T4 测量与验收。

它能覆盖“想清楚 → 写清楚 → 做原型 → 验收”，但覆盖不了：

- 立项前多维可行性；
- 独立竞品证据包；
- 技术 Spike 和研发仓库文档；
- 文档意图与代码实现的一致性；
- 研发验收、已有产品数据和版本迭代；
- 决策复盘和知识回流。

因此建议改成九类产出物。

---

## 8. 修订后的九类产出物路由

| ID | 产出物 | 主要回答的问题 | 历史参考 |
|---|---|---|---|
| A0 | Opportunity / Feasibility Brief | 这个方向是否值得进入深度分析？ | 监控品类可行性、品类筛选框架 |
| A1 | New Product Analysis | 市场、用户、竞品、定位、MVP、商业化、政策是否成立？ | Heart、Doc Reader、Printer、SharedPetCare |
| A2 | Competitor Evidence Pack | 竞品到底做了什么，证据是什么？ | 竞品分析通用工作流、Android 走查 |
| A3 | Product Strategy & MVP | 这版做什么、不做什么、为什么？ | Heart 范围、Printer 优先级、AI Resume 版本计划 |
| A4 | Development PRD | 页面、接口、状态、异常、NFR 和验收如何定义？ | AI Resume 研发 PRD、Stellara PRD |
| A5 | Prototype & Handoff | 设计稿和研发需求如何一一对应？ | Axure、Lanhu、Home-only 低保真、页面需求写法 |
| A6 | Technical & Shipping Artifacts | 架构、权限、变量、测试和自动化意图如何被记录？ | Spike、shipping-artifacts |
| A7 | Tracking / QA / Acceptance Pack | 如何测量并完成真机和研发交付验收？ | 友盟埋点表、tracking validator、QA |
| A8 | Product Metrics / Monetization / Iteration Pack | 已有真实产品数据时，如何判断留存、核心任务、商业化表现和版本方向？ | 版本数据分析、商业化 claims、产品决策复盘 |

说明：不是每个项目都强制生成九份文档。主控根据当前 Task Type 和 Stage 只生成必要产出物，并在 Manifest 中记录未适用项。

---

## 9. 修订后的生命周期

```text
INTAKE
  ↓
OPPORTUNITY_SCAN
  ↓ G1 Direction Gate
DISCOVERY
  ↓
PRODUCT_DECISION
  ↓ G2 Solution Gate
DEFINITION
  ↓
DESIGN_AND_SPIKE
  ↓ G3 Ready-for-Dev Gate
BUILD
  ↓
IMPLEMENTATION_ACCEPTANCE
  ↓ G4 Delivery Gate
ACCEPTED_HANDOFF
  ↓ 已有真实产品数据时
PRODUCT_OBSERVATION
  ↓ G5 Iteration Gate
CONTINUE / ITERATE / HOLD / RETIRE
  ↓
DECISION_RETRO
```

同时保留异常状态：

- `BLOCKED`
- `NEEDS_EVIDENCE`
- `CONDITIONAL_GO`
- `NO_GO`
- `DEFERRED`

---

## 10. 五道 Gate

### G1：Direction Gate

检查：

- Beachhead 用户是否清晰；
- 痛点是否有行为或数据证据；
- 品类收入、竞争和技术天花板；
- 留存路径和回访场景；
- subscription / IAP / ads / hybrid 是否自然；
- 最高风险假设和 Cheapest Test；
- Google Play / App Store 品类红线。

输出：`GO / CONDITIONAL_GO / HOLD / NO_GO`。

### G2：Solution Gate

检查：

- 一句话定位是否与用户缺口一致；
- MVP 是否收敛；
- 现在必须做 / 可以后置 / 不要做；
- 核心路径、失败路径和状态机；
- 免费/付费边界；
- 商店承诺是否超出产品能力；
- Kill Criteria 是否可执行。

### G3：Ready-for-Dev Gate

检查：

- PRD、页面、原型、接口、状态和 Acceptance Criteria 是否对齐；
- 权限、变量、第三方依赖和隐私数据是否明确；
- 技术 Spike 是否有结果，不只是计划；
- 埋点是否能覆盖目标、漏斗和实验；
- 文档意图是否可映射到实现任务和测试。

### G4：Delivery Gate

检查：

- 功能和关键状态真机验证；
- 埋点 Device Inspector 验收；
- subscription / restore / purchase pending / ads / no-fill；
- 权限、隐私数据、健康/儿童/定位等敏感能力是否符合需求边界；
- 崩溃、性能、兼容性、异常和降级方案；
- PRD、原型、实现、埋点和测试证据是否完成闭环。

### G5：Iteration Gate

检查：

- 产品事件和指标口径是否可信；
- activation、核心任务成功率、retention、Ad ARPU、IAP ARPU 和 Total LTV；
- 留存变化来自产品价值、体验摩擦还是商业化干扰；
- 广告密度、付费墙时机和付费转化是否协调；
- 版本实验的样本量、Guardrail 和停止条件；
- Continue / Iterate / Hold / Retire 的明确判断。

---

## 11. 修订后的 12 个核心专项能力

### 11.1 现有能力，直接接入

1. `overseas-consumer-app-workflow`
2. `android-app-screenshot`
3. `prd-prototype-standard`
4. `prototype-requirement-writer`
5. `lead-review`
6. `tracking-spec-from-prototype`
7. `tracking-implementation-validator`

### 11.2 从 Memory 提升为正式能力

8. `lanhu-prototype-inspection`

### 11.3 从 Claude marketplace 安全迁移

9. `strategy-red-team`
10. `shipping-artifacts`
11. `intended-vs-implemented`

### 11.4 基于现有资产新建或安全改造

12. `android-behavior-validation`
   - 来源：Claude `device-verification` 的合法部分；
   - 只覆盖授权设备、正常功能路径、广告/弹窗/状态验证；
   - 不提供订阅、许可或访问控制绕过。

### 11.5 通用 Skill 池，不固定串联

主控按需调用现有市场、用户、战略、产品增长、本地化、数据、QA、DevOps 等 Skill，但不把 65 个通用 PM Skill 全部写入主路径。ASO 和商店发布相关 Skill 不进入本工作流路由。

---

## 12. Source of Truth 优先级

同一产品可能同时存在 PDF、Markdown、Axure HTML、截图、Excel 和多轮衍生版本。建议统一以下优先级：

1. 用户在当前任务明确指定的文件或版本；
2. 原始正式需求文档 / 已确认版本；
3. 当前产品仓库中的 PRD、代码、Manifest 和验收表；
4. 原始竞品证据：商店页、评论、授权设备实测、原始截图；
5. Axure / Lanhu / Figma 当前版本；
6. 带来源、带日期的知识 claim；
7. 衍生分析稿和助手整理稿；
8. 导出 HTML、临时文件、备份和同步副本。

特殊规则：

- 找到“原报告”时，不用整理版代替；
- 找到“原始 Heart Rate PDF”后，它的历史模板地位高于 PDF Reader 的 Heart 衍生版；
- `codex-sync` 是备份，不是当前 Skill Source of Truth；
- 动态平台规则、市场数据和商业化配置必须重新验证；
- Mock、静态检查、真机和线上生产数据是不同证据等级。

---

## 13. Evidence Level

| Level | 含义 | 可以支持的结论 |
|---|---|---|
| E0 | 想法/假设 | 只能进入假设台账 |
| E1 | 二手资料/历史经验 | 方向参考，不能作为当前事实 |
| E2 | 原始文档、官方页面、商店物料、代码静态证据 | 可以支持结构性判断 |
| E3 | 本地原型、静态测试、Mock、构建检查 | 可以支持设计和本地行为判断 |
| E4 | 授权真机 / 模拟器实际运行与设备工具证据 | 可以支持实现验收 |
| E5 | 线上真实 API、商店审核或生产数据 | 可以支持上线与版本迭代决策 |

所有 Gate 都必须声明当前最高证据级别和仍缺的证据。

---

## 14. Manifest 应增加的字段

```yaml
project: 产品名称
platform_priority:
  - Android / Google Play
  - iOS / App Store

current_stage: DISCOVERY
task_type: NEW_PRODUCT_FULL
artifact_route:
  - A1
  - A2
current_gate: G1
gate_status: CONDITIONAL_GO

source_of_truth:
  primary: path-or-url
  supporting: []
  derived: []
  stale_or_backup: []

evidence:
  highest_level: E2
  verified: []
  inferred: []
  missing: []

assumptions:
  load_bearing: []
  cheapest_tests: []
  kill_criteria: []

scope:
  must: []
  later: []
  do_not: []

commercialization:
  model: ads | subscription | iap | hybrid
  value_proof_before_paywall: true
  region_notes: []

release:
  policy_risks: []
  tracking_status: NOT_RUN
  device_status: NOT_RUN

product_iteration:
  metric_status: NOT_RUN
  target_metric: null
  guardrails: []
  decision: null

knowledge_capture:
  authorized: false
  destination: null

next_actions: []
```

---

## 15. 风险隔离清单

以下内容不得进入正式工作流：

- 修改竞品订阅状态、premium getter 或 entitlement；
- 绕过 Google Play 许可校验、签名校验或访问控制；
- 为体验付费功能而对第三方 App 打补丁；
- 未经授权提取或复用第三方私有配置；
- 把“在本地能绕过”当成产品可行性或商业竞争力；
- 将 Claude 旧规则中“先忽略合规风险”作为主控默认行为。

可以保留的合法方法：

- split APK 形态识别和正常安装诊断；
- 公开 SDK 与 Manifest 结构识别；
- 授权设备上的正常 UI/行为测试；
- 商店、评论、公开政策、公开价格和用户可见流程；
- 截图、logcat、Device Inspector、代码和文档之间的证据对照；
- 对自有 App 或明确授权测试包做安全与实现验证。

---

## 16. 工作流搭建顺序修订

### V0.1：先建立资产注册表和路由骨架

必须创建：

- 主控 `SKILL.md`；
- `asset-registry.md`；
- `task-and-stage-routing.md`；
- `artifact-router.md`；
- `stage-gates.md`；
- `evidence-levels.md`；
- `workflow-manifest-template.md`；
- `source-authority.md`；
- `safety-boundaries.md`。

V0.1 不复制 65 个通用 Skill，也不做复杂脚本。

### V0.2：接入和补齐核心能力

1. 接入现有 7 个专项 Skill；
2. 整理并提升 `lanhu-prototype-inspection`；
3. 安全迁移 `strategy-red-team`；
4. 安全迁移 `shipping-artifacts`；
5. 安全迁移 `intended-vs-implemented`；
6. 新建安全版 `android-behavior-validation`。

### V0.3：历史回归测试

至少跑以下 8 组：

1. 原始 Heart Rate：检查 A1 和 G1/G2；
2. Doc Reader：检查完整新品流程和 Android/iOS 分流；
3. Printer：检查政策、信任、广告和版本优先级；
4. SharedPetCare：检查假设、Kill Criteria 和完整母版；
5. AI Resume：检查 A1 与 A4 分离、AI schema、隐私和接口；
6. 竞品分析通用工作流：检查 A2 证据包；
7. tracking spec → device acceptance：检查 A7；
8. 已有产品数据 + 商业化决策：检查 A8 和 G5。

### V1.0：真实项目正向验证

选择一个新 Android 产品，从 `INTAKE` 跑到 `ACCEPTED_HANDOFF`，至少产生：

- A0 或 A1；
- A2；
- A3；
- A4/A5；
- A6；
- A7；
- A8 仅在已有真实产品数据时验证，不作为新项目研发交付的必选项。

只有走过一个真实项目，才能把工作流标记为 V1.0。

---

## 17. 验收标准

工作流完成后必须满足：

1. 能判断窄任务，不强制升级为新品全流程；
2. 能区分原始文件、当前版本、衍生稿、证据、备份；
3. 能从 Heart、Printer、Reader、AI Resume 等模板中选择正确结构；
4. 每个结论标明事实、推断、假设和证据等级；
5. 每道 Gate 有 Pass/Conditional/Hold/No-Go 结果；
6. PRD/原型/接口/埋点/测试/代码可以建立追踪关系；
7. 不把静态检查说成真机或线上验证；
8. 不接入 bypass 类能力；
9. 不自动写 Notion、知识库或 GitHub；
10. 在用户提供真实产品数据时，能输出留存、核心任务、商业化表现和 Continue/Iterate/Hold/Retire 判断；
11. 历史 8 组回归提示词均能路由到正确产出物和 Skill；
12. 用户接手时只读 Manifest 就能知道当前阶段、Source of Truth、阻断项和下一步。

---

## 18. 当前明确缺口

### 现在必须补

- 主控生命周期 Skill；
- 资产注册表与 Source of Truth 规则；
- A0-A8 Artifact Router；
- G1-G5 Gate；
- `strategy-red-team`；
- `shipping-artifacts`；
- `intended-vs-implemented`；
- 安全版真机行为验证；
- 已有产品指标与商业化诊断；
- 历史回归测试集。

### 可以后置

- 自动生成 Word/PDF；
- 自动打包评审材料；
- 自动生成项目仪表盘；
- 自动对接 GitHub Issue；
- 用户明确授权后的 Notion/Obsidian 同步；
- 跨模型 Second Opinion。

### 不要做

- 把全部 110 个 Skill 写进一个超级 Prompt；
- 复制 Claude 的 bypass Skill；
- 让所有任务默认多 Agent 并行；
- 把旧备份覆盖当前 Skill；
- 把 704 个命中文件平铺成“资产清单”而不去重和分级。

---

## 19. 附录 A：Codex 当前 110 个 Skill 入口

```text
.system/imagegen
.system/openai-docs
.system/plugin-creator
.system/review-agent
.system/skill-creator
.system/skill-installer
ab-test-analysis
analyze-feature-requests
android-app-screenshot
ansoff-matrix
apple-hig-designer
aso-copy
backend-developer
beachhead-segment
brainstorm-experiments-existing
brainstorm-experiments-new
brainstorm-ideas-existing
brainstorm-ideas-new
brainstorm-okrs
business-model
cohort-analysis
competitive-battlecard
competitor-analysis
content-strategist
create-prd
customer-journey-map
data-analyst
design-director
devops-engineer
dingtalk-aisearch
dingtalk-aitable
dingtalk-calendar
dingtalk-chat
dingtalk-contact
dingtalk-doc
dingtalk-drive
dingtalk-event
dingtalk-mail
dingtalk-minutes
dingtalk-misc
dingtalk-misc/references
dingtalk-shared
dingtalk-todo
dingtalk-wiki
draft-nda
dummy-dataset
frontend-design
frontend-developer
grammar-check
growth-loops
growth-strategist
gtm-motions
gtm-strategy
ideal-customer-profile
identify-assumptions-existing
identify-assumptions-new
interview-script
job-stories
lead-review
lean-canvas
localization-specialist
market-researcher
market-segments
market-sizing
marketing-ideas
metrics-dashboard
monetization-strategy
north-star-metric
opportunity-solution-tree
outcome-roadmap
overseas-consumer-app-workflow
pdf
pestle-analysis
porters-five-forces
positioning-ideas
prd-prototype-standard
pre-mortem
pricing-strategy
prioritization-frameworks
prioritize-assumptions
prioritize-features
privacy-policy
product-name
product-strategy
product-vision
prompt-builder
prototype-requirement-writer
qa-engineer
release-notes
retro
review-resume
sentiment-analysis
sprint-plan
sql-queries
stakeholder-map
startup-canvas
summarize-interview
summarize-meeting
swot-analysis
tech-architect
test-scenarios
tracking-implementation-validator
tracking-spec-from-prototype
umeng-cli/umeng-cli
user-personas
user-segmentation
user-stories
value-prop-statements
value-proposition
wwas
```

说明：`dingtalk-misc/references` 也包含一个 `SKILL.md`，因此按入口文件计数时被计入 110。

---

## 20. 附录 B：Claude 用户级 29 个 Skill 入口

```text
ad-strategy-teardown
adapty-subscription-bypass
android-app-screenshot
apk-install-bypass
apple-hig-designer
aso-copy
device-verification
dingtalk-aisearch
dingtalk-aitable
dingtalk-calendar
dingtalk-chat
dingtalk-contact
dingtalk-doc
dingtalk-drive
dingtalk-event
dingtalk-mail
dingtalk-minutes
dingtalk-misc
dingtalk-misc/references
dingtalk-shared
dingtalk-todo
dingtalk-wiki
excel
ppt
premium-bypass
prompt-builder
prototype-requirement-writer
serenity-skill
umeng-cli/umeng-cli
```

---

## 21. 最终建议

这次盘点后，工作流的核心已经更清楚：

> 它不是“新品 PRD 生成器”，而是一套从机会识别、证据采集、方向决策、需求与原型、研发实现、真机验收，到产品数据诊断和决策复盘的产品操作系统。

下一步不应继续追加盘点文档，而应进入 V0.1 实施：先创建主控 Skill 的资产注册表、A0-A8 路由、G1-G5 门禁、Manifest 和安全边界；然后再迁移 3 个 Claude 高价值 Skill，并补安全版真机验证。
