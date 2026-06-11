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
                "summary_zh": (
                    f"本条候选新闻由 {article.source} 发布，原标题为“{article.title}”。"
                    f"来源提供的公开摘要为：{article.description or '未提供可用摘要'}。"
                    "当前任务未能调用 Codex 生成扩展分析，因此这里只保留可验证的标题、"
                    "来源、发布时间与公开摘要，不对报道正文、未披露数字或事件背景作推断。"
                    "建议通过原文链接或其他独立可信来源核实事件细节。"
                ),
                "key_facts_zh": [
                    f"新闻来源为 {article.source}，类别标记为 {article.category}。",
                    f"发布时间为 {article.published_at.isoformat()}。",
                    f"规则评分为 {article.score:.1f}，同事件候选报道数为 {article.cluster_size}。",
                ],
                "why_it_matters_zh": (
                    f"该新闻在候选池中的规则评分为 {article.score:.1f}，"
                    f"来源权重和标题中的财经影响关键词使其进入每日 Top 10。"
                    f"当前检测到 {article.cluster_size} 条同事件候选报道。"
                    "由于未获得 Codex 扩展分析，本段不能可靠判断具体市场传导路径；"
                    "投资或经营决策前应进一步核实事件范围、时间表和相关资产敞口。"
                ),
                "what_to_watch_zh": (
                    "后续应关注原始来源是否发布更新、是否出现其他独立媒体或官方机构确认，"
                    "以及相关市场价格、监管公告或公司披露是否发生变化。"
                    "若事件涉及付费墙内容，应通过合法订阅获取正文后再评估。"
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
                "**事件概述**",
                "",
                item["summary_zh"],
                "",
                "**关键事实**",
                "",
                *[f"- {fact}" for fact in item["key_facts_zh"]],
                "",
                "**市场与行业影响**",
                "",
                item["why_it_matters_zh"],
                "",
                "**后续观察**",
                "",
                item["what_to_watch_zh"],
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
