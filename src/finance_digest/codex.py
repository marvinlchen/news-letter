from __future__ import annotations
import re

import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable

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


def is_codebuddy_bin(codex_bin: str) -> bool:
    name = Path(codex_bin).name.lower()
    return name in {"codebuddy", "cbc"} or "codebuddy" in name


def extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in {
                "text",
                "output_text",
            }:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        for key in ("text", "content", "result", "message"):
            text = extract_text_from_content(content.get(key))
            if text:
                return text
    return ""


def extract_codebuddy_text(output: str) -> str:
    text = output.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, list):
        for message in reversed(payload):
            if isinstance(message, dict) and message.get("role") == "assistant":
                content = extract_text_from_content(message.get("content"))
                if content:
                    return content.strip()
        for message in reversed(payload):
            content = extract_text_from_content(message)
            if content:
                return content.strip()
    if isinstance(payload, dict):
        for key in ("result", "response", "text", "content", "message"):
            content = extract_text_from_content(payload.get(key))
            if content:
                return content.strip()
        messages = payload.get("messages")
        if isinstance(messages, list):
            return extract_codebuddy_text(json.dumps(messages, ensure_ascii=False))
    return text


def extract_codex_exec_text(output: str) -> str:
    report_text = ""
    for line in (output or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            obj.get("type") == "item.completed"
            and obj.get("item", {}).get("type") == "agent_message"
        ):
            report_text = obj["item"].get("text", "")
    return report_text.strip()


def run_agent_text(
    project_root: Path,
    prompt: str,
    codex_bin: str,
    timeout: int,
    model: str = "",
) -> str:
    if is_codebuddy_bin(codex_bin):
        completed = subprocess.run(
            [
                codex_bin,
                "-p",
                "--output-format",
                "json",
                "--tools",
                "",
                *([f"--model={model}"] if model else []),
                prompt,
            ],
            cwd=project_root,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"{codex_bin} exited {completed.returncode}: {completed.stderr[-2000:]}"
            )
        text = extract_codebuddy_text(completed.stdout)
        if not text:
            raise RuntimeError(f"{codex_bin} returned empty text")
        return text

    output_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False) as output_file:
            output_path = output_file.name
        completed = subprocess.run(
            [
                codex_bin,
                "exec",
                "--skip-git-repo-check",
                "--output-last-message",
                output_path,
                prompt,
            ],
            cwd=project_root,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"{codex_bin} exited {completed.returncode}: {completed.stderr[-2000:]}"
            )
        text = Path(output_path).read_text(encoding="utf-8").strip()
        if not text:
            text = extract_codex_exec_text(completed.stdout)
        if not text:
            raise RuntimeError(f"{codex_bin} returned empty text")
        return text
    finally:
        if output_path:
            try:
                os.unlink(output_path)
            except OSError:
                pass


