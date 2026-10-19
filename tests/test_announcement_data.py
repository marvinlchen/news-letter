import datetime as dt
import io
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import announcement_data as data


def security(code, market):
    return {"stock_code": code, "market_code": market, "short_name": code}


def announcement(number, title="关于股份回购的公告", code="600001", market="1"):
    return {"art_code": f"AN{number:06d}", "title": title, "notice_date": "2026-10-16 00:00:00",
            "codes": [security(code, market)]}


def bars(count=500, start=dt.date(2024, 1, 1)):
    values = []
    day = start
    while len(values) < count:
        if day.weekday() < 5:
            close = 10 + len(values) * 0.1
            values.append({"date": day.isoformat(), "open": close-0.1, "close": close,
                           "high": close+0.2, "low": close-0.2, "volume": 100})
        day += dt.timedelta(days=1)
    return values


def evidence_pdf(*, scanned_page=False, blank_page=False):
    """A real text first page followed by an optional image-only or blank page."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(50, 750, "First page contains enough real announcement text to pass the old aggregate check.")
    pdf.showPage()
    if scanned_page:
        pdf.drawImage(ImageReader(Image.new("RGB", (30, 30), "black")), 50, 100, width=450, height=550)
        pdf.drawString(50, 50, "2")  # Scanned bodies often retain a selectable page number.
        pdf.showPage()
    if blank_page:
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def paginated_evidence_pdf(first_number="1", second_number="2"):
    """Real two-page CJK PDF with the exact disclosure footer splitting a fact."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("STSong-Light", 11)
    for y, text in [(780, first_number), (750, "报告期内，汽车零部件业务收入同比下降，因产品价格持续"),
                    (60, "本公司及董事会全体成员保证信息披露的内容真实、准确、"),
                    (45, "完整，没有虚假记载、误导性陈述或重大遗漏。")]:
        pdf.drawString(40, y, text)
    pdf.showPage()
    pdf.setFont("STSong-Light", 11)
    for y, text in [(780, second_number), (750, "承压，毛利率同比降低，经营业绩出现下降。"),
                    (720, "公司将按照相关规定披露后续经营及财务情况。")]:
        pdf.drawString(40, y, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class AnnouncementDataTests(unittest.TestCase):
    def test_fixed_footer_and_verified_page_numbers_do_not_split_quote(self):
        text = data._extract_complete_pdf_text(paginated_evidence_pdf())
        compact = re.sub(r"\s+", "", text)
        self.assertIn("产品价格持续承压", compact)
        self.assertNotIn("本公司及董事会全体成员保证", text)
        self.assertNotIn("1", text.splitlines())
        self.assertNotIn("2", text.splitlines())

    def test_bare_numbers_are_retained_without_complete_page_number_sequence(self):
        text = data._extract_complete_pdf_text(paginated_evidence_pdf("100", "2"))
        self.assertIn("100", text.splitlines())
        self.assertIn("2", text.splitlines())

    def test_real_forecast_cross_page_quote_is_usable_after_pdf_cleaning(self):
        path = Path(__file__).resolve().parent.parent / "source-dryrun-cache/announcements/2026-10-16/evidence/cninfo-1225609627.pdf"
        if not path.exists():
            self.skipTest("real source PDF is only available in the local diagnostic cache")
        text = data._extract_complete_pdf_text(path.read_bytes())
        self.assertIn("产品价格持续承压", re.sub(r"\s+", "", text))
        self.assertIn("21,473.66", text)
        self.assertIn("29,282.26", text)
        self.assertNotIn("本公司及董事会全体成员保证", text)

    def test_official_mixed_scan_pdf_falls_back_to_complete_mirror_text(self):
        item = {"id": "AN1", "code": "600001", "url": "https://example.com/detail",
                "official_id": "official1", "official_url": "https://example.com/official.pdf"}
        raw = {"success": 1, "data": {"art_code": "AN1", "page_size": 1,
                "notice_content": "Complete mirror text is available and independently returned by the text endpoint."}}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_download_pdf", return_value=evidence_pdf(scanned_page=True)), patch.object(data, "_request_json", return_value=raw):
            result, gaps = data._announcement_detail(item, folder)
        self.assertFalse(result["official_verified"])
        self.assertTrue(result["text_complete"])
        self.assertEqual(result["text"], raw["data"]["notice_content"])
        self.assertTrue(any("官方" in gap for gap in gaps))

    def test_mixed_scan_fallback_pdf_is_not_claimed_as_complete_text(self):
        item = {"id": "AN1", "code": "600001", "url": "https://example.com/detail"}
        raw = {"success": 1, "data": {"art_code": "AN1", "page_size": 2,
                "notice_content": "Mirror first-page snippet only.", "attach_url": "https://example.com/mirror.pdf"}}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_download_pdf", return_value=evidence_pdf(scanned_page=True)), patch.object(data, "_request_json", return_value=raw):
            result, gaps = data._announcement_detail(item, folder)
        self.assertFalse(result["text_complete"])
        self.assertEqual(result["text"], raw["data"]["notice_content"])
        self.assertTrue(any("PDF全文待核" in gap for gap in gaps))

    def test_truly_blank_second_page_does_not_block_official_pdf(self):
        item = {"id": "AN1", "code": "600001", "url": "https://example.com/detail",
                "official_id": "official1", "official_url": "https://example.com/official.pdf"}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_download_pdf", return_value=evidence_pdf(blank_page=True)), patch.object(data, "_request_json", side_effect=AssertionError("official blank page requires no fallback")):
            result, gaps = data._announcement_detail(item, folder)
        self.assertTrue(result["official_verified"])
        self.assertTrue(result["text_complete"])
        self.assertIn("real announcement text", result["text"])
        self.assertFalse(gaps)

    def test_investments_and_controller_changes_reach_model_screening(self):
        for title in ['关于向全资子公司增资的公告','关于签署投资协议的公告','关于设立产业基金的公告','关于第一大股东变更的提示性公告']:
            self.assertTrue(data._category(title), title)
    def test_shsz_a_filter_excludes_other_security_classes(self):
        for code, market in [("600001", "1"), ("688001", "1"), ("000001", "0"), ("300001", "0"), ("301001", "0")]:
            self.assertTrue(data._is_shsz_a(security(code, market)))
        for code, market in [("900901", "1"), ("200001", "0"), ("920001", "0"), ("430001", "0"), ("510300", "1"), ("159001", "0"), ("00700", "1"), ("600001", "0")]:
            self.assertFalse(data._is_shsz_a(security(code, market)))

    def test_candidates_cover_investment_incentives_and_purchase_contracts(self):
        for title in ("关于对外投资设立合资公司的公告", "关于共同投资的公告", "关于设立全资子公司的公告", "产能建设公告", "股票期权激励计划", "控股股东大额持股事项", "签订销售合同", "签订采购合同"):
            self.assertTrue(data._category(title), title)

    def test_official_title_matching_ignores_company_prefix_and_html(self):
        self.assertEqual(data._normal_title("美诺华：关于<em>重大</em>合同的公告", "美诺华"), data._normal_title("关于重大合同的公告", "美诺华"))

    def test_positive_ma_order_still_requires_close_above_ma(self):
        rows = bars()
        rows[-1]["close"] = 59
        result = data.calculate_indicators(rows, rows[-1]["date"])
        self.assertGreater(result["ma5"], result["ma10"])
        self.assertGreater(result["ma10"], result["ma20"])
        self.assertGreater(result["ma20"], result["ma60"])
        self.assertFalse(result["strict_bullish_alignment"])

    def test_daily_macd_and_negative_histogram_absolute_change(self):
        values = [100-i*.1 for i in range(70)]
        result = data._macd(values)
        self.assertLess(result["histogram"], 0)
        expected = "绿柱放大" if abs(result["histogram"]) > abs(result["previous_histogram"]) else "绿柱收窄"
        self.assertEqual(result["histogram_change"], expected)
        self.assertAlmostEqual(result["histogram"], 2*(result["dif"]-result["dea"]))

    def test_official_pagination_uses_stable_default_sort(self):
        def response(url, params):
            self.assertEqual(params["sortName"], "")
            self.assertEqual(params["sortType"], "")
            indexes = range(30) if params["pageNum"] == 1 else [30]
            return {"totalAnnouncement": 31, "announcements": [{"announcementId": params["plate"]+str(i)} for i in indexes]}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_post_json", side_effect=response):
            result = data._official_announcements("2026-10-16", folder)
        self.assertEqual(len(result), 62)

    def test_financing_only_titles_do_not_add_extra_category(self):
        self.assertFalse(data._category("向特定对象发行股票的募集说明书"))
        self.assertFalse(data._category("关于利润分配的公告"))
        self.assertTrue(data._category("发行股份购买资产并进行重大资产重组"))

    def test_flat_schema_and_zero_industry_limitup_are_real_values(self):
        history = bars(100, dt.date(2026, 6, 1))
        profiles = {"600001": {"level1": "医药生物"}, "600002": {"level1": "汽车"}}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "is_trading_day", return_value=True), patch.object(data, "_fetch_daily", return_value=history), patch.object(data, "_profile", side_effect=lambda code, folder: profiles[code]), patch.object(data, "_board_map", return_value={"医药生物": "BK0001"}), patch.object(data, "_board_daily", return_value=history), patch.object(data, "_limit_pool", return_value=[{"c": "600002"}]):
            items, gaps = data.enrich_technical([{"code":"600001"}], "2026-10-16", folder)
        technical = items[0]["technical"]
        self.assertTrue(all(key in technical for key in ["close", "ma5", "bullish", "status", "weekly_dif", "weekly_dea", "weekly_macd", "weekly_trend", "weekly_axis", "weekly_hist_change", "divergence", "industry", "industry_technical", "limit_up_count"]))
        self.assertEqual(technical["limit_up_count"], 0)
        self.assertIn("指数点位", technical["industry_technical"])
        self.assertIn("MA20上方", technical["industry_technical"])
        self.assertIn("日MACD", technical["industry_technical"])
        self.assertFalse(gaps)

    def test_missing_pool_industry_never_turns_into_zero(self):
        history = bars(100, dt.date(2026, 6, 1))
        def profile(code, folder):
            if code == "600002":
                raise data.DataUnavailable("no mapping")
            return {"level1": "医药生物"}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "is_trading_day", return_value=True), patch.object(data, "_fetch_daily", return_value=history), patch.object(data, "_profile", side_effect=profile), patch.object(data, "_board_map", return_value={"医药生物": "BK0001"}), patch.object(data, "_board_daily", return_value=history), patch.object(data, "_limit_pool", return_value=[{"c": "600002"}]):
            items, gaps = data.enrich_technical([{"code":"600001"}], "2026-10-16", folder)
        self.assertEqual(items[0]["technical"]["limit_up_count"], "数据待核")
        self.assertTrue(gaps)

    def test_complete_pagination_uses_total_and_validates_unique_ids(self):
        def response(url, params):
            number = params["page_index"]
            values = [announcement(i) for i in (range(100) if number == 1 else [100])]
            return {"success": 1, "data": {"list": values, "total_hits": 101, "page_size": 100, "page_index": number}}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_request_json", side_effect=response) as request:
            values, total, pages = data._all_announcement_pages("2026-10-16", folder)
            self.assertEqual((len(values), total, pages), (101, 101, 2))
            self.assertEqual(request.call_count, 2)

    def test_duplicate_or_incomplete_pagination_fails(self):
        for second in ([announcement(0)], []):
            def response(url, params):
                values = [announcement(i) for i in range(100)] if params["page_index"] == 1 else second
                return {"success": 1, "data": {"list": values, "total_hits": 101, "page_size": 100}}
            with tempfile.TemporaryDirectory() as folder, patch.object(data, "_request_json", side_effect=response):
                with self.assertRaises(data.DataUnavailable):
                    data._all_announcement_pages("2026-10-16", folder)

    def test_collection_filters_routine_and_preserves_shsz_total(self):
        records = [announcement(1), announcement(2, "董事会会议通知"), announcement(3, code="920001", market="0"), announcement(4, code="200001", market="0")]
        def detail(item, path):
            return {**item, "text": "真实公告正文", "text_complete": True}, []
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_all_announcement_pages", return_value=(records, 4, 1)), patch.object(data, "_announcement_detail", side_effect=detail), patch.object(data, "_official_announcements", return_value=[]):
            result = data.collect_announcements("2026-10-16", folder)
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["source_total_count"], 4)
        self.assertEqual(len(result["announcements"]), 1)
        self.assertEqual(result["announcements"][0]["date"], "2026-10-16")

    def test_detail_failure_is_explicit_gap(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_request_json", side_effect=data.DataUnavailable("unavailable")):
            result, gaps = data._announcement_detail({"id": "AN1", "code": "600001", "url": "https://example.com"}, folder)
        self.assertFalse(result["text_complete"])
        self.assertTrue(gaps)
        self.assertEqual(result["text"], "")

    def test_future_daily_prices_cannot_change_any_indicator(self):
        rows = bars()
        cutoff = rows[-20]["date"]
        expected = data.calculate_indicators(rows[:-19], cutoff)
        altered = [dict(row, close=999999) if row["date"] > cutoff else row for row in rows]
        self.assertEqual(data.calculate_indicators(altered, cutoff), expected)

    def test_partial_week_uses_only_asof_day(self):
        rows = bars(10, dt.date(2026, 10, 12))
        weeks = data._weekly_rows(rows, "2026-10-14")
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0]["date"], "2026-10-14")
        self.assertEqual(weeks[0]["close"], rows[2]["close"])

    def test_strict_alignment_and_macd_formula(self):
        rows = bars()
        result = data.calculate_indicators(rows, rows[-1]["date"])
        self.assertTrue(result["strict_bullish_alignment"])
        self.assertAlmostEqual(result["ma5"], sum(r["close"] for r in rows[-5:]) / 5)
        self.assertAlmostEqual(result["weekly"]["histogram"], 2 * (result["weekly"]["dif"] - result["weekly"]["dea"]))
        flat = [dict(row, close=10) for row in rows]
        self.assertFalse(data.calculate_indicators(flat, rows[-1]["date"])["strict_bullish_alignment"])

    def test_historical_qfq_future_adjustment_is_rejected(self):
        qfq = {"data": {"sh600001": {"qfqday": [["2025-01-10", "8", "8", "8", "8", "100"]]}}}
        raw = {"data": {"sh600001": {"day": [["2025-01-10", "12", "12", "12", "12", "100"]]}}}
        with tempfile.TemporaryDirectory() as folder, patch.object(data, "_request_json", side_effect=[qfq, raw]):
            with self.assertRaisesRegex(data.DataUnavailable, "复权因子"):
                data._fetch_daily("600001", "2025-01-10", folder, "1")

    def test_weekends_are_closed_without_network(self):
        with patch.object(data, "_request_json", side_effect=AssertionError("network not required")):
            self.assertFalse(data.is_trading_day("2026-10-17", ".unused"))

    def test_unverified_calendar_never_claims_holiday(self):
        with patch.dict("sys.modules", {"akshare": None}), patch.object(data, "_fetch_daily", return_value=bars(1, dt.date(2026, 9, 30))):
            with self.assertRaises(data.DataUnavailable):
                data.is_trading_day("2026-10-01", ".unused")

    def test_actual_index_sessions_can_verify_holiday(self):
        history = [bars(1, dt.date(2026, 9, 30))[0], bars(1, dt.date(2026, 10, 9))[0]]
        with patch.dict("sys.modules", {"akshare": None}), patch.object(data, "_fetch_daily", return_value=history):
            self.assertFalse(data.is_trading_day("2026-10-01", ".unused"))
            self.assertTrue(data.is_trading_day("2026-10-09", ".unused"))


