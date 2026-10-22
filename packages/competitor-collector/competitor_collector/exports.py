"""Portable evidence files; source text is never replaced by translations."""
from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path, PureWindowsPath
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

REVIEW_FIELDS = (
    "review_id", "content", "score", "published_at", "market", "language",
    "version", "source", "platform", "app_id", "thumbs_up_count", "user_name",
    "title", "original_content", "translated_content", "reply_content", "reply_at",
)
LISTING_FIELDS = (
    "platform", "app_id", "market", "language", "title", "developer", "category",
    "short_description", "promotional_text", "long_description", "rating",
    "rating_count", "review_count", "installs", "version", "updated", "price",
    "currency", "contains_ads", "offers_iap", "free", "source_url",
    "privacy_policy_url", "icon_url", "screenshot_urls", "screenshot_files", "collected_at",
)
REQUEST_FIELDS = (
    "platform", "app_id", "source_url", "entries", "countries", "requested_countries",
    "collection_scope", "count_per_country", "sort", "date_from", "date_to",
    "ratings", "include_keywords", "exclude_keywords", "reply_filter",
    "version_filter", "min_thumbs_up", "collect_listing", "collect_reviews",
    "download_screenshots", "translate", "translation_provider",
)


def _atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json(path: Path, value: object) -> None:
    _atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _public_url(value: object) -> str:
    text = str(value or "")
    try:
        parsed = urlparse(text)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return ""
        sensitive = {"token", "api_key", "apikey", "access_token", "authorization", "password", "secret", "key"}
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.casefold() not in sensitive]
        return urlunparse(parsed._replace(query=urlencode(query)))
    except ValueError:
        return ""


def _warning(value: object) -> str:
    text = str(value or "")[:1000]
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [redacted]", text)
    text = re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|token|authorization|password|secret)\s*[:=]\s*)[^\s;,，；]+", r"\1[redacted]", text)
    return text


def _safe_request(request: dict) -> dict:
    clean = {field: request[field] for field in REQUEST_FIELDS if field in request}
    if "entries" in clean:
        clean["entries"] = [
            {key: item.get(key, "") for key in ("platform", "app_id", "source_url")}
            for item in clean["entries"] if isinstance(item, dict)
        ]
        for item in clean["entries"]:
            item["source_url"] = _public_url(item["source_url"])
    if "source_url" in clean:
        clean["source_url"] = _public_url(clean["source_url"])
    return clean


