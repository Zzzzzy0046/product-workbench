# A0 Project Manifest — Plant Rescue AI 跨品类回归

## 项目身份

- 项目：Plant Rescue AI（工作名）
- 一句话方向：帮助英语区 Android 室内植物用户，把“植物看起来不对劲”转化为带置信度的可能原因、立即行动和后续复查，而不是再做一个通用植物识别器
- 工作流模式：Full New Product / Third-category Regression
- 目标平台：Android / Google Play first；iOS secondary
- 候选 Beachhead：美国英语用户；管理多盆室内植物、出现黄叶、斑点、萎蔫或虫害迹象时缺少可靠行动方案
- 当前授权范围：机会、用户、竞品、定位候选、商业化、政策、技术预研和 Gate；排除付费投放、ASO、商店素材和商店发布执行

## 当前状态

- 当前阶段：`OPPORTUNITY`
- 最新 Gate：`G1 = HOLD`（2026-09-09）
- 一句话判断：品类需求和付费信号成立，但“通用识别”已高度饱和；只有“低置信度可解释的植物救治与复查闭环”值得继续验证，当前缺少直接用户证据和真实照片技术 Spike
- 下一步最小动作：用 15 次问题访谈、20 人两周 Concierge Test 和 100 张真实用户照片完成一页 Evidence Refresh，再重过 G1

## Source of Truth

1. 当前用户要求与本次回归范围。
2. 2026-09-09 可核验的 Google Play、Android、Google Play Policy、Pl@ntNet API 和研究论文。
3. Product KB 当前结构化方法与模板：`method-new-product-analysis`、`method-workflow-gates`、`template-a0-project-manifest`、`template-a1-opportunity-brief`、`decision-workflow-scope-2026-09-08`。
4. PDF Reader 与 Heart Rate 仅是弱相似历史案例，只迁移收敛方法和风险写法，不迁移产品结论。

## A1–A7 状态

| 编号 | 交付物 | 状态 | 当前证据等级 | 说明 |
|---|---|---|---|---|
| A1 | Opportunity Brief | Review | Current public sources + inference | 已完成桌面研究；用户与技术证据待验证 |
| A2 | Competitor Evidence Pack | Draft | Current store listings and reviews | 已覆盖 3 个主要竞品，未做获授权实机走查 |
| A3 | Product Definition | Missing | Not verified | G1 通过前不进入 |
| A4 | PRD | Missing | Not verified | 不提前写功能需求 |
| A5 | Prototype Handoff | Missing | Not verified | 只允许做用于验证的低保真测试材料 |
| A6 | Risk & Decision Log | Draft | Current workflow | 核心风险已记录在 A0/A1 |
| A7 | Tracking / QA / Acceptance | Missing | Not verified | 尚未进入 Build |

## 决策、假设与冲突

- `[决策]` 不做通用 Plant Identifier；候选楔子收窄为室内植物症状分诊、行动方案和复查。
- `[决策]` 结果必须给出置信度和替代原因；低置信度时要求补拍或明确建议线下求助，不给确定性“诊断”。
- `[决策]` MVP 不在首次结果前展示订阅墙，不在拍照、分析、结果和复查路径中插广告。
- `[假设]` 用户愿意为纵向植物档案、复查和持续指导付费，而不是只为一次识别付费。
- `[风险]` 真实家庭环境中的光线、背景、植物物种和症状存在 domain shift，模型可能给出危险或过度自信的建议。
- `[风险]` 通用视觉 AI 正在把单次识别商品化，单纯“拍照识别”缺少可持续差异。
- `[冲突]` 历史案例的 Reader-first、健康订阅和平台结论均不适用于本品类；仅复用“先收窄核心任务”和“先证据后 PRD”的方法。

## 阻断、负责人和重审条件

- 用户问题证据：PM；完成 15 次近期真实问题访谈。
- 复访闭环证据：PM/Design；完成 20 人两周 Concierge Test。
- 准确率与安全：ML/Backend；完成 100 张真实照片的识别与症状分诊 Spike。
- Android 权限与提醒：Android；验证 Camera、Photo Picker、通知拒绝和无权限回退。
- 商业化：PM；确认用户在第二次成功复查后对透明价格方案的真实行为，而不是口头意愿。
- 返回阶段：`OPPORTUNITY`。
- 重审条件：A1 中的验证阈值全部有真实结果。
- Kill trigger：救治建议无法安全校准、两周内没有自然复查行为，或用户只需要可被通用 AI 免费替代的一次性识别。

最后更新：2026-09-09
