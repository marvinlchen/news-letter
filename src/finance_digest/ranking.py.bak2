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
    "activity sheet",
    "company announcement",
    "concept note",
    "consumer price index,",
    "contact form",
    "director/pdmr",
    "edgar filing documents for",
    "form 8-k",
    "gisis",
    "holding(s) in company",
    "imodocs",
    "management evaluation",
    "net asset value",
    "newsroom",
    "notice of results",
    "programme webinar",
    "program webinar",
    "result of agm",
    "social media",
    "streaming - imohq",
    "transaction in own shares",
    "total voting rights",
}
LOW_SIGNAL_FILE_EXTENSIONS = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
}
STOCK_MOVEMENT_RE = re.compile(
    r"\b(?:"
    r"bounce[ds]?|climb(?:s|ed)?|drop(?:s|ped)?|fall(?:s|ing)?|fell|"
    r"gain(?:s|ed)?|jump(?:s|ed)?|plunge[ds]?|rall(?:y|ies|ied)|"
    r"rebound(?:s|ed)?|rise[sd]?|rose|sank|sink(?:s|ing)?|"
    r"slid(?:e|es)?|slump(?:s|ed)?|snap(?:s|ped)?|soar(?:s|ed)?|"
    r"surge[ds]?|tumble[ds]?"
    r")\b|\bhit(?:s)? record\b|\bsell-?off\b"
)
TOPICS = {
    "macroeconomics": {
        "name_zh": "宏观经济",
        "keywords": {
            "central bank",
            "consumer price index",
            "cpi",
            "employment",
            "fiscal policy",
            "gdp",
            "growth",
            "inflation",
            "interest rate",
            "monetary policy",
            "payroll",
            "ppi",
            "producer price index",
            "recession",
            "tariff",
            "trade",
            "unemployment",
            "wages",
        },
    },
    "shipping": {
        "name_zh": "航运",
        "keywords": {
            "container",
            "freight",
            "logistics",
            "maritime",
            "ocean carrier",
            "port",
            "ports",
            "red sea",
            "ship",
            "ships",
            "shipping",
            "strait of hormuz",
            "suez",
            "tanker",
            "tankers",
            "vessel",
            "vessels",
        },
    },
    "commodities": {
        "name_zh": "大宗商品",
        "keywords": {
            "agriculture",
            "coal",
            "commodity",
            "commodities",
            "copper",
            "corn",
            "crude",
            "energy",
            "gold",
            "iron ore",
            "lng",
            "metal",
            "mineral",
            "minerals",
            "mining",
            "natural gas",
            "oil",
            "opec",
            "soy",
            "steel",
            "wheat",
        },
    },
    "stock_market": {
        "name_zh": "股票市场",
        "keywords": {
            "dow jones",
            "equities",
            "equity",
            "ftse",
            "hang seng",
            "market cap",
            "nasdaq",
            "nikkei",
            "s&p 500",
            "share price",
            "shares",
            "sell-off",
            "selloff",
            "stock",
            "stocks",
            "stoxx",
        },
    },
    "technology": {
        "name_zh": "科技产业",
        "keywords": {
            "chip",
            "chips",
            "cybersecurity",
            "hardware",
            "operating system",
            "semiconductor",
            "semiconductors",
            "software",
            "tech",
            "technology",
        },
    },
    "consumer": {
        "name_zh": "消费",
        "keywords": {
            "airline",
            "apparel",
            "auto",
            "automaker",
            "beverage",
            "beauty",
            "beer",
            "coffee",
            "cosmetics",
            "consumer demand",
            "consumer goods",
            "consumer spending",
            "e-commerce",
            "food",
            "grocery",
            "hotel",
            "hospitality",
            "luxury",
            "mini-mart",
            "restaurant",
            "restaurants",
            "retail",
            "retailer",
            "retailers",
            "sales",
            "shop",
            "store",
            "supermarket",
            "tourism",
            "travel",
            "vehicle",
        },
    },
    "cloud_infra": {
        "name_zh": "Cloud Infra Engineering",
        "keywords": {
            "aws",
            "aurora",
            "azure",
            "cloud",
            "cloud infrastructure",
            "cloudflare",
            "containerd",
            "database",
            "data center",
            "distributed system",
            "kubernetes",
            "networking",
            "observability",
            "platform engineering",
            "postgres",
            "postgresql",
            "serverless",
            "service mesh",
        },
    },
    "ai_frontier": {
        "name_zh": "AI 前沿",
        "keywords": {
            "agentic",
            "ai agent",
            "ai model",
            "artificial intelligence",
            "alignment",
            "benchmark",
            "diffusion",
            "evaluation",
            "foundation model",
            "frontier model",
            "inference",
            "large language model",
            "llm",
            "machine learning",
            "multimodal",
            "reasoning model",
            "ai safety",
            "training",
            "transformer",
        },
    },
}
COUNTRIES = {
    "singapore": {
        "name_zh": "新加坡",
        "keywords": {
            "changi",
            "dbs",
            "gic",
            "grab",
            "jurong",
            "keppel",
            "mas",
            "monetary authority of singapore",
            "ocbc",
            "pasir panjang",
            "sea limited",
            "sembcorp",
            "sgx",
            "singdollar",
            "singapore",
            "singaporean",
            "singtel",
            "s'pore",
            "straits times index",
            "temasek",
            "uob",
        },
    },
    "china": {
        "name_zh": "中国",
        "keywords": {
            "beijing",
            "china",
            "chinese",
            "hang seng",
            "hong kong",
            "pboc",
            "people's bank of china",
            "shanghai",
            "shenzhen",
        },
    },
    "united_states": {
        "name_zh": "美国",
        "keywords": {
            "american",
            "federal reserve",
            "nasdaq",
            "s&p 500",
            "u.s.",
            "united states",
            "wall street",
            "washington",
            "white house",
        },
    },
}
COUNTRY_NEWS_KEYWORDS = {
    "acquisition",
    "bank",
    "business",
    "capital",
    "company",
    "corporate",
    "currency",
    "earnings",
    "economic",
    "economy",
    "employment",
    "energy",
    "finance",
    "financial",
    "gdp",
    "industry",
    "inflation",
    "investment",
    "licensing",
    "market cap",
    "markets",
    "monetary",
    "oil",
    "policy",
    "port",
    "regulation",
    "regulator",
    "sanctions",
    "semiconductor",
    "shares",
    "shipping",
    "stock",
    "terminal",
    "trade",
    "wages",
}
COUNTRY_LOW_SIGNAL_TITLE_PATTERNS = {
    "academic rankings",
    "citizen science",
    "county employment and wages",
    "data from:",
    "dies at",
    "dog abuse",
    "faqs",
    "food and nutrition administration",
    "lifestyle",
    "opening bell",
    "parish employment and wages",
    "temperature",
    "training requirement",
    "tourists slammed",
    "waivers",
    "weather",
    "wet market",
}
TOPIC_LOW_SIGNAL_TITLE_PATTERNS = {
    "macroeconomics": {"consumer price index,"},
    "shipping": {"inflation", "tariff refund"},
    "commodities": {
        "activity",
        "appointment",
        "conference",
        "expert group",
        "nutrition",
        "procurement",
        "programme",
        "varieties",
        "whistleblower",
        "workshop",
    },
    "stock_market": {
        "best stocks",
        "crude stocks",
        "investment case",
        "market outlook",
        "stock picks",
        "stocks to buy",
    },
    "technology": {
        "community investment",
        "equities",
        "investment case",
        "local jobs",
        "oil",
        "stocks",
        "tsmc online",
        "world markets",
    },
    "consumer": {
        "bank account",
        "cash returns",
        "inflation",
        "rate hike",
        "rewards",
        "your money",
    },
    "cloud_infra": {
        "automate",
        "benchmarking",
        "deep dive",
        "guide",
        "how ",
        "how to",
        "investment case",
        "propaganda",
        "shares",
        "stock",
        "tutorial",
    },
    "ai_frontier": {
        "academy",
        "arxiv",
        "careers",
        "cloud commitment",
        "developer forums",
        "error",
        "help center",
        "investment case",
        "pricing",
        "rate card",
        "recipe",
        "risk analyst",
        "shares",
        "stock",
        "status",
        "survey",
        "world markets",
    },
}


