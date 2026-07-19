from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "a_share_sector_radar_weekly_v2_tests",
    ROOT / "scripts" / "a_share_sector_radar_weekly.py",
)
radar = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(radar)


class MarketFreshnessTest(unittest.TestCase):
    def test_tencent_reference_calendar_parses_sessions_and_cutoff(self) -> None:
        payload = {
            "data": {
                "sh000001": {
                    "day": [
                        ["2026-07-16", "1", "1"],
                        ["2026-07-17", "1", "1"],
                        ["2026-07-20", "1", "1"],
                    ]
                }
            }
        }
        with mock.patch.object(radar, "request_json", return_value=payload):
            self.assertEqual(
                radar.fetch_tencent_reference_trading_dates(date(2026, 7, 19)),
                ["2026-07-16", "2026-07-17"],
            )

    def test_reference_calendar_falls_back_to_tencent(self) -> None:
        expected = ["2026-07-16", "2026-07-17"]
        with mock.patch.object(radar, "request_json", side_effect=ConnectionError("eastmoney closed")), mock.patch.object(
            radar, "fetch_tencent_reference_trading_dates", return_value=expected
        ) as tencent:
            self.assertEqual(radar.fetch_reference_trading_dates(date(2026, 7, 19)), expected)

        tencent.assert_called_once_with(date(2026, 7, 19))

    def test_reference_calendar_fails_closed_when_both_sources_fail(self) -> None:
        with mock.patch.object(radar, "request_json", side_effect=ConnectionError("eastmoney closed")), mock.patch.object(
            radar, "fetch_tencent_reference_trading_dates", side_effect=RuntimeError("tencent unavailable")
        ):
            with self.assertRaisesRegex(RuntimeError, "东财: eastmoney closed；腾讯: tencent unavailable"):
                radar.fetch_reference_trading_dates(date(2026, 7, 19))

    def test_one_missing_session_is_stale(self) -> None:
        result = radar.assess_market_freshness(
            "2026-07-16",
            "2026-07-17",
            ["2026-07-15", "2026-07-16", "2026-07-17"],
        )

        self.assertFalse(result["fresh"])
        self.assertEqual(result["lag_sessions"], 1)
        self.assertEqual(result["missing_sessions"], ["2026-07-17"])

    def test_same_expected_session_is_fresh_including_before_long_holiday(self) -> None:
        for actual, expected, calendar in (
            ("2026-07-17", "2026-07-17", ["2026-07-16", "2026-07-17"]),
            # The next calendar session can be much later; freshness is relative
            # to the latest session expected at the cutoff, not calendar days.
            ("2026-02-13", "2026-02-13", ["2026-02-13", "2026-02-24"]),
        ):
            with self.subTest(actual=actual, expected=expected):
                result = radar.assess_market_freshness(actual, expected, calendar)
                self.assertTrue(result["fresh"])
                self.assertEqual(result["lag_sessions"], 0)
                self.assertEqual(result["missing_sessions"], [])

    def test_stale_run_stops_before_ledger_news_and_ai(self) -> None:
        today = date.today()
        expected = today.isoformat()
        actual = (today - timedelta(days=1)).isoformat()
        args = radar.build_parser().parse_args(["--date", expected])
        radar.RUN_STATS["ai_recovery_batches"] = 9

        with mock.patch.object(radar, "fetch_reference_trading_dates", return_value=[actual, expected]), mock.patch.object(
            radar, "fetch_all_sw_histories", return_value={}
        ), mock.patch.object(
            radar, "calculate_market_metrics", return_value=(actual, [actual], {})
        ), mock.patch.object(radar, "load_ledger") as load_ledger, mock.patch.object(
            radar, "fetch_all_components"
        ) as fetch_components, mock.patch.object(radar, "collect_evidence_candidates") as collect_news, mock.patch.object(
            radar, "analyze_evidence"
        ) as analyze:
            with self.assertRaises(radar.StaleMarketDataError):
                radar.run(args)

        load_ledger.assert_not_called()
        fetch_components.assert_not_called()
        collect_news.assert_not_called()
        analyze.assert_not_called()
        self.assertEqual(radar.RUN_STATS["ai_recovery_batches"], 0)


