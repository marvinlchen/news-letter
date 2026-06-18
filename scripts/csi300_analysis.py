#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
沪深300涨跌分析脚本 - 完整版
支持获取：当日涨跌幅、本周涨幅、年初至今涨幅
自动生成分析报告并发布到GitHub
"""

import os
import sys
import json
import time
import subprocess
import re
import random
import argparse
import tempfile
import shutil
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# ── 配置 ────────────────────────────────────────────────────────────────────────

AI_MODEL = os.environ.get("CSI300_AI_MODEL", "codebuddy")   # "codex" or "codebuddy"
EASTMONEY_PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_PUSH2_FALLBACK = "https://push2delay.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
CSI300_BOARD_FS = "b:BK0500"
HISTORICAL_RANK_CACHE = {}
PUSH2_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json,text/plain,*/*",
}
AI_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["gainers_analysis", "losers_analysis", "market_summary"],
    "properties": {
        "gainers_analysis": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "stocks"],
            "properties": {
                "summary": {"type": "string"},
                "stocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["code", "name", "reason", "evidence"],
                        "properties": {
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "reason": {"type": "string"},
                            "evidence": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["title", "url", "pub_date"],
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                        "pub_date": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "losers_analysis": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "stocks"],
            "properties": {
                "summary": {"type": "string"},
                "stocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["code", "name", "reason", "evidence"],
                        "properties": {
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "reason": {"type": "string"},
                            "evidence": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["title", "url", "pub_date"],
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                        "pub_date": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "market_summary": {"type": "string"},
    },
}

# ── 工具函数 ─────────────────────────────────────────────────────────────────────

def preprocess_json(s):
    """保留 AI 返回内容原样，避免破坏 JSON 字符串中的中文引号。"""
    return s.strip()


def extract_json_response(text):
    """Return a JSON object string, tolerating code fences and surrounding chatter."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        json.loads(clean)
        return clean
    except json.JSONDecodeError:
        pass

    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        return clean[start:end + 1]
    return clean


def call_ai(prompt, max_tokens=4096, expect_json=True):
    """调用 AI 模型（codex 或 codebuddy）"""
    if AI_MODEL == "codex":
        output_path = None
        schema_path = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
                output_path = tmp.name
            if expect_json:
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as schema_file:
                    json.dump(AI_RESPONSE_SCHEMA, schema_file, ensure_ascii=False)
                    schema_path = schema_file.name
            cmd = [
                "codex", "exec",
                "--skip-git-repo-check",
                "--output-last-message", output_path,
            ]
            if schema_path:
                cmd.extend(["--output-schema", schema_path])
            cmd.append(prompt)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout).strip())
            text = Path(output_path).read_text(encoding="utf-8").strip()
            if not text:
                text = result.stdout.strip()
            return extract_json_response(text) if expect_json else text
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
            if schema_path:
                try:
                    os.unlink(schema_path)
                except OSError:
                    pass
    else:
        codebuddy_executable = shutil.which("codebuddy")
        if codebuddy_executable:
            cmd = [codebuddy_executable, "-p", "--output-format", "json", prompt]
        else:
            cmd = None

        # 尝试多个可能的 codebuddy JS 路径
        codebuddy_paths = [
            "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy",
            "/usr/local/bin/codebuddy",
            "/home/ME/.local/bin/codebuddy",
        ]
        if cmd is None:
            for cb_path in codebuddy_paths:
                try:
                    # 测试路径是否存在（使用 node 的完整路径）
                    node_path = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/bin/node"
                    test_cmd = [node_path, cb_path, "--version"]
                    test_result = subprocess.run(test_cmd, capture_output=True, timeout=5)
                    if test_result.returncode != 0:
                        continue
                    # 如果成功，使用 node 直接运行 codebuddy
                    cmd = [node_path, cb_path, "-p", "--output-format", "json", prompt]
                    break
                except Exception:
                    continue
        
        if cmd is None:
            # 如果都找不到，使用默认命令（会失败并抛出错误）
            cmd = ["codebuddy", "-p", "--output-format", "json", prompt]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip())
        text = result.stdout.strip()
        
        # 尝试解析 codebuddy 的输出格式
        # 格式1：纯 JSON 字符串（AI 的直接响应）
        # 格式2：JSON 数组（对话历史）
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                # 是对话历史数组，找到最后一个 assistant 消息
                for msg in reversed(parsed):
                    if isinstance(msg, dict):
                        role = msg.get("role", "")
                        if role == "assistant":
                            content = msg.get("content", "")
                            if isinstance(content, list):
                                # content 是数组，提取 text
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") in ("text", "output_text"):
                                        text = item.get("text", "")
                                        break
                            elif isinstance(content, str):
                                text = content
                            break
                # 现在 text 应该是纯文本 JSON
        except json.JSONDecodeError:
            # 不是 JSON 数组，假设是纯文本
            pass
        
        return extract_json_response(text) if expect_json else text