def title_tokens(title: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(title.lower()) if token not in STOPWORDS}


def contains_keyword(text: str, keyword: str) -> bool:
    if " " in keyword or "-" in keyword or "." in keyword:
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def classify_topics(article: Article) -> list[str]:
    text = f"{article.title} {article.description}".lower()
    topics: list[str] = [topic for topic in article.topics if topic in TOPICS]
    if topics:
        return topics
    for key, config in TOPICS.items():
        if any(contains_keyword(text, keyword) for keyword in config["keywords"]):
            topics.append(key)
    return list(dict.fromkeys(topics))


def topic_keyword_relevance(article: Article, topic: str) -> int:
    keywords = TOPICS[topic]["keywords"]
    title = article.title.lower()
    description = article.description.lower()
    title_matches = sum(contains_keyword(title, keyword) for keyword in keywords)
    description_matches = sum(
        contains_keyword(description, keyword) for keyword in keywords
    )
    return title_matches * 3 + description_matches


def topic_relevance(article: Article, topic: str) -> int:
    authority_bonus = 12 if topic in article.topics else 0
    return authority_bonus + topic_keyword_relevance(article, topic)


def is_topic_low_signal(article: Article, topic: str) -> bool:
    text = f"{article.title} {article.source}".lower()
    return any(
        pattern in text for pattern in TOPIC_LOW_SIGNAL_TITLE_PATTERNS.get(topic, set())
    )


