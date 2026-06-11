from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from finance_digest.deep_reads import (
    fallback_report,
    in_lookback,
    is_deep_eligible,
    render_deep_markdown,
    top_deep_articles,
    validate_deep_items,
)
from finance_digest.models import Article


class DeepReadsTest(unittest.TestCase):
    def article(
        self,
        article_id: str,
        title: str,
        topic: str,
        source: str = "Example Research",
        description: str = "Architecture analysis with experiments and performance benchmarks.",
    ) -> Article:
        return Article(
            article_id=article_id,
            title=title,
            url=f"https://example.com/{article_id}",
            source=source,
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            description=description,
            category=topic,
            source_weight=10,
            topics=[topic],
        )

    def test_lookback_window_is_not_limited_to_one_day(self) -> None:
        article = self.article("window", "Distributed database architecture", "cloud_infra")
        self.assertTrue(in_lookback(article, date(2026, 6, 12), 45))
        self.assertFalse(in_lookback(article, date(2026, 8, 1), 45))

    def test_basic_tutorial_is_rejected(self) -> None:
        article = self.article(
            "tutorial",
            "How to configure a cloud database",
            "cloud_infra",
        )
        self.assertFalse(is_deep_eligible(article, "cloud_infra"))

    def test_marketing_blueprint_is_rejected(self) -> None:
        article = self.article(
            "marketing",
            "Cloud AI blueprint for mission impact",
            "cloud_infra",
        )
        self.assertFalse(is_deep_eligible(article, "cloud_infra"))

    def test_professional_article_is_eligible(self) -> None:
        article = self.article(
            "professional",
            "Analyzing distributed database reliability at scale",
            "cloud_infra",
        )
        self.assertTrue(is_deep_eligible(article, "cloud_infra"))

    def test_deep_report_is_separate_and_has_only_two_topics(self) -> None:
        articles = [
            self.article(
                "cloud",
                "Distributed database architecture and performance",
                "cloud_infra",
            ),
            self.article(
                "ai",
                "Evaluating language model reasoning",
                "ai_frontier",
            ),
        ]
        report = fallback_report(date(2026, 6, 12), articles)
        markdown = render_deep_markdown(report, "rules-fallback", 45, [])
        self.assertEqual(
            [topic["key"] for topic in report["topics"]],
            ["cloud_infra", "ai_frontier"],
        )
        self.assertIn("# Cloud Infra 与 AI 技术深度阅读：2026-06-12", markdown)
        self.assertIn("## Cloud Infra Engineering 专业文章 Top 5", markdown)
        self.assertIn("## AI 前沿 专业文章 Top 5", markdown)
        self.assertNotIn("每日专业 Topic 新闻", markdown)

    def test_candidate_pool_deduplicates_similar_articles(self) -> None:
        first = self.article(
            "first",
            "Testing distributed database reliability at scale",
            "cloud_infra",
        )
        duplicate = self.article(
            "duplicate",
            "Testing distributed database reliability at global scale",
            "cloud_infra",
            source="Another Research Group",
        )
        self.assertEqual(len(top_deep_articles([first, duplicate])["cloud_infra"]), 1)

    def test_codex_selection_rejects_more_than_two_items_from_one_source(self) -> None:
        articles = [
            self.article(
                f"same-source-{index}",
                f"Distributed system architecture benchmark number {index}",
                "cloud_infra",
            )
            for index in range(3)
        ]
        raw_items = [
            {
                "url": article.url,
                "title_zh": "分布式系统架构基准分析",
                "why_read_zh": "文章包含系统架构、性能基准和工程权衡，适合用于理解大规模系统实践。",
                "core_problem_zh": "文章研究分布式系统在规模扩大后的性能与可靠性问题。",
                "key_ideas_zh": "文章通过架构分析和性能实验比较不同设计方案及其工程权衡。",
                "engineering_takeaway_zh": "工程团队可据此评估类似系统设计，但需要结合自身负载验证。",
                "limitations_zh": "候选摘要未提供完整实验配置，结论仍需通过原文进一步核查。",
            }
            for article in articles
        ]
        with self.assertRaises(ValueError):
            validate_deep_items(raw_items, articles, "cloud_infra")


if __name__ == "__main__":
    unittest.main()
