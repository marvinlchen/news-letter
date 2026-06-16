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
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# ── 配置 ────────────────────────────────────────────────────────────────────────

AI_MODEL = "codex"   # "codex" or "codebuddy"
EASTMONEY_PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

# ── 工具函数 ─────────────────────────────────────────────────────────────────────

def preprocess_json(s):
    """
    预处理 JSON 字符串，修复常见格式问题：
    1. 将中文引号替换为 ASCII 引号
    2. 转义字符串值中的未转义双引号
    """
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    return s


def call_ai(prompt, max_tokens=4096, expect_json=True):
    """调用 AI 模型（codex 或 codebuddy）"""
    if AI_MODEL == "codex":
        cmd = [
            "codex", "exec",
            "--skip-git-repo-check",
        ]
        cmd.append(prompt)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        text = result.stdout.strip()
        
        # codex exec 输出格式：
        # 第一行是 "codex"，然后是 AI 响应，最后是 metadata
        # 需要提取 JSON 部分
        if expect_json:
            # 查找 JSON 字符串（从第一个 { 或 [ 开始）
            lines = text.split("\n")
            json_started = False
            json_lines = []
            for line in lines:
                if not json_started and (line.strip().startswith("{") or line.strip().startswith("[")):
                    json_started = True
                if json_started:
                    # 如果遇到 metadata 行（如 "tokens used"），停止
                    if line.strip().startswith("tokens") or line.strip() == "":
                        if json_started:
                            break
                    json_lines.append(line)
            if json_lines:
                clean = "\n".join(json_lines).strip()
                # 移除可能的 Markdown 代码块标记
                if clean.startswith("```"):
                    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
                    clean = re.sub(r"\s*```$", "", clean)
                return clean
            else:
                # 如果没找到 JSON，返回原始文本
                return text
        return text
    else:
        # 尝试多个可能的 codebuddy 路径
        codebuddy_paths = [
            "codebuddy",  # 默认 PATH
            "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy",
            "/usr/local/bin/codebuddy",
            "/home/ME/.local/bin/codebuddy",
        ]
        cmd = None
        for cb_path in codebuddy_paths:
            try:
                # 测试路径是否存在（使用 node 的完整路径）
                node_path = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/bin/node"
                test_cmd = [node_path, cb_path, "--version"]
                subprocess.run(test_cmd, capture_output=True, timeout=5)
                # 如果成功，使用 node 直接运行 codebuddy
                cmd = [node_path, cb_path, "-p", "--output-format", "json", prompt]
                break
            except Exception:
                continue
        
        if cmd is None:
            # 如果都找不到，使用默认命令（会失败并抛出错误）
            cmd = ["codebuddy", "-p", "--output-format", "json", prompt]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text = item.get("text", "")
                                        break
                            elif isinstance(content, str):
                                text = content
                            break
                # 现在 text 应该是纯文本 JSON
        except json.JSONDecodeError:
            # 不是 JSON 数组，假设是纯文本
            pass
        
        clean = text.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\s*```$", "", clean)
        return clean


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


def get_csi300_top_gainers(date_str, top_n=10, max_retries=3):
    """
    获取沪深300成分股中涨幅最大的 top_n 只股票。
    返回 list[dict]，包含：code, name, price, change_pct,
                      week_change（本周涨幅）, ytd_change（年初至今涨幅）
    """
    url = (
        f"{EASTMONEY_PUSH2}?"
        f"pn=1&pz={top_n}&po=1&np=1&fltt=2&invt=2&fid=f3&"
        f"fs=m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23&"
        f"fields=f12,f14,f2,f3"
    )
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw = data.get("data", {}).get("diff", [])
                result = []
                for item in raw:
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
            if attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)
                print(f"[WARN] 获取涨幅榜失败（尝试 {attempt+1}/{max_retries}）: {e}，{wait_time}秒后重试...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"[WARN] 获取涨幅榜失败: {e}", file=sys.stderr)
                return []
    return []


def get_csi300_top_losers(date_str, top_n=10, max_retries=3):
    """
    获取沪深300成分股中跌幅最大的 top_n 只股票。
    返回 list[dict]，字段同 get_csi300_top_gainers。
    """
    url = (
        f"{EASTMONEY_PUSH2}?"
        f"pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&"
        f"fs=m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23&"
        f"fields=f12,f14,f2,f3"
    )
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw = data.get("data", {}).get("diff", [])
                # 按涨幅升序排列（取跌幅最大的）
                raw_sorted = sorted(raw, key=lambda x: x.get("f3", 0))
                result = []
                for item in raw_sorted[:top_n]:
                    result.append({
                        "code":        item.get("f12", ""),
                        "name":        item.get("f14", ""),
                        "price":       item.get("f2", None),
                        "change_pct":  item.get("f3", None),
                        "week_change": None,  # 稍后计算
                        "ytd_change":  None,  # 稍后计算
                    })
                return result
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)
                print(f"[WARN] 获取跌幅榜失败（尝试 {attempt+1}/{max_retries}）: {e}，{wait_time}秒后重试...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"[WARN] 获取跌幅榜失败: {e}", file=sys.stderr)
                return []
    return []


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


# ── Prompt 构建 ──────────────────────────────────────────────────────────────────

def build_prompt(date_str, gainers, losers):
    """
    构建发送给 AI 的 prompt。
    包含：当日涨跌幅、本周涨幅、年初至今涨幅。
    """
    lines = [
        f"# 任务",
        f"你是专业财经分析师。请分析 {date_str} 沪深300指数Top10涨幅和Top10跌幅股票。",
        f"",
        f"## 数据",
        f"",
        f"### Top10 涨幅股",
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
            f"",
        ]

    lines += [
        f"",
        f"### Top10 跌幅股",
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
            f"",
        ]

    lines += [
        f"",
        f"## 要求",
        f"1. 分析涨跌幅居前个股的驱动因素",
        f"2. 总结当日市场主线",
        f"3. 输出格式为 Markdown",
        f"4. 每个股票提供2-3条相关证据链接（含发布时间）",
        f"",
        f"## 输出格式（严格 JSON）",
        f"```json",
        f"{{",
        f'  "gainers_analysis": {{',
        f'    "summary": "涨幅板总结",',
        f'    "stocks": [{{"code": "000001", "name": "平安银行", "reason": "…", "evidence": [{{"title": "…", "url": "…", "pub_date": "YYYY-MM-DD HH:MM"}}]}}]',
        f'  }},',
        f'  "losers_analysis": {{',
        f'    "summary": "跌幅板总结",',
        f'    "stocks": [{{"code": "000002", "name": "万科A", "reason": "…", "evidence": [{{"title": "…", "url": "…", "pub_date": "YYYY-MM-DD HH:MM"}}]}}]',
        f'  }},',
        f'  "market_summary": "当日市场主线总结"',
        f"}}",
        f"```",
    ]

    return "\n".join(lines)


