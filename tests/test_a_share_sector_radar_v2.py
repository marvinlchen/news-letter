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
        self.assertEqual(radar.title_positive_category_tags("铜供给收缩"), ["S"])
        self.assertEqual(radar.title_positive_category_tags("铜供应过剩"), [])

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


class DecisionHashTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "generated_at": "2026-07-19T10:00:00+08:00",
            "ai_raw_protocol": "model prose A",
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

        self.assertNotEqual(baseline, radar.decision_sha256(gate_changed))
        self.assertNotEqual(baseline, radar.decision_sha256(title_changed))


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
            self.assertIn("修复回填（不计前瞻）", (output / f"{report_date}.md").read_text(encoding="utf-8"))


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
                "mode": "codebuddy",
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
            self.assertTrue(json.loads((status_dir / "latest-run.json").read_text())["publish_required"])
            self.assertEqual(before, {path: path.read_bytes() for path in before})


if __name__ == "__main__":
    unittest.main()