class StockPriceSourceTest(unittest.TestCase):
    def test_eastmoney_symbol_keeps_new_beijing_codes_off_shanghai(self) -> None:
        expected = {
            "000001": "0.000001",
            "430047": "0.430047",
            "830000": "0.830000",
            "920001": "0.920001",
            "600000": "1.600000",
            "688981": "1.688981",
            "900901": "1.900901",
        }
        for stock_code, secid in expected.items():
            with self.subTest(stock_code=stock_code):
                self.assertEqual(radar.eastmoney_secid(stock_code), secid)

    def test_tencent_symbol_maps_shenzhen_shanghai_and_beijing(self) -> None:
        expected = {
            "000001": "sz000001",
            "300750": "sz300750",
            "600000": "sh600000",
            "688981": "sh688981",
            "430047": "bj430047",
            "830000": "bj830000",
            "920001": "bj920001",
            "900901": "sh900901",
        }
        for stock_code, symbol in expected.items():
            with self.subTest(stock_code=stock_code):
                self.assertEqual(radar.tencent_stock_symbol(stock_code), symbol)

    def test_tencent_stock_prices_parse_qfq_rows_and_apply_cutoff(self) -> None:
        start = date(2026, 5, 17)
        qfq_rows = [
            [
                (start + timedelta(days=offset)).isoformat(),
                "10.0",
                str(10.5 + offset / 10),
                "20.0",
            ]
            for offset in range(61)
        ]
        qfq_rows.append(["2026-07-17", "11.0", "99.0", "100.0"])
        payload = {
            "data": {
                "sz000652": {
                    "qfqday": qfq_rows,
                }
            }
        }
        with mock.patch.object(radar, "request_json", return_value=payload) as request:
            prices = radar.fetch_tencent_stock_prices("000652", "2026-07-16")

        self.assertEqual(len(prices), 61)
        self.assertEqual(prices[0], {"date": "2026-05-17", "close": 10.5})
        self.assertEqual(prices[-1], {"date": "2026-07-16", "close": 16.5})
        request.assert_called_once_with(
            radar.TENCENT_KLINE_URL,
            {"param": "sz000652,day,2026-01-17,2026-07-16,200,qfq"},
            timeout=10,
            retries=1,
        )

    def test_tencent_stock_prices_reject_day_rows_when_qfq_is_missing(self) -> None:
        payload = {
            "data": {
                "sh600000": {
                    "day": [["2026-07-16", "10.0", "10.8", "11.0"]] * 60,
                }
            }
        }
        with mock.patch.object(radar, "request_json", return_value=payload):
            with self.assertRaisesRegex(RuntimeError, "缺少前复权日线（原始日线60条）"):
                radar.fetch_tencent_stock_prices("600000", "2026-07-16")

    def test_normalize_stock_prices_rejects_bad_duplicate_or_nonfinite_rows(self) -> None:
        invalid_cases = (
            [["2026/07/16", "10.0", "10.8"]],
            [["2026-07-16", "10.0", "inf"]],
            [
                ["2026-07-16", "10.0", "10.8"],
                ["2026-07-16", "10.0", "10.8"],
            ],
        )
        for rows in invalid_cases:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    radar.normalize_stock_prices(rows, "2026-07-16")

    def test_validate_stock_price_series_rejects_sparse_but_preserves_stale_rows(self) -> None:
        sparse = [{"date": "2026-07-16", "close": 10.0}] * 59
        with self.assertRaisesRegex(RuntimeError, "有效日线不足60条"):
            radar.validate_stock_price_series(sparse, "2026-07-16", "测试源")

        stale = [
            {"date": (date(2026, 4, 1) + timedelta(days=offset)).isoformat(), "close": 10.0}
            for offset in range(60)
        ]
        self.assertEqual(radar.validate_stock_price_series(stale, "2026-07-16", "测试源"), stale)
        self.assertFalse(radar.stock_price_series_is_fresh(stale, "2026-07-16"))

    def test_eastmoney_stock_prices_request_qfq_for_new_beijing_code(self) -> None:
        start = date(2026, 5, 18)
        klines = [
            f"{(start + timedelta(days=offset)).isoformat()},10.0,10.8"
            for offset in range(60)
        ]
        payload = {"data": {"klines": klines}}
        with mock.patch.object(radar, "request_json", return_value=payload) as request:
            prices = radar.fetch_eastmoney_stock_prices("920001", "2026-07-16")

        self.assertEqual(len(prices), 60)
        request.assert_called_once_with(
            radar.EASTMONEY_KLINE_URL,
            {
                "secid": "0.920001",
                "klt": 101,
                "fqt": 1,
                "beg": "20260117",
                "end": "20260716",
                "lmt": 160,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53",
            },
            timeout=10,
            retries=1,
        )

    def test_stock_prices_use_tencent_without_eastmoney(self) -> None:
        rows = [{"date": "2026-07-16", "close": 11.0}]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            radar, "fetch_tencent_stock_prices", return_value=rows
        ) as tencent, mock.patch.object(radar, "fetch_eastmoney_stock_prices") as eastmoney:
            result = radar.fetch_stock_prices("000652", "2026-07-16", Path(tmp))

        self.assertEqual(result, rows)
        tencent.assert_called_once_with("000652", "2026-07-16")
        eastmoney.assert_not_called()

    def test_sparse_same_day_cache_is_ignored_and_refreshed(self) -> None:
        start = date(2026, 5, 19)
        cached_rows = [
            {"date": (start + timedelta(days=offset)).isoformat(), "close": 10.0}
            for offset in range(59)
        ]
        remote_rows = [{"date": "2026-07-16", "close": 11.0}]
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            radar.atomic_write_json(
                radar.stock_cache_path(cache_dir, "000652"),
                {"fetched_on": "2026-07-16", "rows": cached_rows},
            )
            with mock.patch.object(
                radar, "fetch_tencent_stock_prices", return_value=remote_rows
            ) as tencent, mock.patch.object(radar, "fetch_eastmoney_stock_prices") as eastmoney:
                result = radar.fetch_stock_prices("000652", "2026-07-16", cache_dir)

        self.assertEqual(result, remote_rows)
        tencent.assert_called_once_with("000652", "2026-07-16")
        eastmoney.assert_not_called()

    def test_valid_same_day_cache_avoids_both_network_sources(self) -> None:
        start = date(2026, 5, 18)
        cached_rows = [
            {"date": (start + timedelta(days=offset)).isoformat(), "close": 10.0}
            for offset in range(60)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            radar.atomic_write_json(
                radar.stock_cache_path(cache_dir, "000652"),
                {"fetched_on": "2026-07-16", "rows": cached_rows},
            )
            with mock.patch.object(radar, "fetch_tencent_stock_prices") as tencent, mock.patch.object(
                radar, "fetch_eastmoney_stock_prices"
            ) as eastmoney:
                result = radar.fetch_stock_prices("000652", "2026-07-16", cache_dir)

        self.assertEqual(result, cached_rows)
        tencent.assert_not_called()
        eastmoney.assert_not_called()

    def test_stock_prices_fall_back_to_eastmoney_and_cache_success(self) -> None:
        rows = [{"date": "2026-07-16", "close": 11.0}]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            radar, "fetch_tencent_stock_prices", side_effect=ConnectionError("tencent unavailable")
        ), mock.patch.object(radar, "fetch_eastmoney_stock_prices", return_value=rows) as eastmoney:
            cache_dir = Path(tmp)
            result = radar.fetch_stock_prices("000652", "2026-07-16", cache_dir)
            cached = json.loads(radar.stock_cache_path(cache_dir, "000652").read_text(encoding="utf-8"))

        self.assertEqual(result, rows)
        self.assertEqual(cached["rows"], rows)
        eastmoney.assert_called_once_with("000652", "2026-07-16")

    def test_stale_tencent_prices_probe_eastmoney_and_choose_newer_series(self) -> None:
        tencent_rows = [{"date": "2026-07-05", "close": 10.0}]
        eastmoney_rows = [{"date": "2026-07-15", "close": 11.0}]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            radar, "fetch_tencent_stock_prices", return_value=tencent_rows
        ), mock.patch.object(
            radar, "fetch_eastmoney_stock_prices", return_value=eastmoney_rows
        ) as eastmoney:
            result = radar.fetch_stock_prices("000652", "2026-07-16", Path(tmp))

        self.assertEqual(result, eastmoney_rows)
        eastmoney.assert_called_once_with("000652", "2026-07-16")

    def test_stale_tencent_prices_survive_eastmoney_failure_for_endpoint_filtering(self) -> None:
        tencent_rows = [{"date": "2026-07-05", "close": 10.0}]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            radar, "fetch_tencent_stock_prices", return_value=tencent_rows
        ), mock.patch.object(
            radar, "fetch_eastmoney_stock_prices", side_effect=ConnectionError("eastmoney unavailable")
        ):
            result = radar.fetch_stock_prices("000652", "2026-07-16", Path(tmp))

        self.assertEqual(result, tencent_rows)

    def test_newer_cache_survives_source_date_regression(self) -> None:
        start = date(2026, 5, 17)
        cached_rows = [
            {"date": (start + timedelta(days=offset)).isoformat(), "close": 10.0}
            for offset in range(60)
        ]
        tencent_rows = [{"date": "2026-07-05", "close": 9.0}]
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cache_path = radar.stock_cache_path(cache_dir, "000652")
            radar.atomic_write_json(cache_path, {"fetched_on": "2026-07-15", "rows": cached_rows})
            with mock.patch.object(
                radar, "fetch_tencent_stock_prices", return_value=tencent_rows
            ), mock.patch.object(
                radar, "fetch_eastmoney_stock_prices", side_effect=ConnectionError("eastmoney unavailable")
            ):
                result = radar.fetch_stock_prices("000652", "2026-07-16", cache_dir)
            persisted = json.loads(cache_path.read_text(encoding="utf-8"))["rows"]

        self.assertEqual(result, cached_rows)
        self.assertEqual(persisted, cached_rows)

    def test_stale_series_is_filtered_per_breadth_endpoint(self) -> None:
        start = date(2026, 4, 17)
        prices = [
            {"date": (start + timedelta(days=offset)).isoformat(), "close": float(offset + 1)}
            for offset in range(80)
        ]
        self.assertIsNone(radar.above_ma60(prices, "2026-07-16"))
        self.assertTrue(radar.above_ma60(prices, "2026-07-10"))

    def test_stock_prices_report_both_source_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            radar, "fetch_tencent_stock_prices", side_effect=ConnectionError("tencent unavailable")
        ), mock.patch.object(
            radar, "fetch_eastmoney_stock_prices", side_effect=RuntimeError("eastmoney unavailable")
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "000652成分股日线双源失败；腾讯: tencent unavailable；东财: eastmoney unavailable",
            ):
                radar.fetch_stock_prices("000652", "2026-07-16", Path(tmp))


