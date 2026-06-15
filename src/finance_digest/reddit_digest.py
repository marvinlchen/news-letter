from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .codex import CJK_RE, validate_text_length
from .feeds import clean_text, local_name, parse_date
from .ranking import contains_keyword
from .render import pretty_json, truncate


TIMEZONE = ZoneInfo("Asia/Shanghai")
SELECTION_PROFILE = "multi-industry-value-investing"
USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT",
    "linux:finance-news-digest:v1.0.0 (by /u/marvinlchen)",
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
LOW_SIGNAL_PATTERNS = {
    "beginner",
    "career",
    "certification",
    "certified",
    "confession",
    "exam",
    "funny",
    "hiring",
    "meme",
    "passed the",
    "rate my",
    "resume",
    "roast",
    "salary",
}
SPECULATION_PATTERNS = {
    "day trade",
    "day trading",
    "price prediction",
    "short squeeze",
    "technical analysis",
    "to the moon",
    "what are you buying",
    "yolo",
}
VALUE_INVESTING_TERMS = {
    "backlog": 3,
    "balance sheet": 4,
    "bankruptcy": 4,
    "buyback": 4,
    "cash burn": 4,
    "capital allocation": 5,
    "capital expenditure": 4,
    "capex": 4,
    "cash flow": 5,
    "competition": 3,
    "competitive advantage": 5,
    "contract": 3,
    "cost": 2,
    "customer acquisition": 3,
    "customer retention": 3,
    "debt": 4,
    "dilution": 4,
    "demand": 3,
    "dividend": 4,
    "earnings": 4,
    "free cash flow": 6,
    "gross margin": 5,
    "inventory": 3,
    "leverage": 4,
    "margin": 4,
    "market share": 4,
    "moat": 6,
    "operating leverage": 5,
    "operating margin": 5,
    "pricing power": 6,
    "profit": 4,
    "regulation": 3,
    "return on capital": 6,
    "roic": 6,
    "revenue": 4,
    "supply": 3,
    "unit economics": 6,
    "valuation": 5,
}
TOPIC_INVESTMENT_TERMS = {
    "macroeconomics": {
        "credit": 3,
        "employment": 3,
        "gdp": 4,
        "inflation": 4,
        "interest rate": 4,
        "productivity": 4,
        "recession": 4,
        "tariff": 3,
    },
    "shipping": {
        "charter rate": 5,
        "container rate": 5,
        "fleet": 3,
        "freight rate": 5,
        "orderbook": 4,
        "port": 2,
        "utilization": 4,
    },
    "commodities": {
        "capacity": 4,
        "commodity price": 4,
        "mine": 3,
        "production": 3,
        "reserve": 4,
        "storage": 3,
    },
    "stock_market": {
        "annual report": 4,
        "discounted cash flow": 6,
        "intrinsic value": 6,
        "multiple": 4,
        "s-1": 4,
        "sec filing": 4,
    },
    "technology": {
        "data center": 3,
        "licensing": 3,
        "semiconductor": 3,
        "switching cost": 5,
        "total addressable market": 4,
    },
    "consumer": {
        "advertising cost": 4,
        "average order value": 4,
        "brand": 3,
        "repeat purchase": 5,
        "return rate": 4,
        "same-store sales": 5,
    },
    "cloud_infra": {
        "cloud spend": 5,
        "downtime": 3,
        "infrastructure cost": 5,
        "lock-in": 4,
        "reliability": 2,
        "utilization": 4,
    },
    "ai_frontier": {
        "adoption": 3,
        "compute cost": 5,
        "inference cost": 5,
        "licensing": 3,
        "model efficiency": 4,
        "training cost": 5,
    },
}


@dataclass
class RedditPost:
    post_id: str
    topic: str
    title: str
    subreddit: str
    url: str
    published_at: datetime
    body: str = ""
    listing_rank: int = 0
    score: int | None = None
    num_comments: int | None = None
    sampled_comments: list[str] = field(default_factory=list)
    investment_score: int = 0
    ranking_score: float = 0.0

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["published_at"] = self.published_at.isoformat()
        value.pop("body", None)
        value.pop("sampled_comments", None)
        value["sampled_comment_count"] = len(self.sampled_comments)
        return value

    def codex_dict(self) -> dict[str, Any]:
        return {
            **self.public_dict(),
            "post_excerpt": truncate(self.body, 1200),
            "top_comment_excerpts": [
                truncate(comment, 700) for comment in self.sampled_comments
            ],
        }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def default_target_date() -> date:
    return datetime.now(TIMEZONE).date() - timedelta(days=1)


