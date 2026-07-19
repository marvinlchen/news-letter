from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "a_share_sector_radar_weekly",
    ROOT / "scripts" / "a_share_sector_radar_weekly.py",
)
radar = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(radar)


class EvidenceProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.industries = [
            {"code": "801080", "name": "电子", "template": "订单", "aliases": ["PCB"]}
        ]
        self.candidates = {
            "801080": [
                {"id": "801080-N1", "title": "甲方科技订单增长", "url": "https://example.com/1", "pub_date": "2026-07-10"},
                {"id": "801080-N2", "title": "乙方电子利润增长", "url": "https://example.com/2", "pub_date": "2026-07-11"},
            ]
        }
        self.components = {
            "801080": [
                {"code": "000001", "name": "甲方科技"},
                {"code": "000002", "name": "乙方电子"},
            ]
        }
        self.ttl = {"S": 45, "O": 120, "E": 120}

    def parse(self, raw: str):
        return radar.parse_evidence_protocol(
            raw,
            self.industries,
            self.candidates,
            "2026-07-17",
            self.ttl,
            self.components,
        )

    def test_pass_requires_two_categories_entities_and_evidence(self) -> None:
        raw = "EVIDENCE\t801080\tPASS\tO@801080-N1@甲方科技,E@801080-N2@乙方电子\tNONE\tPCB\t订单与盈利扩散\tNONE"
        result = self.parse(raw)
        self.assertEqual(result["801080"]["gate"], "PASS")
        self.assertEqual(result["801080"]["categories"], ["E", "O"])

    def test_rejects_single_source_false_pass(self) -> None:
        raw = "EVIDENCE\t801080\tPASS\tO@801080-N1@甲方科技\tNONE\tPCB\t只有单公司订单\tNONE"
        with self.assertRaisesRegex(ValueError, "PASS硬门槛"):
            self.parse(raw)

    def test_rejects_cross_industry_or_unknown_evidence_id(self) -> None:
        raw = "EVIDENCE\t801080\tPASS\tO@801080-N1@甲方科技,E@801050-N1@乙方电子\tNONE\tPCB\t订单与盈利扩散\tNONE"
        with self.assertRaisesRegex(ValueError, "无效证据ID"):
            self.parse(raw)

    def test_rejects_future_or_stale_claim(self) -> None:
        self.candidates["801080"][0]["pub_date"] = "2026-07-18"
        raw = "EVIDENCE\t801080\tWATCH\tO@801080-N1@甲方科技\tNONE\tPCB\t待观察\tNONE"
        with self.assertRaisesRegex(ValueError, "时点"):
            self.parse(raw)

        self.candidates["801080"][0]["pub_date"] = "2025-01-01"
        with self.assertRaisesRegex(ValueError, "TTL"):
            self.parse(raw)

    def test_rejects_entity_or_category_not_grounded_in_title(self) -> None:
        bad_entity = "EVIDENCE\t801080\tWATCH\tO@801080-N1@虚构科技\tNONE\tPCB\t待观察\tNONE"
        with self.assertRaisesRegex(ValueError, "实体"):
            self.parse(bad_entity)
        bad_category = "EVIDENCE\t801080\tWATCH\tS@801080-N1@甲方科技\tNONE\tPCB\t待观察\tNONE"
        with self.assertRaisesRegex(ValueError, "不支持S"):
            self.parse(bad_category)