class EvidenceProtocolV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.industries = [
            {
                "code": "801080",
                "name": "电子",
                "template": "订单",
                "aliases": ["PCB", "半导体"],
            }
        ]
        self.components = {
            "801080": [
                {"code": "000001", "name": "甲方科技"},
                {"code": "000002", "name": "乙方电子"},
            ]
        }
        self.candidates = {
            "801080": [
                {
                    "id": "801080-N1",
                    "title": "甲方科技订单增长",
                    "url": "https://example.test/one",
                    "pub_date": "2026-07-10",
                    "category_tags": ["O"],
                    "entity_names": ["甲方科技"],
                    "component_entities": ["甲方科技"],
                    "event_cluster": "order-one",
                    "source_type": "announcement",
                },
                {
                    "id": "801080-N2",
                    "title": "PCB利润增长",
                    "url": "https://example.test/two",
                    "pub_date": "2026-07-11",
                    "category_tags": ["E"],
                    "entity_names": ["PCB"],
                    "component_entities": [],
                    "event_cluster": "earnings-two",
                    "source_type": "trusted_news",
                },
            ]
        }
        self.ttl = {"S": 45, "O": 120, "E": 120}

    def parse(self, raw: str, *, candidates: dict | None = None) -> dict:
        return radar.parse_evidence_protocol(
            raw,
            self.industries,
            candidates if candidates is not None else self.candidates,
            "2026-07-17",
            self.ttl,
            self.components,
        )

    def test_watch_preserves_grounded_partial_claim(self) -> None:
        raw = (
            "EVIDENCE\t801080\tWATCH\tO@801080-N1@甲方科技\tNONE\tPCB"
            "\t已确认订单，仍缺少跨公司扩散\tNONE"
        )

        item = self.parse(raw)["801080"]

        self.assertEqual(item["gate"], "WATCH")
        self.assertEqual(item["categories"], ["O"])
        self.assertEqual(
            item["claims"],
            [
                {
                    "category": "O",
                    "evidence_id": "801080-N1",
                    "entity": "甲方科技",
                    "published_at": "2026-07-10",
                }
            ],
        )

    def test_pass_requires_distinct_event_clusters(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][1]["event_cluster"] = "order-one"
        raw = (
            "EVIDENCE\t801080\tPASS\tO@801080-N1@甲方科技,E@801080-N2@PCB"
            "\tNONE\tPCB\t订单与盈利来自两个主体\tNONE"
        )

        with self.assertRaisesRegex(ValueError, "PASS硬门槛"):
            self.parse(raw, candidates=candidates)

    def test_pass_requires_at_least_one_component_entity(self) -> None:
        candidates = {
            "801080": [
                {
                    "id": "801080-N1",
                    "title": "PCB订单增长",
                    "url": "https://example.test/one",
                    "pub_date": "2026-07-10",
                    "category_tags": ["O"],
                    "entity_names": ["PCB"],
                    "component_entities": [],
                    "event_cluster": "order-one",
                },
                {
                    "id": "801080-N2",
                    "title": "半导体利润增长",
                    "url": "https://example.test/two",
                    "pub_date": "2026-07-11",
                    "category_tags": ["E"],
                    "entity_names": ["半导体"],
                    "component_entities": [],
                    "event_cluster": "earnings-two",
                },
            ]
        }
        raw = (
            "EVIDENCE\t801080\tPASS\tO@801080-N1@PCB,E@801080-N2@半导体"
            "\tNONE\tPCB\t两个产业链别名但没有成分实体\tNONE"
        )

        with self.assertRaisesRegex(ValueError, "PASS硬门槛"):
            self.parse(raw, candidates=candidates)

    def test_pass_accepts_two_clusters_with_a_component_entity(self) -> None:
        raw = (
            "EVIDENCE\t801080\tPASS\tO@801080-N1@甲方科技,E@801080-N2@PCB"
            "\tNONE\tPCB\t订单与盈利来自两个主体\tNONE"
        )

        item = self.parse(raw)["801080"]

        self.assertEqual(item["gate"], "PASS")
        self.assertEqual(item["component_entity_count"], 1)
        self.assertEqual(item["event_clusters"], ["earnings-two", "order-one"])

    def test_model_cannot_omit_script_detected_contrary_evidence(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"].append(
            {
                "id": "801080-N3",
                "title": "PCB订单同比下降30%",
                "url": "https://example.test/negative",
                "pub_date": "2026-07-12",
                "category_tags": ["O"],
                "positive_category_tags": [],
                "negative_category_tags": ["O"],
                "entity_names": ["PCB"],
                "component_entities": [],
                "event_cluster": "negative-three",
                "source_type": "trusted_news",
            }
        )
        raw = (
            "EVIDENCE\t801080\tPASS\tO@801080-N1@甲方科技,E@801080-N2@PCB"
            "\tNONE\tPCB\t模型错误遗漏了负向订单\tNONE"
        )

        with self.assertRaisesRegex(ValueError, "PASS硬门槛"):
            self.parse(raw, candidates=candidates)

    def test_explicit_positive_tags_block_directionless_claim(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][0]["positive_category_tags"] = []
        raw = (
            "EVIDENCE\t801080\tWATCH\tO@801080-N1@甲方科技\tNONE\tPCB"
            "\t方向不明不能作为正向claim\tNONE"
        )

        with self.assertRaisesRegex(ValueError, "没有O类正向字段"):
            self.parse(raw, candidates=candidates)


