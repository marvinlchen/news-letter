from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from finance_digest.reddit_digest import (
    RedditPost,
    fallback_report,
    in_lookback,
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
        self.assertEqual(parse_args([]).lookback_days, 1)

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

    def test_candidate_selection_limits_one_subreddit_to_two_items(self) -> None:
        posts = [
            self.post("same-1", "Kubernetes networking outage", 1),
            self.post("same-2", "Database replication failure", 2),
            self.post("same-3", "Observability alert fatigue", 3),
        ]
        selected = select_candidates(
            posts, {"subreddit_weights": {"kubernetes": 10}}, 5
        )
        self.assertEqual(len(selected), 2)

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
        self.assertNotIn("每日专业 Topic 新闻", markdown)

    def test_validator_rejects_unknown_url(self) -> None:
        raw = [
            {
                "url": "https://example.com/unknown",
                "title_zh": "专业讨论摘要",
                "summary_zh": "这是一段用于测试的中文讨论摘要，长度足以通过字段长度校验并说明主题内容。",
                "consensus_zh": "样本评论对主要技术方向形成了一定共识，但仍需要验证。",
                "disagreements_zh": "评论对具体实现成本和适用范围存在明显分歧，需要进一步核查。",
                "why_it_matters_zh": "该讨论反映从业者当前关注的工程问题和潜在实践变化。",
                "signals_and_limits_zh": "社区样本存在选择偏差，讨论热度也不能代表事实正确。",
            }
        ]
        with self.assertRaises(ValueError):
            validate_reddit_items(raw, [self.post("one", "Example")])


if __name__ == "__main__":
    unittest.main()