class WeekendTechnicalTests(unittest.TestCase):
    def setUp(self):
        self.history = bars(100, dt.date(2026, 6, 1))
        self.assertEqual(self.history[-1]["date"], "2026-10-16")
        self.profile = patch.object(data, "_profile", return_value={"level1": "医药生物"})
        self.boards = patch.object(data, "_board_map", return_value={"医药生物": "BK0001"})
        self.board_prices = patch.object(data, "_board_daily", return_value=self.history)
        for context in (self.profile, self.boards, self.board_prices):
            context.start()
            self.addCleanup(context.stop)

    def test_sunday_uses_verified_friday_market_and_pool_without_future_prices(self):
        future = {**self.history[-1], "date": "2026-10-19", "close": 999999}
        with patch.object(data, "is_trading_day", return_value=False), patch.object(data, "_fetch_daily", return_value=self.history+[future]) as fetch, patch.object(data, "_limit_pool", return_value=[]) as pool:
            items, gaps = data.enrich_technical([{"code": "600001"}], "2026-10-18", ".unused")
        technical = items[0]["technical"]
        self.assertEqual(technical.get("market_date"), "2026-10-16")
        self.assertEqual(technical.get("limit_up_date"), "2026-10-16")
        self.assertEqual(technical["price_date"], "2026-10-16")
        self.assertEqual(technical["status"], "正常")
        self.assertTrue(technical["bullish"])
        self.assertEqual(technical["close"], 19.9)
        self.assertEqual(technical["ma5"], 19.7)
        self.assertFalse(gaps)
        self.assertIn(("000001", "2026-10-18", ".unused"), [call.args for call in fetch.call_args_list])
        self.assertEqual(pool.call_args.args[0], "2026-10-16")

    def test_sunday_keeps_friday_zero_volume_as_suspension(self):
        stock_prices = [*self.history[:-1], {**self.history[-1], "volume": 0}]
        def prices(code, *args, **kwargs):
            return self.history if code == "000001" else stock_prices
        with patch.object(data, "is_trading_day", return_value=False), patch.object(data, "_fetch_daily", side_effect=prices), patch.object(data, "_limit_pool", return_value=[]):
            items, gaps = data.enrich_technical([{"code": "600001"}], "2026-10-18", ".unused")
        self.assertEqual(items[0]["technical"]["status"], "停牌")
        self.assertIsNone(items[0]["technical"]["bullish"])
        self.assertFalse(gaps)

    def test_sunday_stock_older_than_market_day_stays_unverified(self):
        def prices(code, *args, **kwargs):
            return self.history if code == "000001" else self.history[:-1]
        with patch.object(data, "is_trading_day", return_value=False), patch.object(data, "_fetch_daily", side_effect=prices), patch.object(data, "_limit_pool", return_value=[]):
            items, gaps = data.enrich_technical([{"code": "600001"}], "2026-10-18", ".unused")
        technical = items[0]["technical"]
        self.assertEqual(technical.get("market_date"), "2026-10-16")
        self.assertEqual(technical["price_date"], "2026-10-15")
        self.assertEqual(technical["status"], "数据待核")
        self.assertIsNone(technical["bullish"])
        self.assertTrue(any("600001" in gap and "2026-10-15" in gap for gap in gaps))

    def test_unverified_calendar_does_not_claim_market_or_pool_date(self):
        with patch.object(data, "is_trading_day", side_effect=data.DataUnavailable("calendar unavailable")), patch.object(data, "_fetch_daily", return_value=self.history), patch.object(data, "_limit_pool", side_effect=AssertionError("unverified market date")):
            items, gaps = data.enrich_technical([{"code": "600001"}], "2026-10-18", ".unused")
        technical = items[0]["technical"]
        self.assertIsNone(technical.get("market_date"))
        self.assertIsNone(technical.get("limit_up_date"))
        self.assertEqual(technical["status"], "数据待核")
        self.assertIsNone(technical["bullish"])
        self.assertEqual(technical["limit_up_count"], "数据待核")
        self.assertTrue(any("calendar unavailable" in gap for gap in gaps))

    def test_missing_or_future_only_index_bars_cannot_verify_market_day(self):
        future = {**self.history[-1], "date": "2026-10-19"}
        for index_rows in ([], [future], data.DataUnavailable("index unavailable")):
            def prices(code, *args, **kwargs):
                if code != "000001":
                    return self.history
                if isinstance(index_rows, Exception):
                    raise index_rows
                return index_rows
            with self.subTest(index_rows=index_rows), patch.object(data, "is_trading_day", return_value=False), patch.object(data, "_fetch_daily", side_effect=prices) as fetch, patch.object(data, "_limit_pool", side_effect=AssertionError("unverified market date")) as pool:
                items, gaps = data.enrich_technical([{"code": "600001"}], "2026-10-18", ".unused")
                technical = items[0]["technical"]
                self.assertIsNone(technical.get("market_date"))
                self.assertIsNone(technical.get("limit_up_date"))
                self.assertEqual(technical["status"], "数据待核")
                self.assertTrue(gaps)
                self.assertIn("000001", [call.args[0] for call in fetch.call_args_list])
                pool.assert_not_called()

    def test_empty_report_skips_calendar_and_market_requests(self):
        with patch.object(data, "is_trading_day", side_effect=AssertionError("empty report needs no calendar")), patch.object(data, "_request_json", side_effect=AssertionError("empty report needs no market")) as request:
            self.assertEqual(data.enrich_technical([], "2026-10-18", ".unused"), ([], []))
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
