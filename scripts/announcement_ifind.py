"""Private iFinD CLI configuration and verifiable CodeBuddy MCP evidence.

Transport credentials remain in the private MCP config. Only matched framework
tool-result events, never the model's source claims, authenticate iFinD use.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat


IFIND_TOOLS = (
    "mcp__ifind__get_security_indicators",
    "mcp__ifind__search_notice",
    "mcp__ifind__search_news",
)
ALLOWED_TOOLS = IFIND_TOOLS + ("WaitForMcpServers",)
OFFICIAL_URL = "https://api-mcp.51ifind.com:8643/ds-mcp-servers/hexin-ifind-ds-mcp"


def ifind_cli_options(config_path, notice_only=False):
    """Validate the private single-server JSON and return credential-free argv."""
    path = Path(config_path)
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) not in {0o600, 0o400}:
            raise ValueError("iFinD MCP配置必须为0600或0400的普通JSON文件")
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("无法读取有效的私有iFinD MCP JSON配置") from None
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    if not isinstance(servers, dict) or set(servers) != {"ifind"}:
        raise ValueError("MCP配置必须且只能包含ifind服务器")
    server = servers["ifind"]
    if not isinstance(server, dict) or server.get("type") != "http":
        raise ValueError("ifind必须使用HTTP MCP传输")
    if server.get("url") != OFFICIAL_URL:
        raise ValueError("ifind仅允许官方统一HTTPS endpoint api-mcp.51ifind.com")
    allowed = ("mcp__ifind__search_notice", "WaitForMcpServers") if notice_only else ALLOWED_TOOLS
    return ["--mcp-config", str(path), "--strict-mcp-config", "--permission-mode", "dontAsk",
            "--allowedTools", " ".join(allowed),
            "--settings", json.dumps({"enabledMcpjsonServers": ["ifind"]}, separators=(",", ":"))]


def _nonempty(content):
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(_nonempty(block.get("text")) if isinstance(block, dict) and block.get("type") == "text"
                   else bool(block) for block in content)
    return bool(content)


def _application_error(content):
    """Unwrap bounded JSON/list/text layers and require application code=1.

    An iFinD response envelope is terminal: its financial data is not another
    transport wrapper, and a security-code column must not become a status code.
    """
    pending = [(content, 0)]
    found_code = False
    while pending:
        value, depth = pending.pop()
        if depth > 12:
            return "iFinD application payload exceeds decoding depth"
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                continue
            pending.append((decoded, depth + 1))
            continue
        if isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
            continue
        if not isinstance(value, dict):
            continue
        if "code" in value:
            found_code = True
            code = value["code"]
            if isinstance(code, bool) or code not in (1, "1"):
                return "iFinD application code is not 1"
        elif value.get("type") == "text":
            pending.append((value.get("text"), depth + 1))
        elif "content" in value:
            pending.append((value["content"], depth + 1))
    return "" if found_code else "iFinD application code=1 is not recognizable"


def parse_ifind_stream(raw):
    """Return (final result text, matched evidence), rejecting incomplete runs.

    Both successful and failed completed calls, including connection waits, are
    kept with success and is_ifind flags. At least one genuine iFinD success is
    required; a successful wait alone is insufficient. SHA256 covers canonical
    JSON of raw tool-result content; stream-level headers are never copied.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("CodeBuddy MCP stream不是UTF-8") from None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("CodeBuddy MCP stream为空")
    calls, completed, evidence = {}, set(), []
    final_text = None
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"CodeBuddy MCP stream第{number}行JSON损坏或截断") from None
        if not isinstance(event, dict):
            raise ValueError("CodeBuddy MCP stream事件必须为JSON对象")
        kind = event.get("type")
        if kind == "result":
            if final_text is not None or event.get("is_error") is not False:
                raise ValueError("CodeBuddy缺少明确成功的唯一最终result")
            text = event.get("result")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("CodeBuddy最终result为空")
            final_text = text
            continue
        if kind not in {"assistant", "user"}:
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type not in {"tool_use", "tool_result"}:
                continue
            if final_text is not None:
                raise ValueError("CodeBuddy最终result后仍有工具活动")
            if block_type == "tool_use":
                if kind != "assistant":
                    raise ValueError("工具调用不是assistant事件")
                identifier, tool, arguments = block.get("id"), block.get("name"), block.get("input")
                if tool not in ALLOWED_TOOLS:
                    raise ValueError("CodeBuddy调用了未授权的iFinD工具")
                if not isinstance(identifier, str) or not identifier or identifier in calls:
                    raise ValueError("工具call ID缺失或重复")
                if not isinstance(arguments, dict):
                    raise ValueError("工具实参必须为JSON对象")
                calls[identifier] = {"call_id": identifier, "tool": tool, "arguments": arguments}
                continue
            if kind != "user":
                raise ValueError("工具响应不是user事件")
            identifier = block.get("tool_use_id")
            if identifier not in calls or identifier in completed:
                raise ValueError("工具响应没有匹配的唯一call ID")
            completed.add(identifier)
            raw_content = block.get("content")
            is_ifind = calls[identifier]["tool"] in IFIND_TOOLS
            error = ("MCP tool_result is_error" if block.get("is_error") else
                     "MCP tool_result content is empty" if not _nonempty(raw_content) else
                     _application_error(raw_content) if is_ifind else "")
            canonical = json.dumps(raw_content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            evidence.append({**calls[identifier], "content": raw_content,
                             "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                             "success": not bool(error), "is_ifind": is_ifind, "error": error})
    if final_text is None:
        raise ValueError("CodeBuddy缺少最终result，stream可能被截断")
    if set(calls) != completed:
        raise ValueError("iFinD工具调用缺少配对响应")
    if not any(row["success"] and row["is_ifind"] for row in evidence):
        raise ValueError("CodeBuddy没有成功的可核验iFinD工具响应")
    return final_text, evidence
