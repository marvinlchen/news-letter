from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "index_analysis", ROOT / "scripts" / "index_analysis.py"
)
index_analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(index_analysis)


GAINERS = [
    {
        "code": "300580",
        "name": "贝斯特",
        "news": [
            {
                "title": "贝斯特机器人业务订单增长",
                "url": "https://example.com/g1",
                "pub_date": "2026-07-03 10:00",
            }
        ],
    }
]

LOSERS = [
    {
        "code": "688106",
        "name": "金宏气体",
        "news": [
            {
                "title": "金宏气体发布风险提示公告",
                "url": "https://example.com/l1",
                "pub_date": "2026-07-03 11:00",
            }
        ],
    }
]


class IndexAnalysisProtocolTest(unittest.TestCase):
    def test_parse_complete_tab_protocol(self) -> None:
        raw = "\n".join(
            [
                "MARKET_SUMMARY\t机器人链活跃，半导体材料回调。",
                "GAINERS_SUMMARY\t涨幅股主要受产业链催化。",
                "LOSERS_SUMMARY\t跌幅股主要受风险提示和获利回吐影响。",
                "GAINER\t300580\t行业带动\t机器人产业链景气带动，个股候选新闻提供辅助证据。\tG1-1",
                "LOSER\t688106\t直接催化\t公司风险提示公告触发估值回调。\tL1-1",
            ]
        )

        result = index_analysis.parse_codebuddy_protocol(raw, GAINERS, LOSERS)

        self.assertEqual(result["market_summary"], "机器人链活跃，半导体材料回调。")
        self.assertEqual(
            result["gainers_analysis"]["stocks"][0]["attribution_type"], "行业带动"
        )
        self.assertEqual(
            result["losers_analysis"]["stocks"][0]["evidence"][0]["title"],
            "金宏气体发布风险提示公告",
        )

    def test_reject_natural_language_summary(self) -> None:
        raw = (
            "分析完成。以上为 2026-07-03 中证1000指数成分股涨跌幅 Top 20 "
            "的归因分析，共 43 行输出。"
        )

        with self.assertRaisesRegex(ValueError, "missing summary lines"):
            index_analysis.parse_codebuddy_protocol(raw, GAINERS, LOSERS)

    def test_prompt_puts_protocol_guard_before_task(self) -> None:
        prompt = index_analysis.build_codebuddy_prompt(
            "2026-07-03", GAINERS, LOSERS, market_news_context=[]
        )
        first_line = prompt.splitlines()[0]

        self.assertIn("机器协议模式", first_line)
        self.assertIn("不要写“分析完成”", prompt)
        self.assertIn("MARKET_SUMMARY\t待填写", prompt)


if __name__ == "__main__":
    unittest.main()
