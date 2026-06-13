from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from .models import Article


USER_AGENT = "finance-news-digest/0.1 (+https://github.com/marvinlchen)"
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
TRACKING_PARAMS = {
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element: ET.Element, names: set[str]) -> str:
    for child in element:
        if local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = HTML_TAG_RE.sub(" ", value)
    return WHITESPACE_RE.sub(" ", value).strip()


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def normalize_url(value: str) -> str:
    value = html.unescape(value or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    query = [
        (key, item)
        for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            urllib.parse.urlencode(query),
            "",
        )
    )


def fetch_bytes(url: str, retries: int = 3, timeout: int = 25) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def parse_feed(data: bytes, source_config: dict[str, Any]) -> list[Article]:
    root = ET.fromstring(data)
    entries = [
        element
        for element in root.iter()
        if local_name(element.tag) in {"item", "entry"}
    ]
    articles: list[Article] = []
    for entry in entries:
        title = clean_text(child_text(entry, {"title"}))
        url = child_text(entry, {"link"})
        if not url:
            for child in entry:
                if local_name(child.tag) == "link" and child.attrib.get("href"):
                    url = child.attrib["href"]
                    break
        url = normalize_url(url)
        published = parse_date(
            child_text(entry, {"pubdate", "published", "updated", "date"})
        )
        if not title or not url or published is None:
            continue
        source = clean_text(child_text(entry, {"source"})) or source_config["name"]
        description = clean_text(
            child_text(entry, {"description", "summary", "content", "encoded"})
        )
        article_id = hashlib.sha256(f"{url}\n{title}".encode()).hexdigest()[:20]
        articles.append(
            Article(
                article_id=article_id,
                title=title,
                url=url,
                source=source,
                published_at=published,
                description=description[:1200],
                category=source_config.get("category", "finance"),
                source_weight=int(source_config.get("weight", 5)),
                topics=list(source_config.get("topics", [])),
                topic_binding=source_config.get("topic_binding", "keyword_required"),
                countries=list(source_config.get("countries", [])),
                country_binding=source_config.get(
                    "country_binding", "keyword_required"
                ),
            )
        )
    return articles


def nested_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return clean_text(value.get("cdata!", ""))
    return ""


def parse_world_bank_news(data: bytes, source_config: dict[str, Any]) -> list[Article]:
    payload = json.loads(data)
    documents = payload.get("documents", {})
    if not isinstance(documents, dict):
        return []
    articles: list[Article] = []
    for document in documents.values():
        if not isinstance(document, dict):
            continue
        title = nested_text(document.get("title"))
        url = normalize_url(document.get("url", ""))
        published = parse_date(document.get("lnchdt", ""))
        if not title or not url or published is None:
            continue
        description = nested_text(document.get("descr")) or nested_text(
            document.get("content_1000")
        )
        article_id = hashlib.sha256(f"{url}\n{title}".encode()).hexdigest()[:20]
        articles.append(
            Article(
                article_id=article_id,
                title=title,
                url=url,
                source=source_config["name"],
                published_at=published,
                description=description[:1200],
                category=source_config.get("category", "finance"),
                source_weight=int(source_config.get("weight", 5)),
                topics=list(source_config.get("topics", [])),
                topic_binding=source_config.get("topic_binding", "keyword_required"),
                countries=list(source_config.get("countries", [])),
                country_binding=source_config.get(
                    "country_binding", "keyword_required"
                ),
            )
        )
    return articles


def fetch_feed(source_config: dict[str, Any]) -> list[Article]:
    data = fetch_bytes(source_config["url"])
    provider = source_config.get("provider", "rss")
    if provider == "rss":
        return parse_feed(data, source_config)
    if provider == "world_bank_news":
        return parse_world_bank_news(data, source_config)
    raise ValueError(f"unsupported source provider: {provider}")
