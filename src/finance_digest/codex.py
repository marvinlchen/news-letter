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
from .ranking import TOPICS, is_article_eligible_for_topic, topic_top_articles


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
    return {"date": target_date.isoformat(), "topics": topics}


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
            }
            for article in selected_articles
        ],
    }
    full_prompt = f"{prompt}\n{json.dumps(candidates, ensure_ascii=False, indent=2)}\n"
    schema = project_root / "schemas/digest.schema.json"
    with tempfile.TemporaryDirectory(prefix="finance-digest-codex-") as temp_dir:
        output_path = Path(temp_dir) / "digest.json"
        command = [
            codex_bin,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(output_path),
            "-",
        ]
        completed = subprocess.run(
            command,
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
        digest = json.loads(output_path.read_text(encoding="utf-8"))
        return validate_digest(digest, target_date, selected_articles)
