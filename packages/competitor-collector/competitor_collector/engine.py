"""Portable store material collection engine with a legacy desktop bridge.

All imports with optional providers are lazy. collect is independent of the
workbench database; an explicitly supplied root preserves legacy behavior.
"""
from __future__ import annotations

import json
import math
import os
import re
import socket
import sys
from datetime import date
from pathlib import Path


def _configure_stdio() -> None:
    """Keep the JSON bridge independent from the Windows console code page."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="strict")
        except (AttributeError, ValueError):
            # Older/custom streams may not expose reconfigure; JSON output below
            # is ASCII-safe as a second line of defense.
            pass


def _emit(payload: dict) -> None:
    # ASCII JSON survives a GBK-configured parent even when an imported scraper
    # or a redirected stream ignores the UTF-8 environment override.
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def _parse_json_object(value: str) -> dict:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("翻译服务没有返回 JSON。")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("翻译服务返回格式无效。")
    return payload


def _translate_ai_batch(texts: list[str], root: Path | None) -> list[str]:
    """Translate one aligned batch with the desktop tool's local DeepSeek config."""
    from openai import OpenAI

    if root is not None:
        sys.path.insert(0, str(root))
        from app.config import settings

        if not settings.deepseek_ready:
            raise RuntimeError("桌面工具尚未配置可用的 DeepSeek。")
        api_key = settings.deepseek_api_key
        base_url = str(settings.deepseek_base_url)
        model = settings.deepseek_model
    else:
        api_key = os.environ.get("COMPETITOR_COLLECTOR_API_KEY", "").strip()
        base_url = os.environ.get("COMPETITOR_COLLECTOR_BASE_URL", "").strip()
        model = os.environ.get("COMPETITOR_COLLECTOR_MODEL", "").strip()
        if not api_key or not base_url or not model:
            raise RuntimeError("独立翻译服务未配置：需要 API_KEY、BASE_URL、MODEL。")
        from urllib.parse import urlparse
        endpoint = urlparse(base_url)
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
            raise ValueError("独立翻译服务 BASE_URL 必须是无内嵌凭证的 HTTPS URL。")
    client = OpenAI(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        timeout=90,
        max_retries=1,
    )
    prompt = (
        "将下面的用户评论翻译成简体中文。保持原意、情绪、产品名、金额和版本号；"
        "不要总结、解释、合并或遗漏。严格按 index 返回 JSON："
        '{"translations":[{"index":0,"text":"中文译文"}]}。\n评论：\n'
        + "\n".join(f"[{index}] {text[:3000]}" for index, text in enumerate(texts))
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是用户评论翻译器。只输出合法 JSON，译文必须与输入 index 一一对应。",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=max(2000, min(8000, sum(len(text) for text in texts) // 2 + 800)),
    )
    payload = _parse_json_object(response.choices[0].message.content or "")
    rows = payload.get("translations")
    if not isinstance(rows, list):
        raise ValueError("翻译结果缺少 translations。")
    translated: list[str | None] = [None] * len(texts)
    for fallback_index, row in enumerate(rows):
        if isinstance(row, str):
            index, value = fallback_index, row
        elif isinstance(row, dict):
            try:
                index = int(row.get("index", fallback_index))
            except (TypeError, ValueError):
                continue
            value = row.get("text")
        else:
            continue
        if 0 <= index < len(translated) and str(value or "").strip():
            translated[index] = str(value).strip()[:10000]
    if any(value is None for value in translated):
        raise ValueError("翻译结果与原评论没有完整对齐。")
    return [str(value) for value in translated]


def _translate_google(text: str) -> str:
    from deep_translator import GoogleTranslator

    return str(GoogleTranslator(source="auto", target="zh-CN").translate(text[:4500]) or "").strip()


