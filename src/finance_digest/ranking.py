from __future__ import annotations

import re
from collections import defaultdict

from .models import Article


TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "says",
    "the",
    "to",
    "with",
}
IMPACT_KEYWORDS = {
    "acquisition": 3,
    "bankruptcy": 4,
    "central bank": 4,
    "earnings": 2,
    "federal reserve": 4,
    "inflation": 4,
    "interest rate": 4,
    "merger": 3,
    "oil": 3,
    "recession": 4,
    "sanctions": 4,
    "tariff": 4,
    "trade war": 4,
    "unemployment": 3,
}
LOW_SIGNAL_TITLE_PATTERNS = {
    "company announcement",
    "director/pdmr",
    "holding(s) in company",
    "net asset value",
    "notice of results",
    "result of agm",
    "transaction in own shares",
    "total voting rights",
}


def title_tokens(title: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(title.lower()) if token not in STOPWORDS}


def similarity(left: Article, right: Article) -> float:
    left_tokens = title_tokens(left.title)
    right_tokens = title_tokens(right.title)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def deduplicate(articles: list[Article]) -> list[Article]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[Article] = []
    for article in sorted(articles, key=lambda item: item.source_weight, reverse=True):
        normalized_title = " ".join(sorted(title_tokens(article.title)))
        if article.url in seen_urls or normalized_title in seen_titles:
            continue
        seen_urls.add(article.url)
        seen_titles.add(normalized_title)
        result.append(article)
    return result


def is_low_signal(article: Article) -> bool:
    title = article.title.lower()
    return any(pattern in title for pattern in LOW_SIGNAL_TITLE_PATTERNS)


def cluster_articles(articles: list[Article], threshold: float = 0.34) -> None:
    parent = list(range(len(articles)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(articles)):
        for right in range(left + 1, len(articles)):
            if similarity(articles[left], articles[right]) >= threshold:
                union(left, right)

    sizes: dict[int, int] = defaultdict(int)
    for index in range(len(articles)):
        sizes[find(index)] += 1
    for index, article in enumerate(articles):
        article.cluster_size = sizes[find(index)]


def score_articles(articles: list[Article], per_source_limit: int = 20) -> list[Article]:
    articles = deduplicate([article for article in articles if not is_low_signal(article)])
    cluster_articles(articles)
    for article in articles:
        text = f"{article.title} {article.description}".lower()
        score = float(article.source_weight)
        score += min(article.cluster_size - 1, 3) * 3.0
        for keyword, value in IMPACT_KEYWORDS.items():
            if keyword in text:
                score += value
        if article.category in {"central_banks", "regulation"}:
            score += 2.0
        article.score = score
    ranked = sorted(
        articles,
        key=lambda item: (item.score, item.published_at),
        reverse=True,
    )
    result: list[Article] = []
    source_counts: dict[str, int] = defaultdict(int)
    for article in ranked:
        if source_counts[article.source] >= per_source_limit:
            continue
        source_counts[article.source] += 1
        result.append(article)
    return result
