"""Validated, credential-free collection requests shared by CLI and local UI."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, urlparse

GLOBAL_MARKETS = ("us", "gb", "de", "jp", "in", "id", "br", "sa")
ISO_COUNTRIES = frozenset("ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs bt bv bw by bz ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg eh er es et fi fj fk fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mf mg mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug um us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw".split())


def _entry(value: object) -> dict:
    if isinstance(value, dict):
        platform = str(value.get("platform") or "")
        app_id = str(value.get("app_id") or "").strip()
        if platform not in {"google_play", "app_store"}:
            raise ValueError("竞品平台无效。")
    else:
        raw = str(value or "").strip()
        if not raw or len(raw) > 2400:
            raise ValueError("请填写有效的竞品商店链接或应用 ID。")
        if "://" in raw:
            try:
                parsed = urlparse(raw)
                host = (parsed.hostname or "").lower()
                port = parsed.port
            except ValueError:
                raise ValueError("竞品链接格式无效。") from None
            if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
                raise ValueError("竞品链接必须是无内嵌凭证的 HTTPS 商店链接。")
            if host == "play.google.com":
                platform = "google_play"
                app_id = str((parse_qs(parsed.query).get("id") or [""])[0]).strip()
            elif host == "apps.apple.com":
                match = re.search(r"/id(\d+)(?:/|$)", parsed.path)
                platform, app_id = "app_store", match.group(1) if match else ""
            else:
                raise ValueError("只支持 Google Play 或 App Store 官方链接。")
        else:
            platform, app_id = ("app_store", raw) if raw.isdigit() else ("google_play", raw)
    if len(app_id) > 200 or not app_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id):
        raise ValueError("竞品应用 ID 无效。")
    if platform == "app_store" and not app_id.isdigit():
        raise ValueError("App Store 必须使用数字应用 ID。")
    source_url = f"https://play.google.com/store/apps/details?id={app_id}" if platform == "google_play" else f"https://apps.apple.com/app/id{app_id}"
    return {"platform": platform, "app_id": app_id, "source_url": source_url}


def _integer(value: object, lower: int, upper: int, label: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"{label}必须是整数。")
    number = int(value)
    if not lower <= number <= upper:
        raise ValueError(f"{label}必须在 {lower}–{upper} 之间。")
    return number


def _terms(value: object, label: str) -> list[str]:
    if isinstance(value, str):
        rows = re.split(r"[,，\n]+", value)
    elif isinstance(value, list):
        rows = value
    elif value in (None, ""):
        rows = []
    else:
        raise ValueError(f"{label}格式无效。")
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, str):
            raise ValueError(f"{label}必须是文本。")
        term = row.strip()
        if not term:
            continue
        if len(term) > 80 or any(ord(character) < 32 for character in term):
            raise ValueError(f"{label}单项不能超过 80 字符或包含控制字符。")
        if term.casefold() not in seen:
            seen.add(term.casefold())
            result.append(term)
    if len(result) > 20:
        raise ValueError(f"{label}最多 20 个。")
    return result


def normalize_request(payload: dict) -> dict:
    """Only return supported inputs; never carry root, credentials or output paths."""
    if not isinstance(payload, dict):
        raise ValueError("采集请求必须是 JSON 对象。")
    raw_entries = payload.get("entries", [])
    if isinstance(raw_entries, str):
        raw_entries = raw_entries.splitlines()
    if not isinstance(raw_entries, list):
        raise ValueError("竞品列表必须是多行文本或数组。")
    entries, seen = [], set()
    for value in raw_entries:
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        item = _entry(value)
        key = (item["platform"], item["app_id"])
        if key not in seen:
            seen.add(key)
            entries.append(item)
    if not entries or len(entries) > 20:
        raise ValueError("请提供 1–20 个由你指定的竞品。")
    countries = payload.get("countries", ["us"])
    if isinstance(countries, str):
        countries = re.split(r"[,，\s]+", countries)
    if not isinstance(countries, list):
        raise ValueError("国家或地区格式无效。")
    requested, concrete = [], []
    for value in countries:
        if not isinstance(value, str):
            raise ValueError("国家需要两位 ISO 代码。")
        country = value.strip().lower()
        if not country:
            continue
        if country not in ISO_COUNTRIES and country != "global":
            raise ValueError("国家需要有效的两位 ISO 代码，或选择 global 八市场样本。")
        if country not in requested:
            requested.append(country)
        for expanded in GLOBAL_MARKETS if country == "global" else (country,):
            if expanded not in concrete:
                concrete.append(expanded)
    if not concrete or len(concrete) > 20:
        raise ValueError("请选择 1–20 个具体市场。")
    result = {
        "entries": entries, "countries": concrete, "requested_countries": requested,
        "collection_scope": "global_multi_market" if "global" in requested else "selected_markets",
        "count_per_country": _integer(payload.get("count_per_country", 100), 1, 500, "每市场评论数量"),
    }
    sort = payload.get("sort", "newest")
    if sort not in {"newest", "relevant"}:
        raise ValueError("排序只支持 newest 或 relevant。")
    result["sort"] = sort
    parsed_dates = {}
    for field in ("date_from", "date_to"):
        value = payload.get(field) or ""
        if not isinstance(value, str):
            raise ValueError("日期格式必须为 YYYY-MM-DD。")
        try:
            parsed = date.fromisoformat(value) if value else None
        except ValueError:
            raise ValueError("日期格式必须为 YYYY-MM-DD。") from None
        result[field] = parsed.isoformat() if parsed else ""
        parsed_dates[field] = parsed
    if parsed_dates["date_from"] and parsed_dates["date_to"] and parsed_dates["date_from"] > parsed_dates["date_to"]:
        raise ValueError("开始日期不能晚于结束日期。")
    ratings = payload.get("ratings", [])
    if isinstance(ratings, str):
        ratings = re.split(r"[,，\s]+", ratings)
    if not isinstance(ratings, list):
        raise ValueError("评分筛选格式无效。")
    result["ratings"] = sorted({_integer(item, 1, 5, "评分") for item in ratings if item not in (None, "")})
    result["include_keywords"] = _terms(payload.get("include_keywords"), "包含关键词")
    result["exclude_keywords"] = _terms(payload.get("exclude_keywords"), "排除关键词")
    reply = payload.get("reply_filter", "any")
    if reply not in {"any", "replied", "unreplied"}:
        raise ValueError("开发者回复筛选无效。")
    result["reply_filter"] = reply
    version = payload.get("version_filter", "")
    if not isinstance(version, str) or len(version) > 100 or any(ord(character) < 32 for character in version):
        raise ValueError("版本筛选必须是 100 字符以内文本。")
    result["version_filter"] = version.strip()
    result["min_thumbs_up"] = _integer(payload.get("min_thumbs_up", 0), 0, 1_000_000, "最低点赞数")
    for field, default in (("collect_listing", True), ("collect_reviews", True), ("download_screenshots", True), ("translate", False)):
        value = payload.get(field, default)
        if not isinstance(value, bool):
            raise ValueError(f"{field} 必须是 true 或 false。")
        result[field] = value
    if result["download_screenshots"]:
        result["collect_listing"] = True
    if not result["collect_listing"] and not result["collect_reviews"]:
        raise ValueError("至少选择商店资料、评论或商店截图中的一项。")
    if result["translate"]:
        provider = payload.get("translation_provider")
        if provider not in {"google", "openai"}:
            raise ValueError("翻译需要明确指定 google 或 openai。")
        if not result["collect_reviews"]:
            raise ValueError("翻译需要同时采集评论。")
        result["translation_provider"] = provider
    return result
