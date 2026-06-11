from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from finance_digest.codex import validate_digest
from finance_digest.collect import in_target_date
from finance_digest.feeds import parse_feed
from finance_digest.models import Article
from finance_digest.ranking import (
    classify_sectors,
    is_low_signal,
    score_articles,
    sector_top_articles,
)
from finance_digest.render import fallback_digest, render_markdown


ROOT = Path(__file__).resolve().parents[1]


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        data = (ROOT / "tests/fixtures/sample.xml").read_bytes()
        self.articles = parse_feed(
            data,
            {"name": "Fixture", "weight": 10, "category": "markets"},
        )

    def test_parse_and_normalize(self) -> None:
        self.assertEqual(len(self.articles), 2)
        self.assertEqual(self.articles[0].source, "Example Wire")
        self.assertEqual(self.articles[0].url, "https://example.com/rates")

    def test_date_filter_uses_china_time(self) -> None:
        self.assertTrue(in_target_date(self.articles[0], date(2026, 6, 10)))
        self.assertFalse(in_target_date(self.articles[0], date(2026, 6, 11)))

    def test_impact_terms_affect_score(self) -> None:
        ranked = score_articles(self.articles)
        self.assertIn("Federal Reserve", ranked[0].title)
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_articles_are_classified_into_industry_sectors(self) -> None:
        article = Article(
            article_id="sector",
            title="Chip maker warns port delays will raise freight costs",
            url="https://example.com/sector",
            source="Example",
            published_at=self.articles[0].published_at,
            description="Retail customers may see higher prices.",
            category="finance",
            source_weight=10,
        )
        self.assertEqual(
            classify_sectors(article), ["shipping", "technology", "consumer"]
        )

    def test_targeted_source_category_does_not_force_sector_match(self) -> None:
        article = Article(
            article_id="irrelevant",
            title="Government announces a tariff refund process",
            url="https://example.com/irrelevant",
            source="Example",
            published_at=self.articles[0].published_at,
            description="The policy takes effect immediately.",
            category="shipping",
            source_weight=10,
        )
        self.assertEqual(classify_sectors(article), [])

    def test_industry_ranking_ignores_incidental_macro_mentions(self) -> None:
        direct = Article(
            article_id="direct-tech",
            title="Chip maker launches new AI data center platform",
            url="https://example.com/direct-tech",
            source="Example",
            published_at=self.articles[0].published_at,
            description="",
            category="technology",
            source_weight=10,
        )
        incidental = Article(
            article_id="incidental-tech",
            title="World markets fall as AI stocks and oil shocks weigh",
            url="https://example.com/incidental-tech",
            source="Example",
            published_at=self.articles[0].published_at,
            description="",
            category="technology",
            source_weight=10,
        )
        ranked = score_articles([incidental, direct])
        self.assertEqual(sector_top_articles(ranked, limit=1)["technology"], [direct])

    def test_industry_ranking_deduplicates_the_same_event(self) -> None:
        first = Article(
            article_id="first",
            title="Palantir CEO says businesses are unhappy with AI labs",
            url="https://example.com/first",
            source="Example One",
            published_at=self.articles[0].published_at,
            description="",
            category="technology",
            source_weight=10,
        )
        duplicate = Article(
            article_id="duplicate",
            title="Palantir chief says companies unhappy with frontier AI labs",
            url="https://example.com/duplicate",
            source="Example Two",
            published_at=self.articles[0].published_at,
            description="",
            category="technology",
            source_weight=9,
        )
        ranked = score_articles([first, duplicate])
        self.assertEqual(len(sector_top_articles(ranked)["technology"]), 1)

    def test_fallback_report_contains_all_industry_sections(self) -> None:
        article = Article(
            article_id="shipping",
            title="Container shipping rates rise",
            url="https://example.com/shipping",
            source="Example",
            published_at=self.articles[0].published_at,
            description="Freight costs increased.",
            category="shipping",
            source_weight=10,
        )
        digest = fallback_digest(date(2026, 6, 10), score_articles([article]))
        report = render_markdown(digest, "rules-fallback", [])
        self.assertIn("# 行业新闻 Top 3", report)
        self.assertIn("## 航运 Top 3", report)
        self.assertIn("## 大宗商品 Top 3", report)
        self.assertIn("## 科技 Top 3", report)
        self.assertIn("## 消费 Top 3", report)
        self.assertIn("- **中文标题：** 财经第1条要闻：可信来源报道", report)
        self.assertIn("- **原标题：** Container shipping rates rise", report)
        self.assertIn("- **摘要：** 可信来源发布一则财经消息", report)

    def test_low_signal_company_announcements_are_filtered(self) -> None:
        article = Article(
            article_id="low-signal",
            title="Example Fund: Net Asset Value(s) - Company Announcement",
            url="https://example.com/nav",
            source="Example",
            published_at=self.articles[0].published_at,
            description="",
            category="finance",
            source_weight=10,
        )
        self.assertTrue(is_low_signal(article))
        self.assertEqual(score_articles([article]), [])

    def test_codex_metadata_must_match_a_candidate(self) -> None:
        article = self.articles[0]
        summary = "这是用于验证财经摘要长度、中文标题与元数据覆盖逻辑的中等长度事件概述。" * 3
        digest = {
            "date": "2026-06-10",
            "items": [
                {
                    "rank": 99,
                    "title_zh": "美联储宣布调整利率政策",
                    "title_original": "fabricated",
                    "summary_zh": summary,
                    "category": "fabricated",
                    "source": "fabricated",
                    "published_at": "fabricated",
                    "url": article.url,
                    "confidence": "high",
                }
            ],
            "sectors": [
                {"key": "shipping", "name_zh": "航运", "items": []},
                {"key": "commodities", "name_zh": "大宗商品", "items": []},
                {"key": "technology", "name_zh": "科技", "items": []},
                {"key": "consumer", "name_zh": "消费", "items": []},
            ],
        }
        validated = validate_digest(digest, date(2026, 6, 10), [article])
        self.assertEqual(validated["items"][0]["rank"], 1)
        self.assertEqual(validated["items"][0]["source"], article.source)
        self.assertEqual(validated["items"][0]["title_original"], article.title)

    def test_codex_short_summary_is_rejected(self) -> None:
        article = self.articles[0]
        digest = {
            "date": "2026-06-10",
            "items": [
                {
                    "url": article.url,
                    "title_zh": "中文财经标题",
                    "summary_zh": "太短",
                }
            ],
        }
        with self.assertRaises(ValueError):
            validate_digest(digest, date(2026, 6, 10), [article])

    def test_codex_english_title_is_rejected(self) -> None:
        article = self.articles[0]
        digest = {
            "date": "2026-06-10",
            "items": [
                {
                    "url": article.url,
                    "title_zh": "Federal Reserve Changes Rates",
                    "summary_zh": "这是用于验证英文标题会被拒绝的中文财经新闻摘要。" * 5,
                }
            ],
        }
        with self.assertRaises(ValueError):
            validate_digest(digest, date(2026, 6, 10), [article])

    def test_codex_english_summary_is_rejected(self) -> None:
        article = self.articles[0]
        digest = {
            "date": "2026-06-10",
            "items": [
                {
                    "url": article.url,
                    "title_zh": "中文财经标题",
                    "summary_zh": "This English-only summary is intentionally long enough to pass the configured minimum length check.",
                }
            ],
        }
        with self.assertRaises(ValueError):
            validate_digest(digest, date(2026, 6, 10), [article])

    def test_codex_unknown_url_is_rejected(self) -> None:
        digest = {
            "date": "2026-06-10",
            "items": [{"url": "https://example.com/unknown"}],
        }
        with self.assertRaises(ValueError):
            validate_digest(digest, date(2026, 6, 10), self.articles)


if __name__ == "__main__":
    unittest.main()
