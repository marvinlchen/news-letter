"""Independent iFinD CLI boundary and authenticated stream-evidence tests."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

try:
    import announcement_ifind as data
except ModuleNotFoundError:
    data = None


TOOL = "mcp__ifind__search_notice"
OFFICIAL_URL = "https://api-mcp.51ifind.com:8643/ds-mcp-servers/hexin-ifind-ds-mcp"


def use(identifier="call-1", tool=TOOL, arguments=None):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": identifier, "name": tool, "input": arguments or {"query": "重大公告"}}
    ]}}


def result(identifier="call-1", content=None, error=False):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": identifier, "is_error": error,
         "content": [{"type": "text", "text": json.dumps({"code": 1, "data": ["原始返回"]}, ensure_ascii=False)}] if content is None else content}
    ]}}


def final(text='{"items":[]}', error=False):
    return {"type": "result", "is_error": error, "result": text}


def stream(*events):
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n"


def nested_ifind_content(code=1):
    """The JSON/text/list nesting observed in the real CodeBuddy MCP smoke."""
    application = {"code": code, "msg": "success" if code == 1 else "denied",
                   "data": {"answer": "|证券代码|日期|收盘价|\\n|000001.SZ|20261016|11.5|"}}
    inner = [{"type": "text", "text": json.dumps(application, ensure_ascii=False)}]
    return [{"type": "text", "text": json.dumps(inner, ensure_ascii=False)}]


class IfindBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(data, "iFinD CLI and stream helpers have not been implemented")
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).parent, prefix="ifind-test-")
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "ifind.json"

    def config(self, servers=None, mode=0o600):
        config = {"mcpServers": servers if servers is not None else {"ifind": {
            "type": "http", "url": OFFICIAL_URL,
            "headers": {"Authorization": "test-secret-token-never-put-in-argv"}, "alwaysLoad": True}}}
        self.path.write_text(json.dumps(config), encoding="utf-8")
        self.path.chmod(mode)
        return self.path

    def test_private_config_returns_only_scoped_flags_and_no_token(self):
        flags = data.ifind_cli_options(self.config())
        self.assertEqual(flags[:5], ["--mcp-config", str(self.path), "--strict-mcp-config", "--permission-mode", "dontAsk"])
        allowed = flags[flags.index("--allowedTools") + 1].split()
        self.assertEqual(set(allowed), {"mcp__ifind__get_security_indicators", "mcp__ifind__search_notice", "mcp__ifind__search_news", "WaitForMcpServers"})
        self.assertEqual(json.loads(flags[flags.index("--settings") + 1]), {"enabledMcpjsonServers": ["ifind"]})
        self.assertNotIn("test-secret-token", " ".join(flags))
        self.assertNotIn("Authorization", " ".join(flags))
        self.assertNotIn("alwaysLoad", " ".join(flags))
        self.assertTrue(data.ifind_cli_options(self.config(mode=0o400)))

    def test_config_rejects_loose_permissions_other_servers_or_nonofficial_host(self):
        with self.assertRaises(ValueError):
            data.ifind_cli_options(self.config(mode=0o644))
        for servers in ({}, {"ifind": {"type": "stdio", "command": "bad"}},
                        {"ifind": {"type": "http", "url": "https://api-mcp.51ifind.com.attacker.invalid/mcp"}},
                        {"ifind": {"type": "http", "url": "https://api-mcp.51ifind.com/mcp"}, "other": {}},
                        {"ifind": {"type": "http", "url": "http://api-mcp.51ifind.com/mcp"}},
                        {"ifind": {"type": "http", "url": "https://token@api-mcp.51ifind.com/mcp"}},
                        {"ifind": {"type": "http", "url": "https://api-mcp.51ifind.com/mcp?token=secret"}}):
            with self.subTest(servers=servers), self.assertRaises(ValueError):
                data.ifind_cli_options(self.config(servers))

    def test_notice_only_cli_grants_no_indicators_or_news_permission(self):
        flags = data.ifind_cli_options(self.config(), notice_only=True)
        self.assertEqual(set(flags[flags.index("--allowedTools") + 1].split()),
                         {"mcp__ifind__search_notice", "WaitForMcpServers"})

    def test_success_requires_real_matching_tool_result_and_keeps_hashed_content(self):
        events = [use(arguments={"query": "公司", "date": "2026-10-16"}), result(), final()]
        events[1]["headers"] = {"Authorization": "not-evidence"}
        text, evidence = data.parse_ifind_stream(stream(*events))
        self.assertEqual(text, '{"items":[]}')
        self.assertEqual(len(evidence), 1)
        row = evidence[0]
        self.assertTrue(row["success"])
        self.assertEqual(row["call_id"], "call-1")
        self.assertEqual(row["tool"], TOOL)
        self.assertEqual(row["arguments"]["date"], "2026-10-16")
        self.assertEqual(row["content"], events[1]["message"]["content"][0]["content"])
        canonical = json.dumps(row["content"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(row["sha256"], hashlib.sha256(canonical.encode()).hexdigest())
        self.assertNotIn("Authorization", json.dumps(evidence))

    def test_application_failure_is_recorded_but_cannot_count_as_success(self):
        failure = [{"type": "text", "text": '{"code":0,"msg":"quota failed"}'}]
        with self.assertRaises(ValueError):
            data.parse_ifind_stream(stream(use(), result(content=failure), final()))
        text, evidence = data.parse_ifind_stream(stream(use(), result(content=failure), use("call-2", "mcp__ifind__search_news"), result("call-2"), final()))
        self.assertEqual([row["success"] for row in evidence], [False, True])
        self.assertIn("code", evidence[0]["error"])

    def test_real_nested_application_wrapper_accepts_one_and_rejects_zero(self):
        text, evidence = data.parse_ifind_stream(stream(use(), result(content=nested_ifind_content(1)), final()))
        self.assertTrue(evidence[0]["success"])
        with self.assertRaises(ValueError):
            data.parse_ifind_stream(stream(use(), result(content=nested_ifind_content(0)), final()))
        _, evidence = data.parse_ifind_stream(stream(use(), result(content=nested_ifind_content(0)),
                use("call-2"), result("call-2", content=nested_ifind_content(1)), final()))
        self.assertEqual([row["success"] for row in evidence], [False, True])
        self.assertIn("code", evidence[0]["error"])

    def test_unrecognizable_or_over_nested_application_response_cannot_succeed(self):
        content = {"code": 1}
        for _ in range(20):
            content = [content]
        for index, invalid in enumerate(["Permission denied", [{"type": "text", "text": "unauthorized"}],
                        [{"type": "text", "text": '{"message":"permission denied"}'}], content]):
            with self.subTest(case=index), self.assertRaises(ValueError):
                data.parse_ifind_stream(stream(use(), result(content=invalid), final()))

    def test_actual_redacted_smoke_wrapper_detects_mutated_inner_failure(self):
        path = Path(__file__).resolve().parent.parent / "ifind-integration/codebuddy-smoke-redacted.txt"
        if not path.exists():
            self.skipTest("redacted real smoke fixture is local-only")
        raw = path.read_text(encoding="utf-8").split("\nSTDERR\n", 1)[0]
        _, evidence = data.parse_ifind_stream(raw)
        self.assertTrue(any(row["success"] and row["is_ifind"] for row in evidence))
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        for event in events:
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    outer = block["content"][0]
                    inner = json.loads(outer["text"])
                    application = json.loads(inner[0]["text"])
                    application["code"] = 0
                    inner[0]["text"] = json.dumps(application, ensure_ascii=False)
                    outer["text"] = json.dumps(inner, ensure_ascii=False)
        with self.assertRaises(ValueError):
            data.parse_ifind_stream(stream(*events))

    def test_connection_wait_is_paired_saved_and_separate_from_ifind_evidence(self):
        raw = stream(use("wait-1", "WaitForMcpServers", {"servers": ["ifind"]}),
                     result("wait-1", content="ifind connected"), use(), result(), final())
        text, evidence = data.parse_ifind_stream(raw)
        self.assertEqual(text, '{"items":[]}')
        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0]["tool"], "WaitForMcpServers")
        self.assertTrue(evidence[0]["success"])
        self.assertFalse(evidence[0]["is_ifind"])
        self.assertTrue(evidence[1]["is_ifind"])
        self.assertEqual(sum(row["success"] and row["is_ifind"] for row in evidence), 1)

    def test_connection_wait_success_alone_cannot_authenticate_ifind_use(self):
        raw = stream(use("wait-1", "WaitForMcpServers", {"servers": ["ifind"]}),
                     result("wait-1", content="ifind connected"), final())
        with self.assertRaisesRegex(ValueError, "没有成功.*iFinD"):
            data.parse_ifind_stream(raw)

    def test_unpaired_connection_wait_rejects_otherwise_successful_ifind_run(self):
        raw = stream(use("wait-1", "WaitForMcpServers", {"servers": ["ifind"]}),
                     use(), result(), final())
        with self.assertRaisesRegex(ValueError, "缺少配对"):
            data.parse_ifind_stream(raw)

    def test_connection_wait_does_not_allow_other_discovery_or_execution_tools(self):
        for tool in ("SearchTools", "ListMcpResources", "Bash", "Read"):
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                data.parse_ifind_stream(stream(use(tool=tool), result(), final()))

    def test_errors_empty_and_unpaired_results_never_authenticate_model_claim(self):
        streams = [stream(final('{"ifind_used":true}')),
                   stream(use(), result(error=True), final()),
                   stream(use(), result(content=[]), final()),
                   stream(use(), result("other-id"), final()),
                   stream(use(), final()),
                   stream(use(tool="mcp__other__search_news"), result(), final())]
        for raw in streams:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                data.parse_ifind_stream(raw)

    def test_truncation_bad_json_and_final_errors_reject_even_successful_tool(self):
        base = stream(use(), result())
        for raw in [base, base+'{"type":', base+'not json\n', base+stream(final(error=True)),
                    base+stream({"type": "result", "result": '{"items":[]}'}), base+stream(final(""))]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                data.parse_ifind_stream(raw)

    def test_duplicate_call_ids_cannot_replace_earlier_evidence(self):
        with self.assertRaises(ValueError):
            data.parse_ifind_stream(stream(use(), result(), use(), result(), final()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