class CandidateDirectionTest(unittest.TestCase):
    def test_directionless_or_negative_earnings_title_is_not_positive(self) -> None:
        self.assertEqual(radar.title_positive_category_tags("甲公司2026年半年度业绩预告"), [])
        self.assertEqual(radar.title_positive_category_tags("甲公司预计净利润同比增长80%"), ["E"])
        self.assertEqual(radar.title_positive_category_tags("甲公司预计净利润同比下降80%并转亏"), [])

    def test_positive_order_title_is_grounded(self) -> None:
        self.assertEqual(radar.title_positive_category_tags("甲公司新增订单增长50%"), ["O"])

    def test_demand_and_supply_titles_have_local_direction(self) -> None:
        self.assertEqual(radar.title_positive_category_tags("铜需求回暖"), ["S"])
        self.assertEqual(radar.title_positive_category_tags("铜需求下降"), [])
        self.assertEqual(radar.title_negative_category_tags("铜需求下降"), ["S"])
        self.assertEqual(radar.title_positive_category_tags("铜供给收缩"), ["S"])
        self.assertEqual(radar.title_positive_category_tags("铜供应过剩"), [])
        self.assertEqual(radar.title_negative_category_tags("铜供应过剩"), ["S"])

    def test_single_character_industry_alias_requires_signal_context(self) -> None:
        industry = {"name": "有色金属", "aliases": ["铜"]}
        bound = radar.bind_candidate(
            {"title": "铜价上涨带动行业景气回升", "url": "https://example.test/copper"},
            industry,
            [],
        )

        self.assertIsNotNone(bound)
        self.assertEqual(bound["entity_names"], ["铜"])
        self.assertEqual(bound["positive_category_tags"], ["S"])
        self.assertIsNone(
            radar.bind_candidate(
                {"title": "奥运铜牌价格公布", "url": "https://example.test/medal"},
                industry,
                [],
            )
        )

    def test_downstream_input_price_increase_is_not_positive_supply_evidence(self) -> None:
        bound = radar.bind_candidate(
            {
                "title": "PCB原材料价格上涨，企业成本压力加大",
                "url": "https://example.test/input-cost",
            },
            {"name": "电子", "aliases": ["PCB"]},
            [],
        )

        self.assertIsNotNone(bound)
        self.assertEqual(bound["positive_category_tags"], [])
        self.assertEqual(bound["negative_category_tags"], ["S"])

    def test_positive_direction_does_not_bleed_across_categories(self) -> None:
        self.assertEqual(radar.title_positive_category_tags("甲公司订单增长，利润承压"), ["O"])
        self.assertEqual(radar.title_positive_category_tags("甲公司订单增长，营收同比持平"), ["O"])
        self.assertEqual(radar.title_positive_category_tags("甲公司布局新产能，产品价格承压"), [])
        self.assertEqual(radar.title_positive_category_tags("甲公司利润增长，订单减少"), ["E"])

    def test_identical_official_filing_titles_from_two_companies_are_independent(self) -> None:
        first = radar.candidate_event_cluster("甲公司：2026年半年度业绩预增公告", ["甲公司"], "announcement")
        second = radar.candidate_event_cluster("乙公司：2026年半年度业绩预增公告", ["乙公司"], "announcement")
        self.assertNotEqual(first, second)


