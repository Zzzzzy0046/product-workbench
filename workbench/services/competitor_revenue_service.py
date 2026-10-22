"""Source-linked, manually recorded competitor revenue; no paid API calls."""

from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs, unquote

from workbench.core.runtime import *
from workbench.services.base import BoundService


class CompetitorRevenueService(BoundService):
    TYPES = {"iap": "订阅 / IAP", "ads": "广告收入", "combined": "合计（来源明确包含广告）", "paid_download": "付费下载", "unknown": "来源未明确"}
    BASES = {"consumer_spend": "消费者支出 / 扣费前", "publisher_net": "开发者净收入", "unknown": "来源未明确"}
    NATURES = {"estimate": "第三方估算", "disclosed": "来源披露（未自动核验）", "unknown": "来源未明确"}
    FIELDS = {
        "platform": "平台", "app_id": "应用 ID", "title": "应用名称",
        "provider": "数据来源", "value_display": "收入数值或范围", "currency": "币种",
        "period_start": "统计开始", "period_end": "统计结束", "country": "地区代码",
        "revenue_type": "收入类型代码", "basis": "收入口径代码", "data_nature": "数值性质代码", "observed_on": "查看日期",
        "source_url": "来源链接", "note": "补充说明",
    }
    HEADER = "# 竞品收入资料（人工记录）"

    @staticmethod
    def _text(payload, key, maximum, required=True):
        value = payload.get(key, "")
        if not isinstance(value, str):
            raise ValueError(f"{key} 必须为文本。")
        value = value.strip()
        if (required and not value) or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise ValueError(f"{key} 为空、过长或包含换行/控制字符。")
        return value

    def _identity(self, project_id, payload):
        self.project(project_id)
        self.version_service.resolve(project_id, payload.get("version_id", ""))
        platform = self._text(payload, "platform", 20)
        app_id = self._text(payload, "app_id", 200)
        if platform not in {"google_play", "app_store"} or not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id):
            raise ValueError("竞品平台或应用 ID 无效。")
        if platform == "app_store" and not app_id.isdigit():
            raise ValueError("App Store 应用 ID 必须为数字。")
        return platform, app_id

    def save(self, project_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("收入资料参数无效。")
        platform, app_id = self._identity(project_id, payload)
        values = {"platform": platform, "app_id": app_id}
        limits = {"title": 160, "provider": 80, "value_display": 100, "currency": 3,
                  "period_start": 10, "period_end": 10, "country": 6, "revenue_type": 20,
                  "basis": 20, "data_nature": 20, "observed_on": 10, "source_url": 1800, "note": 600}
        for key, limit in limits.items():
            values[key] = self._text(payload, key, limit, required=key != "note")
        values["country"] = values["country"].lower()
        values["currency"] = values["currency"].upper()
        if not re.fullmatch(r"[A-Z]{3}", values["currency"]):
            raise ValueError("币种须为三位代码，例如 USD。")
        if not re.fullmatch(r"(?:global|[a-z]{2})", values["country"]):
            raise ValueError("收入地区须为两位国家代码或来源明确提供的 global。")
        if values["revenue_type"] not in self.TYPES or values["basis"] not in self.BASES or values["data_nature"] not in self.NATURES:
            raise ValueError("收入类型或口径无效。")
        if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", values[key]) for key in ("period_start", "period_end", "observed_on")):
            raise ValueError("日期须为 YYYY-MM-DD 格式。")
        try:
            start, end, observed = (date.fromisoformat(values[key]) for key in ("period_start", "period_end", "observed_on"))
        except ValueError as exc:
            raise ValueError("统计周期和查看日期须为有效的 YYYY-MM-DD 日期。") from exc
        if start > end or end > observed:
            raise ValueError("统计结束不能早于开始，也不能晚于查看日期；预测收入请不要作为已观察收入记录。")
        if observed > datetime.now(timezone(timedelta(hours=8))).date():
            raise ValueError("查看日期不能晚于当前日期（北京时间）；未来预测不能作为已观察收入。")
        url = urlsplit(values["source_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("来源须为不含账号密码的 HTTPS 链接。")
        try:
            url.port
        except ValueError as exc:
            raise ValueError("来源链接的端口无效。") from exc
        if (any(re.search(r"token|secret|password|cookie|session|api.?key|auth", key, re.I) for key in parse_qs(url.query)) or
                re.search(r"(?:token|secret|password|cookie|session|api.?key|auth)[^&#=]*=", unquote(url.fragment), re.I)):
            raise ValueError("来源链接不能包含登录凭证或 API 密钥参数，请复制公开页面地址。")
        if payload.get("acknowledged") is not True:
            raise ValueError("请确认这是人工记录的来源数值，不是工作台自动核验的真实收入。")
        lines = [self.HEADER, "", "> 人工记录的第三方资料，工作台未自动核验金额、应用匹配或商业真实性。缺失数据不表示零收入；不据此推算广告收入或 D7 ROI。", ""]
        lines += [f"- {label}：{values[key]}" for key, label in self.FIELDS.items()]
        lines += [f"- 收入类型：{self.TYPES[values['revenue_type']]}", f"- 收入口径：{self.BASES[values['basis']]}", f"- 数值性质：{self.NATURES[values['data_nature']]}", "", "## 使用边界", "", "来源链接供人工核对，工作台不会请求该链接或调用付费数据 API。不能把订阅/IAP、付费下载当作含广告的总收入；不同地区、周期、币种和 gross/net 口径不自动合计。全球地区只在来源确实标为全球时填写，与商店搜索的八市场合并不是同一口径。", ""]
        safe_id = app_id[:95]
        name = f"竞品收入-{safe_id}-{values['period_start']}-{values['period_end']}.md"
        document = self.add_document(project_id, name, "\n".join(lines).encode("utf-8"), payload.get("version_id", ""), "evidence", "competitor")
        if hasattr(self._workbench, "competitor_service"):
            competitor = self.competitor_service.upsert(project_id, values)
            self.competitor_service.attach_documents(project_id, competitor["id"], [document["id"]], "revenue", "revenue", document["id"])
        return {"document": document, "record": {**values, "document_id": document["id"], "manual": True, "verified": False}}

    def records(self, project_id, payload):
        platform, app_id = self._identity(project_id, payload)
        version_id = str(payload.get("version_id") or "").strip()
        scope = "EXISTS (SELECT 1 FROM version_documents vd WHERE vd.document_id=d.id AND vd.version_id=?)" if version_id else "NOT EXISTS (SELECT 1 FROM version_documents vd WHERE vd.document_id=d.id)"
        args = (project_id, version_id) if version_id else (project_id,)
        rows = self.rows(f"SELECT d.id,d.name,d.text,d.created FROM documents d WHERE d.project_id=? AND d.kind='upload' AND d.name LIKE '竞品收入-%' AND {scope} ORDER BY d.created DESC,d.rowid DESC LIMIT 200", args)
        records = []
        reverse = {label: key for key, label in self.FIELDS.items()}
        for document in rows:
            text = document["text"]
            if not text.startswith(self.HEADER):
                continue
            values = {}
            for line in text.splitlines():
                if line.startswith("- ") and "：" in line:
                    label, value = line[2:].split("：", 1)
                    if label in reverse:
                        values[reverse[label]] = value
            if values.get("platform") == platform and values.get("app_id") == app_id:
                records.append({**values, "document_id": document["id"], "document_name": document["name"], "created": document["created"], "manual": True, "verified": False})
        return {"items": records, "truncated": len(rows) == 200, "automatic_provider_connected": False}