class StateMachineTest(unittest.TestCase):
    def make_inputs(self, count: int = 5):
        industries = []
        evidence = {}
        candidates = {}
        metrics = {}
        for index in range(count):
            code = f"80{index:04d}"
            industries.append({"code": code, "name": f"行业{index}"})
            evidence[code] = {
                "gate": "PASS",
                "categories": ["E", "O"],
                "entities": ["甲", "乙"],
                "quality_flags": [],
                "driver": "测试",
                "summary": "通过",
                "evidence_ids": [f"{code}-N1", f"{code}-N2"],
            }
            candidates[code] = [
                {"id": f"{code}-N1", "pub_date": "2026-07-10"},
                {"id": f"{code}-N2", "pub_date": "2026-07-11"},
            ]
            metrics[code] = {
                "rank_20d": index + 1,
                "relative_ok": True,
                "breadth_ok": True,
                "turnover_ok": False,
                "crowding_state": "",
                "crowding_reason": "",
            }
        return industries, evidence, candidates, metrics

    def test_activation_is_capped_at_three_and_is_idempotent(self) -> None:
        industries, evidence, candidates, metrics = self.make_inputs()
        ledger = {"strategy_version": "test", "active_cycles": {}, "events": []}
        radar_codes, states, new_codes, _ = radar.apply_state_machine(
            "2026-07-17", industries, evidence, candidates, metrics, ledger, 8, 3
        )
        self.assertEqual(len(radar_codes), 5)
        self.assertEqual(len(new_codes), 3)
        self.assertEqual(sum(value == "待激活（容量外）" for value in states.values()), 2)
        self.assertEqual(len(ledger["events"]), 3)

        _, states_again, new_again, _ = radar.apply_state_machine(
            "2026-07-17", industries, evidence, candidates, metrics, ledger, 8, 3
        )
        self.assertEqual(set(new_again), set(new_codes))
        self.assertEqual(len(ledger["events"]), 3)
        self.assertTrue(all(states_again[code] == "新激活" for code in new_codes))

    def test_e30_blocks_activation_before_market_checks(self) -> None:
        industries, evidence, candidates, metrics = self.make_inputs(1)
        code = industries[0]["code"]
        metrics[code]["crowding_state"] = "周期成熟"
        ledger = {"strategy_version": "test", "active_cycles": {}, "events": []}
        radar_codes, states, new_codes, _ = radar.apply_state_machine(
            "2026-07-17", industries, evidence, candidates, metrics, ledger, 8, 3
        )
        self.assertEqual(radar_codes, [code])
        self.assertEqual(new_codes, [])
        self.assertEqual(states[code], "周期成熟")

    def test_short_term_crowding_does_not_close_existing_cycle(self) -> None:
        industries, evidence, candidates, metrics = self.make_inputs(1)
        code = industries[0]["code"]
        metrics[code]["crowding_state"] = "短期急涨"
        metrics[code]["crowding_reason"] = "20日急涨"
        ledger = {
            "active_cycles": {code: {"signal_date": "2026-06-01", "name": industries[0]["name"]}},
            "events": [{"code": code, "signal_date": "2026-06-01"}],
        }
        radar_codes, states, new_codes, holds = radar.apply_state_machine(
            "2026-07-17", industries, evidence, candidates, metrics, ledger, 8, 3
        )
        self.assertEqual(radar_codes, [code])
        self.assertIn(code, ledger["active_cycles"])
        self.assertEqual(new_codes, [])
        self.assertEqual(holds, [code])
        self.assertEqual(states[code], "持有确认（短期急涨）")

    def test_e30_closes_existing_cycle_with_reason(self) -> None:
        industries, evidence, candidates, metrics = self.make_inputs(1)
        code = industries[0]["code"]
        metrics[code]["crowding_state"] = "周期成熟"
        metrics[code]["crowding_reason"] = "本年已触及E30"
        ledger = {
            "active_cycles": {code: {"signal_date": "2026-06-01", "name": industries[0]["name"]}},
            "events": [],
        }
        _, states, _, _ = radar.apply_state_machine(
            "2026-07-17", industries, evidence, candidates, metrics, ledger, 8, 3
        )
        self.assertNotIn(code, ledger["active_cycles"])
        self.assertEqual(states[code], "周期成熟")
        self.assertEqual(ledger["cycle_closures"][0]["reason"], "本年已触及E30")

    def test_two_quality_flags_invalidate(self) -> None:
        industries, evidence, candidates, metrics = self.make_inputs(1)
        code = industries[0]["code"]
        evidence[code]["quality_flags"] = ["OCF_WEAK", "ONE_OFF_OR_LOW_BASE"]
        ledger = {"strategy_version": "test", "active_cycles": {}, "events": []}
        _, states, new_codes, _ = radar.apply_state_machine(
            "2026-07-17", industries, evidence, candidates, metrics, ledger, 8, 3
        )
        self.assertEqual(states[code], "失效")
        self.assertEqual(new_codes, [])