class EvidenceSemanticValidationTest(unittest.TestCase):
    @staticmethod
    def empty_watch(summary: str) -> dict:
        return {"gate": "WATCH", "claims": [], "summary": summary}

    def test_rejects_empty_claims_when_component_announcements_exist(self) -> None:
        evidence = {"801001": self.empty_watch("仍待确认")}
        candidates = {
            "801001": [
                {
                    "source_type": "announcement",
                    "category_tags": ["O"],
                    "positive_category_tags": ["O"],
                    "component_entities": ["甲公司"],
                },
                {
                    "source_type": "announcement",
                    "category_tags": ["E"],
                    "positive_category_tags": ["E"],
                    "component_entities": ["乙公司"],
                },
            ]
        }

        with self.assertRaisesRegex(ValueError, "正向公司公告.*partial claim"):
            radar.validate_evidence_semantics(evidence, candidates)

    def test_one_claim_cannot_mask_another_industry_missing_official_claim(self) -> None:
        evidence = {
            "801001": {"gate": "WATCH", "claims": [{"evidence_id": "801001-N1"}], "evidence_ids": ["801001-N1"], "summary": "已审计"},
            "801002": {"gate": "WATCH", "claims": [], "evidence_ids": [], "summary": "被错误清空"},
        }
        candidates = {
            code: [
                {
                    "id": f"{code}-N1",
                    "source_type": "announcement",
                    "positive_category_tags": ["E"],
                    "component_entities": ["公司"],
                }
            ]
            for code in evidence
        }

        with self.assertRaisesRegex(ValueError, "801002"):
            radar.validate_evidence_semantics(evidence, candidates)

    def test_rejects_repeated_all_watch_empty_output(self) -> None:
        codes = ["801001", "801002", "801003"]
        evidence = {code: self.empty_watch("候选证据不足") for code in codes}
        candidates = {
            code: [{"source_type": "trusted_news", "category_tags": ["S"]}]
            for code in codes
        }

        with self.assertRaisesRegex(ValueError, "重复的全WATCH空claim"):
            radar.validate_evidence_semantics(evidence, candidates)

    def test_stale_positive_official_is_not_mandatory(self) -> None:
        evidence = {"801001": self.empty_watch("公告已超过TTL")}
        candidates = {
            "801001": [
                {
                    "id": "801001-N1",
                    "source_type": "announcement",
                    "pub_date": "2026-01-01",
                    "positive_category_tags": ["E"],
                    "component_entities": ["甲公司"],
                }
            ]
        }

        radar.validate_evidence_semantics(
            evidence,
            candidates,
            "2026-07-16",
            {"S": 45, "O": 120, "E": 120},
        )

    def test_audited_rules_recovery_may_confirm_no_positive_claims(self) -> None:
        codes = ["801001", "801002", "801003"]
        evidence = {
            code: {
                **self.empty_watch("规则核验无正向字段"),
                "decision_source": "rules_recovery",
            }
            for code in codes
        }
        candidates = {
            code: [
                {
                    "id": f"{code}-N1",
                    "source_type": "trusted_news",
                    "positive_category_tags": [],
                }
            ]
            for code in codes
        }

        radar.validate_evidence_semantics(evidence, candidates)


class DeterministicEvidenceRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.industries = [{"code": "801080", "name": "电子", "aliases": ["PCB"], "template": "订单"}]
        self.components = {
            "801080": [
                {"code": "000001", "name": "甲方科技"},
                {"code": "000002", "name": "乙方电子"},
            ]
        }
        self.candidates = {
            "801080": [
                {
                    "id": "801080-N1",
                    "title": "甲方科技预计净利润同比增长80%",
                    "url": "https://example.test/earnings",
                    "pub_date": "2026-07-10",
                    "source_type": "announcement",
                    "positive_category_tags": ["E"],
                    "negative_category_tags": [],
                    "entity_names": ["甲方科技"],
                    "component_entities": ["甲方科技"],
                    "event_cluster": "earnings-one",
                },
                {
                    "id": "801080-N2",
                    "title": "乙方电子新增订单增长50%",
                    "url": "https://example.test/order",
                    "pub_date": "2026-07-11",
                    "source_type": "trusted_news",
                    "positive_category_tags": ["O"],
                    "negative_category_tags": [],
                    "entity_names": ["乙方电子"],
                    "component_entities": ["乙方电子"],
                    "event_cluster": "order-two",
                },
            ]
        }
        self.ttl = {"S": 45, "O": 120, "E": 120}

    def build(self, candidates: dict[str, list[dict]] | None = None) -> dict:
        return radar.deterministic_grounded_evidence(
            "2026-07-16",
            self.industries,
            candidates or self.candidates,
            self.ttl,
            self.components,
        )

    def test_recovery_can_pass_only_with_grounded_independent_fields(self) -> None:
        item = self.build()["801080"]

        self.assertEqual(item["gate"], "PASS")
        self.assertEqual(item["categories"], ["E", "O"])
        self.assertEqual(item["evidence_ids"], ["801080-N1", "801080-N2"])
        self.assertEqual(item["component_entity_count"], 2)

    def test_multitag_official_prefers_gate_eligible_earnings_over_supply(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][0]["positive_category_tags"] = ["E", "S"]

        item = self.build(candidates)["801080"]

        official_claim = next(claim for claim in item["claims"] if claim["evidence_id"] == "801080-N1")
        self.assertEqual(official_claim["category"], "E")
        self.assertEqual(item["gate_eligible_categories"], ["E", "O"])
        self.assertEqual(item["gate"], "PASS")

    def test_multitag_official_chooses_category_complementing_other_company(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][0]["positive_category_tags"] = ["E", "O"]

        item = self.build(candidates)["801080"]

        official_claim = next(claim for claim in item["claims"] if claim["evidence_id"] == "801080-N1")
        self.assertEqual(official_claim["category"], "E")
        self.assertEqual(item["gate_eligible_categories"], ["E", "O"])
        self.assertEqual(item["gate"], "PASS")

    def test_negative_title_is_contrary_and_forces_watch(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"].append(
            {
                "id": "801080-N3",
                "title": "PCB订单同比下降30%",
                "url": "https://example.test/negative",
                "pub_date": "2026-07-12",
                "source_type": "trusted_news",
                "positive_category_tags": [],
                "negative_category_tags": ["O"],
                "entity_names": ["PCB"],
                "component_entities": [],
                "event_cluster": "negative-three",
            }
        )

        item = self.build(candidates)["801080"]

        self.assertEqual(item["gate"], "WATCH")
        self.assertEqual(item["contrary_ids"], ["801080-N3"])

    def test_news_only_recovery_never_auto_passes(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][0]["source_type"] = "trusted_news"

        item = self.build(candidates)["801080"]

        self.assertEqual(item["gate"], "WATCH")
        self.assertIn("缺少公司公告锚点", item["summary"])

    def test_industry_alias_announcement_is_not_a_company_anchor(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][0].update(
            {
                "title": "PCB利润增长",
                "entity_names": ["PCB"],
                "component_entities": [],
            }
        )

        item = self.build(candidates)["801080"]

        self.assertEqual(item["gate"], "WATCH")
        self.assertIn("缺少公司公告锚点", item["summary"])

    def test_mixed_direction_selected_claim_remains_contrary(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][1]["title"] = "乙方电子利润增长但订单下降"
        candidates["801080"][1]["negative_category_tags"] = ["O"]

        item = self.build(candidates)["801080"]

        self.assertIn("801080-N2", item["evidence_ids"])
        self.assertIn("801080-N2", item["contrary_ids"])
        self.assertEqual(item["gate"], "WATCH")

    def test_supply_signal_does_not_contribute_to_rules_recovery_pass(self) -> None:
        candidates = copy.deepcopy(self.candidates)
        candidates["801080"][1].update(
            {
                "title": "乙方电子产品价格上涨",
                "positive_category_tags": ["S"],
                "negative_category_tags": [],
            }
        )

        item = self.build(candidates)["801080"]

        self.assertIn("S", item["categories"])
        self.assertEqual(item["gate"], "WATCH")
        self.assertEqual(item["decision_source"], "rules_recovery")
        self.assertEqual(item["gate_eligible_categories"], ["E"])
        self.assertTrue(any("成分公司O/E类别不足2类" in gap for gap in item["gate_blockers"]))

    def test_three_invalid_model_attempts_use_audited_recovery(self) -> None:
        before = copy.deepcopy(radar.RUN_STATS)
        radar.RUN_STATS["ai_recovery_batches"] = 0
        try:
            with mock.patch.object(radar, "call_ai", return_value="not a protocol") as call_ai:
                evidence, raw = radar.analyze_evidence(
                    "2026-07-16",
                    self.industries,
                    self.candidates,
                    "codebuddy",
                    "hy3",
                    self.ttl,
                    self.components,
                )

            self.assertEqual(call_ai.call_count, 3)
            self.assertEqual(evidence["801080"]["gate"], "PASS")
            self.assertIn("RULES_RECOVERY_BATCH_1", raw)
            self.assertIn("response_sha256=", raw)
            self.assertNotIn("not a protocol", raw)
            self.assertEqual(radar.RUN_STATS["ai_recovery_batches"], 1)
        finally:
            radar.RUN_STATS.clear()
            radar.RUN_STATS.update(before)


class DecisionHashTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "generated_at": "2026-07-19T10:00:00+08:00",
            "ai_raw_protocol": "model prose A",
            "ai_recovery_batches": 0,
            "evidence_engine_version": "rules-recovery-v1",
            "engine_sha256": "a" * 64,
            "evidence": {"801080": {"gate": "WATCH", "categories": ["O"]}},
            "candidates": {
                "801080": [
                    {
                        "id": "801080-N1",
                        "title": "甲方科技订单增长",
                        "fetched_at": "2026-07-19T09:00:00+08:00",
                    }
                ]
            },
        }

    def test_ignores_collection_time_and_raw_protocol(self) -> None:
        changed = copy.deepcopy(self.payload)
        changed["generated_at"] = "2026-07-20T10:00:00+08:00"
        changed["ai_raw_protocol"] = "model prose B"
        changed["ai_recovery_batches"] = 2
        changed["candidates"]["801080"][0]["fetched_at"] = "2026-07-20T09:00:00+08:00"

        self.assertEqual(
            radar.decision_sha256(self.payload),
            radar.decision_sha256(changed),
        )

    def test_changes_when_evidence_gate_or_candidate_title_changes(self) -> None:
        baseline = radar.decision_sha256(self.payload)
        gate_changed = copy.deepcopy(self.payload)
        gate_changed["evidence"]["801080"]["gate"] = "PASS"
        title_changed = copy.deepcopy(self.payload)
        title_changed["candidates"]["801080"][0]["title"] = "甲方科技订单下滑"
        engine_changed = copy.deepcopy(self.payload)
        engine_changed["engine_sha256"] = "b" * 64

        self.assertNotEqual(baseline, radar.decision_sha256(gate_changed))
        self.assertNotEqual(baseline, radar.decision_sha256(title_changed))
        self.assertNotEqual(baseline, radar.decision_sha256(engine_changed))


