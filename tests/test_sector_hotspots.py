from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sector_hotspots", ROOT / "scripts" / "sector_hotspots.py"
)
sector_hotspots = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sector_hotspots)


def a_share_sector(sector_id: str, board_label: str, name: str) -> dict:
    return {
        "id": sector_id,
        "market": "A股",
        "board_label": board_label,
        "name": name,
        "change_pct": 1.23,
        "amount": 100000000,
        "main_net_inflow": 5000000,
        "up_count": 3,
        "down_count": 1,
        "lead_stock": "样本股份",
        "lead_stock_change_pct": 5.67,
    }


def us_sector(index: int, meta: dict) -> dict:
    return {
        "id": f"US{index}",
        "market": "美股",
        "symbol": meta["symbol"],
        "name": meta["name_zh"],
        "name_en": meta["name_en"],
        "trade_date": "2026-07-06",
        "change_pct": 1.0 - index * 0.1,
        "volume": 1000000 + index,
        "stock_count": 8,
        "stock_up_count": 5,
        "stock_down_count": 3,
        "lead_stock": "NVDA",
        "lead_stock_change_pct": 2.5,
        "lag_stock": "AAPL",
        "lag_stock_change_pct": -1.2,
        "news": [],
    }


class SectorHotspotsReportTest(unittest.TestCase):
    def test_default_us_scope_covers_all_etf_proxies(self) -> None:
        a_top, us_top = sector_hotspots.resolve_top_counts(None)

        self.assertEqual(a_top, sector_hotspots.DEFAULT_TOP)
        self.assertEqual(us_top, len(sector_hotspots.US_SECTOR_ETFS))

    def test_parse_rejects_non_weak_attribution_without_evidence(self) -> None:
        sectors = [a_share_sector("AIND1", "行业板块", "煤炭")]
        sectors[0]["news"] = [
            {
                "title": "煤炭板块走强",
                "link": "https://example.com/coal",
                "pub_date": "2026-07-06 10:00",
            }
        ]
        raw = "\n".join(
            [
                "MARKET_SUMMARY\t煤炭板块活跃。",
                "A_HOTSPOT\tAIND1\t供需景气\t煤炭需求改善。\t",
            ]
        )

        with self.assertRaisesRegex(ValueError, "missing valid evidence"):
            sector_hotspots.parse_protocol(raw, sectors)

    def test_a_share_report_declares_top_scope(self) -> None:
        industry = [
            a_share_sector("AIND1", "行业板块", "煤炭"),
            a_share_sector("AIND2", "行业板块", "养殖业"),
        ]
        concept = [a_share_sector("ACON1", "概念主题", "红利股")]
        result = {
            "market_summary": "周期与红利板块活跃。",
            "items": {
                sector["id"]: {
                    "attribution_type": "弱证据待复核",
                    "reason": "候选证据不足。",
                    "evidence": [],
                }
                for sector in industry + concept
            },
        }

        report = sector_hotspots.format_report(
            "2026-07-06",
            industry,
            concept,
            [],
            [],
            [],
            result,
            "",
            market="a",
        )

        self.assertIn("覆盖行业 Top 2 / 概念 Top 1", report)

    def test_us_report_declares_full_etf_scope(self) -> None:
        us_hot = [
            us_sector(index, meta)
            for index, meta in enumerate(sector_hotspots.US_SECTOR_ETFS, 1)
        ]
        result = {
            "market_summary": "美股ETF代理分化。",
            "items": {
                sector["id"]: {
                    "attribution_type": "弱证据待复核",
                    "reason": "候选证据不足。",
                    "evidence": [],
                }
                for sector in us_hot
            },
        }

        report = sector_hotspots.format_report(
            "2026-07-06",
            [],
            [],
            [],
            us_hot,
            [],
            result,
            "2026-07-06",
            market="us",
        )

        self.assertIn("覆盖全部 15 个ETF代理", report)
        self.assertIn("代表成分股", report)
        self.assertIn("数据质量：** 覆盖板块 15 个", report)
        self.assertIn("代表股行情 120 条", report)
        self.assertIn("## 美股ETF代理表现", report)
        self.assertIn("| 排名 | 板块 | 代理ETF | 数据日 | 涨跌幅 | 成交量 | 代表股涨跌 | 领涨/领跌 | 归因类型 |", report)
        self.assertIn("5涨/3跌", report)
        self.assertIn("领涨 NVDA +2.50% / 领跌 AAPL -1.20%", report)
        self.assertNotIn("数据质量：** 热点板块 15 个", report)

    def test_us_prompt_includes_representative_stock_context(self) -> None:
        sector = us_sector(1, sector_hotspots.US_SECTOR_ETFS[0])

        prompt = sector_hotspots.build_prompt(
            "2026-07-06",
            [],
            [],
            [sector],
            "2026-07-06",
            market="us",
        )

        self.assertIn("代表成分股5涨/3跌", prompt)
        self.assertIn("领涨 NVDA +2.50%", prompt)
        self.assertIn("领跌 AAPL -1.20%", prompt)


if __name__ == "__main__":
    unittest.main()
