from __future__ import annotations

import unittest
import json
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from finance_digest.reddit_digest import (
    RedditRSSClient,
    RedditPost,
    collect_reddit_posts,
    fallback_report,
    in_lookback,
    investment_relevance,
    load_successful_report,
    parse_args,
    parse_reddit_comment_feed,
    parse_reddit_listing_feed,
    render_reddit_markdown,
    reddit_time_filter,
    select_candidates,
    validate_reddit_items,
)


LISTING = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <category term="kubernetes"/>
    <content type="html">&lt;div&gt;Production reliability lessons.&lt;/div&gt; submitted by /u/example</content>
    <id>t3_post1</id>
    <link href="https://www.reddit.com/r/kubernetes/comments/post1/example/"/>
    <published>2026-06-11T03:00:00+00:00</published>
    <title>Production Kubernetes reliability lessons</title>
  </entry>
</feed>"""

COMMENTS = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>t3_post1</id><content>Original post</content></entry>
  <entry><id>t1_comment1</id><content>We found the same failure mode in production and fixed it with admission controls.</content></entry>
  <entry><id>t1_comment2</id><content>The trade-off is higher operational complexity and slower deployment cycles.</content></entry>
</feed>"""


def listing_feed(
    subreddit: str,
    post_id: str,
    title: str,
    body: str = "Production reliability discussion.",
) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <category term="{subreddit}"/>
    <content type="html">{body}</content>
    <id>t3_{post_id}</id>
    <link href="https://www.reddit.com/r/{subreddit}/comments/{post_id}/example/"/>
    <published>2026-06-11T03:00:00+00:00</published>
    <title>{title}</title>
  </entry>
