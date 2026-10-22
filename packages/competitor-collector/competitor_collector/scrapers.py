"""Pure store-review collectors extracted from the local competitor-analysis-platform.

Only collection logic is included. No desktop configuration, analysis, storage or UI.
Source project did not declare a license in the inspected local checkout.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

from dataclasses import asdict, dataclass

@dataclass
class Review:
    """Compatibility record; independent of Pydantic and any project database."""

    review_id: str
    content: str
    score: float | None = None
    published_at: str | None = None
    market: str | None = None
    language: str | None = None
    version: str | None = None
    source: str = "upload"
    platform: str = "upload"
    app_id: str | None = None
    thumbs_up_count: int | None = None
    user_name: str | None = None
    title: str | None = None
    original_content: str | None = None
    translated_content: str | None = None
    reply_content: str | None = None
    reply_at: str | None = None

    def model_dump(self, *, mode: str = "json") -> dict:
        return asdict(self)


GOOGLE_COUNTRIES = [
    "us",
    "gb",
    "ca",
    "au",
    "de",
    "fr",
    "it",
    "es",
    "br",
    "mx",
    "in",
    "jp",
    "kr",
    "id",
    "th",
    "vn",
    "tr",
    "ru",
    "sg",
    "ae",
]
GOOGLE_LANGS = {
    "us": "en",
    "gb": "en",
    "ca": "en",
    "au": "en",
    "de": "de",
    "fr": "fr",
    "it": "it",
    "es": "es",
    "br": "pt",
    "mx": "es",
    "in": "en",
    "jp": "ja",
    "kr": "ko",
    "id": "id",
    "th": "th",
    "vn": "vi",
    "tr": "tr",
    "ru": "ru",
    "sg": "en",
    "ae": "ar",
}
GOOGLE_LANGS.update(
    {
        "ph": "en",
        "my": "ms",
        "tw": "zh-TW",
        "hk": "zh-TW",
        "sa": "ar",
        "pl": "pl",
        "nl": "nl",
        "se": "sv",
        "no": "no",
        "dk": "da",
        "fi": "fi",
        "za": "en",
        "ng": "en",
        "eg": "ar",
        "ar": "es",
        "co": "es",
        "cl": "es",
        "pe": "es",
        "pk": "en",
        "bd": "bn",
        "pt": "pt",
        "ro": "ro",
        "hu": "hu",
        "cz": "cs",
        "ua": "uk",
        "il": "he",
        "nz": "en",
        "at": "de",
        "ch": "de",
        "be": "nl",
    }
)
APP_STORE_COUNTRIES = {
    "us": "美国",
    "gb": "英国",
    "au": "澳大利亚",
    "ca": "加拿大",
    "in": "印度",
    "jp": "日本",
    "kr": "韩国",
    "de": "德国",
    "fr": "法国",
    "br": "巴西",
    "mx": "墨西哥",
    "id": "印度尼西亚",
    "th": "泰国",
    "vn": "越南",
    "ph": "菲律宾",
    "sg": "新加坡",
    "my": "马来西亚",
    "tw": "台湾",
    "hk": "香港",
    "sa": "沙特阿拉伯",
    "ae": "阿联酋",
    "tr": "土耳其",
    "ru": "俄罗斯",
    "it": "意大利",
    "es": "西班牙",
    "pl": "波兰",
    "nl": "荷兰",
    "se": "瑞典",
    "no": "挪威",
    "dk": "丹麦",
    "fi": "芬兰",
    "za": "南非",
    "ng": "尼日利亚",
    "eg": "埃及",
    "ar": "阿根廷",
    "co": "哥伦比亚",
    "cl": "智利",
    "pe": "秘鲁",
    "pk": "巴基斯坦",
    "bd": "孟加拉国",
    "pt": "葡萄牙",
    "ro": "罗马尼亚",
    "hu": "匈牙利",
    "cz": "捷克",
    "ua": "乌克兰",
    "il": "以色列",
    "nz": "新西兰",
    "at": "奥地利",
    "ch": "瑞士",
    "be": "比利时",
}


def _in_date_range(value: Any, date_from: date | None, date_to: date | None) -> bool:
    if not value:
        return True
    current = value.date() if isinstance(value, datetime) else value
    return not ((date_from and current < date_from) or (date_to and current > date_to))


def scrape_google_play(
    package_id: str,
    countries: list[str],
    count_per_country: int = 300,
    sort: str = "newest",
    date_from: date | None = None,
    date_to: date | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    warnings: list[str] | None = None,
) -> list[Review]:
    try:
        from google_play_scraper import Sort, reviews
    except ImportError as exc:
        raise RuntimeError("未安装 google-play-scraper") from exc
    warnings = warnings if warnings is not None else []
    order = Sort.NEWEST if sort == "newest" else Sort.MOST_RELEVANT
    result: list[Review] = []
    seen: set[str] = set()
    for index, country in enumerate(countries):
        country = country.lower()
        lang = GOOGLE_LANGS.get(country, "en")
        token = None
        fetched = 0
        pages = 0
        market_seen: set[str] = set()
        while fetched < count_per_country and pages < 50:
            batch = min(200, count_per_country - fetched)
            try:
                rows, token = reviews(
                    package_id,
                    lang=lang,
                    country=country,
                    sort=order,
                    count=batch,
                    continuation_token=token,
                )
            except Exception as exc:  # noqa: BLE001 - isolate each market
                warnings.append(f"{country} 抓取中断：{type(exc).__name__}；已保留成功页")
                break
            pages += 1
            if not rows:
                break
            for row in rows:
                review_id = str(row.get("reviewId") or "")
                content = str(row.get("content") or "").strip()
                if not content:
                    continue
                key = f"google-play:{review_id or hashlib.sha1(content.encode()).hexdigest()}"
                at = row.get("at")
                if not _in_date_range(at, date_from, date_to) or key in market_seen:
                    continue
                market_seen.add(key)
                fetched += 1
                if key in seen:
                    continue
                seen.add(key)
                result.append(
                    Review(
                        review_id=review_id or hashlib.sha1(content.encode()).hexdigest()[:12],
                        content=content,
                        original_content=content,
                        score=float(row.get("score")) if row.get("score") is not None else None,
                        published_at=at.isoformat() if at else None,
                        market=country.upper(),
                        language=lang,
                        version=str(row.get("reviewCreatedVersion") or "") or None,
                        source=f"google-play:{country}/{lang}",
                        platform="google_play",
                        app_id=package_id,
                        thumbs_up_count=int(row.get("thumbsUpCount") or 0),
                        user_name=str(row.get("userName") or "") or None,
                        reply_content=str(row.get("replyContent") or "") or None,
                        reply_at=row.get("repliedAt").isoformat() if row.get("repliedAt") else None,
                    )
                )
            if not token:
                break
            if (
                sort == "newest"
                and date_from
                and all(row.get("at") and row["at"].date() < date_from for row in rows)
            ):
                break
        if pages >= 50 and token and fetched < count_per_country:
            warnings.append(f"{country} 已达 50 页扫描上限，所选范围可能不完整")
        if on_progress:
            on_progress(country, index + 1, len(countries))
    return result


def _translate(text: str) -> str:
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="zh-CN").translate(text[:4500]) or ""
    except Exception:  # noqa: BLE001 - translation is optional and must not block scraping
        return "[翻译失败]"


def _app_store_country(
    app_id: str,
    country: str,
    count: int,
    date_from: date | None,
    date_to: date | None,
    translate: bool,
    warnings: list[str] | None = None,
) -> list[Review]:
    import requests

    url_base = f"https://itunes.apple.com/{country}/rss/customerreviews/page={{page}}/id={app_id}/sortby=mostrecent/json"
    rows: list[Review] = []
    for page in range(1, 11):
        try:
            response = requests.get(
                url_base.format(page=page), headers={"User-Agent": "Mozilla/5.0"}, timeout=15
            )
            response.raise_for_status()
            entries = response.json().get("feed", {}).get("entry", [])
        except (requests.RequestException, ValueError) as exc:
            if warnings is None:
                raise
            warnings.append(f"{country} 第 {page} 页失败：{type(exc).__name__}；保留前页")
            return rows
        if isinstance(entries, dict):
            entries = [entries]
        if entries and "im:rating" not in entries[0]:
            entries = entries[1:]
        entries = [entry for entry in entries if "im:rating" in entry]
        if not entries:
            break
        for entry in entries:
            rating = float(entry.get("im:rating", {}).get("label", 0) or 0)
            content = entry.get("content", {}).get("label", "").strip()
            title = entry.get("title", {}).get("label", "").strip()
            full = f"{title}：{content}" if title and content else (title or content)
            if not full:
                continue
            updated = entry.get("updated", {}).get("label", "")
            parsed = None
            try:
                parsed = datetime.fromisoformat(updated[:10]).date() if updated else None
            except ValueError:
                pass
            if parsed and not _in_date_range(parsed, date_from, date_to):
                continue
            rid = str(
                entry.get("id", {}).get("label")
                or hashlib.sha1(f"{country}:{full}:{updated}".encode()).hexdigest()[:16]
            )
            rows.append(
                Review(
                    review_id=rid,
                    content=full,
                    original_content=full,
                    translated_content=_translate(full) if translate else None,
                    score=rating,
                    published_at=parsed.isoformat() if parsed else None,
                    market=country.upper(),
                    language=None,
                    version=entry.get("im:version", {}).get("label"),
                    source=f"app-store:{country}",
                    platform="app_store",
                    app_id=app_id,
                    thumbs_up_count=int(entry.get("im:voteSum", {}).get("label", 0) or 0),
                    user_name=entry.get("author", {}).get("name", {}).get("label"),
                )
            )
            if len(rows) >= count:
                return rows
    return rows


def scrape_app_store(
    app_id: str,
    countries: list[str],
    count_per_country: int = 50,
    date_from: date | None = None,
    date_to: date | None = None,
    translate: bool = False,
    on_progress: Callable[[str, int, int], None] | None = None,
    warnings: list[str] | None = None,
) -> list[Review]:
    result: list[Review] = []
    warnings = warnings if warnings is not None else []
    with ThreadPoolExecutor(max_workers=min(5, max(1, len(countries)))) as pool:
        futures = {
            pool.submit(
                _app_store_country,
                app_id,
                country.lower(),
                count_per_country,
                date_from,
                date_to,
                translate,
                warnings,
            ): country
            for country in countries
        }
        for index, future in enumerate(as_completed(futures), 1):
            country = futures[future]
            try:
                result.extend(future.result())
            except Exception as exc:  # noqa: BLE001 - retain other markets
                warnings.append(f"{country} 抓取失败：{type(exc).__name__}")
            if on_progress:
                on_progress(country, index, len(countries))
    return result