def _translate_resilient(texts: list[str], root: Path, warnings: list[str]) -> tuple[list[str], bool]:
    """Retry malformed AI batches by splitting them before using Google."""
    try:
        return _translate_ai_batch(texts, root), False
    except Exception as error:  # noqa: BLE001 - smaller aligned batches are the recovery path
        warnings.append(f"DeepSeek {len(texts)} 条批次拆分重试：{type(error).__name__}")
        if len(texts) > 1:
            middle = max(1, len(texts) // 2)
            left, left_fallback = _translate_resilient(texts[:middle], root, warnings)
            right, right_fallback = _translate_resilient(texts[middle:], root, warnings)
            return left + right, left_fallback or right_fallback
        try:
            return [_translate_google(texts[0])], True
        except Exception:  # noqa: BLE001 - the source remains available when both providers fail
            return [""], True


def _translate_items(items: list[dict], root: Path | None, batch_size: int = 20, provider: str | None = None) -> dict:
    """Translate unique non-Chinese review texts and retain index alignment."""
    if root is None and provider not in {"google", "openai"}:
        raise ValueError("请明确指定 translation_provider：google 或 openai。")
    if not isinstance(items, list) or len(items) > 500:
        raise ValueError("每次最多翻译 500 条评论。")
    translations = [""] * len(items)
    groups: dict[str, list[int]] = {}
    skipped = 0
    for index, item in enumerate(items):
        text = str(item.get("text") or "").strip() if isinstance(item, dict) else ""
        language = str(item.get("language") or "").lower() if isinstance(item, dict) else ""
        if not text or language.startswith("zh") or not any(character.isalpha() for character in text):
            skipped += 1
            continue
        groups.setdefault(text, []).append(index)
    unique_texts = list(groups)
    failed = 0
    warnings: list[str] = []
    provider_name = "deepseek" if root is not None else str(provider)
    for offset in range(0, len(unique_texts), max(1, min(50, int(batch_size)))):
        batch = unique_texts[offset : offset + max(1, min(50, int(batch_size)))]
        if root is not None:
            values, used_fallback = _translate_resilient(batch, root, warnings)
            if used_fallback:
                provider_name = "deepseek+google-fallback"
        elif provider == "google":
            values = []
            for text in batch:
                try:
                    values.append(_translate_google(text))
                except Exception as error:
                    values.append("")
                    warnings.append(f"Google 翻译失败：{type(error).__name__}")
        else:
            try:
                values = _translate_ai_batch(batch, None)
            except Exception as error:
                values = [""] * len(batch)
                warnings.append(f"OpenAI-compatible 翻译失败：{type(error).__name__}；未切换其他服务")
        for text, value in zip(batch, values):
            clean = str(value or "").strip()
            if not clean:
                failed += len(groups[text])
                continue
            for index in groups[text]:
                translations[index] = clean
    return {
        "translations": translations,
        "translated_count": sum(bool(value) for value in translations),
        "failed_count": failed,
        "skipped_count": skipped,
        "provider": provider_name,
        "warnings": list(dict.fromkeys(warnings))[:5],
    }


def _optional_date(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}，请使用 YYYY-MM-DD。") from exc


def _filter_reviews(rows: list[dict], payload: dict) -> tuple[list[dict], dict]:
    ratings = {int(value) for value in (payload.get("ratings") or []) if str(value).isdigit() and 1 <= int(value) <= 5}
    include_keywords = [str(value).strip().casefold() for value in (payload.get("include_keywords") or []) if str(value).strip()]
    exclude_keywords = [str(value).strip().casefold() for value in (payload.get("exclude_keywords") or []) if str(value).strip()]
    reply_filter = str(payload.get("reply_filter") or "any").strip().lower()
    version_filter = str(payload.get("version_filter") or "").strip().casefold()
    try:
        min_thumbs_up = max(0, int(payload.get("min_thumbs_up") or 0))
    except (TypeError, ValueError):
        min_thumbs_up = 0
    active = bool(ratings or include_keywords or exclude_keywords or reply_filter != "any" or version_filter or min_thumbs_up)
    if not active:
        return rows, {"active": False, "fetched": len(rows), "kept": len(rows)}
    filtered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if ratings:
            try:
                score = int(round(float(row.get("score"))))
            except (TypeError, ValueError):
                continue
            if score not in ratings:
                continue
        searchable = "\n".join(str(row.get(key) or "") for key in ("title", "content", "original_content")).casefold()
        if include_keywords and not any(term in searchable for term in include_keywords):
            continue
        if exclude_keywords and any(term in searchable for term in exclude_keywords):
            continue
        has_reply = bool(str(row.get("reply_content") or "").strip())
        if reply_filter == "replied" and not has_reply:
            continue
        if reply_filter == "unreplied" and has_reply:
            continue
        if version_filter and version_filter not in str(row.get("version") or "").casefold():
            continue
        try:
            thumbs_up = int(row.get("thumbs_up_count") or 0)
        except (TypeError, ValueError):
            thumbs_up = 0
        if thumbs_up < min_thumbs_up:
            continue
        filtered.append(row)
    return filtered, {"active": True, "fetched": len(rows), "kept": len(filtered)}


def _json_value(value):
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _google_listing(app_id: str, country: str, language: str) -> dict:
    from google_play_scraper import app as google_app

    raw = google_app(app_id, lang=language, country=country)
    categories = raw.get("categories") or []
    if categories and isinstance(categories[0], dict):
        category = str(categories[0].get("name") or raw.get("genre") or "")
    else:
        category = str(raw.get("genre") or "")
    return {
        "platform": "google_play",
        "app_id": app_id,
        "market": country.upper(),
        "language": language,
        "title": str(raw.get("title") or app_id),
        "developer": str(raw.get("developer") or ""),
        "category": category,
        "short_description": str(raw.get("summary") or ""),
        "promotional_text": "",
        "long_description": str(raw.get("description") or ""),
        "rating": _json_value(raw.get("score")),
        "rating_count": _json_value(raw.get("ratings")),
        "review_count": _json_value(raw.get("reviews")),
        "installs": str(raw.get("installs") or ""),
        "version": str(raw.get("version") or ""),
        "updated": _json_value(raw.get("lastUpdatedOn") or raw.get("updated")),
        "price": _json_value(raw.get("price")),
        "currency": str(raw.get("currency") or ""),
        "contains_ads": raw.get("containsAds", raw.get("adSupported")),
        "offers_iap": raw.get("offersIAP"),
        "free": raw.get("free"),
        "source_url": str(raw.get("url") or f"https://play.google.com/store/apps/details?id={app_id}&gl={country}"),
        "privacy_policy_url": str(raw.get("privacyPolicy") or ""),
        "icon_url": str(raw.get("icon") or ""),
        "screenshot_urls": [str(item) for item in (raw.get("screenshots") or []) if str(item).startswith("http")][:20],
    }


def _app_store_listing(app_id: str, country: str, warnings: list[str]) -> dict:
    import requests

    response = requests.get(
        "https://itunes.apple.com/lookup",
        params={"id": app_id, "country": country},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json().get("results") or []
    if not rows:
        raise ValueError(f"App Store {country.upper()} 未找到应用 {app_id}")
    raw = rows[0]
    short_description = str(raw.get("subtitle") or "")
    if not short_description:
        warnings.append("App Store Lookup 未返回 Subtitle；短描述留空，未使用其他字段猜测")
    screenshots = list(raw.get("screenshotUrls") or []) + list(raw.get("ipadScreenshotUrls") or [])
    return {
        "platform": "app_store",
        "app_id": app_id,
        "market": country.upper(),
        "language": "",
        "title": str(raw.get("trackName") or app_id),
        "developer": str(raw.get("artistName") or ""),
        "category": str(raw.get("primaryGenreName") or ""),
        "short_description": short_description,
        "promotional_text": str(raw.get("promotionalText") or ""),
        "long_description": str(raw.get("description") or ""),
        "rating": _json_value(raw.get("averageUserRating")),
        "rating_count": _json_value(raw.get("userRatingCount")),
        "review_count": "",
        "installs": "",
        "version": str(raw.get("version") or ""),
        "updated": str(raw.get("currentVersionReleaseDate") or ""),
        "price": _json_value(raw.get("price")),
        "currency": str(raw.get("currency") or ""),
        "contains_ads": None,
        "offers_iap": None,
        "free": raw.get("price") == 0 if isinstance(raw.get("price"), (int, float)) else None,
        "source_url": str(raw.get("trackViewUrl") or f"https://apps.apple.com/{country}/app/id{app_id}"),
        "privacy_policy_url": "",
        "icon_url": str(raw.get("artworkUrl512") or raw.get("artworkUrl100") or ""),
        "screenshot_urls": [str(item) for item in screenshots if str(item).startswith("http")][:20],
    }


def _discovery_url(value: object, hosts: set[str] | None = None) -> str:
    from urllib.parse import urlparse

    value = str(value or "")[:2400]
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    if hosts and parsed.hostname.lower() not in hosts:
        return ""
    return value


def _discovery_number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _discovery_bool(value):
    return value if isinstance(value, bool) else None


def _candidate(raw: dict, platform: str, country: str) -> dict:
    """Missing fields stay missing: discovery never uses an LLM or app detail fanout."""
    apple = platform == "app_store"
    app_id = str((raw.get("trackId") if apple else raw.get("appId")) or "")[:200]
    source = f"https://apps.apple.com/{country}/app/id{app_id}" if apple else f"https://play.google.com/store/apps/details?id={app_id}&gl={country}"
    return {
        "platform": platform, "app_id": app_id,
        "title": str((raw.get("trackName") if apple else raw.get("title")) or "")[:300],
        "developer": str((raw.get("artistName") if apple else raw.get("developer")) or "")[:300],
        "icon_url": _discovery_url(raw.get("artworkUrl100") or raw.get("artworkUrl512") if apple else raw.get("icon")),
        "source_url": _discovery_url(raw.get("trackViewUrl") if apple else raw.get("url"), {"apps.apple.com"} if apple else {"play.google.com"}) or source,
        "short_description": str(raw.get("subtitle") or "" if apple else raw.get("summary") or "")[:2000],
        "description": str(raw.get("description") or "")[:6000],
        "score": _discovery_number(raw.get("averageUserRating") if apple else raw.get("score")),
        "ratings": _discovery_number(raw.get("userRatingCount") if apple else raw.get("ratings")),
        "installs": "" if apple else str(raw.get("installs") or "")[:80],
        "price": _discovery_number(raw.get("price")),
        "currency": str(raw.get("currency") or "")[:12],
        "free": (raw.get("price") == 0 if _discovery_number(raw.get("price")) is not None else None) if apple else _discovery_bool(raw.get("free")),
        "offers_iap": None if apple else _discovery_bool(raw.get("offersIAP")),
        "contains_ads": None if apple else _discovery_bool(raw.get("containsAds", raw.get("adSupported"))),
        "updated": str(raw.get("currentVersionReleaseDate") or "")[:80] if apple else _json_value(raw.get("lastUpdatedOn") or raw.get("updated")),
    }


def _apple_discovery_request(endpoint: str, params: dict) -> dict:
    """Fixed HTTPS origin, constrained redirects and bounded response body."""
    from urllib.parse import urlencode, urlparse
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class AppleRedirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlparse(newurl)
            if target.scheme != "https" or target.hostname != "itunes.apple.com" or target.username or target.password:
                raise ValueError("unsupported_redirect")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    if endpoint not in {"search", "lookup"}:
        raise ValueError("unsupported_endpoint")
    request = Request(f"https://itunes.apple.com/{endpoint}?{urlencode(params)}", headers={"User-Agent": "PM-Product-Workbench/1.0"})
    with build_opener(AppleRedirects()).open(request, timeout=15) as response:
        content = response.read(3 * 1024 * 1024 + 1)
    if len(content) > 3 * 1024 * 1024:
        raise ValueError("response_too_large")
    result = json.loads(content)
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        raise ValueError("invalid_response")
    return result


def _bounded_listing(listing: dict) -> dict:
    result = {}
    for key, value in listing.items():
        if key == "screenshot_urls":
            result[key] = [url for item in value[:20] if (url := _discovery_url(item))]
        elif key.endswith("_url"):
            result[key] = _discovery_url(value)
        elif isinstance(value, str):
            result[key] = value[:80000 if key == "long_description" else 2400]
        else:
            result[key] = _json_value(value)
    result["collected_at"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
    return result


def _discovery(payload: dict, root: Path | None) -> dict:
    mode = payload.get("mode")
    platform = payload.get("platform")
    country, language = str(payload.get("country") or "us"), str(payload.get("lang") or "en")
    warnings = ["商店搜索结果仅用于候选发现，顺序不代表市场排名、收入或推荐结论；缺失字段未补写。"]
    socket.setdefaulttimeout(15)
    if platform == "google_play":
        if root is not None:
            sys.path.insert(0, str(root))
        import google_play_scraper as google

        operation = getattr(google, "search" if mode == "discovery_search" else "app", None)
        if not callable(operation):
            return {"error_code": "unsupported_capability"}
        if mode == "discovery_search":
            rows = operation(str(payload["query"]), n_hits=int(payload["limit"]), lang=language, country=country)
            if not isinstance(rows, list):
                raise ValueError("invalid_search_response")
            items, seen = [], set()
            for row in rows[:int(payload["limit"])]:
                if not isinstance(row, dict):
                    continue
                item = _candidate(row, platform, country)
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", item["app_id"]) or item["app_id"] in seen:
                    continue
                seen.add(item["app_id"])
                items.append(item)
            if not items:
                warnings.append("当前关键词和国家未返回候选，可缩短关键词或切换国家；也可直接粘贴竞品链接。")
            return {"items": items, "warnings": warnings}
        listing = _google_listing(str(payload["app_id"]), country, language)
    elif platform == "app_store":
        if mode == "discovery_search":
            result = _apple_discovery_request("search", {"term": payload["query"], "country": country, "entity": "software", "limit": int(payload["limit"]), "lang": "ja_jp" if language.startswith("ja") else "en_us"})
            items = [_candidate(row, platform, country) for row in result["results"][:int(payload["limit"])] if isinstance(row, dict) and row.get("trackId")]
            warnings.append("App Store 搜索接口通常不提供安装量、广告和内购标记，短描述可能为空；未用长描述伪造 Subtitle。")
            if not items:
                warnings.append("当前关键词和国家未返回候选，请换关键词或国家。")
            return {"items": items, "warnings": warnings}
        result = _apple_discovery_request("lookup", {"id": payload["app_id"], "country": country, "entity": "software"})
        rows = result["results"]
        if not rows:
            return {"error_code": "not_found"}
        raw = rows[0]
        candidate = _candidate(raw, platform, country)
        listing = {
            **candidate, "market": country.upper(), "language": language,
            "category": str(raw.get("primaryGenreName") or ""),
            "long_description": str(raw.get("description") or ""),
            "promotional_text": str(raw.get("promotionalText") or ""),
            "rating": candidate["score"], "rating_count": candidate["ratings"],
            "version": str(raw.get("version") or ""), "privacy_policy_url": "",
            "screenshot_urls": list(raw.get("screenshotUrls") or []) + list(raw.get("ipadScreenshotUrls") or []),
        }
        if not candidate["short_description"]:
            warnings.append("App Store Lookup 未返回 Subtitle，短描述保持为空。")
    else:
        raise ValueError("unsupported_platform")
    return {"listing": _bounded_listing(listing), "warnings": warnings}


_SCREENSHOT_DOMAINS = ("googleusercontent.com", "ggpht.com", "mzstatic.com", "apple.com")
_SCREENSHOT_LIMIT = 12 * 1024 * 1024


def _safe_screenshot_url(value: object) -> str:
    from urllib.parse import urlparse

    text = str(value or "")
    try:
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise ValueError("invalid_screenshot_url") from None
    if (
        parsed.scheme != "https" or not host or parsed.username or parsed.password
        or port not in (None, 443)
        or not any(host == domain or host.endswith("." + domain) for domain in _SCREENSHOT_DOMAINS)
    ):
        raise ValueError("unsupported_screenshot_origin")
    return text


def _read_screenshot(url: str) -> tuple[bytes, str]:
    """Only trusted store-image origins; redirects and bodies are bounded."""
    import io
    import warnings as python_warnings
    from urllib.parse import urljoin
    import requests
    from PIL import Image

    current = _safe_screenshot_url(url)
    for redirect in range(4):
        response = requests.get(
            current, headers={"User-Agent": "Competitor-Collector/0.1"},
            timeout=25, stream=True, allow_redirects=False,
        )
        try:
            if response.status_code in {301, 302, 303, 307, 308}:
                if redirect == 3:
                    raise ValueError("too_many_screenshot_redirects")
                current = _safe_screenshot_url(urljoin(current, response.headers.get("Location", "")))
                continue
            response.raise_for_status()
            declared = response.headers.get("Content-Length", "")
            if declared and declared.isdigit() and int(declared) > _SCREENSHOT_LIMIT:
                raise ValueError("screenshot_too_large")
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > _SCREENSHOT_LIMIT:
                    raise ValueError("screenshot_too_large")
                chunks.append(chunk)
            content = b"".join(chunks)
            if not content:
                raise ValueError("empty_screenshot")
            with python_warnings.catch_warnings():
                python_warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(image.format)
                    if not extension or image.width * image.height > 40_000_000:
                        raise ValueError("unsupported_screenshot_format")
                    image.verify()
            return content, extension
        finally:
            response.close()
    raise ValueError("too_many_screenshot_redirects")


def _download_screenshots(listing: dict, output_dir: Path, warnings: list[str]) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    urls = listing.get("screenshot_urls") or []
    if not isinstance(urls, list):
        raise ValueError("截图 URL 列表无效。")
    for index, url in enumerate(urls[:20], 1):
        temporary = None
        try:
            content, extension = _read_screenshot(str(url))
            name = f"{index:02d}{extension}"
            target = output_dir / name
            temporary = output_dir / f".{name}.tmp"
            temporary.write_bytes(content)
            os.replace(temporary, target)
            saved.append(name)
        except Exception as exc:  # one image must not abort listing/reviews
            warnings.append(f"商店截图 {index} 下载失败：{type(exc).__name__}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if len(urls) > 20:
        warnings.append("商店截图最多下载前 20 张。")
    return saved


def _listing_country(payload: dict, countries: list[str]) -> str:
    """Prefer a discovered market, but never query outside user-selected markets."""
    selected = [str(country).strip().lower() for country in countries if re.fullmatch(r"[a-zA-Z]{2}", str(country).strip())]
    if not selected:
        raise ValueError("商店详情需要至少一个本次选择的具体国家，不能使用 global。")
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    lookup = str(selection.get("lookup_country") or "").strip().lower()
    if lookup in selected:
        return lookup
    observed = selection.get("observed_countries")
    if isinstance(observed, list):
        for value in observed:
            country = str(value or "").strip().lower()
            if country in selected:
                return country
    return selected[0]


def _resolve_legacy_root(payload: dict) -> Path | None:
    value = str(payload.get("root") or "").strip()
    if not value:
        return None
    root = Path(value).expanduser().resolve()
    if not root.is_dir() or not (root / "app" / "scrapers.py").is_file():
        raise ValueError("竞品评论工具目录无效，未找到 app/scrapers.py。")
    return root


def _normalized_collection_request(payload: dict) -> dict:
    """Validate public API inputs independently from any UI/database."""
    result = dict(payload)
    platform = str(result.get("platform") or "google_play").strip()
    if platform not in {"google_play", "app_store"}:
        raise ValueError("只支持 Google Play 或 App Store。")
    app_id = str(result.get("app_id") or "").strip()
    if not app_id or len(app_id) > 200 or not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id):
        raise ValueError("需要有效的应用 ID。")
    countries = result.get("countries", [])
    if isinstance(countries, str):
        countries = re.split(r"[,，\s]+", countries)
    if not isinstance(countries, list):
        raise ValueError("国家或地区格式无效。")
    requested, concrete = [], []
    for value in countries:
        country = str(value or "").strip().lower()
        if not country:
            continue
        if country not in requested:
            requested.append(country)
        expanded = ("us", "gb", "de", "jp", "in", "id", "br", "sa") if country == "global" else (country,)
        for item in expanded:
            if not re.fullmatch(r"[a-z]{2}", item):
                raise ValueError("国家需要两位代码；global 仅指八个预设市场。")
            if item not in concrete:
                concrete.append(item)
    if not concrete or len(concrete) > 20:
        raise ValueError("至少选择一个具体市场，最多 20 个。")
    try:
        count = int(result.get("count_per_country", 100))
    except (TypeError, ValueError):
        raise ValueError("每个国家的评论数量必须是数字。") from None
    if not 1 <= count <= 500:
        raise ValueError("每个国家最多采集 500 条评论。")
    sort = str(result.get("sort") or "newest")
    if sort not in {"newest", "relevant"}:
        raise ValueError("评论排序只支持最新或相关。")
    lower, upper = _optional_date(result.get("date_from")), _optional_date(result.get("date_to"))
    if lower and upper and lower > upper:
        raise ValueError("开始日期不能晚于结束日期。")
    result.update(platform=platform, app_id=app_id, countries=concrete,
                  count_per_country=count, sort=sort, requested_countries=requested)
    return result


def collect(payload: dict) -> dict:
    """Collect store materials with no project/DB dependency.

    Omit root for native collection. root explicitly selects legacy desktop
    modules/configuration. Native translation requires a named provider.
    """
    if not isinstance(payload, dict):
        raise ValueError("采集参数必须是 JSON 对象。")
    root = _resolve_legacy_root(payload)
    mode = str(payload.get("mode") or "")
    if mode in {"discovery_search", "discovery_detail"}:
        return _discovery(payload, root)
    if mode == "translate":
        kwargs = {} if root is not None else {"provider": payload.get("translation_provider")}
        return _translate_items(payload.get("items") or [], root, int(payload.get("batch_size", 20)), **kwargs)
    if mode not in {"", "collect", "reviews"}:
        raise ValueError("不支持的采集模式。")
    request = _normalized_collection_request(payload)
    if root is not None:
        sys.path.insert(0, str(root))
        from app import scrapers as scraper_module
    else:
        from competitor_collector import scrapers as scraper_module
    scrape_app_store = scraper_module.scrape_app_store
    scrape_google_play = scraper_module.scrape_google_play
    google_languages = getattr(scraper_module, "GOOGLE_LANGS", {})
    platform, app_id = request["platform"], request["app_id"]
    countries, count = request["countries"], request["count_per_country"]
    translate = bool(request.get("translate", False))
    if translate and root is None and request.get("translation_provider") not in {"google", "openai"}:
        raise ValueError("请明确指定 translation_provider：google 或 openai。")
    warnings: list[str] = []
    if "global" in request["requested_countries"]:
        warnings.append("全球已展开为 US、GB、DE、JP、IN、ID、BR、SA 八个预设市场，并非所有国家。")
    listing = None
    if request.get("collect_listing"):
        try:
            primary_country = _listing_country(request, countries)
            if platform == "google_play":
                listing = _google_listing(app_id, primary_country, google_languages.get(primary_country, "en"))
            else:
                listing = _app_store_listing(app_id, primary_country, warnings)
            if listing:
                listing["collected_at"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
                output_value = str(request.get("output_dir") or "").strip()
                if output_value and request.get("download_screenshots", True):
                    output_dir = Path(output_value).expanduser().resolve()
                    listing["screenshot_files"] = _download_screenshots(listing, output_dir, warnings)
                else:
                    listing["screenshot_files"] = []
        except Exception as exc:
            warnings.append(f"商店信息采集失败：{type(exc).__name__}")
            listing = None
    if not request.get("collect_reviews", True):
        reviews = []
    elif platform == "google_play":
        reviews = scrape_google_play(
            app_id, countries, count_per_country=count, sort=request["sort"],
            date_from=_optional_date(request.get("date_from")),
            date_to=_optional_date(request.get("date_to")), warnings=warnings,
        )
    else:
        if count > 100:
            warnings.append("App Store 本次每市场最多 100 条；RSS 不是历史全量接口。")
        reviews = scrape_app_store(
            app_id, countries, count_per_country=min(100, count),
            date_from=_optional_date(request.get("date_from")),
            date_to=_optional_date(request.get("date_to")), translate=False, warnings=warnings,
        )
    rows = [review.model_dump(mode="json") if hasattr(review, "model_dump") else dict(review) for review in reviews]
    rows, filter_stats = _filter_reviews(rows, request)
    if translate and rows:
        kwargs = {} if root is not None else {"provider": request.get("translation_provider")}
        translation = _translate_items(
            [{"text": row.get("original_content") or row.get("content") or "",
              "language": row.get("language") or ""} for row in rows[:500]],
            root, int(request.get("translation_batch_size", 20)), **kwargs,
        )
        for row, value in zip(rows, translation["translations"]):
            if value:
                row["translated_content"] = value
        if len(rows) > 500:
            warnings.append(f"本次只翻译前 500 条评论，其余 {len(rows) - 500} 条未翻译")
        if translation["failed_count"]:
            warnings.append(f"{translation['failed_count']} 条评论翻译失败，原文已保留")
        warnings.extend(translation.get("warnings") or [])
    return {"listing": listing, "reviews": rows, "warnings": warnings, "filter_stats": filter_stats}


def main() -> int:
    payload = {}
    try:
        payload = json.load(sys.stdin)
        result = collect(payload)
        _emit(result)
        return 1 if result.get("error_code") else 0
    except Exception as exc:
        if isinstance(payload, dict) and payload.get("mode") in {"discovery_search", "discovery_detail"}:
            error_type = type(exc).__name__.lower()
            code = "missing_dependency" if isinstance(exc, (ImportError, ModuleNotFoundError)) else "not_found" if "notfound" in error_type else "network_error" if any(word in error_type for word in ("http", "connection", "timeout", "urlerror", "ssl")) else "store_error"
            _emit({"error_code": code})
        else:
            # Validation errors are deliberate safe messages. Imported libraries'
            # arbitrary exception strings may contain proxy credentials.
            _emit({"error": _safe_exception_message(exc)})
        return 1


def _safe_exception_message(error: Exception) -> str:
    """Expose deliberate input messages, never arbitrary provider diagnostics."""
    allowed = {
        "竞品评论工具目录无效，未找到 app/scrapers.py。",
        "采集参数必须是 JSON 对象。", "不支持的采集模式。",
        "只支持 Google Play 或 App Store。", "需要有效的应用 ID。",
        "国家或地区格式无效。", "国家需要两位代码；global 仅指八个预设市场。",
        "至少选择一个具体市场，最多 20 个。", "每个国家的评论数量必须是数字。",
        "每个国家最多采集 500 条评论。", "评论排序只支持最新或相关。",
        "开始日期不能晚于结束日期。", "每次最多翻译 500 条评论。",
        "请明确指定 translation_provider：google 或 openai。",
    }
    if type(error) is ValueError and str(error) in allowed:
        return str(error)
    if isinstance(error, json.JSONDecodeError):
        return "JSON 参数解析失败。"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "缺少当前功能所需依赖，请检查安装。"
    return f"采集服务失败：{type(error).__name__}；未输出可能含凭证的底层错误。"


if __name__ == "__main__":
    _configure_stdio()
    raise SystemExit(main())