class LedgerEvaluationTest(unittest.TestCase):
    def test_next_day_entry_and_twenty_day_cross_sectional_rank(self) -> None:
        start = date(2026, 1, 1)
        dates = [(start + timedelta(days=index)).isoformat() for index in range(70)]
        histories = {}
        for code, daily_gain in (("801001", 0.02), ("801002", 0.01), ("801003", 0.0)):
            rows = []
            price = 100.0
            for day in dates:
                rows.append({"date": day, "open": price, "close": price * (1 + daily_gain), "amount": 1.0})
                price *= 1 + daily_gain
            histories[code] = rows
        event = {"code": "801002", "name": "中间行业", "signal_date": dates[0]}
        radar.event_outcome(event, histories, dates, dates[-1])

        self.assertEqual(event["entry_date"], dates[1])
        self.assertEqual(event["future_20d"]["rank"], 2)
        self.assertEqual(event["future_60d"]["rank"], 2)
        self.assertEqual(event["status"], "60日已完成")

    def test_missing_any_industry_open_keeps_window_incomplete(self) -> None:
        start = date(2026, 1, 1)
        dates = [(start + timedelta(days=index)).isoformat() for index in range(25)]
        histories = {
            "801001": [{"date": day, "open": 100.0, "close": 101.0, "amount": 1.0} for day in dates],
            "801002": [{"date": day, "open": None if index == 1 else 100.0, "close": 100.0, "amount": 1.0} for index, day in enumerate(dates)],
        }
        event = {"code": "801001", "name": "行业", "signal_date": dates[0]}
        radar.event_outcome(event, histories, dates, dates[-1])
        self.assertIsNone(event["future_20d"])
        self.assertEqual(event["status"], "横截面开盘数据不完整")


class MarketMetricTest(unittest.TestCase):
    def test_e30_latches_at_exact_threshold_and_missing_turnover_is_unknown(self) -> None:
        start = date(2023, 1, 1)
        dates = [(start + timedelta(days=index)).isoformat() for index in range(1000)]
        current_dates = [day for day in dates if day.startswith("2025-")]
        crossing_date = current_dates[20]
        industries = []
        histories = {}
        for index in range(31):
            code = f"81{index:04d}"
            industries.append({"code": code, "name": f"行业{index}"})
            rows = []
            for day in dates:
                close = 100.0
                if index == 0 and day.startswith("2025-"):
                    if day < crossing_date:
                        close = 129.99
                    elif day == crossing_date:
                        close = 130.0
                    else:
                        close = 110.0
                amount = None if index == 30 and day == dates[-1] else 1.0
                rows.append({"date": day, "open": close, "close": close, "amount": amount})
            histories[code] = rows

        _, _, metrics = radar.calculate_market_metrics(industries, histories)

        self.assertEqual(metrics[industries[0]["code"]]["e30_date"], crossing_date)
        self.assertEqual(metrics[industries[0]["code"]]["crowding_state"], "周期成熟")
        self.assertIsNone(metrics[industries[1]["code"]]["turnover_share"])
        self.assertFalse(metrics[industries[1]["code"]]["turnover_ok"])


class LedgerIntegrityTest(unittest.TestCase):
    def test_existing_corrupt_or_mismatched_ledger_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "账本损坏"):
                radar.load_ledger(path, "v1")
            path.write_text(json.dumps({"schema_version": 1, "strategy_version": "old"}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "版本不一致"):
                radar.load_ledger(path, "v1")


class ConfigurationAndCronTest(unittest.TestCase):
    def test_configuration_freezes_all_31_industries(self) -> None:
        config = radar.load_config(ROOT / "config" / "a_share_sector_radar.json")
        self.assertEqual(len(config["industries"]), 31)
        self.assertEqual(config["strategy_version"], "v0.2-F.2-pilot")

    def test_cron_is_sunday_at_ten(self) -> None:
        installer = (ROOT / "scripts" / "install-cron.sh").read_text(encoding="utf-8")
        self.assertIn("0 10 * * 0", installer)
        self.assertIn("# finance-a-share-sector-radar-weekly", installer)

    def test_publisher_keeps_commit_attribution_trailer(self) -> None:
        publisher = (ROOT / "scripts" / "publish-a-share-sector-radar-weekly.sh").read_text(encoding="utf-8")
        self.assertIn("Co-authored-by: Codex <noreply@openai.com>", publisher)
        self.assertIn("status is not publishable", publisher)
        self.assertIn("report_sha256", publisher)

    def test_runner_forces_diagnostics_not_to_publish(self) -> None:
        runner = (ROOT / "scripts" / "run-a-share-sector-radar-weekly.sh").read_text(encoding="utf-8")
        self.assertIn("PUBLISH_ALLOWED=0", runner)
        self.assertIn("--skip-ai|--no-news|--no-status", runner)


if __name__ == "__main__":
    unittest.main()
