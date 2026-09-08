---
id: case-pdf-reader-product-boundary
type: case
domain: product-boundary
product: pdf-reader
stage: product-definition
platform: [android]
region: [global]
evidence_level: project-validated
status: active
source:
  - source-pdf-reader-heart-template
reviewed_at: 2026-09-08
expires_at:
supersedes: []
tags: [PDF Reader, Reader-first, Android, 文件权限]
---

# PDF Reader 的产品边界

产品边界应由用户任务深度决定，而不是由支持的文件格式数量决定。V0 采用 Reader-first：优先打通“文件 → 可读页面 → 可重复继续阅读”的核心循环，不把文件管理器、扫描器和复杂编辑器全部塞进首版。

Android 外部 PDF 打开使用 `ACTION_VIEW`；主动选取文件优先使用 SAF `ACTION_OPEN_DOCUMENT` 并持久化 URI 权限，不默认申请 `MANAGE_EXTERNAL_STORAGE`。外部打开必须保留原始 Intent/URI 并直接进入 Reader。