# ── 报告生成 ─────────────────────────────────────────────────────────────────────

def format_report(result, target_date, gainers=None, losers=None):
    """
    生成报告 Markdown。
    如果传入 gainers/losers，则从原始数据获取涨跌幅百分比和扩展数据。
    """
    # 创建 code -> data 映射
    change_map = {}
    week_map = {}
    ytd_map = {}
    if gainers:
        for s in gainers:
            change_map[s["code"]] = s["change_pct"]
            week_map[s["code"]] = s.get("week_change")
            ytd_map[s["code"]] = s.get("ytd_change")
    if losers:
        for s in losers:
            change_map[s["code"]] = s["change_pct"]
            week_map[s["code"]] = s.get("week_change")
            ytd_map[s["code"]] = s.get("ytd_change")

    lines = [
        f"# 沪深300涨跌分析 — {target_date}",
        f"",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**分析基于：** 沪深300指数成分股涨跌幅 top20",
        f"",
        f"---",
        f"",
        f"## 一、指数概况",
        f"",
        f"（由AI自动生成的市场概况）",
        f"",
        f"---",
        f"",
        f"## 二、涨幅分析（Top 20）",
        f"",
        f"**板块共性：** {result.get('gainers_analysis', {}).get('summary', '')}",
        f"",
        f"| 排名 | 股票代码 | 股票名称 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |",
        f"|------|----------|----------|--------|----------|--------------|",
    ]

    for i, st in enumerate(result.get("gainers_analysis", {}).get("stocks", []), 1):
        code = st.get("code", "")
        name = st.get("name", "")
        change_pct = change_map.get(code, None)
        week_pct   = week_map.get(code, None)
        ytd_pct    = ytd_map.get(code, None)

        chg_str  = f"{change_pct:+.2f}%" if change_pct is not None else "（暂无）"
        week_str = f"{week_pct:+.2f}%" if week_pct is not None else "（暂无）"
        ytd_str  = f"{ytd_pct:+.2f}%" if ytd_pct is not None else "（暂无）"

        lines.append(f"| {i} | {code} | {name} | {chg_str} | {week_str} | {ytd_str} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 三、跌幅分析（Top 20）",
        f"",
        f"**板块共性：** {result.get('losers_analysis', {}).get('summary', '')}",
        f"",
        f"| 排名 | 股票代码 | 股票名称 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |",
        f"|------|----------|----------|--------|----------|--------------|",
    ]

    for i, st in enumerate(result.get("losers_analysis", {}).get("stocks", []), 1):
        code = st.get("code", "")
        name = st.get("name", "")
        change_pct = change_map.get(code, None)
        week_pct   = week_map.get(code, None)
        ytd_pct    = ytd_map.get(code, None)

        chg_str  = f"{change_pct:+.2f}%" if change_pct is not None else "（暂无）"
        week_str = f"{week_pct:+.2f}%" if week_pct is not None else "（暂无）"
        ytd_str  = f"{ytd_pct:+.2f}%" if ytd_pct is not None else "（暂无）"

        lines.append(f"| {i} | {code} | {name} | {chg_str} | {week_str} | {ytd_str} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 四、当日市场主线",
        f"",
        result.get("market_summary", ""),
        f"",
        f"---",
        f"",
        f"## 五、证据来源",
        f"",
    ]

    # 证据列表（涨幅板）
    for st in result.get("gainers_analysis", {}).get("stocks", []):
        lines.append(f"**{st.get('name')}（{st.get('code')}）**")
        for ev in st.get("evidence", []):
            title = ev.get("title", "链接")
            url = ev.get("url", "#")
            pub_date = ev.get("pub_date", "")
            if pub_date:
                lines.append(f"- [{title}]({url}) （{pub_date}）")
            else:
                lines.append(f"- [{title}]({url})")
        lines.append("")

    # 证据列表（跌幅板）
    for st in result.get("losers_analysis", {}).get("stocks", []):
        lines.append(f"**{st.get('name')}（{st.get('code')}）**")
        for ev in st.get("evidence", []):
            title = ev.get("title", "链接")
            url = ev.get("url", "#")
            pub_date = ev.get("pub_date", "")
            if pub_date:
                lines.append(f"- [{title}]({url}) （{pub_date}）")
            else:
                lines.append(f"- [{title}]({url})")
        lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="沪深300涨跌分析")
    parser.add_argument("--date", default=None, help="分析日期 (YYYY-MM-DD)，默认前一天")
    parser.add_argument("--top", type=int, default=10, help="涨跌榜选取数量 (default: 10)")
    parser.add_argument("--skip-extended", action="store_true", help="跳过扩展数据获取（本周、YTD）")
    parser.add_argument("--skip-ai", action="store_true", help="跳过 AI 分析（快速生成基础报告）")
    parser.add_argument("--input-json", default=None, help="从JSON文件读取预计算数据（跳过API调用）")
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        target_date = get_trading_dates(1)[0]

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
    print(report)


if __name__ == "__main__":
    main()
