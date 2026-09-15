"""Stable paths, limits, statuses and fast-workflow source boundaries."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "workbench"
MAX_FILE = 12 * 1024 * 1024
MAX_PACKAGE = 200 * 1024 * 1024
MAX_TEXT = 2_000_000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
REVIEW_SCRAPER_CONFIG_KEY = "integration:review-scraper"
SCRAPE_STATUSES = {"queued", "running", "ready", "completed", "empty", "failed", "cancelled"}
TOOLS = [
    {"id":"document-parser", "name":"资料解析", "status":"ready", "description":"MD、TXT、CSV、JSON、文本 PDF、DOCX 与 PNG/JPG/WEBP 截图；扫描 PDF 需先 OCR。"},
    {"id":"project-search", "name":"项目资料检索", "status":"ready", "description":"项目隔离 Hybrid RAG；不可用时自动回退关键词检索。"},
    {"id":"knowledge-search", "name":"方法与模板检索", "status":"ready", "description":"组合全局只读 Product KB，为项目证据补充方法和模板。"},
    {"id":"codex", "name":"Codex 生成引擎", "status":"ready", "description":"通过本机已登录的 Codex CLI 执行，使用本机默认模型；实际就绪状态见运行环境。"},
    {"id":"review-scraper", "name":"竞品资料采集器", "status":"ready", "description":"用户指定竞品后，复用桌面工具环境采集商店长短描述、宣传截图和原始评论；不调用分析、翻译或 AI。"},
    {"id":"lanhu-mcp", "name":"蓝湖 MCP 原型读取", "status":"manual", "description":"通过当前会话的 Lanhu MCP 只读页面与状态，再将脱敏快照导入项目；工作台不保存 Cookie 或 Token。"},
]
LANHU_CONFIG_KEY = "integration:lanhu"
LANHU_PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9_.@/-]+$")
ID_PATTERN = re.compile(r"^[a-f0-9]{16,64}$")

WORKFLOW_MODES = {"fast", "full"}
PRODUCT_VERSION_TYPES = {"new-product", "feature", "experience", "monetization", "bugfix"}
PRODUCT_VERSION_STATUSES = {"planning", "developing", "testing", "released", "reviewed", "archived"}
CONDITION_STATUSES = {"open", "in_progress", "waiting_evidence", "closed", "waived"}
BLOCK_LEVELS = {"development", "internal-test", "external-release", "non-blocking"}
COMMENT_ACTIONS = {"add", "modify", "delete", "compress", "preserve"}
COMMENT_STATUSES = {"open", "resolved"}
COMMENT_BLOCK_TYPES = {"heading", "paragraph", "blockquote", "table", "code"}
RESTORABLE_JOB_STATUSES = {"cancelled", "failed", "interrupted"}
MANAGED_FRONTMATTER_FIELDS = {"status", "reviewed_at"}
FAST_EXCLUDED_KNOWLEDGE_IDS = {
    "method-evidence-status",
    "method-workflow-gates",
    "source-historical-workflow-v1",
    "source-workflow-implementation-v1",
    "source-workflow-inventory-v2",
    "template-t1-new-product-analysis",
    "template-t2-product-framework-version-plan",
    "template-t3-prd-prototype-handoff",
    "template-t4-tracking-qa-acceptance",
    "template-t4-acceptance-run",
    "template-a0-project-manifest",
    "template-a1-opportunity-brief",
    "template-a2-competitor-evidence-pack",
    "template-a3-product-definition",
    "template-a4-prd",
    "template-a5-prototype-handoff",
    "template-a6-risk-decision-log",
    "template-a7-tracking-qa-acceptance",
}
# Fast F1 may use the current writing method and Heart Rate structure as
# guidance, but historical product pages and example decisions must never be
# treated as facts for a new product.  Keep this allow-list deliberately small.
FAST_F1_METHOD_KNOWLEDGE_IDS = {
    "method-new-product-analysis",
    "template-f1-new-product-analysis",
    "case-heart-rate-template-evolution",
}
# Automatically retrieved confirmed deliverables may only flow to their direct
# downstream task. Users can still pin another current-project document
# explicitly when they intentionally want to override this default boundary.
FAST_ACCEPTED_UPSTREAM_TASKS = {
    "fast/core-prd": {"fast/new-product-analysis", "fast/version-brief"},
    "fast/tracking-spec": {"fast/core-prd"},
    "fast/acceptance": {"fast/core-prd", "fast/tracking-spec"},
}
