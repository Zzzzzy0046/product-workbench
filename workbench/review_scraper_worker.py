"""Bridge to the existing desktop competitor review scraper.

The workbench calls the scraper and its local AI configuration, but never the
desktop tool's analysis pipeline or UI.  Review translation is an explicit,
source-preserving operation: the original review remains untouched and the
Chinese result is written to ``translated_content``.
"""
from __future__ import annotations

import json
import mimetypes
import re
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


def _translate_ai_batch(texts: list[str], root: Path) -> list[str]:
    """Translate one aligned batch with the desktop tool's local DeepSeek config."""
    sys.path.insert(0, str(root))
    from app.config import settings
    from openai import OpenAI

    if not settings.deepseek_ready:
        raise RuntimeError("桌面工具尚未配置可用的 DeepSeek。")
    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=str(settings.deepseek_base_url).rstrip("/"),
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
        model=settings.deepseek_model,
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


def _translate_items(items: list[dict], root: Path, batch_size: int = 20) -> dict:
    """Translate unique non-Chinese review texts and retain index alignment."""
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
    provider = "deepseek"
    for offset in range(0, len(unique_texts), max(1, min(50, int(batch_size)))):
        batch = unique_texts[offset : offset + max(1, min(50, int(batch_size)))]
        values, used_fallback = _translate_resilient(batch, root, warnings)
        if used_fallback:
            provider = "deepseek+google-fallback"
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
        "provider": provider,
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
        "contains_ads": bool(raw.get("containsAds") or raw.get("adSupported")),
        "offers_iap": bool(raw.get("offersIAP")),
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
    short_description = str(raw.get("subtitle") or raw.get("promotionalText") or "")
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
        "source_url": str(raw.get("trackViewUrl") or f"https://apps.apple.com/{country}/app/id{app_id}"),
        "privacy_policy_url": "",
        "icon_url": str(raw.get("artworkUrl512") or raw.get("artworkUrl100") or ""),
        "screenshot_urls": [str(item) for item in screenshots if str(item).startswith("http")][:20],
    }


def _download_screenshots(listing: dict, output_dir: Path, warnings: list[str]) -> list[str]:
    import requests

    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    extensions = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
    for index, url in enumerate(listing.get("screenshot_urls") or [], 1):
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            extension = extensions.get(content_type)
            if not extension:
                guessed = mimetypes.guess_extension(content_type) or Path(url.split("?", 1)[0]).suffix.lower()
                extension = guessed if guessed in {".png", ".jpg", ".jpeg", ".webp"} else ""
            if not extension or not response.content or len(response.content) > 12 * 1024 * 1024:
                raise ValueError("图片格式不支持或超过 12 MB")
            name = f"{index:02d}{extension}"
            (output_dir / name).write_bytes(response.content)
            saved.append(name)
        except Exception as exc:  # noqa: BLE001 - one failed image must not abort the listing
            warnings.append(f"商店截图 {index} 下载失败：{type(exc).__name__}")
    return saved


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        root = Path(str(payload.get("root", ""))).expanduser().resolve()
        if not root.is_dir() or not (root / "app" / "scrapers.py").is_file():
            raise ValueError("竞品评论工具目录无效，未找到 app/scrapers.py。")
        if str(payload.get("mode") or "").strip() == "translate":
            items = payload.get("items") or []
            result = _translate_items(items, root, int(payload.get("batch_size", 20)))
            _emit(result)
            return 0
        sys.path.insert(0, str(root))
        from app import scrapers as scraper_module

        scrape_app_store = scraper_module.scrape_app_store
        scrape_google_play = scraper_module.scrape_google_play
        google_languages = getattr(scraper_module, "GOOGLE_LANGS", {})

        platform = str(payload.get("platform", "google_play")).strip()
        app_id = str(payload.get("app_id", "")).strip()
        countries = [str(item).strip().lower() for item in payload.get("countries", []) if str(item).strip()]
        count = max(1, min(500, int(payload.get("count_per_country", 100))))
        warnings: list[str] = []
        if not app_id or not countries:
            raise ValueError("需要提供应用 ID 和至少一个国家或地区。")
        listing = None
        if payload.get("collect_listing"):
            try:
                primary_country = countries[0]
                if platform == "google_play":
                    listing = _google_listing(app_id, primary_country, google_languages.get(primary_country, "en"))
                elif platform == "app_store":
                    listing = _app_store_listing(app_id, primary_country, warnings)
                if listing:
                    listing["collected_at"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
                    output_value = str(payload.get("output_dir") or "").strip()
                    if output_value:
                        output_dir = Path(output_value).expanduser().resolve()
                        listing["screenshot_files"] = _download_screenshots(listing, output_dir, warnings)
            except Exception as exc:  # noqa: BLE001 - reviews can still be useful when listing capture fails
                warnings.append(f"商店信息采集失败：{type(exc).__name__}：{str(exc)[:160]}")
                listing = None
        if platform == "google_play":
            reviews = scrape_google_play(
                app_id,
                countries,
                count_per_country=count,
                sort=str(payload.get("sort", "newest")),
                date_from=_optional_date(payload.get("date_from")),
                date_to=_optional_date(payload.get("date_to")),
                warnings=warnings,
            )
        elif platform == "app_store":
            reviews = scrape_app_store(
                app_id,
                countries,
                count_per_country=min(100, count),
                date_from=_optional_date(payload.get("date_from")),
                date_to=_optional_date(payload.get("date_to")),
                translate=False,
                warnings=warnings,
            )
        else:
            raise ValueError("只支持 Google Play 或 App Store。")
        rows = []
        for review in reviews:
            if hasattr(review, "model_dump"):
                rows.append(review.model_dump(mode="json"))
            else:
                rows.append(dict(review))
        if payload.get("translate") and rows:
            translation = _translate_items(
                [
                    {
                        "text": row.get("original_content") or row.get("content") or "",
                        "language": row.get("language") or "",
                    }
                    for row in rows[:500]
                ],
                root,
                int(payload.get("translation_batch_size", 20)),
            )
            for row, value in zip(rows, translation["translations"]):
                if value:
                    row["translated_content"] = value
            if len(rows) > 500:
                warnings.append(f"本次只翻译前 500 条评论，其余 {len(rows) - 500} 条可入库后继续补翻译")
            if translation["failed_count"]:
                warnings.append(f"{translation['failed_count']} 条评论翻译失败，原文已保留")
            warnings.extend(translation.get("warnings") or [])
        _emit({"listing": listing, "reviews": rows, "warnings": warnings})
        return 0
    except Exception as exc:  # noqa: BLE001 - serialized for the caller
        _emit({"error": str(exc)[:1000]})
        return 1


if __name__ == "__main__":
    _configure_stdio()
    raise SystemExit(main())