def get_trading_dates(count=1, include_today=False):
    """获取最近的交易日（简单版：跳过周末）"""
    dates = []
    d = datetime.now()
    if not include_today:
        d -= timedelta(days=1)
    while len(dates) < count:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return dates


# ── 数据获取 ─────────────────────────────────────────────────────────────────────

def get_stock_history(stock_code, market="0", target_date="2026-06-14", max_retries=3):
    """
    获取股票历史K线数据，过滤到目标日期
    返回: list[dict] 包含 date, open, close, high, low, volume, amount
    使用新浪财经API
    """
    # 新浪财经 API
    sina_market = "sh" if market == "1" else "sz"
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_market}{stock_code}&scale=240&ma=no&datalen=1023"
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data or not isinstance(data, list):
                    if attempt < max_retries - 1:
                        time.sleep(2 * (attempt + 1))
                        continue
                    return None
                
                result = []
                for item in data:
                    date_str = item.get("day", "")
                    # 只保留目标日期之前的数据
                    if date_str > target_date:
                        continue
                    result.append({
                        "date": date_str,
                        "open": float(item.get("open", 0)),
                        "close": float(item.get("close", 0)),
                        "high": float(item.get("high", 0)),
                        "low": float(item.get("low", 0)),
                        "volume": int(float(item.get("volume", 0))),
                        "amount": float(item.get("amount", 0)),
                    })
                
                if result:
                    return result
                else:
                    return None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))  # 指数退避
                continue
            return None
    return None


def calc_extended_changes(stock_code, stock_name, target_date="2026-06-14"):
    """
    计算股票的本周涨幅和年初至今涨幅
    返回: (week_change_pct, ytd_change_pct)
    """
    # 判断市场
    market = "1" if stock_code.startswith(("6", "5", "9")) else "0"
    
    history = get_stock_history(stock_code, market, target_date)
    if not history or len(history) < 5:
        return None, None
    
    # 当前价格（目标日期前最近一个交易日收盘价）
    current_data = history[-1]
    current_price = current_data["close"]
    current_date = current_data["date"]
    
    # 本周涨幅：找到本周第一个交易日（周一）或上周五的收盘价
    week_change_pct = None
    current_dt = datetime.strptime(current_date, "%Y-%m-%d")
    
    # 找本周一或上周五
    for i in range(len(history)-2, -1, -1):
        d = datetime.strptime(history[i]["date"], "%Y-%m-%d")
        # 如果是周一，或者当前是周一且找到上周五
        if d.weekday() == 0:  # 周一
            week_start_price = history[i]["close"]
            week_change_pct = (current_price - week_start_price) / week_start_price * 100
            break
        elif d.weekday() == 4 and (len(history) - i) <= 3:  # 上周五且距离很近
            week_start_price = history[i]["close"]
            week_change_pct = (current_price - week_start_price) / week_start_price * 100
            break
    
    # 如果没找到周一，用5天前
    if week_change_pct is None and len(history) >= 6:
        week_start_price = history[-6]["close"]
        week_change_pct = (current_price - week_start_price) / week_start_price * 100
    
    # 年初至今涨幅
    ytd_change_pct = None
    for i in range(len(history)-1, -1, -1):
        d = datetime.strptime(history[i]["date"], "%Y-%m-%d")
        if d.year < current_dt.year or (d.year == current_dt.year and d.month == 1 and d.day <= 10):
            ytd_start_price = history[i]["close"]
            ytd_change_pct = (current_price - ytd_start_price) / ytd_start_price * 100
            break
    
    return week_change_pct, ytd_change_pct


