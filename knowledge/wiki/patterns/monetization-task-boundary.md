---
id: pattern-monetization-task-boundary
type: pattern
domain: monetization
stage: product-definition
platform: [android, ios]
region: [global]
evidence_level: project-validated
status: active
source:
  - source-historical-workflow-v1
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [广告, 订阅, 核心任务]
---

# 商业化不能破坏核心任务

商业化方式必须匹配价值频率。广告优先出现在任务之间，而不是任务之中；读取、测量、保存、恢复等核心任务不能被无关全屏流程破坏。

订阅状态、购买历史和 Trial 资格必须分开判断。支付失败、恢复失败、广告 No Fill 或超时，都应回到用户原来的任务，而不是形成死路。
