from __future__ import annotations

import json
from datetime import date
from typing import Any

from .models import Article


def fallback_digest(target_date: date, articles: list[Article]) -> dict[str, Any]:
    items = []
    for rank, article in enumerate(articles[:10], start=1):
        items.append(
            {
                "rank": rank,
                "title_zh": article.title,
                "title_original": article.title,
                "summary_zh": article.description or "来源未提供摘要。",
                "why_it_matters_zh": (
                    f"规则评分 {article.score:.1f}；"
                    f"同事件候选报道数 {article.cluster_size}。"
                ),
                "category": article.category,
                "source": article.source,
                "published_at": article.published_at.isoformat(),
                "url": article.url,
                "confidence": "medium" if article.cluster_size > 1 else "low",
            }
        )
    return {"date": target_date.isoformat(), "items": items}


def render_markdown(digest: dict[str, Any], mode: str, source_errors: list[dict[str, str]]) -> str:
    lines = [
        f"# 财经新闻 Top 10：{digest['date']}",
        "",
        f"> 生成模式：`{mode}`。新闻链接可能受订阅或付费墙限制。",
        "",
    ]
    for item in sorted(digest["items"], key=lambda value: value["rank"]):
        lines.extend(
            [
                f"## {item['rank']}. {item['title_zh']}",
                "",
                f"- **来源：** {item['source']}",
                f"- **发布时间：** {item['published_at']}",
                f"- **类别：** {item['category']}",
                f"- **置信度：** {item['confidence']}",
                f"- **原文：** {item['url']}",
                "",
                f"**摘要：** {item['summary_zh']}",
                "",
                f"**重要性：** {item['why_it_matters_zh']}",
                "",
            ]
        )
    if source_errors:
        lines.extend(["## 数据源状态", ""])
        for error in source_errors:
            lines.append(f"- `{error['source']}`：{error['error']}")
        lines.append("")
    return "\n".join(lines)


def pretty_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

