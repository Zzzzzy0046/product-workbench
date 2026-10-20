"""Stable paths, limits, statuses and fast-workflow source boundaries."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "workbench"
MAX_FILE = 12 * 1024 * 1024
MAX_PACKAGE = 200 * 1024 * 1024
MAX_TEXT = 2_000_000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MATERIAL_CATEGORIES = {
    "competitor": "竞品资料",
    "reviews": "评论数据",
    "images": "截图与图片",
    "policy": "政策与合规",
    "technical": "技术与日志",
    "research": "研究资料",
    "deliverable": "交付物",
    "other": "其他资料",
}
IMAGE_SUBCATEGORIES = {
    "competitor": "竞品截图",
    "prototype": "产品与原型",
    "data": "数据与报表",
    "policy": "政策与规则",
    "feedback": "用户反馈",
    "reference": "参考与素材",
    "other": "其他图片",
}
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
FAST_F1_SECTION_TASKS = (
    "fast/f1-category-user",
    "fast/f1-competitor-differences",
    "fast/f1-positioning-scope",
    "fast/f1-product-solution",
    "fast/f1-flow-monetization",
)
FAST_F1_TASKS = {"fast/new-product-analysis", *FAST_F1_SECTION_TASKS}


def infer_material_category(name, kind="upload"):
    """Choose a useful default category without asking users to pre-sort files."""
    filename = str(name or "").strip()
    lowered = filename.casefold()
    suffix = Path(filename).suffix.casefold()
    document_kind = str(kind or "upload").strip().lower()
    if document_kind in {"accepted", "deliverable"}:
        return "deliverable"
    if filename.startswith("竞品评论-") or "review" in lowered or "评论" in filename:
        return "reviews"
    if suffix in IMAGE_SUFFIXES:
        return "images"
    if filename.startswith("竞品商店信息-") or "竞品" in filename or "competitor" in lowered:
        return "competitor"
    if any(term in lowered for term in ("policy", "privacy", "terms", "compliance")) or any(term in filename for term in ("政策", "合规", "隐私", "条款", "规则")):
        return "policy"
    if any(term in lowered for term in ("log", "crash", "api", "technical")) or any(term in filename for term in ("日志", "崩溃", "技术", "接口")):
        return "technical"
    if any(term in lowered for term in ("research", "report", "market")) or any(term in filename for term in ("研究", "调研", "报告", "市场")):
        return "research"
    return "other"


def infer_image_subcategory(name, category="images"):
    """Infer a second-level image bucket while keeping screenshots in one main library category."""
    if str(category or "").strip().lower() != "images":
        return ""
    filename = str(name or "").strip()
    lowered = filename.casefold()
    if filename.startswith("竞品截图-") or "竞品" in filename or "competitor" in lowered:
        return "competitor"
    if any(term in lowered for term in ("prototype", "figma", "axure", "wireframe", "mockup")) or any(term in filename for term in ("原型", "蓝湖", "页面", "界面")):
        return "prototype"
    if any(term in lowered for term in ("dashboard", "analytics", "chart", "ga4", "firebase", "umeng")) or any(term in filename for term in ("数据", "报表", "图表", "漏斗", "友盟")):
        return "data"
    if any(term in lowered for term in ("policy", "compliance", "play console", "app store connect")) or any(term in filename for term in ("政策", "规则", "审核", "拒审", "合规")):
        return "policy"
    if any(term in lowered for term in ("feedback", "review", "comment", "support")) or any(term in filename for term in ("用户反馈", "评论", "客服")):
        return "feedback"
    if any(term in lowered for term in ("reference", "inspiration", "asset")) or any(term in filename for term in ("参考", "灵感", "素材")):
        return "reference"
    return "other"
# Automatically retrieved confirmed deliverables may only flow to their direct
# downstream task. Users can still pin another current-project document
# explicitly when they intentionally want to override this default boundary.
FAST_ACCEPTED_UPSTREAM_TASKS = {
    "fast/f1-competitor-differences": {"fast/f1-category-user"},
    "fast/f1-positioning-scope": {
        "fast/f1-category-user",
        "fast/f1-competitor-differences",
    },
    "fast/f1-product-solution": {"fast/f1-positioning-scope"},
    "fast/f1-flow-monetization": {
        "fast/f1-positioning-scope",
        "fast/f1-product-solution",
    },
    "fast/core-prd": {"fast/new-product-analysis", "fast/version-brief"},
    "fast/tracking-spec": {"fast/core-prd"},
    "fast/acceptance": {"fast/core-prd", "fast/tracking-spec"},
}
