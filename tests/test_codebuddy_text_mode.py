from __future__ import annotations

import importlib.util
import subprocess
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from finance_digest.codex import parse_daily_protocol, run_protocol_with_retry
from finance_digest.models import Article


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CodeBuddyTextModeTest(unittest.TestCase):
    def test_sector_hotspots_uses_text_output(self) -> None:
        module = load_script("sector_hotspots")
        completed = subprocess.CompletedProcess([], 0, stdout="MARKET_SUMMARY\t正常", stderr="")
        with mock.patch.object(module.shutil, "which", return_value="/usr/bin/codebuddy"), mock.patch.object(
            module.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(module.call_ai("prompt"), "MARKET_SUMMARY\t正常")
        self.assertEqual(run.call_args.args[0][3], "text")

    def test_index_analysis_uses_text_output(self) -> None:
        module = load_script("index_analysis")
        module.AI_MODEL = "codebuddy"
        module.AI_MODEL_NAME = ""
        completed = subprocess.CompletedProcess([], 0, stdout="MARKET_SUMMARY\t正常", stderr="")
        with mock.patch.object(module.shutil, "which", return_value="/usr/bin/codebuddy"), mock.patch.object(
            module.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(module.call_ai("prompt", expect_json=False), "MARKET_SUMMARY\t正常")
        self.assertEqual(run.call_args.args[0][3], "text")

    def test_stock_pool_uses_text_output_and_nonempty_label(self) -> None:
        module = load_script("stock_pool_news")
        completed = subprocess.CompletedProcess([], 0, stdout="## 1. 测试\n暂无重要新闻", stderr="")
        with mock.patch.object(module.shutil, "which", return_value="/usr/bin/codebuddy"), mock.patch.object(
            module.subprocess, "run", return_value=completed
        ) as run:
            module.call_codebuddy("prompt", "")
        self.assertEqual(run.call_args.args[0][3], "text")
        report = module.render_report("2026-09-20", "", date(2026, 9, 19), "正文")
        self.assertNotIn("生成模式：``", report)


class DailyProtocolToleranceTest(unittest.TestCase):
    def test_markdown_table_record_is_accepted(self) -> None:
        article = Article(
            article_id="a1",
            title="Original title",
            url="https://example.com/a1",
            source="Example",
            published_at=datetime(2026, 9, 19, 12, 0),
            description="Description",
            category="markets",
            source_weight=10,
            topics=["macroeconomics"],
        )
        summary = "这是用于验证协议解析兼容性的中性中文摘要，内容仅来自候选数据，并说明事件影响及仍待确认的信息，确保长度满足六十个字符以上的严格要求。"
        raw = f"```text\n| TOPIC | macroeconomics | T-macroeconomics-1 | 中文测试标题 | {summary} |\n```"
        result = parse_daily_protocol(
            raw,
            date(2026, 9, 19),
            {"T-macroeconomics-1": ("topic", "macroeconomics", article)},
        )
        self.assertEqual(result["topics"][0]["items"][0]["title_zh"], "中文测试标题")

    def test_retry_includes_rejected_output_as_diagnostic(self) -> None:
        prompts: list[str] = []

        def fake_run(_root, prompt, _bin, _timeout, _model):
            prompts.append(prompt)
            return "散文回答" if len(prompts) == 1 else "OK\tvalue"

        def parser(raw: str):
            if not raw.startswith("OK\t"):
                raise ValueError("bad protocol")
            return {"ok": True}

        with mock.patch("finance_digest.codex.run_agent_text", side_effect=fake_run):
            result = run_protocol_with_retry(ROOT, "PROMPT", "codebuddy", 10, parser, "test")
        self.assertEqual(result, {"ok": True})
        self.assertIn("<rejected_output>\n散文回答", prompts[1])


if __name__ == "__main__":
    unittest.main()
