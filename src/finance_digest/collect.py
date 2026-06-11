from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .feeds import fetch_feed
from .models import Article
from .ranking import score_articles


TIMEZONE = ZoneInfo("Asia/Singapore")


def load_sources(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [source for source in payload["sources"] if source.get("enabled", True)]


def in_target_date(article: Article, target_date: date) -> bool:
    start = datetime.combine(target_date, time.min, tzinfo=TIMEZONE)
    end = start + timedelta(days=1)
    published = article.published_at.astimezone(TIMEZONE)
    return start <= published < end


def collect_articles(
    sources: list[dict[str, Any]], target_date: date
) -> tuple[list[Article], list[dict[str, str]]]:
    articles: list[Article] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as executor:
        futures = {executor.submit(fetch_feed, source): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                articles.extend(
                    article
                    for article in future.result()
                    if in_target_date(article, target_date)
                )
            except Exception as exc:  # A failed source must not fail the daily digest.
                errors.append({"source": source["name"], "error": str(exc)})
    return score_articles(articles), errors

