from __future__ import annotations

import json
from datetime import date
from typing import Any

from .models import Article
from .ranking import TOPICS, topic_top_articles


SOURCE_NAMES = {
    "AP News": "美联社",
    "BBC Business": "英国广播公司商业频道",
    "Bank of Japan": "日本央行",
    "Bloomberg.com": "彭博社",
    "CNBC": "CNBC",
    "EIA": "美国能源信息署",
    "European Central Bank": "欧洲央行",
    "Federal Reserve": "美联储",
    "Financial Times": "英国《金融时报》",
    "Reuters": "路透社",
    "SEC": "美国证监会",
    "World Bank": "世界银行",
    "Trusted Commodities Index": "可信大宗商品索引",
    "Trusted Consumer Index": "可信消费行业索引",
    "Trusted Shipping Index": "可信航运索引",
    "Trusted Company Share Movers Index": "可信个股涨跌索引",
    "Trusted Global Equity Index Movers": "可信全球股指涨跌索引",
    "Trusted Technology Index": "可信科技行业索引",
}
CATEGORY_NAMES = {
    "business": "商业动态",
    "central_banks": "央行政策",
    "energy": "能源市场",
    "finance": "财经市场",
    "markets": "市场动态",
    "regulation": "金融监管",
    "shipping": "航运",
    "commodities": "大宗商品",
    "stock_market": "股票市场",
    "technology": "科技",
    "consumer": "消费",
}


def truncate(value: str, maximum: int) -> str:
    value = " ".join(value.split())
    if len(value) <= maximum:
        return value
    return value[: maximum - 1].rstrip() + "…"


def fallback_item(article: Article, rank: int, section_name: str) -> dict[str, Any]:
    return {
        "rank": rank,
        "title_zh": (
            f"{section_name}第{rank}条要闻："
            f"{SOURCE_NAMES.get(article.source, '可信来源')}报道"
        ),
        "title_original": article.title,
        "summary_zh": truncate(
            f"{SOURCE_NAMES.get(article.source, '可信来源')}发布一则"
            f"{section_name}消息。该条目规则评分为 {article.score:.1f}，"
            f"检测到 {article.cluster_size} 条同事件候选报道。"
            "当前未能调用 Codex 生成具体中文摘要，事件内容与市场影响请通过原文"
            "及其他可信来源进一步核实。",
            200,
        ),
        "category": article.category,
        "source": article.source,
        "published_at": article.published_at.isoformat(),
        "url": article.url,
        "confidence": "medium" if article.cluster_size > 1 else "low",
    }


def fallback_digest(target_date: date, articles: list[Article]) -> dict[str, Any]:
    topics = []
    for key, topic_articles in topic_top_articles(articles).items():
        name_zh = TOPICS[key]["name_zh"]
        topics.append(
            {
                "key": key,
                "name_zh": name_zh,
                "items": [
                    fallback_item(article, rank, name_zh)
                    for rank, article in enumerate(topic_articles, start=1)
                ],
            }
        )
    return {"date": target_date.isoformat(), "topics": topics}


def render_markdown(digest: dict[str, Any], mode: str, source_errors: list[dict[str, str]]) -> str:
    lines = [
        f"# 每日专业 Topic 新闻：{digest['date']}",
        "",
        f"> 生成模式：`{mode}`。新闻链接可能受订阅或付费墙限制。",
        "",
    ]
    def render_items(items: list[dict[str, Any]], heading_level: int) -> None:
        prefix = "#" * heading_level
        for item in sorted(items, key=lambda value: value["rank"]):
            lines.extend(
                [
                    f"{prefix} {item['rank']}. {item['title_zh']}",
                    "",
                    f"- **原标题：** {item['title_original']}",
                    f"- **来源：** {item['source']}",
                    f"- **发布时间：** {item['published_at']}",
                    f"- **原文：** {item['url']}",
                    f"- **摘要：** {item['summary_zh']}",
                    "",
                ]
            )

    for topic in digest.get("topics", []):
        lines.extend([f"## {topic['name_zh']} Top 3", ""])
        if topic["items"]:
            render_items(topic["items"], 3)
        else:
            lines.extend(["当日候选新闻不足，未选出符合条件的报道。", ""])
    if source_errors:
        lines.extend(["## 数据源状态", ""])
        for error in source_errors:
            lines.append(f"- `{error['source']}`：{error['error']}")
        lines.append("")
    return "\n".join(lines)


def pretty_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
