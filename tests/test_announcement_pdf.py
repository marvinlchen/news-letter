"""PDF contract checks; all generated synthetic fixtures remain under work/."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
try:
    import announcement_pdf
except ModuleNotFoundError:
    announcement_pdf = None


def stock(number=1, direction="利好", score=5):
    return {
        "code": f"600{number:03d}", "name": f"示例公司{number}", "date": "2026-10-16",
        "categories": ["业绩", "合同中标"], "direction": direction, "score": score,
        "expectation": "无一致预期",
        "announcements": [{"title": "关于签订重大经营合同暨预计年度业绩增长的公告", "url": "https://example.com/announcement/1", "event": "签订重大经营合同，披露业绩增长。"}],
        "event": "签订重大合同并披露业绩增长。", "conclusion": "订单增长有望改善收入与盈利。",
        "analysis": ["合同金额占上年营业收入较高，分期履行将改善收入可见度。", "仍需跟踪交付进度及客户实际回款情况。"],
        "key_data": [{"label": "归母净利润", "value": "1.2-1.5亿元，同比增长30%-60%"}, {"label": "交易对方", "value": "示例客户"}, {"label": "合同金额", "value": "人民币3亿元"}, {"label": "当前进度", "value": "已签署，尚待按期交付"}],
        "industry_news": "行业需求恢复，近期政策鼓励设备更新；消息来源已在采集中核验。",
        "focus": ["关注合同交付与回款节点", "关注下一期财报兑现情况"],
        "technical": {"close": 12.5, "ma5": 12.3, "ma10": 12.1, "ma20": 11.8, "ma60": 11.1, "bullish": True, "status": "正常", "weekly_dif": .25, "weekly_dea": .18, "weekly_macd": .14, "weekly_trend": "金叉", "weekly_axis": "零轴上方", "weekly_hist_change": "红柱增加", "divergence": "未发现顶底背离", "industry": "机械设备", "industry_technical": "行业指数站上MA20、MA60，日MACD处于金叉状态。", "limit_up_count": 3},
    }


def report(items):
    return {"date": "2026-10-16", "generated_at": "2026-10-17T05:12:00+08:00", "items": items,
            "source_notes": ["交易所公告原文；行情截至2026-10-16收盘。"], "gaps": [], "collection_count": 3500, "announcement_count": len(items)}


class PDFContractTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(announcement_pdf, "PDF renderer has not been implemented")
        self.temp = tempfile.TemporaryDirectory(prefix="pdf-contract-", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.pdf"

    def render(self, data):
        meta = announcement_pdf.render_report(data, self.path)
        return meta, PdfReader(self.path)

    def test_five_stocks_have_two_a3_pages_and_four_fixed_slots(self):
        items = [stock(n) for n in range(1, 6)]
        meta, pdf = self.render(report(items))
        self.assertEqual(len(pdf.pages), 2)
        self.assertEqual(meta["page_count"], 2)
        self.assertEqual(meta["cards_per_page"], [4, 1])
        self.assertEqual(meta["slots_per_page"], [4, 4])
        self.assertEqual(meta["empty_slots_per_page"], [0, 3])
        self.assertGreaterEqual(min(meta["card_font_sizes"]), 7.5)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), 841.89, places=1)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.height), 1190.55, places=1)
        first, second = [page.extract_text() for page in pdf.pages]
        self.assertIn("600001", first)
        self.assertNotIn("600005", first)
        self.assertIn("600005", second)
        self.assertEqual(second.count("无更多条目"), 3)
        self.assertIn("第1页/共2页", first.replace(" ", ""))
        self.assertIn("第2页/共2页", second.replace(" ", ""))

    def test_pdf_preserves_direction_order_and_rejects_wrong_order(self):
        valid = report([stock(1, "利好", 5), stock(2, "利好", 3), stock(3, "中性", 0), stock(4, "利空", -4)])
        meta, pdf = self.render(valid)
        text = pdf.pages[0].extract_text()
        self.assertEqual(meta["stock_order"], ["600001", "600002", "600003", "600004"])
        self.assertLess(text.index("600001"), text.index("600002"))
        self.assertLess(text.index("600003"), text.index("600004"))
        invalid = report([stock(4, "利空", -4), stock(1, "利好", 5)])
        with self.assertRaisesRegex(ValueError, "排序"):
            announcement_pdf.render_report(invalid, Path(self.temp.name) / "invalid.pdf")

    def test_unknown_data_are_visible_and_zero_is_not_missing(self):
        item = stock()
        item["technical"] = {"status": "数据待核", "limit_up_count": 0}
        item["key_data"] = [{"label": "归母净利润", "value": None}]
        data = report([item])
        data["gaps"] = ["行情通道未返回均线和MACD，待核验。"]
        _, pdf = self.render(data)
        text = pdf.pages[0].extract_text().replace(" ", "")
        self.assertGreaterEqual(text.count("数据待核"), 8)
        self.assertIn("当日涨停0家", text)
        self.assertIn("行情通道未返回", text)

    def test_text_is_escaped_and_announcement_url_is_link_annotation(self):
        item = stock()
        item["conclusion"] = "A&B <script>不能执行</script>"
        _, pdf = self.render(report([item]))
        text = pdf.pages[0].extract_text()
        self.assertIn("A&B", text)
        self.assertIn("<script>", text)
        links = [ref.get_object().get("/A", {}).get("/URI") for ref in pdf.pages[0].get("/Annots", [])]
        self.assertIn("https://example.com/announcement/1", links)

    def test_long_card_raises_explicit_overflow_without_partial_pdf(self):
        item = stock()
        item["analysis"] = ["这是不能被静默截断的重要公告内容。" * 500]
        with self.assertRaisesRegex(ValueError, "溢出|overflow"):
            announcement_pdf.render_report(report([item]), self.path)
        self.assertFalse(self.path.exists())

    def test_zero_items_has_one_overview_page_and_four_honest_empty_slots(self):
        meta, pdf = self.render(report([]))
        self.assertEqual(len(pdf.pages), 1)
        self.assertEqual(meta["cards_per_page"], [0])
        self.assertEqual(meta["empty_slots_per_page"], [4])
        self.assertIn("0只", pdf.pages[0].extract_text().replace(" ", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