def fetch_csi300_constituents(max_retries=3):
    """获取当前沪深300成分股代码和名称。"""
    page_size = 100
    page = 1
    total = None
    result = []
    seen = set()

    while total is None or len(result) < total:
        query = (
            f"pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2&fid=f3&"
            f"fs={CSI300_BOARD_FS}&"
            f"fields=f12,f14"
        )
        page_data = None
        for attempt in range(max_retries):
            last_error = None
            try:
                for endpoint in (EASTMONEY_PUSH2, EASTMONEY_PUSH2_FALLBACK):
                    try:
                        req = urllib.request.Request(f"{endpoint}?{query}", headers=PUSH2_HEADERS)
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            page_data = json.loads(resp.read().decode("utf-8"))
                        break
                    except Exception as e:
                        last_error = e
                if page_data is None:
                    raise last_error
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)
                    print(f"[WARN] 获取沪深300成分股第 {page} 页失败（尝试 {attempt+1}/{max_retries}）: {e}，{wait_time}秒后重试...", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    print(f"[WARN] 获取沪深300成分股第 {page} 页失败: {e}", file=sys.stderr)
                    return result

        data = page_data.get("data") or {}
        total = data.get("total") or total or 0
        raw = data.get("diff", [])
        if not raw:
            break
        for item in raw:
            code = item.get("f12", "")
            if code and code not in seen:
                seen.add(code)
                result.append({"code": code, "name": item.get("f14", "")})
        page += 1

    return result[:total] if total else result


def calc_daily_change(stock_code, stock_name, target_date):
    """根据历史 K 线计算指定日期的单日涨跌幅。"""
    market = "1" if stock_code.startswith(("6", "5", "9")) else "0"
    history = get_stock_history(stock_code, market, target_date)
    if not history or len(history) < 2:
        return None

    idx = None
    for i in range(len(history) - 1, -1, -1):
        if history[i]["date"] == target_date:
            idx = i
            break
    if idx is None or idx == 0:
        return None

    current = history[idx]
    previous = history[idx - 1]
    prev_close = previous.get("close")
    close = current.get("close")
    if not prev_close or not close:
        return None
    return {
        "code": stock_code,
        "name": stock_name,
        "price": close,
        "change_pct": (close - prev_close) / prev_close * 100,
        "week_change": None,
        "ytd_change": None,
    }


def fetch_csi300_historical_rank(date_str, top_n=20, ascending=False):
    """按指定历史交易日重算沪深300涨跌幅排行。"""
    if date_str in HISTORICAL_RANK_CACHE:
        ranked = list(HISTORICAL_RANK_CACHE[date_str])
        ranked.sort(key=lambda x: x.get("change_pct", 0), reverse=not ascending)
        return ranked[:top_n]

    constituents = fetch_csi300_constituents()
    ranked = []
    print(f"[INFO] 计算 {len(constituents)} 只沪深300成分股的 {date_str} 历史涨跌幅...", file=sys.stderr)
    for i, stock in enumerate(constituents, 1):
        if i % 25 == 0 or i == 1:
            print(f"  [rank {i}/{len(constituents)}]", file=sys.stderr)
        item = calc_daily_change(stock["code"], stock["name"], date_str)
        if item is not None:
            ranked.append(item)
        time.sleep(0.05)
    HISTORICAL_RANK_CACHE[date_str] = list(ranked)
    ranked.sort(key=lambda x: x.get("change_pct", 0), reverse=not ascending)
    return ranked[:top_n]


def fetch_csi300_live_rank(top_n=20, ascending=False, max_retries=3):
    """
    获取沪深300成分股实时涨跌幅排行。
    返回 list[dict]，包含：code, name, price, change_pct,
                      week_change（本周涨幅）, ytd_change（年初至今涨幅）
    """
    order = "0" if ascending else "1"
    query = (
        f"pn=1&pz={top_n}&po={order}&np=1&fltt=2&invt=2&fid=f3&"
        f"fs={CSI300_BOARD_FS}&"
        f"fields=f12,f14,f2,f3"
    )
    
    for attempt in range(max_retries):
        last_error = None
        try:
            for endpoint in (EASTMONEY_PUSH2, EASTMONEY_PUSH2_FALLBACK):
                try:
                    req = urllib.request.Request(f"{endpoint}?{query}", headers=PUSH2_HEADERS)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    raw = data.get("data", {}).get("diff", [])
                    if ascending:
                        raw = sorted(raw, key=lambda x: x.get("f3", 0))
                    else:
                        raw = sorted(raw, key=lambda x: x.get("f3", 0), reverse=True)
                    result = []
                    for item in raw[:top_n]:
                        result.append({
                            "code":        item.get("f12", ""),
                            "name":        item.get("f14", ""),
                            "price":       item.get("f2",  None),
                            "change_pct":  item.get("f3",  None),
                            "week_change": None,  # 稍后计算
                            "ytd_change":  None,  # 稍后计算
                        })
                    return result
                except Exception as e:
                    last_error = e
            raise last_error
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)
                print(f"[WARN] 获取沪深300排行失败（尝试 {attempt+1}/{max_retries}）: {e}，{wait_time}秒后重试...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"[WARN] 获取沪深300排行失败: {e}", file=sys.stderr)
                return []
    return []


def get_csi300_top_gainers(date_str, top_n=20, max_retries=3):
    """获取沪深300成分股中涨幅最大的 top_n 只股票。"""
    if date_str == datetime.now().strftime("%Y-%m-%d"):
        return fetch_csi300_live_rank(top_n=top_n, ascending=False, max_retries=max_retries)
    return fetch_csi300_historical_rank(date_str, top_n=top_n, ascending=False)


def get_csi300_top_losers(date_str, top_n=20, max_retries=3):
    """获取沪深300成分股中跌幅最大的 top_n 只股票。"""
    if date_str == datetime.now().strftime("%Y-%m-%d"):
        return fetch_csi300_live_rank(top_n=top_n, ascending=True, max_retries=max_retries)
    return fetch_csi300_historical_rank(date_str, top_n=top_n, ascending=True)


def enrich_with_extended_changes(stocks, target_date, max_workers=5):
    """
    为股票列表添加本周涨幅和年初至今涨幅数据
    使用串行处理（避免API限制）
    """
    print(f"[INFO] 开始获取扩展数据（本周涨幅、年初至今涨幅）...", file=sys.stderr)
    
    for i, stock in enumerate(stocks):
        code = stock["code"]
        name = stock["name"]
        print(f"  [{i+1}/{len(stocks)}] {code} {name}", file=sys.stderr)
        
        week, ytd = calc_extended_changes(code, name, target_date)
        stock["week_change"] = week
        stock["ytd_change"] = ytd
        
        time.sleep(0.8)  # 避免请求过快
    
    print(f"[INFO] 扩展数据获取完成", file=sys.stderr)
    return stocks


def search_stock_news(stock_name, stock_code, limit=5):
    """通过 Google News RSS 搜索个股相关新闻，并提取发布时间"""
    query = urllib.parse.quote(f"{stock_name} {stock_code} 沪深300")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
            items = re.split(r"<item>", xml)[1:]
            news_list = []
            for item in items[:limit]:
                t = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
                l = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
                d = re.search(r"<pubDate>(.*?)</pubDate>", item, re.DOTALL)
                if t and l:
                    title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t.group(1)).strip()
                    link  = l.group(1).strip()
                    pub_date = d.group(1).strip() if d else ""
                    # 格式化时间：RFC 822 → YYYY-MM-DD HH:MM
                    if pub_date:
                        try:
                            dt = parsedate_to_datetime(pub_date)
                            pub_date = dt.strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            pass
                    news_list.append({"title": title, "link": link, "pub_date": pub_date})
            return news_list
    except Exception as e:
        print(f"[WARN] 搜索新闻失败 ({stock_name}): {e}", file=sys.stderr)
        return []


