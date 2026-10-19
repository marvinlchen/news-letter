"""Markdown delivery behavior, with no PDF dependency in the report pipeline."""
from copy import deepcopy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import a_share_announcements as daily
import announcement_data as data


def stock():
    return {
        "code": "600001", "name": "示例公司", "date": "2026-10-16",
        "categories": ["业绩", "合同中标"], "direction": "利好", "score": 4,
        "expectation": "无一致预期", "event": "重大合同改善盈利可见度。",
        "conclusion": "订单增长有望推动盈利改善。",
        "analysis": ["合同已签署，收入确认取决于后续履约。", "关注交付进度、回款及业绩兑现。"],
        "key_data": [{"label": "合同|金额", "value": "第一行|口径\n第二行"},
                     {"label": "未知字段", "value": None}],
        "announcements": [{"id": "A1", "title": "关于签订重大合同的公告", "url": "https://example.org/a.pdf", "event": "已签署合同。"},
                          {"id": "A2", "title": "关于披露业绩预告的公告", "url": "https://example.org/b.pdf", "event": "已披露业绩预告。"}],
        "source_note": "官方原文已核验。", "industry_news": "行业政策鼓励更新，消息已检索核验。",
        "focus": ["关注合同交付", "关注年度报告"],
        "technical": {"close": 12.5, "ma5": 12.3, "ma10": 12.1, "ma20": 11.8, "ma60": 11.1,
                      "bullish": True, "status": "正常", "weekly_dif": 0.25, "weekly_dea": 0.18,
                      "weekly_macd": 0.14, "weekly_trend": "金叉", "weekly_axis": "零轴上方",
                      "weekly_hist_change": "红柱放大", "divergence": "数据待核", "industry": "机械设备",
                      "industry_technical": "行业指数处于MA20、MA60上方，日MACD金叉。", "limit_up_count": 0},
    }


def report():
    return {"date": "2026-10-16", "generated_at": "2026-10-17T05:10:00+08:00", "items": [stock()],
            "collection_count": 100, "announcement_count": 2,
            "source_notes": ["iFinD按公告日交叉核验；官方原文作为事实依据。"], "gaps": ["历史背离数据待核。"]}


