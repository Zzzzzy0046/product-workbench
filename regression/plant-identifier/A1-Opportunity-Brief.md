# A1 Opportunity Brief — Plant Rescue AI

日期：2026-09-09

## 0. 结论

- 一句话判断：**通用植物识别不值得做；“症状分诊 → 安全行动 → 复查验证”的室内植物救治闭环值得做低成本验证，但现在不能立项。**
- G1：`HOLD`。
- 最大不确定性：真实家庭照片下能否稳定给出安全、可解释、比通用 AI 更有行动价值的建议，以及用户是否会自然回来复查。
- 下一步最小验证：15 次问题访谈 + 20 人两周 Concierge Test + 100 张真实用户照片 Spike。

## 1. 市场与区域

### 品类判断

- `[事实]` PictureThis 在 Google Play 显示 50M+ 下载、约 79 万条评价，并覆盖识别、病害、养护和专家咨询；Plant Parent 显示 10M+ 下载、约 11 万条评价，并覆盖提醒、病害、识别和植物档案；PlantNet 也达到 10M+ 下载和约 26 万条评价。[PictureThis](https://play.google.com/store/apps/details?id=cn.danatech.xingseus)、[Plant Parent](https://play.google.com/store/apps/details?id=com.plantparentai.app)、[PlantNet](https://play.google.com/store/apps/details?id=org.plantnet)
- `[推断]` 这是已有强需求、强头部和完整功能套件的成熟品类，不是蓝海。把“识别 + 养护 + 提醒 + 病害”再做一遍，没有可感知差异。
- `[事实]` PictureThis 的美国 App Store 页面列出多档 IAP，其中多项 PictureThis Pro 标价 39.99 美元；页面没有把每一项周期完整映射出来，因此这里只把它作为付费存在性的方向性证据，不能代替 Android 价格与真实转化验证。[PictureThis App Store](https://apps.apple.com/us/app/picturethis-plant-identifier/id1252497129)
- `[事实]` Google Play 用户评论已经直接把付费产品与 Gemini 等通用 AI 比较，说明单次识别和泛化建议正在被替代。[PictureThis Google Play reviews](https://play.google.com/store/apps/details?hl=it&id=cn.danatech.xingseus)

### 区域选择

- `[决策]` 第一轮验证只选美国英语 Android 用户，原因是当前有明确的头部产品、付费价格锚点和大量公开评论可验证问题；这不等于已经证明美国是最终最优市场。
- `[假设]` 欧洲更敏感于图片上传、删除和订阅透明度；东南亚、拉美可能更看重本地物种覆盖且价格敏感；中东可能更看重高温、光照和浇水情境。以上差异没有当前一手证据，不进入 G1 通过项。

## 2. 用户与问题

### Beachhead

- 具体用户：管理多盆室内植物的 Android 用户；植物出现黄叶、斑点、萎蔫、虫害或生长异常时，需要立即知道“先做什么、不要做什么、何时复查”。
- 触发场景：看到异常后拍照，已经搜索过但得到互相矛盾的浇水、光照、施肥或病害建议。
- 当前替代方案：PictureThis、Plant Parent、PlantNet、Google Lens/Gemini、搜索、Reddit/论坛、花店人员或园艺师。

### 问题证据

- `[事实]` Plant Parent 评论出现健康植物被判病、病株被判健康、信息过于简单和缺少具体处理建议的问题。[Plant Parent reviews](https://play.google.com/store/apps/details?id=com.plantparentai.app)
- `[事实]` 2026 年评论出现自动浇水节奏导致土壤长真菌、病害状态被误判，以及换机后植物与历史记录丢失的问题。[Plant Parent France](https://play.google.com/store/apps/details?hl=fr&id=com.plantparentai.app)、[Plant Parent Romania](https://play.google.com/store/apps/details?hl=ro&id=com.plantparentai.app)
- `[事实]` PictureThis 评论集中出现首次体验被订阅弹窗打断、试用/扣费不透明、免费结果只有“植物生病了”却不给行动建议的问题。[PictureThis reviews](https://play.google.com/store/apps/details?hl=it&id=cn.danatech.xingseus)、[PictureThis subscription review](https://play.google.com/store/apps/details?hl=hr&id=cn.danatech.xingseus)
- `[推断]` 用户核心痛点不是“完全不知道这是什么植物”，而是“不相信结果、不知道下一步、无法确认措施是否有效”。

## 3. 价值循环

- 为什么现在下载：一盆植物正在出现可见异常，用户担心继续操作会加重问题。
- 第一次价值：90 秒内完成拍照引导，返回 2–3 个可能原因、置信度、立即行动、明确禁忌和复查时间。
- 低置信度处理：要求补拍叶片正反面、土壤和整株；仍不足时只做风险分层，不输出确定性病名或治疗承诺。
- 为什么回来：3 天或 7 天后上传复查照片，比较变化并调整方案；新的异常继续沉淀到同一植物档案。
- 留存判断：提醒只在用户完成首次方案并主动设定复查后申请；通知拒绝不影响核心功能。是否形成自然复访必须通过两周 Concierge Test 验证。

## 4. 商业化与约束

### 商业化判断

- `[决策]` MVP 不使用强制年度订阅墙，也不在首次分析前要求试用。
- 推荐顺序：首次救治免费 → 完成一次复查后展示透明方案 → 若持续复查与档案价值成立，再测试 Subscription。
- 如果用户只购买单次问题解决，应改为 IAP 救治包，不得把一次性价值包装为订阅。
- MVP 不加入广告；后续即使验证 Ads，也不能出现在拍照、分析、结果、行动清单和复查中。
- `[事实]` Google Play 要求订阅提供持续或重复价值，并清楚披露周期、自动续费、试用转付费和取消方式。[Google Play Subscriptions policy](https://support.google.com/googleplay/android-developer/answer/9900533)

### 技术与政策前置

- `[事实]` Pl@ntNet API 能返回按置信度排序的候选物种，支持同一植物最多 5 张图片；官方同时说明性能会随物种训练样本和输入图片质量变化。[Pl@ntNet API](https://my.plantnet.org/doc/api/identify)、[Pl@ntNet introduction](https://my.plantnet.org/doc/getting-started/introduction)
- `[风险]` 物种识别能力不能证明病害或护理建议可靠。研究显示实验室数据在真实光线、背景、遮挡和视角变化下存在 domain shift，因此必须校准不确定性并在真实用户图片上测试。[Scientific Reports 2026](https://www.nature.com/articles/s41598-026-55107-6)
- App 内自建相机需要 `CAMERA`；若仅调用系统相机 Intent 可不申请该权限。从图库偶发选图使用系统 Photo Picker，不申请广泛 `READ_MEDIA_IMAGES`。[Android Camera](https://developer.android.com/media/camera/camera-intents)、[Google Play Photo and Video Permissions](https://support.google.com/googleplay/android-developer/answer/14115180?hl=en-CA)
- Android 13+ 的养护提醒需要 `POST_NOTIFICATIONS`，应在用户主动创建第一次复查提醒时再按场景申请。[Android notification permission](https://developer.android.com/develop/ui/compose/notifications/notification-permission)
- 必须在上传前说明图片用途、是否保存、保留时间、第三方处理方、是否用于训练和删除方式；位置元数据默认不上传。

## 5. MVP 候选边界

### 现在验证

1. 引导拍摄整株、异常区域、叶片正反面和土壤。
2. 用户确认物种或从 Top 3 候选中选择。
3. 输出可能原因排序、置信度、安全行动和“不要做什么”。
4. 保存一盆植物、一份行动方案和一次复查时间。
5. 复查照片对比，记录改善/恶化/无变化并调整下一步。

### 不做

- 通用植物百科、社区 Feed、AR、专家 24/7 聊天。
- 农作物生产、农药处方或有保证的病害治疗。
- 自动读取整个相册、强制位置权限、默认开启通知。
- 无置信度的确定性诊断。
- 首次结果前 Paywall、隐藏试用条款或一次性价值订阅化。

## 6. G1 Opportunity Gate

### 已有证据

- 品类需求和付费存在性：通过头部下载、评价和 IAP 价格获得方向性支持。
- 当前用户抱怨：误判、泛化建议、过度浇水、历史丢失和激进订阅存在公开证据。
- 技术可行性：物种识别 API 可用，但症状分诊和安全建议尚未证明。
- 政策路径：相机、Photo Picker、通知和订阅均有可执行的最小权限方案。

### 缺失证据与通过阈值

1. 问题访谈：15 名目标用户中，至少 10 名在过去 90 天有植物异常事件，至少 8 名使用过两种以上信息源仍不确定下一步。
2. 首次价值：10 名可用性测试用户中至少 8 名在 90 秒内正确理解行动和置信度；0 人把低置信度结果理解为确定诊断。
3. 复访：20 人两周 Concierge Test 中，至少 8 人按计划完成一次主动复查，至少 5 人完成第二次复查；不是只靠通知点击。
4. 技术 Spike：100 张真实家庭环境照片中，物种 Top 3 接受率 ≥85%；60 个有参考答案的症状案例中，园艺审核认为安全下一步可接受率 ≥80%；危险建议为 0；低置信度 fallback 召回 ≥95%。
5. 商业化：第二次成功复查后展示完整价格与取消信息，至少 15% 用户进入购买确认页；正式定价另行验证。

### Gate 记录

- 结果：`HOLD`。
- 通过项：成熟需求信号、明确问题线索、可描述的首次价值、候选复查循环、最小权限路径。
- 未通过项：直接用户证据、真实复访、症状安全性、模型成本与 Android 真实价格意愿。
- Owner：PM、ML/Backend、Android。
- 返回阶段：`OPPORTUNITY`。
- 下一步最小动作：完成上述三项验证包，不写 A3/A4。
- Kill Criteria：通用 AI 已足够满足目标任务；安全建议不能达到阈值；复查率低于 25%；或用户只愿为单次识别付费但单位经济性不成立。
