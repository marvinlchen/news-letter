from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "a_share_sector_report",
    ROOT / "scripts" / "a_share_sector_report.py",
)
reporter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reporter)


class DeterministicReportTest(unittest.TestCase):
    def make_inputs(self):
        industries = [
            {"code": "801001", "name": "行业甲"},
            {"code": "801002", "name": "行业乙"},
            {"code": "801003", "name": "行业丙"},
        ]
        evidence = {
            "801001": {
                "gate": "WATCH",
                "categories": ["O"],
                "entities": ["甲公司"],
                "evidence_ids": ["801001-N1"],
                "claims": [
                    {
                        "category": "O",
                        "entity": "甲公司",
                        "evidence_id": "801001-N1",
                        "text": "甲公司披露新增订单",
                    }
                ],
                "quality_flags": [],
                "contrary_evidence_ids": [],
                "driver": "AI_DRIVER_SENTINEL",
                "summary": "AI_SUMMARY_SENTINEL",
            },
            "801002": {
                "gate": "WATCH",
                "categories": ["S", "O"],
                "entities": ["乙公司", "供应商乙"],
                "evidence_ids": ["801002-N1", "801002-N2"],
                "quality_flags": [],
                "contrary_evidence_ids": ["801002-N3"],
                "driver": "AI_DRIVER_SENTINEL",
                "summary": "AI_SUMMARY_SENTINEL",
            },
            "801003": {
                "gate": "WATCH",
                "categories": [],
                "entities": [],
                "evidence_ids": [],
                "quality_flags": [],
                "driver": "AI_DRIVER_SENTINEL",
                "summary": "AI_SUMMARY_SENTINEL",
            },
        }
        candidates = {
            "801001": [
                {
                    "id": "801001-N1",
                    "title": "甲公司披露新增订单公告",
                    "url": "https://example.com/alpha-order",
                    "pub_date": "2026-07-16",
                }
            ],
            "801002": [
                {
                    "id": "801002-N1",
                    "title": "乙行业现货库存下降",
                    "url": "https://example.com/beta-stock",
                    "pub_date": "2026-07-15",
                },
                {
                    "id": "801002-N2",
                    "title": "乙公司中标新项目",
                    "url": "https://example.com/beta-order",
                    "pub_date": "2026-07-16",
                },
            ],
            "801003": [
                {
                    "id": "801003-N1",
                    "title": "行业丙候选标题一",
                    "url": "https://example.com/gamma-1",
                    "pub_date": "2026-07-14",
                },
                {
                    "id": "801003-N2",
                    "title": "行业丙候选标题二",
                    "url": "https://example.com/gamma-2",
                    "pub_date": "2026-07-15",
                },
                {
                    "id": "801003-N3",
                    "title": "行业丙候选标题三不应展示",
                    "url": "https://example.com/gamma-3",
                    "pub_date": "2026-07-16",
                },
            ],
        }
        metrics = {
            "801001": {
                "rank_20d": 1,
                "return_5d": 0.03,
                "return_20d": 0.11,
                "relative_20d": 0.08,
                "relative_ok": True,
                "breadth_ok": False,
                "breadth": {"available": False},
                "turnover_ok": True,
                "turnover_percentile": 60.0,
                "crowding_state": "",
            },
            "801002": {
                "rank_20d": 8,
                "return_5d": 0.01,
                "return_20d": 0.04,
                "relative_20d": 0.01,
                "relative_ok": True,
                "breadth_ok": True,
                "breadth": {"available": True, "ratios": [0.7, 0.6, 0.5]},
                "turnover_ok": True,
                "turnover_percentile": 55.0,
                "crowding_state": "",
            },
            "801003": {
                "rank_20d": 5,
                "return_5d": 0.02,
                "return_20d": 0.06,
                "relative_20d": 0.03,
                "relative_ok": True,
                "breadth_ok": False,
                "breadth": {"available": False},
                "turnover_ok": True,
                "turnover_percentile": 50.0,
                "crowding_state": "",
            },
        }
        states = {code: "早期观察" for code in evidence}
        return industries, evidence, candidates, metrics, states

    def render(
        self,
        industries=None,
        evidence_transform=None,
        metrics_transform=None,
        radar_codes=None,
        run_quality_update=None,
    ):
        base_industries, evidence, candidates, metrics, states = self.make_inputs()
        if evidence_transform:
            evidence_transform(evidence)
        if metrics_transform:
            metrics_transform(metrics)
        run_quality = {
            "outcome": "repair_excluded",
            "expected_market_date": "2026-07-17",
            "source_market_date": "2026-07-16",
            "candidate_count": 6,
            "claim_count": 1,
            "evidence_ref_count": 3,
            "semantic_utilization": 1 / 6,
            "ai_recovery_batches": 1,
            "evidence_engine_version": "rules-recovery-v1",
            "engine_sha256": "abcdef0123456789",
        }
        if run_quality_update:
            run_quality.update(run_quality_update)
        return reporter.format_report(
            "2026-07-17",
            "v-test",
            industries or base_industries,
            evidence,
            candidates,
            metrics,
            radar_codes if radar_codes is not None else [],
            states,
            [],
            [],
            {"events": [], "hold_observations": []},
            "test-model",
            120,
            run_quality=run_quality,
        )

    def test_zero_pass_has_useful_sections_instead_of_empty_radar(self) -> None:
        rendered = self.render()
        self.assertIn("0 个行业通过硬证据门", rendered)
        self.assertIn("行情领先但证据未闭环（近失配 Top 5）", rendered)
        self.assertNotIn("## 已通过证据门的雷达", rendered)
        self.assertNotIn("## 产业证据雷达 Top 8", rendered)
        self.assertIn("修复回填（不计前瞻）", rendered)
        self.assertIn("2026-07-17 / 2026-07-16", rendered)
        self.assertIn("模型协议规则恢复 | 1 批", rendered)
        self.assertIn("rules-recovery-v1 @ abcdef012345", rendered)

    def test_free_model_prose_never_leaks(self) -> None:
        rendered = self.render()
        self.assertNotIn("AI_DRIVER_SENTINEL", rendered)
        self.assertNotIn("AI_SUMMARY_SENTINEL", rendered)

    def test_partial_claim_is_linked_and_unadopted_titles_are_labeled(self) -> None:
        rendered = self.render()
        self.assertIn("[甲公司披露新增订单](https://example.com/alpha-order)", rendered)
        self.assertIn("未被证据门采用的候选标题（最多2条）", rendered)
        self.assertIn("[行业丙候选标题二](https://example.com/gamma-2)", rendered)
        self.assertIn("[行业丙候选标题三不应展示](https://example.com/gamma-3)", rendered)
        self.assertNotIn("[行业丙候选标题一](https://example.com/gamma-1)", rendered)
        self.assertIn("广度未计算", rendered)
        self.assertNotIn("广度未通过", rendered)

    def test_near_miss_sort_is_deterministic_and_audit_quality_first(self) -> None:
        industries, _, _, _, _ = self.make_inputs()
        first = self.render(industries)
        second = self.render(list(reversed(industries)))
        self.assertEqual(first, second)
        self.assertLess(first.index("### 1. 行业乙"), first.index("### 2. 行业甲"))

    def test_rules_recovery_watch_explains_why_partial_s_does_not_pass(self) -> None:
        def mark_recovery(evidence):
            evidence["801002"].update(
                {
                    "decision_source": "rules_recovery",
                    "gate_eligible_categories": ["E"],
                    "gate_eligible_entities": ["乙公司"],
                    "gate_eligible_url_count": 1,
                    "gate_blockers": ["规则恢复可入门的成分公司O/E类别不足2类"],
                }
            )

        rendered = self.render(evidence_transform=mark_recovery)

        self.assertIn("规则恢复可入门O/E：类别E；成分公司主体1/2；独立URL1/2", rendered)
        self.assertIn("成分公司O/E类别不足2类", rendered)

    def test_pass_radar_exposes_market_inputs_and_cleaned_source_errors(self) -> None:
        def mark_pass(evidence):
            evidence["801002"].update(
                {
                    "gate": "PASS",
                    "claims": [
                        {"category": "S", "entity": "乙公司", "evidence_id": "801002-N1"},
                        {"category": "O", "entity": "供应商乙", "evidence_id": "801002-N2"},
                    ],
                }
            )

        def add_breadth_dates(metrics):
            metrics["801002"].update(
                {
                    "relative_20d_previous": 0.005,
                    "relative_20d_two_weeks_ago": 0.0,
                    "relative_improving": True,
                    "turnover_share_previous": 0.02,
                    "turnover_share": 0.03,
                }
            )
            metrics["801002"]["breadth"].update(
                {
                    "endpoints": ["2026-07-17", "2026-07-10", "2026-07-03"],
                    "coverages": [0.80, 0.75, 0.70],
                    "improving": True,
                }
            )

        rendered = self.render(
            evidence_transform=mark_pass,
            metrics_transform=add_breadth_dates,
            radar_codes=["801002"],
            run_quality_update={
                "source_error_total": 4,
                "source_errors": [
                    "接口|失败\n<script>alert(1)</script>",
                    "第二个 [链接](javascript:bad)",
                    "第三个错误",
                    "第四个不应出现",
                ],
                "breadth_stock_requests": 87,
                "breadth_stock_cache_hits": 21,
            },
        )

        self.assertIn(
            "市场核对：20日收益+4.00%；排名第8；相对端点（旧→新）",
            rendered,
        )
        self.assertIn("2026-07-03=+0.00%；2026-07-10=+0.50%；2026-07-17=+1.00%", rendered)
        self.assertIn("相对连续改善：是（相对门通过）", rendered)
        self.assertIn("成交分位55.0%；成交占比（前期→本期）：2.000%→3.000%（成交门通过）", rendered)
        self.assertIn("2026-07-17=70.0%（覆盖80.0%）", rendered)
        self.assertIn("2026-07-10=60.0%（覆盖75.0%）", rendered)
        self.assertIn("2026-07-03=50.0%（覆盖70.0%）", rendered)
        self.assertIn("广度端点（旧→新）", rendered)
        self.assertLess(rendered.index("2026-07-03=50.0%"), rendered.index("2026-07-10=60.0%"))
        self.assertLess(rendered.index("2026-07-10=60.0%"), rendered.index("2026-07-17=70.0%"))
        self.assertIn("广度连续改善：是（广度门通过）", rendered)
        self.assertIn("广度成分股请求 / 缓存命中 | 87 / 21", rendered)
        self.assertIn("数据源错误明细（最多3条，已清洗）", rendered)
        self.assertIn("接口\\|失败 &lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn("第二个 \\[链接\\](javascript:bad)", rendered)
        self.assertIn("第三个错误", rendered)
        self.assertNotIn("第四个不应出现", rendered)
        self.assertNotIn("AI_DRIVER_SENTINEL", rendered)
        self.assertNotIn("AI_SUMMARY_SENTINEL", rendered)

    def test_market_audit_does_not_invent_missing_gate_flags(self) -> None:
        rendered = reporter._market_audit(
            {
                "rank_20d": 3,
                "return_20d": 0.04,
                "relative_20d": 0.01,
                "turnover_percentile": 42.0,
                "breadth": {
                    "available": True,
                    "endpoints": ["2026-07-17", "2026-07-10", "2026-07-03"],
                    "ratios": [0.7, 0.6, 0.5],
                    "coverages": [0.9, 0.9, 0.9],
                },
            }
        )

        self.assertIn("2026-07-17=+1.00%", rendered)
        self.assertIn("相对连续改善：未计算（相对门未计算）", rendered)
        self.assertIn("成交分位42.0%；成交占比（前期→本期）：未计算→未计算（成交门未计算）", rendered)
        self.assertIn("广度连续改善：是（广度门未计算）", rendered)

    def test_market_audit_explains_improving_negative_relative_and_declining_turnover(self) -> None:
        rendered = reporter._market_audit(
            {
                "rank_20d": 9,
                "return_20d": -0.02,
                "relative_20d": -0.01,
                "relative_20d_previous": -0.02,
                "relative_20d_two_weeks_ago": -0.03,
                "relative_improving": True,
                "relative_ok": True,
                "turnover_percentile": 40.0,
                "turnover_share_previous": 0.03,
                "turnover_share": 0.02,
                "turnover_ok": False,
                "breadth_ok": False,
                "breadth": {
                    "available": True,
                    "improving": False,
                    "endpoints": ["2026-07-17", "2026-07-10", "2026-07-03"],
                    "ratios": [0.4, 0.4, 0.4],
                    "coverages": [1.0, 1.0, 1.0],
                },
            }
        )

        self.assertIn("2026-07-03=-3.00%；2026-07-10=-2.00%；2026-07-17=-1.00%", rendered)
        self.assertIn("相对连续改善：是（相对门通过）", rendered)
        self.assertIn("成交分位40.0%；成交占比（前期→本期）：3.000%→2.000%（成交门未通过）", rendered)


if __name__ == "__main__":
    unittest.main()
