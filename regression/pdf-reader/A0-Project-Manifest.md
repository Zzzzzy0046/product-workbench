# A0 Project Manifest — PDF Reader 跨品类回归

## 项目身份

- 项目：PDF Reader
- 一句话方向：以 Android-first、Reader-first 为历史候选方向，验证“文件 → 可读页面 → 可重复继续阅读”的单文件深度阅读闭环
- 工作流模式：Resume Existing Project
- Agent 模型：使用任务当前默认模型，不锁定特定型号
- 候选区域：历史材料为 Global；当前 Beachhead 未确认

## 当前状态

- 当前阶段：`OPPORTUNITY`
- 最新 Gate：`G1 = HOLD`（2026-09-09）
- 原因：历史方案、需求和原型存在，但当前市场、用户、竞品、价格、政策和技术可行性证据未刷新
- 下一步最小动作：完成一页 A1 Evidence Refresh 后重新过 G1

## A1–A7 状态

| 编号 | 交付物 | 状态 | 当前证据等级 | 说明 |
|---|---|---|---|---|
| A1 | Opportunity Brief | Review | Historical project document | 当前证据待刷新 |
| A2 | Competitor Evidence Pack | Review | Historical static evidence | 当前商店页与获授权实机证据待刷新 |
| A3 | Product Definition | Review | Historical candidate | Reader-first 可作为假设，不是当前验证 |
| A4 | PRD | Draft | Static document | 未新增或扩写 |
| A5 | Prototype Handoff | Draft | Static prototype | 无当前用户测试证据 |
| A6 | Risk & Decision Log | Missing | Not verified | 风险散落在历史材料中 |
| A7 | Tracking / QA / Acceptance | Missing | Not verified | 无构建、真机、埋点或验收证据 |

## Source of Truth 与冲突

1. 当前用户授权与本次回归范围。
2. 当前可核验文件存在性和 Product KB MCP 返回。
3. 历史项目材料与决策，仅作候选或类比。
4. 通用方法和模板。

历史材料中的 Google Play listing 测试与当前“排除投放、ASO 和商店发布执行”冲突，状态记为 `Not Applicable`，不进入执行队列。

## 阻断与重审条件

- 阻断：Beachhead 用户与区域、当前问题成本、市场窗口、竞品体验、价格/变现、政策与最小技术 Spike 证据不足。
- 重审：上述证据带来源、日期、区域、平台和证据等级后重新进入 G1。
- Kill trigger：仍找不到高频重复任务、可感知差异或自然变现路径，或文件入口/渲染出现不可接受的平台限制。

最后更新：2026-09-09