def _review_csv(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        clean = {}
        for field in REVIEW_FIELDS:
            value = row.get(field)
            value = "" if value is None else str(value)
            if value.lstrip("\ufeff\t\r\n ")[:1] in {"=", "+", "-", "@"}:
                value = "'" + value
            clean[field] = value
        writer.writerow(clean)
    return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")


def _listing_markdown(listing: dict, screenshots: list[dict]) -> str:
    def present(value):
        return "未提供" if value is None or value == "" else str(value)
    lines = [f"# {listing.get('title') or listing.get('app_id') or '竞品'}商店资料", ""]
    labels = (("platform", "平台"), ("app_id", "应用 ID"), ("market", "市场"),
              ("language", "语言"), ("developer", "开发者"), ("category", "分类"),
              ("rating", "评分"), ("rating_count", "评分数量"), ("installs", "安装量（商店字段，非月下载）"),
              ("version", "版本"), ("updated", "更新时间"), ("source_url", "来源"), ("collected_at", "采集时间"))
    lines += [f"- {label}：{present(listing.get(field))}" for field, label in labels]
    for field, label in (("short_description", "短描述（原文）"), ("promotional_text", "Promotional Text（原文）"), ("long_description", "长描述（原文）")):
        lines += ["", f"## {label}", "", str(listing.get(field) or "当前商店接口未提供此字段，未补写。")]
    lines += ["", "## 商店截图", ""]
    if screenshots:
        for item in screenshots:
            lines += [f"![商店宣传截图 {item['name']}]({item['relative_path']})", ""]
    else:
        lines += ["未下载到商店截图。", ""]
    lines += ["## 资料边界", "", "以上为指定市场的商店快照；缺失值不补造。商店宣传图不等于 App 内实机页面。安装量不等于月下载，当前没有收入数据。", ""]
    return "\n".join(lines)


def write_evidence(directory: Path, result: dict, request: dict) -> dict:
    """Write one application's evidence under an already scoped output folder."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not isinstance(result, dict) or not isinstance(request, dict):
        raise ValueError("采集结果和请求必须是对象。")
    warnings = [_warning(item) for item in (result.get("warnings") or [])]
    listing_raw = result.get("listing")
    listing = {field: listing_raw[field] for field in LISTING_FIELDS if field in listing_raw} if isinstance(listing_raw, dict) else {}
    for field in ("source_url", "privacy_policy_url", "icon_url"):
        if field in listing:
            listing[field] = _public_url(listing[field])
    if "screenshot_urls" in listing:
        listing["screenshot_urls"] = [url for value in listing["screenshot_urls"][:20] if (url := _public_url(value))]
    screenshots, seen = [], set()
    files = listing_raw.get("screenshot_files") or [] if isinstance(listing_raw, dict) else []
    for value in files[:20] if isinstance(files, list) else []:
        name = str(value or "")
        windows = PureWindowsPath(name)
        if not name or name in {".", ".."} or "/" in name or "\\" in name or windows.drive or ":" in name or "\x00" in name or Path(name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            warnings.append("忽略不安全的截图文件路径。")
            continue
        candidate = directory / "screenshots" / name
        try:
            target = candidate.resolve(strict=True)
            target.relative_to((directory / "screenshots").resolve())
            target.relative_to(directory)
            if not candidate.is_file() or candidate.is_symlink():
                raise ValueError("invalid file")
        except (OSError, ValueError):
            warnings.append("截图文件缺失或不属于当前采集目录。")
            continue
        if name not in seen:
            seen.add(name)
            screenshots.append({"name": name, "relative_path": f"screenshots/{name}"})
    if listing:
        listing["screenshot_files"] = [item["relative_path"] for item in screenshots]
    reviews = [
        {field: row.get(field) for field in REVIEW_FIELDS}
        for row in (result.get("reviews") or []) if isinstance(row, dict)
    ]
    if request.get("collect_listing") and not listing:
        warnings.append("未采集到本次要求的商店资料，其他成功资料已保留。")
    if request.get("collect_reviews") and not reviews:
        warnings.append("未采集到本次要求的评论，其他成功资料已保留。")
    if request.get("download_screenshots") and not screenshots:
        warnings.append("未下载到本次要求的商店截图，其他成功资料已保留。")
    warnings = list(dict.fromkeys(warnings))
    files = {"reviews_csv": "reviews.csv", "listing_json": "store-listing.json", "listing_md": "store-listing.md", "result_json": "result.json"}
    _atomic(directory / files["reviews_csv"], _review_csv(reviews))
    _json(directory / files["listing_json"], listing)
    _atomic(directory / files["listing_md"], _listing_markdown(listing, screenshots).encode("utf-8"))
    stats = result.get("filter_stats")
    stats = {field: stats[field] for field in ("active", "fetched", "kept") if field in stats} if isinstance(stats, dict) else {}
    clean_result = {"listing": listing or None, "reviews": reviews, "warnings": warnings,
                    "filter_stats": stats}
    _json(directory / files["result_json"], clean_result)
    has_data = bool(listing or reviews or screenshots)
    status = "partial" if has_data and warnings else "completed" if has_data else "failed"
    if not has_data:
        warnings.append("没有采集到商店资料、评论或截图，不能视为采集成功。")
        clean_result["warnings"] = warnings
        _json(directory / files["result_json"], clean_result)
    summary = {"status": status, "title": str(listing.get("title") or request.get("app_id") or "竞品"),
               "review_count": len(reviews), "screenshot_count": len(screenshots), "warnings": warnings,
               "listing": listing, "review_samples": reviews[:20], "screenshots": screenshots, "files": files}
    _json(directory / "manifest.json", {
        "schema": 1, "status": status, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "request": _safe_request(request), "review_count": len(reviews), "screenshot_count": len(screenshots),
        "warnings": warnings, "files": files,
    })
    return summary
