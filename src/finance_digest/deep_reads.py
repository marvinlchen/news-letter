from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .codex import CJK_RE, validate_text_length
from .collect import load_sources
from .feeds import fetch_feed
from .models import Article
from .ranking import contains_keyword, similarity
from .render import pretty_json, truncate


TIMEZONE = ZoneInfo("Asia/Shanghai")
DEEP_TOPICS = {
    "cloud_infra": {
        "name_zh": "Cloud Infra Engineering",
        "keywords": {
            "architecture",
            "availability",
            "cloud",
            "consensus",
            "database",
            "distributed",
            "kubernetes",
            "latency",
            "network",
            "observability",
            "operating system",
            "performance",
            "reliability",
            "scalability",
            "storage",
            "systems",
        },
    },
    "ai_frontier": {
        "name_zh": "AI 前沿",
        "keywords": {
            "agent",
            "alignment",
            "artificial intelligence",
            "benchmark",
            "evaluation",
            "foundation model",
            "generative ai",
            "genai",
            "inference",
            "interpretability",
            "language model",
            "machine learning",
            "model",
            "multimodal",
            "reasoning",
            "research",
            "training",
            "transformer",
        },
    },
}
DEPTH_TERMS = {
    "analysis",
    "architecture",
    "benchmark",
    "case study",
    "design",
    "distributed",
    "evaluation",
    "experiment",
    "implementation",
    "method",
    "performance",
    "production",
    "reliability",
    "research",
    "scalability",
    "system",
    "trade-off",
}
LOW_SIGNAL_PATTERNS = {
    "apply now",
    "career",
    "certification",
    "conference recap",
    "customer story",
    "event",
    "getting started",
    "guide",
    "how to ",
    "job details",
    "mission impact",
    "monthly roundup",
    "newsletter",
    "podcast",
    "register now",
    "training course",
    "webinar",
    "what's new",
    "what’s new",
}
SOURCE_AUTHORITY = {
    "ACM Queue": 18,
    "Anthropic": 14,
    "Google DeepMind": 14,
    "Google Research": 14,
    "Meta Engineering": 12,
    "Netflix TechBlog": 12,
    "OpenReview": 12,
    "USENIX": 16,
    "arXiv AI": 0,
}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def default_target_date() -> date:
    return datetime.now(TIMEZONE).date() - timedelta(days=1)


def in_lookback(article: Article, target_date: date, lookback_days: int) -> bool:
    end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=TIMEZONE)
    start = end - timedelta(days=lookback_days)
    published = article.published_at.astimezone(TIMEZONE)
    return start <= published < end


def topic_relevance(article: Article, topic: str) -> int:
    text = f"{article.title} {article.description}".lower()
    return sum(
        contains_keyword(text, keyword) for keyword in DEEP_TOPICS[topic]["keywords"]
    )


def is_deep_eligible(article: Article, topic: str) -> bool:
    title = article.title.lower()
    return (
        topic in article.topics
        and topic_relevance(article, topic) > 0
        and not any(pattern in title for pattern in LOW_SIGNAL_PATTERNS)
    )


def depth_score(article: Article, topic: str) -> float:
    text = f"{article.title} {article.description}".lower()
    depth_matches = sum(contains_keyword(text, term) for term in DEPTH_TERMS)
    description_bonus = min(len(article.description) / 200, 8)
    return (
        article.source_weight * 3
        + topic_relevance(article, topic) * 2
        + depth_matches * 3
        + description_bonus
        + SOURCE_AUTHORITY.get(article.source, 4)
    )


def top_deep_articles(
    articles: list[Article], candidate_limit: int = 20, per_source_limit: int = 4
) -> dict[str, list[Article]]:
    result: dict[str, list[Article]] = {}
    for topic in DEEP_TOPICS:
        matches = [article for article in articles if is_deep_eligible(article, topic)]
        matches.sort(
            key=lambda article: (
                depth_score(article, topic),
                article.published_at,
            ),
            reverse=True,
        )
        selected: list[Article] = []
        source_counts: dict[str, int] = defaultdict(int)
        for article in matches:
            if source_counts[article.source] >= per_source_limit:
                continue
            if any(similarity(article, existing) >= 0.42 for existing in selected):
                continue
            selected.append(article)
            source_counts[article.source] += 1
            if len(selected) == candidate_limit:
                break
        result[topic] = selected
    return result