</feed>""".encode()


class RedditDigestTest(unittest.TestCase):
    def post(self, post_id: str, title: str, rank: int = 1) -> RedditPost:
        return RedditPost(
            post_id=post_id,
            topic="cloud_infra",
            title=title,
            subreddit="kubernetes",
            url=f"https://www.reddit.com/r/kubernetes/comments/{post_id}/example/",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            body="Production architecture and reliability discussion.",
            listing_rank=rank,
        )

    def test_default_window_is_daily(self) -> None:
        args = parse_args([])
        self.assertEqual(args.lookback_days, 1)
        self.assertEqual(args.candidate_limit, 12)

    def test_reddit_sort_window_matches_report_window(self) -> None:
        self.assertEqual(reddit_time_filter(1), "day")
        self.assertEqual(reddit_time_filter(7), "week")

    def test_daily_window_uses_target_china_calendar_day(self) -> None:
        target = date(2026, 6, 11)
        self.assertTrue(
            in_lookback(datetime(2026, 6, 10, 16, tzinfo=timezone.utc), target, 1)
        )
        self.assertTrue(
            in_lookback(
                datetime(2026, 6, 11, 15, 59, tzinfo=timezone.utc), target, 1
            )
        )
        self.assertFalse(
            in_lookback(datetime(2026, 6, 10, 15, 59, tzinfo=timezone.utc), target, 1)
        )
        self.assertFalse(
            in_lookback(datetime(2026, 6, 11, 16, tzinfo=timezone.utc), target, 1)
        )

    def test_listing_parser_discards_username_footer(self) -> None:
        posts = parse_reddit_listing_feed(
            LISTING, "cloud_infra", date(2026, 6, 11), 1
        )
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].subreddit, "kubernetes")
        self.assertEqual(posts[0].body, "Production reliability lessons.")
        self.assertNotIn("/u/", posts[0].body)

    def test_rss_listing_fetches_each_subreddit_and_preserves_partial_results(
        self,
    ) -> None:
        class FakeHTTP:
            def __init__(self) -> None:
                self.urls: list[str] = []

            def request(self, request: object, retries: int = 5) -> bytes:
                url = request.full_url
                self.urls.append(url)
                if "/r/sysadmin/" in url:
                    raise OSError("temporary feed failure")
                return listing_feed(
                    "kubernetes",
                    "kubernetes-post",
                    "Kubernetes infrastructure cost and reliability",
                )

        client = RedditRSSClient()
        fake_http = FakeHTTP()
        client.http = fake_http
        posts = client.listing(
            "cloud_infra",
            ["kubernetes", "sysadmin"],
            date(2026, 6, 11),
            1,
            20,
        )

        self.assertEqual([post.post_id for post in posts], ["kubernetes-post"])
        self.assertEqual(len(fake_http.urls), 2)
        self.assertTrue(any("/r/kubernetes/top/" in url for url in fake_http.urls))
        self.assertTrue(any("/r/sysadmin/top/" in url for url in fake_http.urls))
        self.assertEqual(client.errors[0]["source"], "r/sysadmin")

    def test_comment_parser_does_not_persist_authors(self) -> None:
        comments = parse_reddit_comment_feed(COMMENTS, "post1", 8)
        self.assertEqual(len(comments), 2)
        self.assertNotIn("Original post", comments)

    def test_candidate_selection_rejects_low_signal_and_duplicates(self) -> None:
        professional = self.post("one", "Production Kubernetes reliability lessons")
        duplicate = self.post(
            "two", "Kubernetes production reliability lessons", rank=2
        )
        career = self.post("three", "My Kubernetes certification career journey")
        selected = select_candidates(
            [professional, duplicate, career],
            {"subreddit_weights": {"kubernetes": 10}},
            5,
        )
        self.assertEqual(selected, [professional])

    def test_macro_job_discussion_is_not_rejected_as_a_job_post(self) -> None:
        post = self.post("jobs", "Why did the jobs report surprise economists?")
        selected = select_candidates(
            [post], {"subreddit_weights": {"kubernetes": 10}}, 5
        )
        self.assertEqual(selected, [post])

    def test_candidate_selection_limits_one_subreddit_to_three_items(self) -> None:
        posts = [
            self.post("same-1", "Kubernetes networking outage", 1),
            self.post("same-2", "Database replication failure", 2),
            self.post("same-3", "Observability alert fatigue", 3),
            self.post("same-4", "Cloud storage capacity planning", 4),
        ]
        selected = select_candidates(
            posts, {"subreddit_weights": {"kubernetes": 10}}, 5
        )
        self.assertEqual(len(selected), 3)

    def test_collection_reports_candidate_pool_and_subreddit_distribution(
        self,
    ) -> None:
        class FakeClient:
            mode = "rss"

            def __init__(self, posts: list[RedditPost]) -> None:
                self.posts = posts
                self.errors = [{"source": "r/sysadmin", "error": "feed unavailable"}]

            def listing(self, *args: object) -> list[RedditPost]:
                return self.posts

        kubernetes = self.post(
            "kubernetes", "Kubernetes infrastructure cost and reliability"
        )
        sysadmin = self.post("sysadmin", "Cloud capacity planning and capex", 2)
        sysadmin.subreddit = "sysadmin"
        low_signal = self.post("career", "My cloud certification career journey", 3)
        client = FakeClient([kubernetes, sysadmin, low_signal])

        candidates, errors, stats = collect_reddit_posts(
            client,
            {
                "cloud_infra": {
                    "subreddits": ["kubernetes", "sysadmin"],
                    "subreddit_weights": {"kubernetes": 10, "sysadmin": 9},
                }
            },
            date(2026, 6, 11),
            1,
            12,
            0,
        )

        self.assertEqual(len(candidates["cloud_infra"]), 2)
        self.assertEqual(errors[0]["source"], "r/sysadmin")
        self.assertEqual(
            stats["cloud_infra"],
            {
                "fetched_count": 3,
                "eligible_count": 2,
                "candidate_count": 2,
                "subreddit_counts": {"kubernetes": 2, "sysadmin": 1},
            },
        )
        self.assertEqual(client.errors, [])

    def test_value_investing_signal_outranks_generic_popularity(self) -> None:
        generic = self.post("generic", "Interesting Kubernetes discussion", 1)
        fundamental = self.post(
            "fundamental",
            "Cloud capex and pricing power reshape free cash flow",
            10,
        )
        selected = select_candidates(
            [generic, fundamental],
            {"subreddit_weights": {"kubernetes": 10}},
            1,
        )
        self.assertEqual(selected, [fundamental])
        self.assertGreater(investment_relevance(fundamental), 0)

    def test_speculative_trading_content_is_rejected(self) -> None:
        post = self.post("speculation", "Technical analysis price prediction to the moon")
        selected = select_candidates(
            [post], {"subreddit_weights": {"kubernetes": 10}}, 5
        )
        self.assertEqual(selected, [])

    def test_public_candidate_data_excludes_post_and_comment_content(self) -> None:
        post = self.post("private", "Production reliability discussion")
        post.sampled_comments = ["A detailed comment that is used only during summarization."]
        public = post.public_dict()
        self.assertNotIn("body", public)
        self.assertNotIn("sampled_comments", public)
        self.assertEqual(public["sampled_comment_count"], 1)

    def test_fallback_report_and_markdown_are_separate(self) -> None:
        topics = {"cloud_infra": {"name_zh": "Cloud Infra Engineering"}}
        report = fallback_report(date(2026, 6, 11), topics, {"cloud_infra": [self.post("one", "Example")]})
        markdown = render_reddit_markdown(report, "rules-fallback", "rss", 1, [])
        self.assertIn("# 每日 Reddit 社区 Topic 观察：2026-06-11", markdown)
        self.assertIn("## Cloud Infra Engineering 社区讨论 Top 3", markdown)
        self.assertIn("**基本面影响：**", markdown)
        self.assertIn("**价值投资者视角：**", markdown)
        self.assertIn("**待验证数据：**", markdown)
        self.assertNotIn("每日专业 Topic 新闻", markdown)

    def test_validator_rejects_unknown_url(self) -> None:
        raw = [
            {
                "url": "https://example.com/unknown",
                "title_zh": "专业讨论摘要",
                "summary_zh": "这是一段用于测试的中文讨论摘要，长度足以通过字段长度校验并说明主题内容。",
                "community_signal_zh": "样本评论对主要技术方向形成了一定共识，但仍需要验证。",
                "fundamental_impact_zh": "该讨论可能影响企业成本、资本开支和长期现金流，但具体幅度需要验证。",
                "value_investor_takeaway_zh": "价值投资者应把它作为研究线索，结合公司基本面和估值进一步判断。",
                "key_risks_zh": "社区样本存在选择偏差，短期讨论热度也不能代表趋势能够持续。",
                "evidence_to_verify_zh": "需要核查公司披露、行业需求、竞争格局、资本回报和估值数据。",
            }
        ]
        with self.assertRaises(ValueError):
            validate_reddit_items(raw, [self.post("one", "Example")])

    def test_validator_adds_value_investing_metadata(self) -> None:
        post = self.post(
            "fundamental",
            "Cloud capex and pricing power reshape free cash flow",
        )
        post.investment_score = investment_relevance(post)
        raw = [
            {
                "url": post.url,
                "title_zh": "云资本开支与定价权影响长期现金流",
                "summary_zh": "讨论聚焦云基础设施资本开支、定价能力与自由现金流之间的长期关系，并提出行业竞争可能改变回报结构。",
                "community_signal_zh": "帖子提供了行业关注方向，但没有评论样本支持其代表广泛共识。",
                "fundamental_impact_zh": "若资本开支增速长期超过收入增速，企业自由现金流与资本回报率可能承压。",
                "value_investor_takeaway_zh": "价值投资者应重点比较增长投入带来的增量回报，而不是只关注收入增速。",
                "key_risks_zh": "帖子未提供公司数据，成本上升也可能被规模效应和定价权抵消。",
                "evidence_to_verify_zh": "需要核查资本开支、自由现金流、增量资本回报率、客户留存和价格变化。",
            }
        ]
        items = validate_reddit_items(raw, [post])
        self.assertEqual(items[0]["investment_score"], post.investment_score)
        self.assertGreater(items[0]["investment_score"], 0)

    def test_old_report_shape_is_not_preserved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "date": "2026-06-11",
                        "topics": [
                            {
                                "key": "cloud_infra",
                                "items": [{"consensus_zh": "old shape"}],
                            }
                        ],
                        "metadata": {"mode": "codex"},
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(load_successful_report(path, date(2026, 6, 11)))


if __name__ == "__main__":
    unittest.main()