class BatchedEvidenceAnalysisTest(unittest.TestCase):
    def test_batches_only_contain_their_codes_and_only_failed_batch_retries(self) -> None:
        industries = [
            {"code": f"80100{index}", "name": f"行业{index}", "template": "模板", "aliases": []}
            for index in range(1, 6)
        ]
        candidates = {item["code"]: [] for item in industries}
        components = {item["code"]: [] for item in industries}
        calls: list[list[str]] = []
        failed_once = False

        def fake_call_ai(prompt: str, model: str, model_name: str) -> str:
            nonlocal failed_once
            codes = re.findall(r"^INDUSTRY\t(\d{6})\t", prompt, flags=re.MULTILINE)
            calls.append(codes)
            if codes == ["801003", "801004"] and not failed_once:
                failed_once = True
                return "not a protocol"
            return "\n".join(
                f"EVIDENCE\t{code}\tWATCH\tNONE\tNONE\t待验证\t{code}暂无候选\tNONE"
                for code in codes
            )

        with mock.patch.dict(os.environ, {"A_SHARE_SECTOR_RADAR_AI_BATCH_SIZE": "2"}), mock.patch.object(
            radar, "call_ai", side_effect=fake_call_ai
        ):
            evidence, raw = radar.analyze_evidence(
                "2026-07-17",
                industries,
                candidates,
                "codex",
                "",
                {"S": 45, "O": 120, "E": 120},
                components,
            )

        self.assertEqual(
            calls,
            [
                ["801001", "801002"],
                ["801003", "801004"],
                ["801003", "801004"],
                ["801005"],
            ],
        )
        self.assertEqual(list(evidence), [item["code"] for item in industries])
        self.assertEqual(raw.count("EVIDENCE\t"), len(industries))