def collect_deep_articles(
    sources: list[dict[str, Any]], target_date: date, lookback_days: int
) -> tuple[list[Article], list[dict[str, str]]]:
    articles: list[Article] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as executor:
        futures = {executor.submit(fetch_feed, source): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                articles.extend(
                    article
                    for article in future.result()
                    if in_lookback(article, target_date, lookback_days)
                )
            except Exception as exc:
                errors.append({"source": source["name"], "error": str(exc)})
    unique: dict[str, Article] = {}
    for article in articles:
        unique.setdefault(article.url, article)
    return list(unique.values()), errors


def fallback_item(article: Article, rank: int, topic: str) -> dict[str, Any]:
    topic_name = DEEP_TOPICS[topic]["name_zh"]
    insufficient = (
        "当前仅根据来源提供的标题与摘要生成，尚未验证完整正文中的实验细节与限制。"
    )
    return {
        "rank": rank,
        "title_zh": f"{topic_name}专业文章推荐第{rank}篇",
        "title_original": article.title,
        "why_read_zh": truncate(
            f"该文章来自{article.source}，围绕{topic_name}的专业问题展开，"
            "适合作为进一步技术阅读候选。",
            220,
        ),
        "core_problem_zh": truncate(
            f"文章关注的问题可从原标题和摘要判断，但具体问题边界仍需阅读原文确认。{insufficient}",
            220,
        ),
        "key_ideas_zh": truncate(
            f"候选摘要显示文章包含与{topic_name}相关的方法、系统或研究内容。{insufficient}",
            320,
        ),
        "engineering_takeaway_zh": truncate(
            f"可用于跟进{topic_name}领域的方法和工程实践，应用前应核查原文证据。",
            240,
        ),
        "limitations_zh": truncate(insufficient, 220),
        "source": article.source,
        "published_at": article.published_at.isoformat(),
        "url": article.url,
    }


def fallback_report(target_date: date, articles: list[Article]) -> dict[str, Any]:
    topics = []
    for key, candidates in top_deep_articles(
        articles, candidate_limit=5, per_source_limit=2
    ).items():
        topics.append(
            {
                "key": key,
                "name_zh": DEEP_TOPICS[key]["name_zh"],
                "items": [
                    fallback_item(article, rank, key)
                    for rank, article in enumerate(candidates, start=1)
                ],
            }
        )
    return {"date": target_date.isoformat(), "topics": topics}


def validate_deep_items(
    raw_items: Any, articles: list[Article], topic: str
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list) or len(raw_items) > 5:
        raise ValueError("Codex returned an invalid deep-read item count")
    articles_by_url = {article.url: article for article in articles}
    text_fields = {
        "title_zh": (4, 80),
        "why_read_zh": (30, 220),
        "core_problem_zh": (20, 220),
        "key_ideas_zh": (30, 320),
        "engineering_takeaway_zh": (20, 240),
        "limitations_zh": (20, 220),
    }
    result: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    source_counts: dict[str, int] = defaultdict(int)
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Codex returned a non-object deep-read item")
        url = raw_item.get("url")
        article = articles_by_url.get(url)
        if article is None or not is_deep_eligible(article, topic):
            raise ValueError(f"Codex returned an invalid deep-read URL: {url}")
        if url in seen_urls:
            raise ValueError(f"Codex returned a duplicate deep-read URL: {url}")
        seen_urls.add(url)
        if source_counts[article.source] >= 2:
            continue
        for field, (minimum, maximum) in text_fields.items():
            validate_text_length(raw_item, field, minimum, maximum)
            if not CJK_RE.search(raw_item[field]):
                raise ValueError(f"Codex returned non-Chinese {field}")
        item = dict(raw_item)
        item.update(
            {
                "rank": len(result) + 1,
                "title_original": article.title,
                "source": article.source,
                "published_at": article.published_at.isoformat(),
                "url": article.url,
            }
        )
        result.append(item)
        source_counts[article.source] += 1
    return result


def validate_deep_report(
    report: dict[str, Any], target_date: date, articles: list[Article]
) -> dict[str, Any]:
    if report.get("date") != target_date.isoformat():
        raise ValueError("Codex returned the wrong deep-read date")
    raw_topics = report.get("topics")
    if not isinstance(raw_topics, list) or len(raw_topics) != len(DEEP_TOPICS):
        raise ValueError("Codex returned an invalid deep-read topic count")
    topics = []
    seen: set[str] = set()
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            raise ValueError("Codex returned a non-object deep-read topic")
        key = raw_topic.get("key")
        if key not in DEEP_TOPICS or key in seen:
            raise ValueError(f"Codex returned an invalid deep-read topic: {key}")
        seen.add(key)
        topics.append(
            {
                "key": key,
                "name_zh": DEEP_TOPICS[key]["name_zh"],
                "items": validate_deep_items(raw_topic.get("items"), articles, key),
            }
        )
    topics.sort(key=lambda topic: list(DEEP_TOPICS).index(topic["key"]))
    return {"date": target_date.isoformat(), "topics": topics}


def run_codex_deep_reads(
    project_root: Path,
    target_date: date,
    articles: list[Article],
    codex_bin: str,
) -> dict[str, Any]:
    candidates: list[Article] = []
    seen_urls: set[str] = set()
    for topic_articles in top_deep_articles(articles).values():
        for article in topic_articles:
            if article.url not in seen_urls:
                candidates.append(article)
                seen_urls.add(article.url)
    payload = {
        "date": target_date.isoformat(),
        "candidates": [
            {
                **article.to_dict(),
                "matched_topics": [
                    topic
                    for topic in DEEP_TOPICS
                    if is_deep_eligible(article, topic)
                ],
                "depth_scores": {
                    topic: round(depth_score(article, topic), 2)
                    for topic in DEEP_TOPICS
                    if is_deep_eligible(article, topic)
                },
            }
            for article in candidates
        ],
    }
    prompt = (project_root / "prompts/select_deep_reads.md").read_text(encoding="utf-8")
    schema = project_root / "schemas/deep_reads.schema.json"
    full_prompt = f"{prompt}\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    with tempfile.TemporaryDirectory(prefix="finance-deep-reads-") as temp_dir:
        output_path = Path(temp_dir) / "deep-reads.json"
        completed = subprocess.run(
            [
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
            ],
            cwd=project_root,
            env=os.environ.copy(),
            input=full_prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1200,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"codex exited {completed.returncode}: {completed.stderr[-2000:]}"
            )
        report = json.loads(output_path.read_text(encoding="utf-8"))
        return validate_deep_report(report, target_date, candidates)


def render_deep_markdown(
    report: dict[str, Any], mode: str, lookback_days: int, source_errors: list[dict[str, str]]
) -> str:
    lines = [
        f"# 每周 Cloud Infra 与 AI 技术深度阅读：{report['date']}",
        "",
        f"> 候选窗口：最近 {lookback_days} 天。生成模式：`{mode}`。"
        "本报告与每日新闻报告独立。",
        "",
    ]
    for topic in report.get("topics", []):
        lines.extend([f"## {topic['name_zh']} 专业文章 Top 5", ""])
        if not topic["items"]:
            lines.extend(["本期没有选出达到质量要求的专业文章。", ""])
            continue
        for item in sorted(topic["items"], key=lambda value: value["rank"]):
            lines.extend(
                [
                    f"### {item['rank']}. {item['title_zh']}",
                    "",
                    f"- **原标题：** {item['title_original']}",
                    f"- **来源：** {item['source']}",
                    f"- **发布时间：** {item['published_at']}",
                    f"- **原文：** {item['url']}",
                    f"- **推荐理由：** {item['why_read_zh']}",
                    f"- **核心问题：** {item['core_problem_zh']}",
                    f"- **关键思路：** {item['key_ideas_zh']}",
                    f"- **工程启示：** {item['engineering_takeaway_zh']}",
                    f"- **局限与待验证项：** {item['limitations_zh']}",
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
    return report if report.get("topics") else None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a weekly technical deep-reading report"
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=default_target_date(),
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="candidate publication window in days (default: 7)",
    )
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
    sources = load_sources(project_root / "config/deep_sources.json")
    articles, source_errors = collect_deep_articles(
        sources, args.date, args.lookback_days
    )
    raw_payload = {
        "date": args.date.isoformat(),
        "lookback_days": args.lookback_days,
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "source_count": len(sources),
        "candidate_count": len(articles),
        "source_errors": source_errors,
        "candidates": [article.to_dict() for article in articles],
    }
    atomic_write(
        output_root / "deep-raw" / f"{args.date.isoformat()}-candidates.json",
        pretty_json(raw_payload),
    )

    mode = "rules-fallback"
    codex_error = ""
    report = fallback_report(args.date, articles)
    if args.use_codex and articles:
        try:
            report = run_codex_deep_reads(
                project_root, args.date, articles, args.codex_bin
            )
            mode = "codex"
        except Exception as exc:
            codex_error = str(exc)

    report_dir = output_root / "deep-reads"
    report_json = report_dir / f"{args.date.isoformat()}.json"
    if args.use_codex and codex_error:
        successful = load_successful_report(report_json, args.date)
        if successful is not None:
            report = successful
            mode = "codex-preserved"
    report["metadata"] = {
        "mode": mode,
        "lookback_days": args.lookback_days,
        "candidate_count": len(articles),
        "source_errors": source_errors,
        "codex_error": codex_error,
    }
    report_md = report_dir / f"{args.date.isoformat()}.md"
    atomic_write(report_json, pretty_json(report))
    atomic_write(
        report_md,
        render_deep_markdown(report, mode, args.lookback_days, source_errors),
    )
    shutil.copyfile(report_json, report_dir / "latest.json")
    shutil.copyfile(report_md, report_dir / "latest.md")
    atomic_write(
        output_root / "deep-status/latest.json",
        pretty_json(
            {
                "date": args.date.isoformat(),
                "generated_at": datetime.now(TIMEZONE).isoformat(),
                "mode": mode,
                "lookback_days": args.lookback_days,
                "candidate_count": len(articles),
                "selected_count": sum(
                    len(topic["items"]) for topic in report.get("topics", [])
                ),
                "source_error_count": len(source_errors),
                "codex_error": codex_error,
            }
        ),
    )
    print(report_md)
    if not articles:
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
        print(f"finance-deep-reads: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