def protocol_field(value: Any, limit: int = 700) -> str:
    text = str(value or "")
    text = re.sub(r"[\t\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def protocol_lines(raw: str) -> list[str]:
    text = raw.strip()
    match = re.search(r"```(?:text|tsv)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        text = match.group(1)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if not line or line.startswith("```"):
            continue
        lines.append(line)
    return lines


def run_protocol_with_retry(
    project_root: Path,
    prompt: str,
    codex_bin: str,
    timeout: int,
    parser: Callable[[str], dict[str, Any]],
    label: str,
    max_attempts: int = 2,
    model: str = "",
) -> dict[str, Any]:
    last_error: Exception | None = None
    current_prompt = prompt
    for attempt in range(max_attempts):
        raw = run_agent_text(project_root, current_prompt, codex_bin, timeout, model)
        try:
            return parser(raw)
        except Exception as exc:
            last_error = exc
            print(
                f"[WARN] {label} protocol parse failed on attempt {attempt + 1}: {exc}",
                file=sys.stderr,
            )
            if attempt + 1 < max_attempts:
                current_prompt = (
                    prompt
                    + "\n\n## Retry output requirements\n"
                    + "The previous output could not be parsed. Output the complete report again as pure TAB-separated text records only. "
                    + "Do not output JSON, Markdown, code fences, explanations, or blank lines. "
                    + "Use only candidate IDs from the candidate lines."
                )
    assert last_error is not None
    raise last_error


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
            print(f"[WARNING] Unknown candidate URL: {url}, skipping", file=__import__("sys").stderr)
            continue
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


def build_daily_protocol_prompt(
    project_root: Path,
    target_date: date,
    articles: list[Article],
) -> tuple[str, dict[str, tuple[str, str, Article]]]:
    prompt = (project_root / "prompts/select_topics.md").read_text(encoding="utf-8")
    topic_candidates = topic_top_articles(articles, limit=12)
    country_candidates = country_top_articles(articles, limit=12)
    catalog: dict[str, tuple[str, str, Article]] = {}
    lines = [
        prompt.strip(),
        "",
        f"REPORT_DATE\t{target_date.isoformat()}",
        "",
        "Candidate lines follow. They are inputs, not output records.",
    ]
    for key in TOPICS:
        for index, article in enumerate(topic_candidates.get(key, []), start=1):
            candidate_id = f"T-{key}-{index}"
            catalog[candidate_id] = ("topic", key, article)
            lines.append(
                "\t".join(
                    [
                        "TOPIC_CANDIDATE",
                        candidate_id,
                        key,
                        article.published_at.isoformat(),
                        protocol_field(article.source, 120),
                        protocol_field(article.title, 220),
                        protocol_field(article.description, 800),
                    ]
                )
            )
    for key in COUNTRIES:
        for index, article in enumerate(country_candidates.get(key, []), start=1):
            candidate_id = f"C-{key}-{index}"
            catalog[candidate_id] = ("country", key, article)
            lines.append(
                "\t".join(
                    [
                        "COUNTRY_CANDIDATE",
                        candidate_id,
                        key,
                        article.published_at.isoformat(),
                        protocol_field(article.source, 120),
                        protocol_field(article.title, 220),
                        protocol_field(article.description, 800),
                    ]
                )
            )
    return "\n".join(lines) + "\n", catalog


def append_daily_protocol_item(
    items: list[dict[str, Any]],
    seen_ids: set[str],
    section_type: str,
    section_key: str,
    candidate_id: str,
    title_zh: str,
    summary_zh: str,
    catalog: dict[str, tuple[str, str, Article]],
    maximum: int,
) -> bool:
    if len(items) >= maximum:
        return False
    entry = catalog.get(candidate_id)
    if entry is None:
        raise ValueError(f"model returned unknown candidate ID: {candidate_id}")
    candidate_type, candidate_key, article = entry
    if candidate_type != section_type or candidate_key != section_key:
        raise ValueError(
            f"model returned candidate {candidate_id} outside {section_type} {section_key}"
        )
    if candidate_id in seen_ids:
        raise ValueError(f"model returned duplicate candidate ID: {candidate_id}")
    raw_item = {"title_zh": title_zh, "summary_zh": summary_zh}
    validate_text_length(raw_item, "title_zh", 4, 60)
    validate_text_length(raw_item, "summary_zh", 60, 200)
    if not CJK_RE.search(title_zh):
        raise ValueError("model returned a non-Chinese title_zh")
    if not CJK_RE.search(summary_zh):
        raise ValueError("model returned a non-Chinese summary_zh")
    seen_ids.add(candidate_id)
    items.append(
        {
            "rank": len(items) + 1,
            "title_zh": title_zh,
            "summary_zh": summary_zh,
            "title_original": article.title,
            "category": article.category,
            "source": article.source,
            "published_at": article.published_at.isoformat(),
            "url": article.url,
        }
    )
    return True



def deduplicate_topics(digest: dict[str, Any]) -> dict[str, Any]:
    """Remove duplicate articles across topic sections.
    
    Each article should appear in at most ONE topic section.
    Deduplication is by URL or by similar title (same story from different sources).
    Keep the first occurrence (most relevant topic).
    """
    seen_urls = set()
    seen_titles: set[str] = set()
    for topic in digest.get("topics", []):
        unique_items = []
        for item in topic.get("items", []):
            url = item.get("url")
            title = item.get("title_original", "")
            # Normalize title for comparison (lowercase, remove spaces/punctuation)
            title_norm = re.sub(r"[^a-z0-9]", "", title.lower())
            
            # Skip if URL already seen
            if url and url in seen_urls:
                continue
            # Skip if very similar title already seen (same story, different source)
            if title_norm and len(title_norm) > 20:
                is_dup = False
                for seen_title in seen_titles:
                    if len(seen_title) > 20 and (
                        title_norm in seen_title or seen_title in title_norm or
                        (len(title_norm) > 30 and seen_title[:30] == title_norm[:30])
                    ):
                        is_dup = True
                        break
                if is_dup:
                    continue
            
            unique_items.append(item)
            if url:
                seen_urls.add(url)
            if title_norm and len(title_norm) > 20:
                seen_titles.add(title_norm)
        topic["items"] = unique_items
    return digest


def parse_daily_protocol(
    raw: str,
    target_date: date,
    catalog: dict[str, tuple[str, str, Article]],
) -> dict[str, Any]:
    topic_items: dict[str, list[dict[str, Any]]] = {key: [] for key in TOPICS}
    country_items: dict[str, list[dict[str, Any]]] = {key: [] for key in COUNTRIES}
    seen_by_section: dict[tuple[str, str], set[str]] = {}
    parsed_count = 0
    for line in protocol_lines(raw):
        if line.startswith("TOPIC\t"):
            parts = line.split("\t", 4)
            if len(parts) != 5:
                raise ValueError(f"invalid TOPIC protocol line: {line}")
            _, key, candidate_id, title_zh, summary_zh = parts
            if key not in TOPICS:
                raise ValueError(f"invalid topic key: {key}")
            if append_daily_protocol_item(
                topic_items[key],
                seen_by_section.setdefault(("topic", key), set()),
                "topic",
                key,
                candidate_id,
                title_zh,
                summary_zh,
                catalog,
                3,
            ):
                parsed_count += 1
        elif line.startswith("COUNTRY\t"):
            parts = line.split("\t", 4)
            if len(parts) != 5:
                raise ValueError(f"invalid COUNTRY protocol line: {line}")
            _, key, candidate_id, title_zh, summary_zh = parts
            if key not in COUNTRIES:
                raise ValueError(f"invalid country key: {key}")
            if append_daily_protocol_item(
                country_items[key],
                seen_by_section.setdefault(("country", key), set()),
                "country",
                key,
                candidate_id,
                title_zh,
                summary_zh,
                catalog,
                3,
            ):
                parsed_count += 1
    if parsed_count == 0:
        raise ValueError("model returned no parseable daily protocol records")
    return {
        "date": target_date.isoformat(),
        "topics": [
            {"key": key, "name_zh": TOPICS[key]["name_zh"], "items": topic_items[key]}
            for key in TOPICS
        ],
        "countries": [
            {
                "key": key,
                "name_zh": COUNTRIES[key]["name_zh"],
                "items": country_items[key],
            }
            for key in COUNTRIES
        ],
    }


def validate_digest(
    digest: dict[str, Any], target_date: date, articles: list[Article]
) -> dict[str, Any]:
    if digest.get("date") != target_date.isoformat():
        raise ValueError("Codex returned the wrong digest date")
    raw_topics = digest.get("topics")
    # Handle both list format (from codex) and dict format (from codebuddy)
    if isinstance(raw_topics, dict):
        raw_topics = [{"key": k, "items": v} for k, v in raw_topics.items()]
        digest["topics"] = raw_topics
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
    # Handle both list format (from codex) and dict format (from codebuddy)
    if isinstance(raw_countries, dict):
        raw_countries = [{"key": k, "items": v} for k, v in raw_countries.items()]
        digest["countries"] = raw_countries
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
    model: str = "",
) -> dict[str, Any]:
    prompt, catalog = build_daily_protocol_prompt(project_root, target_date, articles)
    return run_protocol_with_retry(
        project_root,
        prompt,
        codex_bin,
        900,
        lambda raw: deduplicate_topics(parse_daily_protocol(raw, target_date, catalog)),
        "daily digest",
        model=model,
    )
