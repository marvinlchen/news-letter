from __future__ import annotations

import json
from datetime import date
from typing import Any

from .models import Article


SOURCE_NAMES = {
    "AP News": "美联社",
    "BBC Business": "英国广播公司商业频道",
    "Bloomberg.com": "彭博社",
    "CNBC": "CNBC",
    "EIA": "美国能源信息署",
    "European Central Bank": "欧洲央行",
    "Federal Reserve": "美联储",
    "Financial Times": "英国《金融时报》",
    "Reuters": "路透社",
    "SEC": "美国证监会",
}
CATEGORY_NAMES = {
    "business": "商业动态",
    "central_banks": "央行政策",
    "energy": "能源市场",
    "finance": "财经市场",
    "markets": "市场动态",
    "regulation": "金融监管",
}


def truncate(value: str, maximum: int) -> str:
    value = " ".join(value.split())
    if len(value) <= maximum:
        return value
    return value[: maximum - 1].rstrip() + "…"


def fallback_digest(target_date: date, articles: list[Article]) -> dict[str, Any]:
    items = []
    for rank, article in enumerate(articles[:10], start=1):
        items.append(
            {
                "rank": rank,
                "title_zh": (
                    f"第{rank}条{CATEGORY_NAMES.get(article.category, '财经')}要闻："
                    f"{SOURCE_NAMES.get(article.source, '可信来源')}报道"
                ),
                "title_original": article.title,
                "summary_zh": truncate(
                    f"{SOURCE_NAMES.get(article.source, '可信来源')}发布一则"
                    f"{CATEGORY_NAMES.get(article.category, '财经')}消息。"
                    f"该条目规则评分为 {article.score:.1f}，"
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
                f"- **原文：** {item['url']}",
                "",
                item["summary_zh"],
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