def is_article_eligible_for_topic(article: Article, topic: str) -> bool:
    authoritative_binding = (
        topic in article.topics and article.topic_binding == "authoritative"
    )
    has_topic_assignment = topic in article.topics
    eligible = (
        topic in classify_topics(article)
        and (topic_keyword_relevance(article, topic) > 0 or authoritative_binding or has_topic_assignment)
        and not is_topic_low_signal(article, topic)
    )
    if topic == "stock_market":
        text = f"{article.title} {article.description}".lower()
        return eligible and STOCK_MOVEMENT_RE.search(text) is not None
    return eligible


def topic_top_articles(articles: list[Article], limit: int = 3) -> dict[str, list[Article]]:
    result = {}
    for key in TOPICS:
        matches = [
            article
            for article in articles
            if is_article_eligible_for_topic(article, key)
        ]
        matches.sort(
            key=lambda article: (
                article.score + topic_relevance(article, key) * 2,
                topic_relevance(article, key),
                article.published_at,
            ),
            reverse=True,
        )
        selected: list[Article] = []
        source_counts: dict[str, int] = defaultdict(int)
        similarity_threshold = 0.10 if key == "stock_market" else 0.34
        for article in matches:
            if any(
                similarity(article, existing) >= similarity_threshold
                for existing in selected
            ):
                continue
            if source_counts[article.source] >= 2:
                continue
            selected.append(article)
            source_counts[article.source] += 1
            if len(selected) == limit:
                break
        result[key] = selected
    return result


def country_keyword_relevance(article: Article, country: str) -> int:
    keywords = COUNTRIES[country]["keywords"]
    title = article.title.lower()
    description = article.description.lower()
    title_matches = sum(contains_keyword(title, keyword) for keyword in keywords)
    description_matches = sum(
        contains_keyword(description, keyword) for keyword in keywords
    )
    return title_matches * 3 + description_matches


def is_article_eligible_for_country(article: Article, country: str) -> bool:
    authoritative_binding = (
        country in article.countries and article.country_binding == "authoritative"
    )
    text = f"{article.title} {article.description}".lower()
    country_match = country_keyword_relevance(article, country) > 0
    finance_match = any(
        contains_keyword(text, keyword) for keyword in COUNTRY_NEWS_KEYWORDS
    ) or any(topic_keyword_relevance(article, topic) > 0 for topic in TOPICS)
    low_signal = any(
        pattern in article.title.lower()
        for pattern in COUNTRY_LOW_SIGNAL_TITLE_PATTERNS
    )
    return (country_match or authoritative_binding) and finance_match and not low_signal


def country_top_articles(
    articles: list[Article], limit: int = 3
) -> dict[str, list[Article]]:
    result = {}
    for key in COUNTRIES:
        matches = [
            article
            for article in articles
            if is_article_eligible_for_country(article, key)
        ]
        matches.sort(
            key=lambda article: (
                article.score
                + country_keyword_relevance(article, key) * 2
                + (12 if key in article.countries else 0),
                country_keyword_relevance(article, key),
                article.published_at,
            ),
            reverse=True,
        )
        selected: list[Article] = []
        source_counts: dict[str, int] = defaultdict(int)
        for article in matches:
            if any(similarity(article, existing) >= 0.34 for existing in selected):
                continue
            if source_counts[article.source] >= 2:
                continue
            selected.append(article)
            source_counts[article.source] += 1
            if len(selected) == limit:
                break
        result[key] = selected
    return result


def similarity(left: Article, right: Article) -> float:
    left_tokens = title_tokens(left.title)
    right_tokens = title_tokens(right.title)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def deduplicate(articles: list[Article]) -> list[Article]:
    by_url: dict[str, Article] = {}
    by_title: dict[str, Article] = {}
    result: list[Article] = []
    for article in sorted(articles, key=lambda item: item.source_weight, reverse=True):
        normalized_title = " ".join(sorted(title_tokens(article.title)))
        existing = by_url.get(article.url) or by_title.get(normalized_title)
        if existing is not None:
            existing.topics = list(dict.fromkeys([*existing.topics, *article.topics]))
            existing.countries = list(
                dict.fromkeys([*existing.countries, *article.countries])
            )
            if article.topic_binding == "authoritative":
                existing.topic_binding = "authoritative"
            if article.country_binding == "authoritative":
                existing.country_binding = "authoritative"
            if len(article.description) > len(existing.description):
                existing.description = article.description
            continue
        by_url[article.url] = article
        by_title[normalized_title] = article
        result.append(article)
    return result


def is_low_signal(article: Article) -> bool:
    title = article.title.lower()
    normalized = title.rsplit(" - ", 1)[0].strip("- ")
    return (
        not normalized
        or title.startswith("- ")
        or any(pattern in title for pattern in LOW_SIGNAL_TITLE_PATTERNS)
        or any(extension in title for extension in LOW_SIGNAL_FILE_EXTENSIONS)
    )


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
