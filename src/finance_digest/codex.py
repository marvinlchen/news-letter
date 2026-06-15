from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .models import Article
from .ranking import (
    COUNTRIES,
    TOPICS,
    country_top_articles,
    is_article_eligible_for_country,
    is_article_eligible_for_topic,
    topic_top_articles,
)


CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def validate_text_length(
    item: dict[str, Any], field: str, minimum: int, maximum: int
) -> None:
    value = item.get(field)
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError(
            f"Codex returned invalid {field} length; expected {minimum}-{maximum}"
        )


def validate_items(
    raw_items: Any,
    articles: list[Article],
    maximum: int,
    allowed_topic: str | None = None,
    allowed_country: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list) or len(raw_items) > maximum:
        raise ValueError("Codex returned an invalid item count")
    articles_by_url = {article.url: article for article in articles}
    seen_urls: set[str] = set()
    items: list[dict[str, Any]] = []
    for rank, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError("Codex returned a non-object item")
        url = raw_item.get("url")
        if url not in articles_by_url:
            raise ValueError(f"Codex returned an unknown candidate URL: {url}")
        if url in seen_urls:
            raise ValueError(f"Codex returned a duplicate candidate URL: {url}")
        seen_urls.add(url)
        article = articles_by_url[url]
        if allowed_topic and not is_article_eligible_for_topic(article, allowed_topic):
            raise ValueError(
                f"Codex returned an article outside topic {allowed_topic}: {url}"
            )
        if allowed_country and not is_article_eligible_for_country(
            article, allowed_country
        ):
            raise ValueError(
                f"Codex returned an article outside country {allowed_country}: {url}"
            )
        validate_text_length(raw_item, "title_zh", 4, 60)
        validate_text_length(raw_item, "summary_zh", 60, 200)
        if not CJK_RE.search(raw_item["title_zh"]):
            raise ValueError("Codex returned a non-Chinese title_zh")
        if not CJK_RE.search(raw_item["summary_zh"]):
            raise ValueError("Codex returned a non-Chinese summary_zh")
        item = dict(raw_item)
        item.update(
            {
                "rank": rank,
                "title_original": article.title,
                "category": article.category,
                "source": article.source,
                "published_at": article.published_at.isoformat(),
                "url": article.url,
            }
        )
        items.append(item)
    return items


def validate_digest(
    digest: dict[str, Any], target_date: date, articles: list[Article]
) -> dict[str, Any]:
    if digest.get("date") != target_date.isoformat():
        raise ValueError("Codex returned the wrong digest date")
    raw_topics = digest.get("topics")
    if not isinstance(raw_topics, list) or len(raw_topics) != len(TOPICS):
        raise ValueError("Codex returned an invalid topic count")
    topics = []
    seen_topic_keys: set[str] = set()
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            raise ValueError("Codex returned a non-object topic")
        key = raw_topic.get("key")
        if key not in TOPICS or key in seen_topic_keys:
            raise ValueError(f"Codex returned an invalid topic key: {key}")
        seen_topic_keys.add(key)
        topics.append(
            {
                "key": key,
                "name_zh": TOPICS[key]["name_zh"],
                "items": validate_items(raw_topic.get("items"), articles, 3, key),
            }
        )
    topics.sort(key=lambda topic: list(TOPICS).index(topic["key"]))
    raw_countries = digest.get("countries")
    if not isinstance(raw_countries, list) or len(raw_countries) != len(COUNTRIES):
        raise ValueError("Codex returned an invalid country count")
    countries = []
    seen_country_keys: set[str] = set()
    for raw_country in raw_countries:
        if not isinstance(raw_country, dict):
            raise ValueError("Codex returned a non-object country")
        key = raw_country.get("key")
        if key not in COUNTRIES or key in seen_country_keys:
            raise ValueError(f"Codex returned an invalid country key: {key}")
        seen_country_keys.add(key)
        countries.append(
            {
                "key": key,
                "name_zh": COUNTRIES[key]["name_zh"],
                "items": validate_items(
                    raw_country.get("items"),
                    articles,
                    3,
                    allowed_country=key,
                ),
            }
        )
    countries.sort(key=lambda country: list(COUNTRIES).index(country["key"]))
    return {
        "date": target_date.isoformat(),
        "topics": topics,
        "countries": countries,
    }


def run_codex(
    project_root: Path,
    target_date: date,
    articles: list[Article],
    codex_bin: str = "codex",
) -> dict[str, Any]:
    prompt = (project_root / "prompts/select_topics.md").read_text(encoding="utf-8")
    selected_articles: list[Article] = []
    selected_urls = {article.url for article in selected_articles}
    for topic_articles in topic_top_articles(articles, limit=12).values():
        for article in topic_articles:
            if article.url not in selected_urls:
                selected_articles.append(article)
                selected_urls.add(article.url)
    for country_articles in country_top_articles(articles, limit=12).values():
        for article in country_articles:
            if article.url not in selected_urls:
                selected_articles.append(article)
                selected_urls.add(article.url)
    candidates = {
        "date": target_date.isoformat(),
        "candidates": [
            {
                **article.to_dict(),
                "matched_topics": [
                    topic
                    for topic in TOPICS
                    if is_article_eligible_for_topic(article, topic)
                ],
                "matched_countries": [
                    country
                    for country in COUNTRIES
                    if is_article_eligible_for_country(article, country)
                ],
            }
            for article in selected_articles
        ],
    }
    full_prompt = f"{prompt}\n{json.dumps(candidates, ensure_ascii=False, indent=2)}\n"
    schema = project_root / "schemas/digest.schema.json"
    schema = project_root / "schemas/digest.schema.json"
    completed = subprocess.run(
        [
            codex_bin,
            "exec",
            "--experimental-json",
            "--sandbox=read-only",
            "--skip-git-repo-check",
            "-",
        ],
        cwd=project_root,
        env=os.environ.copy(),
        input=full_prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"codex exited {completed.returncode}: {completed.stderr[-2000:]}"
        )
    # Parse --experimental-json output: one JSON object per line
    report_json_str = ""
    for line in (completed.stdout or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "item.completed" and obj.get("item", {}).get("type") == "agent_message":
            text = obj["item"].get("text", "")
            report_json_str = text
    if not report_json_str:
        raise RuntimeError(f"codex returned no agent_message: {completed.stdout[-1000:]}")
    # Extract JSON from the text (may be wrapped in markdown)
    match = re.search(r"", report_json_str)
    if match:
        report_json_str = match.group(1)
    else:
        # Try to find JSON object boundaries
        start_idx = report_json_str.find("{")
        end_idx = report_json_str.rfind("}")
        if start_idx != -1 and end_idx != -1:
            report_json_str = report_json_str[start_idx:end_idx+1]
    report = json.loads(report_json_str)
    return validate_digest(report, target_date, selected_articles)
