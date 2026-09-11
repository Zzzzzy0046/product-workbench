"""Bridge to the existing desktop competitor review scraper.

The workbench intentionally calls only the scraper functions.  Analysis,
translation and the desktop tool's UI remain outside this process.
"""
from __future__ import annotations

import json
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


def _optional_date(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}，请使用 YYYY-MM-DD。") from exc


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        root = Path(str(payload.get("root", ""))).expanduser().resolve()
        if not root.is_dir() or not (root / "app" / "scrapers.py").is_file():
            raise ValueError("竞品评论工具目录无效，未找到 app/scrapers.py。")
        sys.path.insert(0, str(root))
        from app.scrapers import scrape_app_store, scrape_google_play

        platform = str(payload.get("platform", "google_play")).strip()
        app_id = str(payload.get("app_id", "")).strip()
        countries = [str(item).strip().lower() for item in payload.get("countries", []) if str(item).strip()]
        count = max(1, min(500, int(payload.get("count_per_country", 100))))
        warnings: list[str] = []
        if not app_id or not countries:
            raise ValueError("需要提供应用 ID 和至少一个国家或地区。")
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
        _emit({"reviews": rows, "warnings": warnings})
        return 0
    except Exception as exc:  # noqa: BLE001 - serialized for the caller
        _emit({"error": str(exc)[:1000]})
        return 1


if __name__ == "__main__":
    _configure_stdio()
    raise SystemExit(main())