def in_lookback(published_at: datetime, target_date: date, lookback_days: int) -> bool:
    end = datetime.combine(
        target_date + timedelta(days=1), datetime_time.min, tzinfo=TIMEZONE
    )
    start = end - timedelta(days=lookback_days)
    return start <= published_at.astimezone(TIMEZONE) < end


def load_topics(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    topics = payload.get("topics")
    if not isinstance(topics, dict) or not topics:
        raise ValueError("reddit topic configuration is empty")
    return topics


def reddit_time_filter(lookback_days: int) -> str:
    if lookback_days <= 1:
        return "day"
    if lookback_days <= 7:
        return "week"
    if lookback_days <= 31:
        return "month"
    return "year"


def strip_reddit_footer(value: str) -> str:
    value = clean_text(value)
    value = re.split(r"\s+submitted by\s+", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.split(
        r"\s+permalink\s+(?:embed\s+)?save\s+", value, maxsplit=1, flags=re.IGNORECASE
    )[0]
    return value.strip()


def child_value(entry: ET.Element, name: str) -> str:
    for child in entry:
        if local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def entry_link(entry: ET.Element) -> str:
    for child in entry:
        if local_name(child.tag) == "link" and child.attrib.get("href"):
            return child.attrib["href"].strip()
    return ""


def parse_reddit_listing_feed(
    data: bytes,
    topic: str,
    target_date: date,
    lookback_days: int,
) -> list[RedditPost]:
    root = ET.fromstring(data)
    posts: list[RedditPost] = []
    for rank, entry in enumerate(
        (item for item in root.iter() if local_name(item.tag) == "entry"), start=1
    ):
        post_id = child_value(entry, "id")
        title = clean_text(child_value(entry, "title"))
        url = entry_link(entry)
        published = parse_date(
            child_value(entry, "published") or child_value(entry, "updated")
        )
        subreddit = ""
        for child in entry:
            if local_name(child.tag) == "category":
                subreddit = child.attrib.get("term", "")
                break
        if (
            not post_id.startswith("t3_")
            or not title
            or not url
            or published is None
            or not in_lookback(published, target_date, lookback_days)
        ):
            continue
        posts.append(
            RedditPost(
                post_id=post_id.removeprefix("t3_"),
                topic=topic,
                title=title,
                subreddit=subreddit,
                url=url,
                published_at=published,
                body=strip_reddit_footer(child_value(entry, "content")),
                listing_rank=rank,
            )
        )
    return posts


def parse_reddit_comment_feed(data: bytes, post_id: str, limit: int) -> list[str]:
    root = ET.fromstring(data)
    comments: list[str] = []
    seen: set[str] = set()
    for entry in (item for item in root.iter() if local_name(item.tag) == "entry"):
        entry_id = child_value(entry, "id")
        if entry_id == f"t3_{post_id}" or not entry_id.startswith("t1_"):
            continue
        comment = strip_reddit_footer(child_value(entry, "content"))
        normalized = comment.lower()
        if len(comment) < 30 or normalized in seen:
            continue
        seen.add(normalized)
        comments.append(truncate(comment, 900))
        if len(comments) == limit:
            break
    return comments


class RedditHTTPClient:
    def __init__(self, minimum_interval: float = 1.2) -> None:
        self.minimum_interval = minimum_interval
        self.last_request_at = 0.0

    def request(self, request: urllib.request.Request, retries: int = 5) -> bytes:
        last_error: Exception | None = None
        for attempt in range(retries):
            wait = self.minimum_interval - (time.monotonic() - self.last_request_at)
            if wait > 0:
                time.sleep(wait)
            try:
                socket.setdefaulttimeout(35)
                with urllib.request.urlopen(request, timeout=35) as response:
                    self.last_request_at = time.monotonic()
                    return response.read()
            except urllib.error.HTTPError as exc:
                self.last_request_at = time.monotonic()
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 3
                time.sleep(max(delay, 2**attempt))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self.last_request_at = time.monotonic()
                last_error = exc
                time.sleep(2**attempt)
        assert last_error is not None
        raise last_error


class RedditRSSClient:
    mode = "rss"

    def __init__(self) -> None:
        # Reddit's unauthenticated RSS endpoint applies aggressive per-IP limits.
        self.http = RedditHTTPClient(minimum_interval=30.0)
        self.errors: list[dict[str, str]] = []

    def listing(
        self,
        topic: str,
        subreddits: list[str],
        target_date: date,
        lookback_days: int,
        limit: int,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        for subreddit in subreddits:
            url = (
                f"https://www.reddit.com/r/{subreddit}/top/.rss?"
                + urllib.parse.urlencode(
                    {"t": reddit_time_filter(lookback_days), "limit": limit}
                )
            )
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"},
            )
            try:
                posts.extend(
                    parse_reddit_listing_feed(
                        self.http.request(request, retries=3),
                        topic,
                        target_date,
                        lookback_days,
                    )
                )
            except Exception as exc:
                self.errors.append({"source": f"r/{subreddit}", "error": str(exc)})
        return posts

    def comments(self, post: RedditPost, limit: int) -> list[str]:
        url = post.url.rstrip("/") + "/.rss"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"},
        )
        return parse_reddit_comment_feed(
            self.http.request(request, retries=3), post.post_id, limit
        )


class RedditOAuthClient:
    mode = "oauth"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.http = RedditHTTPClient(minimum_interval=0.25)
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        request = urllib.request.Request(
            "https://www.reddit.com/api/v1/access_token",
            data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
            headers={
                "Authorization": f"Basic {credentials}",
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        payload = json.loads(self.http.request(request))
        self.token = payload["access_token"]
        self.errors: list[dict[str, str]] = []

    def get_json(self, path: str, parameters: dict[str, Any]) -> Any:
        url = f"https://oauth.reddit.com{path}?{urllib.parse.urlencode(parameters)}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        return json.loads(self.http.request(request))

    def listing(
        self,
        topic: str,
        subreddits: list[str],
        target_date: date,
        lookback_days: int,
        limit: int,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        for subreddit in subreddits:
            try:
                payload = self.get_json(
                    f"/r/{subreddit}/top",
                    {
                        "t": reddit_time_filter(lookback_days),
                        "limit": limit,
                        "raw_json": 1,
                    },
                )
            except Exception as exc:
                self.errors.append({"source": f"r/{subreddit}", "error": str(exc)})
                continue
            for rank, child in enumerate(payload["data"]["children"], start=1):
                data = child.get("data", {})
                published = datetime.fromtimestamp(
                    data.get("created_utc", 0), timezone.utc
                )
                if not in_lookback(published, target_date, lookback_days):
                    continue
                posts.append(
                    RedditPost(
                        post_id=data["id"],
                        topic=topic,
                        title=clean_text(data.get("title", "")),
                        subreddit=data.get("subreddit", ""),
                        url="https://www.reddit.com" + data.get("permalink", ""),
                        published_at=published,
                        body=clean_text(data.get("selftext", "")),
                        listing_rank=rank,
                        score=int(data.get("score", 0)),
                        num_comments=int(data.get("num_comments", 0)),
                    )
                )
        return posts

    def comments(self, post: RedditPost, limit: int) -> list[str]:
        payload = self.get_json(
            f"/comments/{post.post_id}",
            {"sort": "top", "limit": limit, "depth": 2, "raw_json": 1},
        )
        comments: list[str] = []

        def visit(children: list[dict[str, Any]]) -> None:
            for child in children:
                if child.get("kind") != "t1" or len(comments) >= limit:
                    continue
                data = child.get("data", {})
                body = clean_text(data.get("body", ""))
                if len(body) >= 30:
                    comments.append(truncate(body, 900))
                replies = data.get("replies")
                if isinstance(replies, dict):
                    visit(replies.get("data", {}).get("children", []))

        visit(payload[1].get("data", {}).get("children", []))
        return comments[:limit]


def create_client() -> RedditRSSClient | RedditOAuthClient:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if bool(client_id) != bool(client_secret):
        raise ValueError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be configured together"
        )
    if client_id and client_secret:
        return RedditOAuthClient(client_id, client_secret)
    return RedditRSSClient()


def is_eligible(post: RedditPost, topic_config: dict[str, Any]) -> bool:
    text = f"{post.title} {post.body}".lower()
    excluded = (
        set(topic_config.get("exclude_patterns", []))
        | LOW_SIGNAL_PATTERNS
        | SPECULATION_PATTERNS
    )
    return not any(pattern.lower() in text for pattern in excluded)


def title_similarity(left: RedditPost, right: RedditPost) -> float:
    left_tokens = set(TOKEN_RE.findall(left.title.lower()))
    right_tokens = set(TOKEN_RE.findall(right.title.lower()))
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def investment_relevance(post: RedditPost) -> int:
    text = f"{post.title} {post.body}".lower()
    terms = dict(VALUE_INVESTING_TERMS)
    terms.update(TOPIC_INVESTMENT_TERMS.get(post.topic, {}))
    return sum(weight for term, weight in terms.items() if contains_keyword(text, term))


def score_post(post: RedditPost, subreddit_weight: int) -> float:
    score = 120 - post.listing_rank * 4 + subreddit_weight * 3
    if post.score is not None:
        score += math.log1p(max(post.score, 0)) * 5
    if post.num_comments is not None:
        score += math.log1p(max(post.num_comments, 0)) * 7
    score += min(len(post.body) / 300, 5)
    score += min(len(post.sampled_comments), 8) * 1.5
    score += post.investment_score * 10
    return round(score, 2)


def select_candidates(
    posts: list[RedditPost],
    topic_config: dict[str, Any],
    limit: int,
) -> list[RedditPost]:
    weights = {
        subreddit.lower(): int(weight)
        for subreddit, weight in topic_config.get("subreddit_weights", {}).items()
    }
    eligible = [post for post in posts if is_eligible(post, topic_config)]
    for post in eligible:
        post.investment_score = investment_relevance(post)
        post.ranking_score = score_post(post, weights.get(post.subreddit.lower(), 5))
    eligible.sort(
        key=lambda post: (post.ranking_score, post.published_at), reverse=True
    )
    selected: list[RedditPost] = []
    subreddit_counts: dict[str, int] = {}
    per_subreddit_limit = int(topic_config.get("per_subreddit_limit", 3))
    for post in eligible:
        subreddit = post.subreddit.lower()
        if subreddit_counts.get(subreddit, 0) >= per_subreddit_limit:
            continue
        if any(title_similarity(post, existing) >= 0.55 for existing in selected):
            continue
        selected.append(post)
        subreddit_counts[subreddit] = subreddit_counts.get(subreddit, 0) + 1
        if len(selected) == limit:
            break
    return selected


def collect_reddit_posts(
    client: RedditRSSClient | RedditOAuthClient,
    topics: dict[str, dict[str, Any]],
    target_date: date,
    lookback_days: int,
    candidate_limit: int,
    comment_limit: int,
) -> tuple[
    dict[str, list[RedditPost]],
    list[dict[str, str]],
    dict[str, dict[str, Any]],
]:
    result: dict[str, list[RedditPost]] = {}
    errors: list[dict[str, str]] = []
    pool_stats: dict[str, dict[str, Any]] = {}
    for topic, config in topics.items():
        try:
            posts = client.listing(
                topic,
                list(config["subreddits"]),
                target_date,
                lookback_days,
                int(config.get("listing_limit", 35)),
            )
            eligible = [post for post in posts if is_eligible(post, config)]
            candidates = select_candidates(posts, config, candidate_limit)
        except Exception as exc:
            errors.append({"source": topic, "error": str(exc)})
            result[topic] = []
            pool_stats[topic] = {
                "fetched_count": 0,
                "eligible_count": 0,
                "candidate_count": 0,
                "subreddit_counts": {},
            }
            continue
        if client.errors:
            errors.extend(client.errors)
            client.errors.clear()
        subreddit_counts: dict[str, int] = {}
        for post in posts:
            subreddit_counts[post.subreddit] = (
                subreddit_counts.get(post.subreddit, 0) + 1
            )
        pool_stats[topic] = {
            "fetched_count": len(posts),
            "eligible_count": len(eligible),
            "candidate_count": len(candidates),
            "subreddit_counts": subreddit_counts,
        }
        # RSS is a degraded fallback. Avoid one request per thread because Reddit
        # heavily throttles unauthenticated feeds; OAuth mode supplies comments.
        comment_candidates = (
            candidates if client.mode == "oauth" and comment_limit > 0 else []
        )
        for post in comment_candidates:
            try:
                post.sampled_comments = client.comments(post, comment_limit)
                post.investment_score = investment_relevance(post)
                weights = {
                    name.lower(): int(weight)
                    for name, weight in config.get("subreddit_weights", {}).items()
                }
                post.ranking_score = score_post(
                    post, weights.get(post.subreddit.lower(), 5)
                )
            except Exception as exc:
                errors.append(
                    {"source": f"r/{post.subreddit}:{post.post_id}", "error": str(exc)}
                )
        candidates.sort(
            key=lambda post: (post.ranking_score, post.published_at), reverse=True
        )
        result[topic] = candidates
    return result, errors, pool_stats


def fallback_item(post: RedditPost, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "title_zh": f"r/{post.subreddit} 当日重点讨论第{rank}项",
        "title_original": post.title,
        "subreddit": post.subreddit,
        "published_at": post.published_at.isoformat(),
        "url": post.url,
        "score": post.score,
        "num_comments": post.num_comments,
        "sampled_comment_count": len(post.sampled_comments),
        "summary_zh": (
            "该帖子进入相关社区当日高热度候选。当前未能调用 Codex 生成具体摘要，"
            "需要结合原帖和高质量评论进一步判断其事实依据与专业价值。"
        ),
        "community_signal_zh": (
            "规则模式无法可靠提炼社区信号；报告已保留原帖入口，建议核查高赞评论。"
        ),
        "fundamental_impact_zh": (
            "规则模式无法判断该讨论对收入、利润率、现金流、资本回报或行业结构的长期影响。"
        ),
        "value_investor_takeaway_zh": (
            "当前只能将其作为研究线索，不能据此形成价值投资判断或买卖结论。"
        ),
        "key_risks_zh": (
            "主要风险包括社区选择偏差、未经验证的陈述，以及短期事件被误判为长期趋势。"
        ),
        "evidence_to_verify_zh": (
            "投资前应核查公司披露、行业数据、竞争格局、资本配置、估值与长期现金流影响。"
        ),
    }


def fallback_report(
    target_date: date,
    topics: dict[str, dict[str, Any]],
    candidates: dict[str, list[RedditPost]],
) -> dict[str, Any]:
    return {
        "date": target_date.isoformat(),
        "topics": [
            {
                "key": key,
                "name_zh": config["name_zh"],
                "items": [
                    fallback_item(post, rank)
                    for rank, post in enumerate(candidates.get(key, [])[:3], start=1)
                ],
            }
            for key, config in topics.items()
        ],
    }


def validate_reddit_items(
    raw_items: Any, candidates: list[RedditPost]
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list) or len(raw_items) > 3:
        raise ValueError("Codex returned an invalid Reddit item count")
    candidates_by_url = {post.url: post for post in candidates}
    text_fields = {
        "title_zh": (4, 80),
        "summary_zh": (40, 260),
        "community_signal_zh": (25, 240),
        "fundamental_impact_zh": (30, 260),
        "value_investor_takeaway_zh": (30, 260),
        "key_risks_zh": (25, 240),
        "evidence_to_verify_zh": (25, 240),
    }
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError("Codex returned a non-object Reddit item")
        url = raw_item.get("url")
        post = candidates_by_url.get(url)
        if post is None or url in seen:
            raise ValueError(f"Codex returned an invalid Reddit URL: {url}")
        seen.add(url)
        for field, limits in text_fields.items():
            validate_text_length(raw_item, field, *limits)
            if not CJK_RE.search(raw_item[field]):
                raise ValueError(f"Codex returned non-Chinese {field}")
        item = dict(raw_item)
        item.update(
            {
                "rank": rank,
                "title_original": post.title,
                "subreddit": post.subreddit,
                "published_at": post.published_at.isoformat(),
                "url": post.url,
                "score": post.score,
                "num_comments": post.num_comments,
                "sampled_comment_count": len(post.sampled_comments),
                "investment_score": post.investment_score,
            }
        )
        result.append(item)
    return result


def validate_reddit_report(
    report: dict[str, Any],
    target_date: date,
    topics: dict[str, dict[str, Any]],
    candidates: dict[str, list[RedditPost]],
) -> dict[str, Any]:
    if report.get("date") != target_date.isoformat():
        raise ValueError("Codex returned the wrong Reddit report date")
    raw_topics = report.get("topics")
    if not isinstance(raw_topics, list) or len(raw_topics) != len(topics):
        raise ValueError("Codex returned an invalid Reddit topic count")
    raw_by_key = {
        topic.get("key"): topic for topic in raw_topics if isinstance(topic, dict)
    }
    if set(raw_by_key) != set(topics):
        raise ValueError("Codex returned invalid Reddit topic keys")
    return {
        "date": target_date.isoformat(),
        "topics": [
            {
                "key": key,
                "name_zh": config["name_zh"],
                "items": validate_reddit_items(
                    raw_by_key[key].get("items"), candidates.get(key, [])
                ),
            }
            for key, config in topics.items()
        ],
    }


def run_codex_reddit(
    project_root: Path,
    target_date: date,
    topics: dict[str, dict[str, Any]],
    candidates: dict[str, list[RedditPost]],
    codex_bin: str,
) -> dict[str, Any]:
    payload = {
        "date": target_date.isoformat(),
        "topics": [
            {
                "key": key,
                "name_zh": config["name_zh"],
                "candidates": [post.codex_dict() for post in candidates.get(key, [])],
            }
            for key, config in topics.items()
        ],
    }
    prompt = (project_root / "prompts/select_reddit.md").read_text(encoding="utf-8")
    schema = project_root / "schemas/reddit_digest.schema.json"
    full_prompt = f"{prompt}\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    completed = subprocess.run(
        [
            codex_bin,
            "exec",
            "--experimental-json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-",
        ],
        cwd=project_root,
        env=os.environ.copy(),
        input=full_prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1800,
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
            # The agent output may contain the JSON report
            report_json_str = text
    if not report_json_str:
        raise RuntimeError(f"codex returned no agent_message: {completed.stdout[-1000:]}")
    # Extract JSON from the text (may be wrapped in markdown)
    match = re.search(r"", report_json_str)
    if match:
        report_json_str = match.group(1)
    else:
        # Try to find JSON object boundaries
        start = report_json_str.find("{")
        end = report_json_str.rfind("}")
        if start != -1 and end != -1:
            report_json_str = report_json_str[start:end+1]
    report = json.loads(report_json_str)
    return validate_reddit_report(report, target_date, topics, candidates)


def render_reddit_markdown(
    report: dict[str, Any],
    mode: str,
    collector: str,
    lookback_days: int,
    source_errors: list[dict[str, str]],
) -> str:
    range_description = (
        "报告日期当天（中国时区）"
        if lookback_days == 1
        else f"报告日期及此前共 {lookback_days} 个中国自然日"
    )
    lines = [
        f"# 每日 Reddit 社区 Topic 观察：{report['date']}",
        "",
        f"> 候选范围：{range_description}。"
        "筛选视角：`多行业长期价值投资`。"
        f"生成模式：`{mode}`。"
        f"抓取模式：`{collector}`。Reddit 热度与评论不代表事实正确。",
        "",
    ]
    for topic in report.get("topics", []):
        lines.extend([f"## {topic['name_zh']} 社区讨论 Top 3", ""])
        if not topic["items"]:
            lines.extend(["本期没有选出达到质量要求的社区讨论。", ""])
            continue
        for item in sorted(topic["items"], key=lambda value: value["rank"]):
            metrics = [f"日榜来源 r/{item['subreddit']}"]
            if item.get("score") is not None:
                metrics.append(f"{item['score']} 分")
            if item.get("num_comments") is not None:
                metrics.append(f"{item['num_comments']} 条评论")
            metrics.append(f"摘要采样 {item['sampled_comment_count']} 条评论")
            metrics.append(f"价值投资相关度 {item.get('investment_score', 0)}")
            lines.extend(
                [
                    f"### {item['rank']}. {item['title_zh']}",
                    "",
                    f"- **原标题：** {item['title_original']}",
                    f"- **社区热度：** {' / '.join(metrics)}",
                    f"- **发布时间：** {item['published_at']}",
                    f"- **原帖：** {item['url']}",
                    f"- **讨论摘要：** {item['summary_zh']}",
                    f"- **社区信号：** {item['community_signal_zh']}",
                    f"- **基本面影响：** {item['fundamental_impact_zh']}",
                    f"- **价值投资者视角：** {item['value_investor_takeaway_zh']}",
                    f"- **关键风险：** {item['key_risks_zh']}",
                    f"- **待验证数据：** {item['evidence_to_verify_zh']}",
                    "",
                ]
            )
    if source_errors:
        lines.extend(["## 数据源状态", ""])
        for error in source_errors:
            lines.append(f"- `{error['source']}`：{error['error']}")
        lines.append("")
    return "\n".join(lines)


def load_successful_report(path: Path, target_date: date) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if report.get("date") != target_date.isoformat():
        return None
    if report.get("metadata", {}).get("mode") not in {"codex", "codex-preserved"}:
        return None
    required_fields = {
        "community_signal_zh",
        "fundamental_impact_zh",
        "value_investor_takeaway_zh",
        "key_risks_zh",
        "evidence_to_verify_zh",
    }
    topics = report.get("topics")
    if not isinstance(topics, list):
        return None
    for topic in topics:
        if not isinstance(topic, dict) or not isinstance(topic.get("items"), list):
            return None
        if any(
            not isinstance(item, dict) or not required_fields <= set(item)
            for item in topic["items"]
        ):
            return None
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a daily Reddit topic digest")
    parser.add_argument("--date", type=date.fromisoformat, default=default_target_date())
    parser.add_argument("--lookback-days", type=int, default=1)
    parser.add_argument("--candidate-limit", type=int, default=12)
    parser.add_argument("--comment-limit", type=int, default=8)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--use-codex", action="store_true")
    parser.add_argument("--require-codex", action="store_true")
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", "codex"))
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = args.project_root.resolve()
    output_root = (args.output_root or project_root / "var").resolve()
    topics = load_topics(project_root / "config/reddit_topics.json")
    client = create_client()
    candidates, source_errors, pool_stats = collect_reddit_posts(
        client,
        topics,
        args.date,
        args.lookback_days,
        args.candidate_limit,
        args.comment_limit,
    )
    candidate_count = sum(len(posts) for posts in candidates.values())
    raw_payload = {
        "date": args.date.isoformat(),
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "collector": client.mode,
        "selection_profile": SELECTION_PROFILE,
        "lookback_days": args.lookback_days,
        "candidate_count": candidate_count,
        "source_errors": source_errors,
        "topic_pool_stats": pool_stats,
        "topics": {
            key: [post.public_dict() for post in posts]
            for key, posts in candidates.items()
        },
    }
    atomic_write(
        output_root / "reddit-raw" / f"{args.date.isoformat()}-candidates.json",
        pretty_json(raw_payload),
    )

    mode = "rules-fallback"
    codex_error = ""
    report = fallback_report(args.date, topics, candidates)
    if args.use_codex and candidate_count:
        try:
            report = run_codex_reddit(
                project_root, args.date, topics, candidates, args.codex_bin
            )
            mode = "codex"
        except Exception as exc:
            codex_error = str(exc)

    report_dir = output_root / "reddit-digests"
    report_json = report_dir / f"{args.date.isoformat()}.json"
    if args.use_codex and codex_error:
        successful = load_successful_report(report_json, args.date)
        if successful is not None:
            report = successful
            mode = "codex-preserved"
    report["metadata"] = {
        "mode": mode,
        "collector": client.mode,
        "selection_profile": SELECTION_PROFILE,
        "lookback_days": args.lookback_days,
        "candidate_count": candidate_count,
        "source_errors": source_errors,
        "topic_pool_stats": pool_stats,
        "codex_error": codex_error,
    }
    report_md = report_dir / f"{args.date.isoformat()}.md"
    atomic_write(report_json, pretty_json(report))
    atomic_write(
        report_md,
        render_reddit_markdown(
            report, mode, client.mode, args.lookback_days, source_errors
        ),
    )
    shutil.copyfile(report_json, report_dir / "latest.json")
    shutil.copyfile(report_md, report_dir / "latest.md")
    atomic_write(
        output_root / "reddit-status/latest.json",
        pretty_json(
            {
                "date": args.date.isoformat(),
                "generated_at": datetime.now(TIMEZONE).isoformat(),
                "mode": mode,
                "collector": client.mode,
                "selection_profile": SELECTION_PROFILE,
                "lookback_days": args.lookback_days,
                "candidate_count": candidate_count,
                "selected_count": sum(
                    len(topic["items"]) for topic in report.get("topics", [])
                ),
                "source_error_count": len(source_errors),
                "topic_pool_stats": pool_stats,
                "codex_error": codex_error,
            }
        ),
    )
    print(report_md)
    if not candidate_count:
        return 2
    if args.require_codex and mode != "codex":
        return 3
    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"finance-reddit-digest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
