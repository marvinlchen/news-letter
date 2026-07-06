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


class SectorHotspotsReportTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
