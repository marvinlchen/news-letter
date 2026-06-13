from __future__ import annotations

import unittest
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from finance_digest.codex import validate_digest
from finance_digest.cli import load_successful_digest
from finance_digest.collect import in_target_date
from finance_digest.feeds import parse_feed, parse_world_bank_news
from finance_digest.models import Article
from finance_digest.ranking import (
    TOPICS,
    classify_topics,
    is_article_eligible_for_topic,
    is_low_signal,
    score_articles,
    topic_top_articles,
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

    def test_parse_world_bank_news_api(self) -> None:
        data = json.dumps(
            {
                "documents": {
                    "id": {
                        "title": {"cdata!": "World Bank releases economic outlook"},
                        "url": "http://www.worldbank.org/en/news/example",
                        "lnchdt": "2026-06-11T10:42:00Z",
                        "descr": {"cdata!": "Growth projections were updated."},
                    }
                }
            }
        ).encode()
        articles = parse_world_bank_news(
            data,
            {
                "name": "World Bank",
                "weight": 9,
                "category": "finance",
            },
        )
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].source, "World Bank")
        self.assertEqual(articles[0].description, "Growth projections were updated.")

    def test_date_filter_uses_china_time(self) -> None:
        self.assertTrue(in_target_date(self.articles[0], date(2026, 6, 10)))
        self.assertFalse(in_target_date(self.articles[0], date(2026, 6, 11)))

    def test_impact_terms_affect_score(self) -> None:
        ranked = score_articles(self.articles)
        self.assertIn("Federal Reserve", ranked[0].title)
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_articles_are_classified_into_topics(self) -> None:
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
            classify_topics(article), ["shipping", "technology", "consumer"]
        )

    def test_authoritative_source_topic_is_preserved(self) -> None:
        article = Article(
            article_id="authoritative",
            title="New AI model release notes",
            url="https://example.com/authoritative",
            source="Example",
            published_at=self.articles[0].published_at,
            description="",
            category="ai_frontier",
            source_weight=10,
            topics=["ai_frontier"],
        )
        self.assertEqual(classify_topics(article), ["ai_frontier"])

    def test_authoritative_topic_binding_does_not_require_title_keyword(self) -> None:
        article = Article(
            article_id="authoritative-bound",
            title="The machines behind the machines",
            url="https://example.com/authoritative-bound",
            source="Example Semiconductor Authority",
            published_at=self.articles[0].published_at,
            description="",
            category="technology",
            source_weight=10,
            topics=["technology"],
            topic_binding="authoritative",
        )
        self.assertTrue(is_article_eligible_for_topic(article, "technology"))

    def test_keyword_required_binding_still_rejects_irrelevant_index_result(self) -> None:
        article = Article(
            article_id="noisy-bound",
            title="Central bank holds interest rates",
            url="https://example.com/noisy-bound",
            source="Example Broad Index",
            published_at=self.articles[0].published_at,
            description="",
            category="shipping",
            source_weight=10,
            topics=["shipping"],
        )
        self.assertFalse(is_article_eligible_for_topic(article, "shipping"))

    def test_authoritative_source_does_not_cross_classify_topics(self) -> None:
        article = Article(
            article_id="authoritative-cloud",
            title="Cloud platform adds AI model inference support",
            url="https://example.com/authoritative-cloud",
            source="Example Cloud Engineering",
            published_at=self.articles[0].published_at,
            description="",
            category="cloud_infra",
            source_weight=10,
            topics=["cloud_infra"],
        )
        self.assertEqual(classify_topics(article), ["cloud_infra"])

    def test_multi_topic_source_requires_topic_relevance(self) -> None:
        article = Article(
            article_id="multi-topic",
            title="Critical minerals reshape global trade",
            url="https://example.com/multi-topic",
            source="Example Authority",
            published_at=self.articles[0].published_at,
            description="",
            category="finance",
            source_weight=10,
            topics=["macroeconomics", "shipping", "commodities"],
        )
        self.assertTrue(is_article_eligible_for_topic(article, "commodities"))
        self.assertFalse(is_article_eligible_for_topic(article, "shipping"))

    def test_successful_digest_can_be_preserved_after_codex_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "digest.json"
            path.write_text(
                json.dumps(
                    {
                        "date": "2026-06-10",
                        "topics": [
                            {"key": key, "items": []}
                            for key in TOPICS
                        ],
                        "metadata": {"mode": "codex"},
                    }
                ),
                encoding="utf-8",
            )
            digest = load_successful_digest(path, date(2026, 6, 10))
            self.assertIsNotNone(digest)
            self.assertEqual(
                [topic["key"] for topic in digest["topics"]],
                list(TOPICS),
            )

    def test_incompatible_old_digest_is_not_preserved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "digest.json"
            path.write_text(
                json.dumps(
                    {
                        "date": "2026-06-10",
                        "topics": [{"key": "shipping", "items": []}],
                        "metadata": {"mode": "codex"},
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(load_successful_digest(path, date(2026, 6, 10)))

    def test_fallback_digest_is_not_preserved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "digest.json"
            path.write_text(
                json.dumps(
                    {
                        "date": "2026-06-10",
                        "topics": [{"key": "shipping", "items": []}],
                        "metadata": {"mode": "rules-fallback"},
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(load_successful_digest(path, date(2026, 6, 10)))

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
        self.assertEqual(topic_top_articles(ranked, limit=1)["technology"], [direct])

    def test_industry_ranking_deduplicates_the_same_event(self) -> None:
        first = Article(
            article_id="first",
            title="Palantir CEO says businesses are unhappy with frontier AI model labs",
            url="https://example.com/first",
            source="Example One",
            published_at=self.articles[0].published_at,
            description="",
            category="technology",
            source_weight=10,
        )
        duplicate = Article(
            article_id="duplicate",
            title="Palantir chief says companies unhappy with frontier AI model labs",
            url="https://example.com/duplicate",
            source="Example Two",
            published_at=self.articles[0].published_at,
            description="",
            category="technology",
            source_weight=9,
        )
        ranked = score_articles([first, duplicate])
        self.assertEqual(len(topic_top_articles(ranked)["ai_frontier"]), 1)

    def test_topic_ranking_limits_one_source_to_two_items(self) -> None:
        titles = [
            "Kubernetes networking proxy release",
            "PostgreSQL database performance update",
            "Serverless observability platform launch",
        ]
        articles = [
            Article(
                article_id=f"cloud-{index}",
                title=title,
                url=f"https://example.com/cloud-{index}",
                source="Example Cloud",
                published_at=self.articles[0].published_at,
                description="",
                category="cloud_infra",
                source_weight=10,
                topics=["cloud_infra"],
            )
            for index, title in enumerate(titles)
        ]
        ranked = score_articles(articles)
        self.assertEqual(len(topic_top_articles(ranked)["cloud_infra"]), 2)

    def test_generic_safety_story_is_not_ai_frontier_news(self) -> None:
        article = Article(
            article_id="generic-safety",
            title="For Robotaxis, Safety Must Be Built In",
            url="https://example.com/generic-safety",
            source="Example AI Lab",
            published_at=self.articles[0].published_at,
            description="",
            category="ai_frontier",
            source_weight=10,
            topics=["ai_frontier"],
        )
        ranked = score_articles([article])
        self.assertEqual(topic_top_articles(ranked)["ai_frontier"], [])

    def test_fallback_report_contains_all_topic_sections_without_top10(self) -> None:
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
        self.assertNotIn("财经新闻 Top 10", report)
        self.assertIn("## 宏观经济 Top 3", report)
        self.assertIn("## 航运 Top 3", report)
        self.assertIn("## 大宗商品 Top 3", report)
        self.assertIn("## 股票市场 Top 3", report)
        self.assertIn("## 科技产业 Top 3", report)
        self.assertIn("## 消费 Top 3", report)
        self.assertIn("## Cloud Infra Engineering Top 3", report)
        self.assertIn("## AI 前沿 Top 3", report)
        self.assertNotIn("- **中文标题：**", report)
        self.assertIn("- **原标题：** Container shipping rates rise", report)
        self.assertIn("- **摘要：** 可信来源发布一则航运消息", report)

    def test_all_eight_topics_are_configured(self) -> None:
        self.assertEqual(
            list(TOPICS),
            [
                "macroeconomics",
                "shipping",
                "commodities",
                "stock_market",
                "technology",
                "consumer",
                "cloud_infra",
                "ai_frontier",
            ],
        )

    def test_stock_market_topic_selects_daily_market_move(self) -> None:
        article = Article(
            article_id="stock-move",
            title="Nvidia shares jump 12% after earnings beat estimates",
            url="https://example.com/stock-move",
            source="Example Markets",
            published_at=self.articles[0].published_at,
            description="The stock recorded its largest daily gain this year.",
            category="stock_market",
            source_weight=10,
            topics=["stock_market"],
        )
        ranked = score_articles([article])
        self.assertEqual(topic_top_articles(ranked)["stock_market"], [article])

    def test_stock_market_topic_rejects_ipo_commentary_without_a_move(self) -> None:
        article = Article(
            article_id="stock-ipo",
            title="Space company prepares for stock market debut",
            url="https://example.com/stock-ipo",
            source="Example Markets",
            published_at=self.articles[0].published_at,
            description="The IPO could transform the company.",
            category="stock_market",
            source_weight=10,
            topics=["stock_market"],
        )
        ranked = score_articles([article])
        self.assertEqual(topic_top_articles(ranked)["stock_market"], [])

    def test_stock_market_topic_rejects_crude_inventory_move(self) -> None:
        article = Article(
            article_id="crude-stocks",
            title="US crude stocks fall sharply as refiners increase activity",
            url="https://example.com/crude-stocks",
            source="Example Markets",
            published_at=self.articles[0].published_at,
            description="",
            category="stock_market",
            source_weight=10,
            topics=["stock_market"],
        )
        ranked = score_articles([article])
        self.assertEqual(topic_top_articles(ranked)["stock_market"], [])

    def test_stock_market_topic_deduplicates_same_market_move(self) -> None:
        articles = [
            Article(
                article_id="market-rally-one",
                title="Equities rally as Trump cancels Iran attacks",
                url="https://example.com/market-rally-one",
                source="Example One",
                published_at=self.articles[0].published_at,
                description="",
                category="stock_market",
                source_weight=10,
                topics=["stock_market"],
            ),
            Article(
                article_id="market-rally-two",
                title="Stocks bounce after Trump ends Iran strikes",
                url="https://example.com/market-rally-two",
                source="Example Two",
                published_at=self.articles[0].published_at,
                description="",
                category="stock_market",
                source_weight=9,
                topics=["stock_market"],
            ),
        ]
        ranked = score_articles(articles)
        self.assertEqual(len(topic_top_articles(ranked)["stock_market"]), 1)

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

    def test_low_signal_official_index_pages_are_filtered(self) -> None:
        article = Article(
            article_id="official-junk",
            title="News/Press Release Contact Form - Official Agency",
            url="https://example.com/contact",
            source="Official Agency",
            published_at=self.articles[0].published_at,
            description="",
            category="finance",
            source_weight=10,
        )
        self.assertTrue(is_low_signal(article))
        self.assertEqual(score_articles([article]), [])

    def test_low_signal_raw_edgar_filings_are_filtered(self) -> None:
        article = Article(
            article_id="edgar-junk",
            title="EDGAR Filing Documents for 0001193125-26-266936 - SEC.gov",
            url="https://example.com/edgar",
            source="SEC.gov",
            published_at=self.articles[0].published_at,
            description="",
            category="regulation",
            source_weight=9,
        )
        self.assertTrue(is_low_signal(article))
        self.assertEqual(score_articles([article]), [])

    def test_codex_metadata_must_match_a_candidate(self) -> None:
        article = self.articles[0]
        summary = "这是用于验证财经摘要长度、中文标题与元数据覆盖逻辑的中等长度事件概述。" * 3
        digest = {
            "date": "2026-06-10",
            "topics": [
                {
                    "key": "macroeconomics",
                    "name_zh": "宏观经济",
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
                },
                {"key": "shipping", "name_zh": "航运", "items": []},
                {"key": "commodities", "name_zh": "大宗商品", "items": []},
                {"key": "stock_market", "name_zh": "股票市场", "items": []},
                {"key": "technology", "name_zh": "科技产业", "items": []},
                {"key": "consumer", "name_zh": "消费", "items": []},
                {
                    "key": "cloud_infra",
                    "name_zh": "Cloud Infra Engineering",
                    "items": [],
                },
                {"key": "ai_frontier", "name_zh": "AI 前沿", "items": []},
            ],
        }
        validated = validate_digest(digest, date(2026, 6, 10), [article])
        item = validated["topics"][0]["items"][0]
        self.assertEqual(item["rank"], 1)
        self.assertEqual(item["source"], article.source)
        self.assertEqual(item["title_original"], article.title)

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