class MarkdownDeliveryTests(unittest.TestCase):
    def run_main(self, root, *extra, markdown=None):
        item = stock()
        collection = {"total_count": 100, "announcements": [{"id": "A1", "code": item["code"], "date": item["date"]}],
                      "source_notes": ["官方原文已核验。"], "gaps": []}
        patches = [patch.object(data, "is_trading_day", return_value=True),
                   patch.object(data, "collect_announcements", return_value=collection),
                   patch.object(data, "enrich_technical", return_value=([item], ["历史背离数据待核。"])),
                   patch.object(daily, "analyze_batch", return_value=([item], [{"code": item["code"], "important": True}], [])),
                   patch.dict(sys.modules, {"announcement_pdf": None, "reportlab": None})]
        if markdown is not None:
            patches.append(patch.object(daily, "report_markdown", return_value=markdown))
        for context in patches:
            context.start()
        try:
            return daily.main(["--project-root", str(root), "--date", "2026-10-16", *extra])
        finally:
            for context in reversed(patches):
                context.stop()

    def test_main_generates_only_dated_markdown_latest_and_json_with_md_hashes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            self.assertEqual(self.run_main(root), 0)
            out = root / "published/a-share-announcements"
            self.assertEqual({path.name for path in out.iterdir()}, {"2026-10-16.md", "latest.md", "2026-10-16.json"})
            self.assertEqual((out / "latest.md").read_bytes(), (out / "2026-10-16.md").read_bytes())
            self.assertFalse(list(root.rglob("*.pdf")))
            status = json.loads((root / "var/a-share-announcements-status/latest-artifact.json").read_text())
            self.assertEqual(status["output_format"], "markdown")
            self.assertEqual(Path(status["output_path"]), out / "2026-10-16.md")
            self.assertEqual(status["report_filename"], "2026-10-16.md")
            self.assertEqual(status["report_sha256"], hashlib.sha256((out / "2026-10-16.md").read_bytes()).hexdigest())
            self.assertEqual(status["markdown_sha256"], status["report_sha256"])
            self.assertEqual(status["json_sha256"], hashlib.sha256((out / "2026-10-16.json").read_bytes()).hexdigest())
            self.assertTrue(status["markdown_review"]["passed"])
            self.assertNotIn("layout_review", status)
            self.assertNotIn("每页", (out / "2026-10-16.md").read_text())

    def test_markdown_contains_complete_stock_details_and_escaped_table_cells(self):
        text = daily.report_markdown(report())
        for required in ["示例公司", "600001", "2026-10-16", "合同中标", "重要性", "重大", "无一致预期",
                         "重大合同改善盈利可见度", "订单增长有望推动盈利改善", "收入确认取决于后续履约",
                         "合同\\|金额", "第一行\\|口径<br>第二行", "数据待核", "行业政策鼓励更新",
                         "关注合同交付", "关于签订重大合同的公告", "https://example.org/a.pdf", "已披露业绩预告",
                         "MA5", "12.3", "MA10", "12.1", "MA20", "11.8", "MA60", "11.1",
                         "周线DIF", "0.25", "周线DEA", "0.18", "周线MACD柱", "0.14", "金叉", "红柱放大",
                         "零轴上方", "机械设备", "行业指数处于", "0家", "iFinD", "历史背离数据待核"]:
            self.assertIn(required, text)
        self.assertNotIn("下载PDF", text)
        self.assertIn("**订单增长有望推动盈利改善。**", text)
        self.assertTrue(daily.review_markdown(report(), text)["content_complete"])

    def test_diagnostic_outputs_do_not_touch_published_latest_or_live_status(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            out = root / "published/a-share-announcements"
            out.mkdir(parents=True)
            (out / "latest.md").write_text("existing live report")
            self.assertEqual(self.run_main(root, "--limit", "1"), 0)
            self.assertEqual((out / "latest.md").read_text(), "existing live report")
            diagnostic = root / "var/a-share-announcements-diagnostic"
            self.assertEqual({path.name for path in diagnostic.iterdir()}, {"2026-10-16.md", "2026-10-16.json"})
            self.assertFalse((root / "var/a-share-announcements-status").exists())
            status = json.loads((root / "var/a-share-announcements-diagnostic-status/latest-run.json").read_text())
            self.assertFalse(status["publishable"])
            self.assertTrue(status["markdown_review"]["passed"])

    def test_incomplete_markdown_fails_review_and_never_replaces_live_latest(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            out = root / "published/a-share-announcements"
            out.mkdir(parents=True)
            (out / "latest.md").write_text("existing live report")
            self.assertEqual(self.run_main(root, markdown="# 摘要缺失全部详细内容\n"), 2)
            self.assertEqual((out / "latest.md").read_text(), "existing live report")
            self.assertFalse((out / "2026-10-16.md").exists())
            status = json.loads((root / "var/a-share-announcements-status/latest-run.json").read_text())
            self.assertFalse(status["publishable"])
            self.assertEqual(status["state"], "failed")

    def test_markdown_review_rejects_missing_indicator_and_wrong_direction_order(self):
        source = report()
        text = daily.report_markdown(source)
        with self.assertRaises(ValueError):
            daily.review_markdown(source, text.replace("12.3", "数据待核"))
        bad = deepcopy(source)
        bearish = stock()
        bearish.update(code="600002", direction="利空", score=-4)
        bad["items"] = [bearish, bad["items"][0]]
        with self.assertRaises(ValueError):
            daily.review_markdown(bad, daily.report_markdown(bad))

    def test_key_data_is_not_rejected_by_old_pdf_label_or_value_length_budget(self):
        label, value = "披露的经营数据说明" * 8, "连续披露的真实经营数据" * 16
        source = {"600001": [{"id": "A1", "name": "示例公司", "date": "2026-10-16", "title": "重大合同", "url": "https://example.org/a.pdf", "text": value}]}
        row = {"code": "600001", "important": True, "announcement_ids": ["A1"], "categories": ["合同中标"],
               "direction": "利好", "score": 3, "event": "公司签订合同。", "conclusion": "订单可见度改善。",
               "analysis": ["合同已签署，收入确认取决于后续履约。", "关注交付进度及回款。"],
               "key_data": [{"label": label, "value": value, "evidence": value}], "focus": ["关注履约"]}
        item = daily.validate_selection([row], source)[0]
        self.assertEqual(item["key_data"][0]["value"], value)
        self.assertNotIn("版式预算", daily.model_prompt(source, dt.date(2026, 10, 16)))


class WeekendMarkdownDeliveryTests(unittest.TestCase):
    """Calendar dates with no exchange session still have disclosure reports."""
    sunday = dt.date(2026, 10, 18)

    def run_sunday(self, root, selected, records, decisions):
        collection = {"total_count": len(records), "announcements": records,
                      "source_notes": ["当日完整公告索引已核验。"], "gaps": []}

        def collect(date, cache_dir, limit_companies=None):
            self.assertEqual(date, self.sunday)
            return collection

        with patch.object(data, "collect_announcements", side_effect=collect), \
                patch.object(data, "enrich_technical", return_value=(selected, [])), \
                patch.object(daily, "analyze_batch", return_value=(selected, decisions, [])):
            result = daily.main(["--project-root", str(root), "--date", "2026-10-18"])
        status = json.loads((root / "var/a-share-announcements-status/latest-run.json").read_text())
        self.assertEqual(result, 0, status.get("error"))
        self.assertEqual(status["state"], "generated", "周末应采集公告并生成日报，不能按休市日跳过")
        self.assertTrue(status["publishable"])
        self.assertTrue(status["publish_required"])
        self.assertTrue(status["fact_review"]["passed"])
        self.assertTrue(status["markdown_review"]["passed"])
        out = root / "published/a-share-announcements"
        self.assertEqual({p.name for p in out.iterdir()}, {"2026-10-18.md", "latest.md", "2026-10-18.json"})
        text = (out / "2026-10-18.md").read_text()
        self.assertEqual((out / "latest.md").read_text(), text)
        self.assertEqual(status["output_path"], str(out / "2026-10-18.md"))
        self.assertEqual(status["report_filename"], "2026-10-18.md")
        self.assertEqual(status["report_sha256"], hashlib.sha256(text.encode()).hexdigest())
        return text, json.loads((out / "2026-10-18.json").read_text()), status

    def sunday_record(self, title="关于签订重大合同的公告"):
        return {"id": "A1", "code": "600001", "name": "示例公司", "date": "2026-10-18",
                "title": title, "text": "公司于当日披露公告，原文完整。", "url": "https://example.org/sunday.pdf",
                "official_verified": True}

    def test_sunday_announcements_generate_publishable_dated_markdown(self):
        item = stock()
        item["date"] = "2026-10-18"
        item["announcements"] = [{"id": "A1", "title": "关于签订重大合同的公告",
                                   "url": "https://example.org/sunday.pdf", "event": "已签署合同。"}]
        item["technical"].update(price_date="2026-10-16", market_date="2026-10-16",
                                 limit_up_date="2026-10-16", status="正常", bullish=True)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            text, structured, status = self.run_sunday(Path(folder), [item], [self.sunday_record()],
                                                       [{"code": "600001", "important": True}])
        self.assertIn("# A股重大公告利好利空日报 · 2026-10-18", text)
        self.assertIn("重大股票 1 只；重大公告 1 份", text)
        self.assertIn("示例公司（600001）", text)
        self.assertIn("https://example.org/sunday.pdf", text)
        self.assertIn("| 行情状态 | 正常 |", text)
        self.assertIn("| 行情截至日 | 2026-10-16 |", text)
        self.assertIn("| 最近交易日 | 2026-10-16 |", text)
        self.assertIn("| 行业涨停统计日 | 2026-10-16 |", text)
        self.assertIn("| 行业涨停数 | 0家 |", text)
        self.assertEqual(structured["date"], "2026-10-18")
        self.assertEqual(structured["items"][0]["date"], "2026-10-18")
        self.assertEqual(status["candidate_company_count"], 1)

    def test_sunday_without_major_announcements_generates_complete_zero_item_markdown(self):
        for label, records, decisions, collected in [
            ("只有例行公告", [self.sunday_record("关于例行会议安排的公告")],
             [{"code": "600001", "important": False, "reason": "例行事项，不构成重大公告。"}], 1),
            ("没有公告", [], [], 0),
        ]:
            with self.subTest(case=label), tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
                text, structured, status = self.run_sunday(Path(folder), [], records, decisions)
                self.assertIn(f"采集公告 {collected} 份；重大股票 0 只；重大公告 0 份。", text)
                self.assertIn("利好 0、中性 0、利空 0", text)
                self.assertIn("## 数据来源与口径", text)
                self.assertIn("当日完整公告索引已核验。", text)
                self.assertIn("## 数据缺口", text)
                self.assertIn("当日未筛选出符合重大性标准的公告。", text)
                self.assertEqual(structured["items"], [])
                self.assertEqual(structured["announcement_count"], 0)
                self.assertEqual(status["stock_count"], 0)
                self.assertTrue(status["markdown_review"]["content_complete"])
                if collected == 0:
                    self.assertIn("未调用CodeBuddy及iFinD MCP", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