def attach_news_candidates(stocks, limit=3):
    """为股票列表附加 Google News RSS 候选证据，供 AI 选择和归因。"""
    for i, stock in enumerate(stocks, 1):
        print(f"  [news {i}/{len(stocks)}] {stock['code']} {stock['name']}", file=sys.stderr)
        stock["news"] = search_stock_news(stock["name"], stock["code"], limit=limit)
        time.sleep(0.2)
    return stocks


# ── Prompt 构建 ──────────────────────────────────────────────────────────────────

def build_prompt(date_str, gainers, losers):
    """
    构建发送给 AI 的 prompt。
    包含：当日涨跌幅、本周涨幅、年初至今涨幅。
    """
    top_n = max(len(gainers), len(losers))
    lines = [
        "# 任务",
        f"你是专业财经分析师。请分析 {date_str} 沪深300指数成分股涨跌幅 Top {top_n}。",
        "只能基于下方行情数据和新闻候选做归因；证据链接必须从新闻候选中选取，不要编造链接。",
        "最终只输出一个 JSON 对象，不要输出 Markdown 代码块或额外说明。",
        "",
        "## 数据",
        "",
        f"### Top {len(gainers)} 涨幅股",
    ]

    for i, st in enumerate(gainers, 1):
        chg = f"{st['change_pct']:+.2f}%" if st.get("change_pct") is not None else "（暂无）"
        week = f"{st['week_change']:+.2f}%" if st.get("week_change") is not None else "（暂无）"
        ytd  = f"{st['ytd_change']:+.2f}%" if st.get("ytd_change") is not None else "（暂无）"
        lines += [
            f"**{i}. {st['name']}（{st['code']}）**",
            f"- 当日涨跌幅：{chg}",
            f"- 本周涨幅：{week}",
            f"- 年初至今涨幅：{ytd}",
            "- 新闻候选：",
        ]
        for news in st.get("news", []):
            lines.append(f"  - {news.get('title')} | {news.get('link')} | {news.get('pub_date')}")
        if not st.get("news"):
            lines.append("  - （暂无候选新闻）")
        lines.append("")

    lines += [
        "",
        f"### Top {len(losers)} 跌幅股",
    ]

    for i, st in enumerate(losers, 1):
        chg  = f"{st['change_pct']:+.2f}%" if st.get("change_pct") is not None else "（暂无）"
        week = f"{st['week_change']:+.2f}%" if st.get("week_change") is not None else "（暂无）"
        ytd  = f"{st['ytd_change']:+.2f}%" if st.get("ytd_change") is not None else "（暂无）"
        lines += [
            f"**{i}. {st['name']}（{st['code']}）**",
            f"- 当日涨跌幅：{chg}",
            f"- 本周涨幅：{week}",
            f"- 年初至今涨幅：{ytd}",
            "- 新闻候选：",
        ]
        for news in st.get("news", []):
            lines.append(f"  - {news.get('title')} | {news.get('link')} | {news.get('pub_date')}")
        if not st.get("news"):
            lines.append("  - （暂无候选新闻）")
        lines.append("")

    lines += [
        "",
        "## 要求",
        "1. market_summary 写成一段指数概况，概括板块分化、资金主线和核心驱动力。",
        "2. gainers_analysis.summary 和 losers_analysis.summary 分别总结板块共性。",
        "3. 每只股票给出一句直接原因。原因要结合行业、公司事件、资金风格或基本面，不要泛泛而谈。",
        "4. evidence 最多 2 条，只能使用该股票新闻候选里的标题、链接和发布时间；没有合适证据时返回空数组。",
        "",
        "## 输出 JSON Schema",
        "{",
        f'  "gainers_analysis": {{',
        f'    "summary": "涨幅板总结",',
        f'    "stocks": [{{"code": "000001", "name": "平安银行", "reason": "…", "evidence": [{{"title": "…", "url": "…", "pub_date": "YYYY-MM-DD HH:MM"}}]}}]',
        f'  }},',
        f'  "losers_analysis": {{',
        f'    "summary": "跌幅板总结",',
        f'    "stocks": [{{"code": "000002", "name": "万科A", "reason": "…", "evidence": [{{"title": "…", "url": "…", "pub_date": "YYYY-MM-DD HH:MM"}}]}}]',
        f'  }},',
        f'  "market_summary": "当日市场主线总结"',
        "}",
    ]

    return "\n".join(lines)