class LedgerMigrationV2Test(unittest.TestCase):
    @staticmethod
    def ledger(*, events: list[dict] | None = None) -> dict:
        return {
            "schema_version": 1,
            "strategy_version": "v0.2-F.1-pilot",
            "last_report_date": "2026-07-16",
            "active_cycles": {},
            "cycle_closures": [],
            "events": events or [],
            "hold_observations": [],
            "weekly_snapshots": [{"report_date": "2026-07-16", "radar_codes": []}],
        }

    def test_explicit_f1_to_f2_migration_marks_old_snapshot_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text(json.dumps(self.ledger(), ensure_ascii=False), encoding="utf-8")

            migrated = radar.load_ledger(path, "v0.2-F.2-pilot")

        self.assertEqual(migrated["strategy_version"], "v0.2-F.2-pilot")
        self.assertEqual(
            migrated["weekly_snapshots"][0]["sample_eligibility"],
            "excluded_invalidated_v0.2-F.1",
        )
        self.assertEqual(migrated["migrations"][-1]["from"], "v0.2-F.1-pilot")
        self.assertEqual(migrated["migrations"][-1]["to"], "v0.2-F.2-pilot")

    def test_f1_to_f2_migration_refuses_nonempty_forward_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text(
                json.dumps(
                    self.ledger(events=[{"code": "801080", "signal_date": "2026-07-16"}]),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "必须显式迁移"):
                radar.load_ledger(path, "v0.2-F.2-pilot")


class RepairRunIntegrationTest(unittest.TestCase):
    def test_repair_refuses_same_date_forward_state(self) -> None:
        ledger = {
            "active_cycles": {"801080": {"signal_date": "2026-07-17"}},
            "events": [{"code": "801080", "signal_date": "2026-07-17"}],
            "hold_observations": [{"code": "801150", "signal_date": "2026-07-17"}],
        }
        self.assertEqual(
            radar.repair_forward_state_conflicts(ledger, "2026-07-17"),
            ["active_cycle:801080", "events:801080", "hold_observations:801150"],
        )

    def test_repair_overwrites_invalid_artifact_without_forward_activation(self) -> None:
        cutoff = date.today()
        report_day = cutoff - timedelta(days=1)
        report_date = report_day.isoformat()
        expected_date = cutoff.isoformat()
        config = radar.load_config(ROOT / "config" / "a_share_sector_radar.json")
        industries = config["industries"]
        common_dates = [(report_day - timedelta(days=offset)).isoformat() for offset in range(10, -1, -1)]
        metrics = {
            item["code"]: {
                "return_5d": 0.0,
                "return_20d": 0.0,
                "relative_20d": 0.0,
                "rank_20d": index + 1,
                "relative_ok": False,
                "breadth_ok": False,
                "breadth": None,
                "turnover_ok": False,
                "turnover_percentile": None,
                "crowding_state": "",
                "crowding_reason": "",
                "e30_date": "",
            }
            for index, item in enumerate(industries)
        }
        histories = {
            item["code"]: [{"date": report_date, "open": 100.0, "close": 100.0, "amount": 1.0}]
            for item in industries
        }
        components = {
            item["code"]: [{"code": f"{index + 1:06d}", "name": f"成分{index + 1}", "weight": 1.0}]
            for index, item in enumerate(industries)
        }
        candidates = {
            item["code"]: [
                {"id": f"{item['code']}-N1", "title": "方向不明业绩预告", "url": "https://example.test/1", "pub_date": report_date},
                {"id": f"{item['code']}-N2", "title": "方向不明产能公告", "url": "https://example.test/2", "pub_date": report_date},
            ]
            for item in industries
        }
        evidence = radar.watch_only_evidence(industries)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "published"
            status_dir = root / "status"
            cache_dir = root / "cache"
            (output / "snapshots").mkdir(parents=True)
            (output / f"{report_date}.md").write_text("invalid old report\n", encoding="utf-8")
            (output / "latest.md").write_text("invalid old report\n", encoding="utf-8")
            (output / "snapshots" / f"{report_date}.json").write_text(
                json.dumps({"strategy_version": "v0.2-F.1-pilot"}), encoding="utf-8"
            )
            (output / "ledger.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "strategy_version": "v0.2-F.1-pilot",
                        "last_report_date": report_date,
                        "active_cycles": {},
                        "cycle_closures": [],
                        "events": [],
                        "hold_observations": [],
                        "weekly_snapshots": [{"date": report_date}],
                    }
                ),
                encoding="utf-8",
            )
            args = radar.build_parser().parse_args(
                [
                    "--date", expected_date,
                    "--config", str(ROOT / "config" / "a_share_sector_radar.json"),
                    "--output-dir", str(output),
                    "--status-dir", str(status_dir),
                    "--cache-dir", str(cache_dir),
                    "--repair-existing",
                ]
            )

            with mock.patch.object(radar, "fetch_reference_trading_dates", return_value=[report_date, expected_date]), mock.patch.object(
                radar, "fetch_all_sw_histories", return_value=histories
            ), mock.patch.object(
                radar, "calculate_market_metrics", return_value=(report_date, common_dates, metrics)
            ), mock.patch.object(radar, "fetch_all_components", return_value=components), mock.patch.object(
                radar, "collect_evidence_candidates", return_value=candidates
            ), mock.patch.object(radar, "analyze_evidence", return_value=(evidence, "protocol\n")):
                status = radar.run(args)

            repaired_ledger = json.loads((output / "ledger.json").read_text(encoding="utf-8"))
            repaired_snapshot = json.loads(
                (output / "snapshots" / f"{report_date}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["sample_eligibility"], "excluded_repair")
            self.assertTrue(status["publish_required"])
            self.assertEqual(repaired_ledger["events"], [])
            self.assertEqual(repaired_ledger["active_cycles"], {})
            self.assertEqual(repaired_snapshot["new_activations"], [])
            self.assertEqual(repaired_snapshot["sample_eligibility"], "excluded_repair")
            self.assertEqual(repaired_snapshot["evidence_engine_version"], "rules-recovery-v1")
            self.assertRegex(repaired_snapshot["engine_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                repaired_ledger["weekly_snapshots"][-1]["engine_sha256"],
                repaired_snapshot["engine_sha256"],
            )
            rendered = (output / f"{report_date}.md").read_text(encoding="utf-8")
            self.assertIn("修复回填（不计前瞻）", rendered)
            self.assertIn("rules-recovery-v1", rendered)


class ReuseStatusTest(unittest.TestCase):
    def test_pending_publish_is_retried_without_mutating_artifacts(self) -> None:
        report_date = "2026-07-17"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "published"
            status_dir = root / "status"
            (output / "snapshots").mkdir(parents=True)
            status_dir.mkdir()
            report = output / f"{report_date}.md"
            latest = output / "latest.md"
            snapshot = output / "snapshots" / f"{report_date}.json"
            ledger = output / "ledger.json"
            local_snapshot = root / "local.json"
            for path, content in (
                (report, "report\n"),
                (latest, "report\n"),
                (snapshot, "{}\n"),
                (ledger, "{}\n"),
                (local_snapshot, "{}\n"),
            ):
                path.write_text(content, encoding="utf-8")

            def digest(path: Path) -> str:
                return hashlib.sha256(path.read_bytes()).hexdigest()

            artifact_status = {
                "date": report_date,
                "strategy_version": "v-test",
                "evidence_engine_version": "rules-recovery-v1",
                "engine_sha256": "a" * 64,
                "mode": "codebuddy+rules-recovery",
                "fallback_used": True,
                "fallback_kind": "audited_evidence_recovery",
                "ai_recovery_used": True,
                "ai_recovery_batches": 1,
                "publishable": True,
                "publish_status": "pending",
                "report_sha256": digest(report),
                "snapshot_sha256": digest(snapshot),
                "ledger_sha256": digest(ledger),
                "local_snapshot_path": str(local_snapshot),
                "local_snapshot_sha256": digest(local_snapshot),
                "sample_eligibility": "formal_forward",
            }
            (status_dir / "latest-artifact.json").write_text(
                json.dumps(artifact_status), encoding="utf-8"
            )
            before = {path: path.read_bytes() for path in (report, latest, snapshot, ledger, local_snapshot)}

            run_status = radar.reuse_completed_run(
                report_date,
                output,
                status_dir,
                ledger,
                {"actual": report_date, "expected": report_date, "lag_sessions": 0},
            )

            self.assertTrue(run_status["publish_required"])
            self.assertEqual(run_status["outcome"], "reused_pending_publish")
            self.assertEqual(run_status["evidence_engine_version"], "rules-recovery-v1")
            self.assertEqual(run_status["engine_sha256"], "a" * 64)
            self.assertTrue(run_status["fallback_used"])
            self.assertEqual(run_status["fallback_kind"], "audited_evidence_recovery")
            self.assertTrue(json.loads((status_dir / "latest-run.json").read_text())["publish_required"])
            self.assertEqual(before, {path: path.read_bytes() for path in before})


if __name__ == "__main__":
    unittest.main()