# ── 报告生成 ─────────────────────────────────────────────────────────────────────

def format_report(result, target_date, gainers=None, losers=None):
    """
    生成报告 Markdown。
    如果传入 gainers/losers，则从原始数据获取涨跌幅百分比和扩展数据。
    """
    top_n = max(len(gainers or []), len(losers or []))

    change_map = {}
    week_map = {}
    ytd_map = {}
    news_map = {}
    if gainers:
        for s in gainers:
            change_map[s["code"]] = s["change_pct"]
            week_map[s["code"]] = s.get("week_change")
            ytd_map[s["code"]] = s.get("ytd_change")
            news_map[s["code"]] = s.get("news", [])
    if losers:
        for s in losers:
            change_map[s["code"]] = s["change_pct"]
            week_map[s["code"]] = s.get("week_change")
            ytd_map[s["code"]] = s.get("ytd_change")
            news_map[s["code"]] = s.get("news", [])

    def fmt_pct(value):
        return f"{value:+.2f}%" if value is not None else "（暂无）"

    def analysis_by_code(section):
        return {
            item.get("code", ""): item
            for item in result.get(section, {}).get("stocks", [])
        }

    def append_stock_details(lines, stocks, section):
        ai_items = analysis_by_code(section)
        for stock in stocks or []:
            code = stock.get("code", "")
            name = stock.get("name", "")
            item = ai_items.get(code, {})
            evidence = item.get("evidence") or []
            if not evidence:
                evidence = [
                    {"title": news.get("title"), "url": news.get("link"), "pub_date": news.get("pub_date")}
                    for news in news_map.get(code, [])[:2]
                ]

            lines += [
                "",
                f"### {name}（{code}）",
                "",
                f"**原因：** {item.get('reason') or '暂无明确新闻归因，需人工复核'}",
            ]
            if evidence:
                lines += ["", "**证据：**"]
                for ev in evidence[:2]:
                    title = ev.get("title", "链接")
                    url = ev.get("url") or ev.get("link") or "#"
                    pub_date = ev.get("pub_date", "")
                    if pub_date:
                        lines.append(f"- [{title}]({url}) （{pub_date}）")
                    else:
                        lines.append(f"- [{title}]({url})")

    lines = [
        f"# 沪深300涨跌分析 — {target_date}",
        f"",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**分析基于：** 沪深300指数成分股涨跌幅 top{top_n}",
        f"",
        f"---",
        f"",
        f"## 一、指数概况",
        f"",
        result.get("market_summary", ""),
        f"",
        f"---",
        f"",
        f"## 二、涨幅分析（Top {len(gainers or [])}）",
        f"",
        f"**板块共性：** {result.get('gainers_analysis', {}).get('summary', '')}",
        f"",
        f"| 排名 | 股票代码 | 股票名称 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |",
        f"|------|----------|----------|--------|----------|--------------|",
    ]

    for i, st in enumerate(gainers or [], 1):
        code = st.get("code", "")
        name = st.get("name", "")
        lines.append(
            f"| {i} | {code} | {name} | {fmt_pct(change_map.get(code))} | "
            f"{fmt_pct(week_map.get(code))} | {fmt_pct(ytd_map.get(code))} |"
        )

    append_stock_details(lines, gainers, "gainers_analysis")

    lines += [
        f"",
        f"---",
        f"",
        f"## 三、跌幅分析（Top {len(losers or [])}）",
        f"",
        f"**板块共性：** {result.get('losers_analysis', {}).get('summary', '')}",
        f"",
        f"| 排名 | 股票代码 | 股票名称 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |",
        f"|------|----------|----------|--------|----------|--------------|",
    ]

    for i, st in enumerate(losers or [], 1):
        code = st.get("code", "")
        name = st.get("name", "")
        lines.append(
            f"| {i} | {code} | {name} | {fmt_pct(change_map.get(code))} | "
            f"{fmt_pct(week_map.get(code))} | {fmt_pct(ytd_map.get(code))} |"
        )

    append_stock_details(lines, losers, "losers_analysis")

    lines += ["", "---", "", "*报告由 AI 生成，仅供参考。*"]

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="沪深300涨跌分析")
    parser.add_argument("output_dir", nargs="?", default=None, help="报告输出目录（兼容旧 run 脚本）")
    parser.add_argument("--date", default=None, help="分析日期 (YYYY-MM-DD)，默认最近交易日")
    parser.add_argument("--top", type=int, default=20, help="涨跌榜选取数量 (default: 20)")
    parser.add_argument("--output-dir", dest="output_dir_opt", default=None, help="报告输出目录")
    parser.add_argument("--skip-extended", action="store_true", help="跳过扩展数据获取（本周、YTD）")
    parser.add_argument("--skip-ai", action="store_true", help="跳过 AI 分析（快速生成基础报告）")
    parser.add_argument("--no-news", action="store_true", help="跳过新闻候选获取")
    parser.add_argument("--input-json", default=None, help="从JSON文件读取预计算数据（跳过API调用）")
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        target_date = get_trading_dates(1, include_today=True)[0]

    print(f"[INFO] 开始分析 {target_date} ...", file=sys.stderr)

    # 1. 获取基础数据
    if args.input_json:
        # 从JSON文件读取
        print(f"[INFO] 从JSON文件读取数据: {args.input_json}", file=sys.stderr)
        with open(args.input_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        gainers = data.get("gainers", [])[:args.top]
        losers  = data.get("losers", [])[:args.top]
        print(f"[INFO] 读取到涨幅榜 {len(gainers)} 只、跌幅榜 {len(losers)} 只", file=sys.stderr)
    else:
        # 从API获取
        gainers = get_csi300_top_gainers(target_date, args.top)
        losers  = get_csi300_top_losers(target_date, args.top)

        if not gainers or not losers:
            print("[ERROR] 获取涨跌榜数据失败，退出。", file=sys.stderr)
            sys.exit(1)

        print(f"[INFO] 获取到涨幅榜 {len(gainers)} 只、跌幅榜 {len(losers)} 只", file=sys.stderr)

        # 2. 获取扩展数据（本周涨幅、年初至今涨幅）
        if not args.skip_extended:
            gainers = enrich_with_extended_changes(gainers, target_date)
            losers  = enrich_with_extended_changes(losers, target_date)
        else:
            print("[INFO] 跳过扩展数据获取", file=sys.stderr)

    if not args.no_news:
        print("[INFO] 开始获取新闻候选...", file=sys.stderr)
        gainers = attach_news_candidates(gainers)
        losers  = attach_news_candidates(losers)
        print("[INFO] 新闻候选获取完成", file=sys.stderr)
    else:
        print("[INFO] 跳过新闻候选获取", file=sys.stderr)

    # 3. 构建 prompt 并调用 AI（或跳过）
    if args.skip_ai:
        print(f"[INFO] 跳过 AI 分析，生成基础报告...", file=sys.stderr)
        result = {
            "gainers_analysis": {
                "summary": "（AI 分析跳过，请手动补充）",
                "stocks": [{"code": st["code"], "name": st["name"], "reason": "（AI 分析跳过）", "evidence": []} for st in gainers]
            },
            "losers_analysis": {
                "summary": "（AI 分析跳过，请手动补充）",
                "stocks": [{"code": st["code"], "name": st["name"], "reason": "（AI 分析跳过）", "evidence": []} for st in losers]
            },
            "market_summary": "（AI 分析跳过，请手动补充）"
        }
    else:
        prompt = build_prompt(target_date, gainers, losers)
        print(f"[INFO] 调用 AI ({AI_MODEL}) ...", file=sys.stderr)

        raw = call_ai(prompt, max_tokens=4096, expect_json=True)

        # 4. 解析 JSON（带预处理）
        try:
            cleaned = preprocess_json(raw)
            result = json.loads(cleaned)
        except Exception as e:
            print(f"[ERROR] JSON 解析失败: {e}", file=sys.stderr)
            print(f"[DEBUG] AI 原始输出:\n{raw}", file=sys.stderr)
            sys.exit(1)

    # 5. 生成报告
    report = format_report(result, target_date, gainers=gainers, losers=losers)
    output_dir = args.output_dir_opt or args.output_dir
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"{target_date}.md"
        report_path.write_text(report + "\n", encoding="utf-8")
        (out_dir / "latest.md").write_text(report + "\n", encoding="utf-8")
        print(f"[INFO] 已写入报告: {report_path}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
