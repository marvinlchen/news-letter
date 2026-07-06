#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily A-share and US sector hotspot report."""

import argparse
import csv
import hashlib
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL = os.environ.get("SECTOR_HOTSPOTS_AI_MODEL", "codebuddy")
AI_MODEL_NAME = os.environ.get("SECTOR_HOTSPOTS_AI_MODEL_NAME", "")
NEWS_LOOKBACK_DAYS = int(os.environ.get("SECTOR_HOTSPOTS_NEWS_LOOKBACK_DAYS", "2"))
NEWS_FETCH_LIMIT = int(os.environ.get("SECTOR_HOTSPOTS_NEWS_FETCH_LIMIT", "6"))
NEWS_PROMPT_LIMIT = int(os.environ.get("SECTOR_HOTSPOTS_NEWS_PROMPT_LIMIT", "4"))
MARKET_NEWS_LIMIT = int(os.environ.get("SECTOR_HOTSPOTS_MARKET_NEWS_LIMIT", "40"))
DEFAULT_TOP = int(os.environ.get("SECTOR_HOTSPOTS_TOP", "8"))

EASTMONEY_PUSH2_DELAY = "https://push2delay.eastmoney.com/api/qt/clist/get"
EASTMONEY_FAST_NEWS = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
PUSH2_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/center/boardlist.html",
    "Accept": "application/json,text/plain,*/*",
}
JSON_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}

A_SHARE_BOARD_TYPES = (
    ("industry", "行业板块", "m:90+t:2", "AIND"),
    ("concept", "概念主题", "m:90+t:3", "ACON"),
)

US_SECTOR_ETFS = (
    {"symbol": "XLK", "name_zh": "科技", "name_en": "Technology", "keywords": "technology software semiconductors AI"},
    {"symbol": "SMH", "name_zh": "半导体", "name_en": "Semiconductors", "keywords": "semiconductor chips AI data center"},
    {"symbol": "IGV", "name_zh": "软件", "name_en": "Software", "keywords": "software cloud SaaS enterprise"},
    {"symbol": "XLC", "name_zh": "通信服务", "name_en": "Communication Services", "keywords": "communication services internet media telecom"},
    {"symbol": "XLY", "name_zh": "可选消费", "name_en": "Consumer Discretionary", "keywords": "consumer discretionary retail autos travel"},
    {"symbol": "XLP", "name_zh": "必需消费", "name_en": "Consumer Staples", "keywords": "consumer staples food beverages retail"},
    {"symbol": "XLF", "name_zh": "金融", "name_en": "Financials", "keywords": "banks financials insurance rates"},
    {"symbol": "XLV", "name_zh": "医疗保健", "name_en": "Health Care", "keywords": "health care pharma biotech medical devices"},
    {"symbol": "XLI", "name_zh": "工业", "name_en": "Industrials", "keywords": "industrials aerospace machinery transport"},
    {"symbol": "XLE", "name_zh": "能源", "name_en": "Energy", "keywords": "energy oil gas crude"},
    {"symbol": "XLB", "name_zh": "材料", "name_en": "Materials", "keywords": "materials chemicals metals mining"},
    {"symbol": "XLU", "name_zh": "公用事业", "name_en": "Utilities", "keywords": "utilities power electricity rates"},
    {"symbol": "XLRE", "name_zh": "房地产", "name_en": "Real Estate", "keywords": "real estate REITs mortgage rates"},
    {"symbol": "IBB", "name_zh": "生物科技", "name_en": "Biotechnology", "keywords": "biotechnology FDA drug trials pharma"},
    {"symbol": "ITA", "name_zh": "航空航天与军工", "name_en": "Aerospace & Defense", "keywords": "aerospace defense orders budget"},
)

ATTRIBUTION_TYPES = ("政策催化", "供需景气", "公司事件", "资金交易", "宏观变量", "弱证据待复核")
RUN_STATS = {
    "source_error_count": 0,
    "codex_error": False,
    "fallback_used": False,
    "parse_attempts": 0,
    "codebuddy_parse_errors": [],
}


def normalize_inline_text(text):
    return re.sub(r"\s+", " ", str(text or "").replace("\t", " ")).strip()


def clean_html_text(text):
    text = re.sub(r"<[^>]+>", "", str(text or ""))
    return normalize_inline_text(html.unescape(text))


def strip_code_fences(text):
    clean = str(text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```[^\n]*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    return clean.strip()


def record_source_error(message):
    RUN_STATS["source_error_count"] = int(RUN_STATS.get("source_error_count", 0) or 0) + 1
    print(f"[WARN] {message}", file=sys.stderr)


def parse_number(value):
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except Exception:
        return None


def parse_int(value):
    num = parse_number(value)
    return int(num) if num is not None else None


def fmt_pct(value):
    return f"{value:+.2f}%" if value is not None else "暂无"


def fmt_amount(value):
    if value is None:
        return "暂无"
    value = float(value)
    if abs(value) >= 100000000:
        return f"{value / 100000000:.2f}亿"
    if abs(value) >= 10000:
        return f"{value / 10000:.2f}万"
    return f"{value:.0f}"


def request_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or JSON_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def normalize_news_datetime(value, target_date=None):
    text = normalize_inline_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{2}-\d{2}\s+\d{2}:\d{2}", text):
        year = (target_date or datetime.now().strftime("%Y-%m-%d"))[:4]
        return f"{year}-{text}"
    if re.fullmatch(r"\d{2}-\d{2}", text):
        year = (target_date or datetime.now().strftime("%Y-%m-%d"))[:4]
        return f"{year}-{text}"
    return text[:16] if re.match(r"\d{4}-\d{2}-\d{2}", text) else text


def parse_report_datetime(value):
    if not value:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:16] if fmt.endswith("%M") else text[:10], fmt)
        except ValueError:
            continue
    return None


def news_candidate_in_window(news, target_date=None, lookback_days=None):
    if lookback_days is None:
        lookback_days = NEWS_LOOKBACK_DAYS
    if not target_date:
        return True
    news_dt = parse_report_datetime(news.get("pub_date", ""))
    target_dt = parse_report_datetime(target_date)
    if not news_dt or not target_dt:
        return True
    age_days = (target_dt.date() - news_dt.date()).days
    return -1 <= age_days <= lookback_days


def compact_news_title(title):
    text = normalize_inline_text(title)
    text = re.sub(r"\s+-\s+[^-]+$", "", text)
    return text.lower()


def format_rss_pub_date(pub_date):
    if not pub_date:
        return ""
    try:
        return parsedate_to_datetime(str(pub_date)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(pub_date)


def parse_google_rss_items(xml, limit=NEWS_FETCH_LIMIT, source_type="google_news"):
    news_list = []
    try:
        root = ET.fromstring(xml)
        items = root.findall("./channel/item")
        for item in items[:limit]:
            title = normalize_inline_text(html.unescape(item.findtext("title") or ""))
            link = normalize_inline_text(html.unescape(item.findtext("link") or ""))
            pub_date = format_rss_pub_date(item.findtext("pubDate") or "")
            if title and link:
                news_list.append({"title": title, "link": link, "pub_date": pub_date, "source_type": source_type})
        return news_list
    except Exception:
        return news_list


def fetch_google_news_rss(query, limit=NEWS_FETCH_LIMIT, source_type="google_news", locale="CN"):
    if locale == "US":
        params = "&hl=en-US&gl=US&ceid=US:en"
    else:
        params = "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    rss_url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + params
    req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        xml = resp.read().decode("utf-8", errors="ignore")
    return parse_google_rss_items(xml, limit=limit, source_type=source_type)


def fetch_eastmoney_market_news(target_date=None, limit=None):
    if limit is None:
        limit = MARKET_NEWS_LIMIT
    params = urllib.parse.urlencode(
        {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(limit),
            "req_trace": f"{int(time.time() * 1000)}{random.randint(1000, 9999)}",
        }
    )
    try:
        payload = request_json(EASTMONEY_FAST_NEWS + "?" + params, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://kuaixun.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
        }, timeout=12)
    except Exception as exc:
        record_source_error(f"东方财富7x24快讯获取失败: {exc}")
        return []

    result = []
    for item in ((payload.get("data") or {}).get("fastNewsList") or [])[:limit]:
        title = clean_html_text(item.get("title", ""))
        if not title:
            continue
        summary = clean_html_text(item.get("summary", ""))[:180]
        result.append(
            {
                "title": f"{title} - 东方财富7x24",
                "link": item.get("url") or item.get("shareUrl") or "https://kuaixun.eastmoney.com/",
                "pub_date": normalize_news_datetime(
                    item.get("showTime") or item.get("time") or item.get("publishTime"),
                    target_date=target_date,
                ),
                "summary": summary,
                "source_type": "eastmoney_market_news",
            }
        )
    return result


def fetch_eastmoney_boards(board_type, board_label, fs, limit, ascending=False):
    order = "0" if ascending else "1"
    query = urllib.parse.urlencode(
        {
            "pn": "1",
            "pz": str(max(limit, 20)),
            "po": order,
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": fs,
            "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f8,f62,f104,f105,f128,f140,f141,f136",
        }
    )
    try:
        payload = request_json(EASTMONEY_PUSH2_DELAY + "?" + query, headers=PUSH2_HEADERS, timeout=15)
    except Exception as exc:
        record_source_error(f"东方财富{board_label}排行获取失败: {exc}")
        return []

    rows = (payload.get("data") or {}).get("diff") or []
    result = []
    for item in rows[:limit]:
        result.append(
            {
                "market": "A股",
                "board_type": board_type,
                "board_label": board_label,
                "code": normalize_inline_text(item.get("f12", "")),
                "name": normalize_inline_text(item.get("f14", "")),
                "price": parse_number(item.get("f2")),
                "change_pct": parse_number(item.get("f3")),
                "change": parse_number(item.get("f4")),
                "volume": parse_number(item.get("f5")),
                "amount": parse_number(item.get("f6")),
                "amplitude": parse_number(item.get("f7")),
                "turnover": parse_number(item.get("f8")),
                "main_net_inflow": parse_number(item.get("f62")),
                "up_count": parse_int(item.get("f104")),
                "down_count": parse_int(item.get("f105")),
                "lead_stock": normalize_inline_text(item.get("f128", "")),
                "lead_stock_code": normalize_inline_text(item.get("f140", "")),
                "lead_stock_market": parse_int(item.get("f141")),
                "lead_stock_change_pct": parse_number(item.get("f136")),
                "source": "eastmoney_push2delay",
            }
        )
    return result


def assign_ids(items, prefix):
    for idx, item in enumerate(items, 1):
        item["id"] = f"{prefix}{idx}"
    return items


def fetch_a_share_hotspots(limit):
    groups = {}
    weak = []
    for board_type, board_label, fs, prefix in A_SHARE_BOARD_TYPES:
        hot = fetch_eastmoney_boards(board_type, board_label, fs, limit, ascending=False)
        groups[board_type] = assign_ids(hot, prefix)
        weak.extend(fetch_eastmoney_boards(board_type, board_label, fs, max(3, min(limit, 5)), ascending=True))
        time.sleep(0.2)
    weak.sort(key=lambda item: item.get("change_pct") if item.get("change_pct") is not None else 999)
    return groups, weak[:5]


def fetch_us_yahoo_chart(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=10d&interval=1d&includePrePost=false&events=history"
    payload = request_json(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=15)
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError("empty Yahoo chart result")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [None])[0] or {}
    closes = quote.get("close") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    volumes = quote.get("volume") or []
    valid = [(i, closes[i]) for i in range(min(len(timestamps), len(closes))) if closes[i] is not None]
    if len(valid) < 2:
        raise ValueError("not enough Yahoo bars")
    latest_i, latest_close = valid[-1]
    prev_i, prev_close = valid[-2]
    trade_date = datetime.fromtimestamp(timestamps[latest_i], timezone.utc).strftime("%Y-%m-%d")
    return {
        "trade_date": trade_date,
        "price": parse_number(latest_close),
        "previous_close": parse_number(prev_close),
        "open": parse_number(opens[latest_i] if latest_i < len(opens) else None),
        "high": parse_number(highs[latest_i] if latest_i < len(highs) else None),
        "low": parse_number(lows[latest_i] if latest_i < len(lows) else None),
        "volume": parse_number(volumes[latest_i] if latest_i < len(volumes) else None),
        "source": "yahoo_chart",
    }


def parse_us_date(value):
    return datetime.strptime(value, "%m/%d/%Y").strftime("%Y-%m-%d")


def fetch_us_nasdaq_history(symbol):
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=25)).strftime("%Y-%m-%d")
    url = (
        "https://api.nasdaq.com/api/quote/"
        + urllib.parse.quote(symbol)
        + "/historical?assetclass=etf&fromdate="
        + start
        + "&todate="
        + end
        + "&limit=10"
    )
    payload = request_json(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }, timeout=15)
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    if len(rows) < 2:
        raise ValueError("not enough Nasdaq rows")
    latest = rows[0]
    previous = rows[1]
    return {
        "trade_date": parse_us_date(latest.get("date", "")),
        "price": parse_number(latest.get("close")),
        "previous_close": parse_number(previous.get("close")),
        "open": parse_number(latest.get("open")),
        "high": parse_number(latest.get("high")),
        "low": parse_number(latest.get("low")),
        "volume": parse_number(latest.get("volume")),
        "source": "nasdaq_history",
    }


def fetch_us_etf_quote(symbol):
    errors = []
    for fetcher in (fetch_us_yahoo_chart, fetch_us_nasdaq_history):
        try:
            data = fetcher(symbol)
            if data.get("price") is not None and data.get("previous_close"):
                data["change_pct"] = (data["price"] - data["previous_close"]) / data["previous_close"] * 100
                return data
        except Exception as exc:
            errors.append(f"{fetcher.__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_us_hotspots(limit):
    rows = []
    for meta in US_SECTOR_ETFS:
        symbol = meta["symbol"]
        try:
            quote = fetch_us_etf_quote(symbol)
            rows.append(
                {
                    "id": "",
                    "market": "美股",
                    "symbol": symbol,
                    "name": meta["name_zh"],
                    "name_en": meta["name_en"],
                    "keywords": meta["keywords"],
                    **quote,
                }
            )
        except Exception as exc:
            record_source_error(f"美股ETF {symbol} 行情获取失败: {exc}")
        time.sleep(0.15)
    rows.sort(key=lambda item: item.get("change_pct") if item.get("change_pct") is not None else -999, reverse=True)
    hot = assign_ids(rows[:limit], "US")
    weak = sorted(rows, key=lambda item: item.get("change_pct") if item.get("change_pct") is not None else 999)[:5]
    return hot, weak


def score_news_candidate(news, sector):
    title = normalize_inline_text(news.get("title", ""))
    summary = normalize_inline_text(news.get("summary", ""))
    haystack = f"{title} {summary}".lower()
    score = 0
    if sector.get("market") == "A股":
        for token in (sector.get("name"), sector.get("lead_stock"), sector.get("lead_stock_code")):
            if token and str(token).lower() in haystack:
                score += 20
        for token in ("板块", "行业", "概念", "A股", "涨停", "资金", "政策", "价格", "订单", "需求"):
            if token.lower() in haystack:
                score += 2
    else:
        for token in (sector.get("symbol"), sector.get("name_en"), sector.get("name")):
            if token and str(token).lower() in haystack:
                score += 18
        for token in str(sector.get("keywords", "")).split():
            if token.lower() in haystack:
                score += 3
        for token in ("stocks", "sector", "earnings", "rates", "demand", "policy", "tariff", "AI", "chips"):
            if token.lower() in haystack:
                score += 1
    news_dt = parse_report_datetime(news.get("pub_date", ""))
    if news_dt:
        score += max(0, 6 - (datetime.now() - news_dt).days)
    return score


def rank_news_candidates(news_list, sector, target_date, limit=None):
    if limit is None:
        limit = NEWS_PROMPT_LIMIT
    ranked = []
    seen = set()
    for original_index, news in enumerate(news_list):
        if not news_candidate_in_window(news, target_date=target_date):
            continue
        dedupe_key = compact_news_title(news.get("title", "")) or news.get("link", "")
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ranked.append((score_news_candidate(news, sector), -original_index, news))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in ranked[:limit]]


def a_share_news_queries(sector):
    name = sector.get("name", "")
    lead = sector.get("lead_stock", "")
    return [
        f"{name} A股 板块 when:{NEWS_LOOKBACK_DAYS}d",
        f"{name} 财联社 东方财富 证券时报 when:{NEWS_LOOKBACK_DAYS}d",
        f"{lead} {name} 板块 when:{NEWS_LOOKBACK_DAYS}d" if lead else "",
    ]


def us_news_queries(sector):
    symbol = sector.get("symbol", "")
    name_en = sector.get("name_en", "")
    keywords = sector.get("keywords", "")
    return [
        f"{name_en} sector stocks {symbol} when:{NEWS_LOOKBACK_DAYS}d",
        f"{keywords} stocks market when:{NEWS_LOOKBACK_DAYS}d",
    ]


def attach_news_candidates(sectors, target_date, market_news=None):
    market_news = market_news or []
    for idx, sector in enumerate(sectors, 1):
        print(f"  [news {idx}/{len(sectors)}] {sector.get('market')} {sector.get('name')}", file=sys.stderr)
        raw = []
        if sector.get("market") == "A股":
            raw.extend(
                item for item in market_news
                if sector.get("name", "") in item.get("title", "")
                or sector.get("lead_stock", "") and sector.get("lead_stock", "") in item.get("title", "")
            )
            queries = a_share_news_queries(sector)
            locale = "CN"
        else:
            queries = us_news_queries(sector)
            locale = "US"
        for query in [q for q in queries if q]:
            try:
                raw.extend(fetch_google_news_rss(query, limit=NEWS_FETCH_LIMIT, locale=locale))
            except Exception as exc:
                record_source_error(f"新闻搜索失败 ({sector.get('name')}, {query}): {exc}")
            time.sleep(0.15)
        sector["raw_news_count"] = len(raw)
        sector["news"] = rank_news_candidates(raw, sector, target_date=target_date, limit=NEWS_PROMPT_LIMIT)
    return sectors


def extract_response_text(text):
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(parsed, list):
        return text
    for msg in reversed(parsed):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") in ("text", "output_text"):
                    return item.get("text", "")
    return text


def call_ai(prompt):
    if AI_MODEL == "codex":
        output_path = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
                output_path = tmp.name
            cmd = ["codex", "exec", "--skip-git-repo-check", "--output-last-message", output_path, prompt]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout).strip())
            text = Path(output_path).read_text(encoding="utf-8").strip()
            return strip_code_fences(text or result.stdout)
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

    codebuddy = shutil.which("codebuddy")
    if codebuddy:
        cmd = [codebuddy, "-p", "--output-format", "json", "--input-format", "text"]
        if AI_MODEL_NAME:
            cmd.append(f"--model={AI_MODEL_NAME}")
    else:
        node_path = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/bin/node"
        cb_path = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy"
        cmd = [node_path, cb_path, "-p", "--output-format", "json", "--input-format", "text"]
        if AI_MODEL_NAME:
            cmd.append(f"--model={AI_MODEL_NAME}")

    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return strip_code_fences(extract_response_text(result.stdout.strip()))


def split_protocol_fields(line):
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    if "|" in line:
        return [part.strip() for part in line.split("|")]
    return []


def normalize_attribution(value):
    text = normalize_inline_text(value)
    for item in ATTRIBUTION_TYPES:
        if item in text:
            return item
    return "弱证据待复核"


def build_evidence_catalog(sectors):
    catalog = {}
    for sector in sectors:
        sector_id = sector.get("id", "")
        for idx, news in enumerate(sector.get("news", [])[:NEWS_PROMPT_LIMIT], 1):
            evidence_id = f"{sector_id}-N{idx}"
            catalog[evidence_id] = {
                "sector_id": sector_id,
                "title": news.get("title"),
                "url": news.get("link"),
                "pub_date": news.get("pub_date"),
            }
    return catalog


def parse_evidence_ids(text):
    return [item.upper() for item in re.findall(r"\b(?:AIND|ACON|US)\d+-N\d+\b", text or "", flags=re.IGNORECASE)]


def parse_protocol(raw, sectors):
    clean = strip_code_fences(raw)
    catalog = build_evidence_catalog(sectors)
    result = {"market_summary": "", "items": {}}
    valid_ids = {sector.get("id", "") for sector in sectors}

    for raw_line in clean.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line.strip(" \r\n"))
        if not line:
            continue
        fields = split_protocol_fields(line)
        if len(fields) >= 2 and fields[0].upper() == "MARKET_SUMMARY":
            result["market_summary"] = normalize_inline_text(fields[1])
            continue
        if len(fields) < 4:
            continue
        tag = fields[0].upper()
        sector_id = fields[1].upper()
        if tag not in {"A_HOTSPOT", "US_HOTSPOT"} or sector_id not in valid_ids:
            continue
        selected = []
        evidence_field = fields[4] if len(fields) >= 5 else ""
        for evidence_id in parse_evidence_ids(evidence_field):
            item = catalog.get(evidence_id)
            if item and item.get("sector_id") == sector_id:
                selected.append(item)
            if len(selected) >= 2:
                break
        result["items"][sector_id] = {
            "attribution_type": normalize_attribution(fields[2]),
            "reason": normalize_inline_text(fields[3]),
            "evidence": selected,
        }

    if not result["market_summary"]:
        raise ValueError("missing MARKET_SUMMARY")
    missing = [sector.get("id", "") for sector in sectors if sector.get("id", "") not in result["items"]]
    if missing:
        raise ValueError("missing sector lines: " + ",".join(missing))
    return result


def fallback_item(sector):
    news = sector.get("news", [])
    evidence = []
    if news:
        evidence = [{"title": news[0].get("title"), "url": news[0].get("link"), "pub_date": news[0].get("pub_date")}]
    lead = sector.get("lead_stock")
    lead_part = f"，领涨股为{lead}" if lead else ""
    return {
        "attribution_type": "弱证据待复核",
        "reason": f"{sector.get('name')}当日表现居前{lead_part}；自动归因证据不足，需结合后续候选新闻证据复核。",
        "evidence": evidence,
    }


def build_fallback_result(sectors):
    RUN_STATS["fallback_used"] = True
    return {
        "market_summary": "AI 输出未完整返回，以下内容基于板块行情和候选新闻证据自动整理，归因需人工复核。",
        "items": {sector.get("id", ""): fallback_item(sector) for sector in sectors},
    }


def run_ai_analysis(prompt, sectors, max_attempts=2):
    attempts = [
        prompt,
        prompt
        + "\n\n重新输出要求：上一次输出未能被脚本解析。请只输出协议行，TAB 分隔，不要 Markdown、不要解释、不要空行；必须覆盖所有给定 sector_id。",
    ]
    last_error = None
    for attempt in range(max_attempts):
        RUN_STATS["parse_attempts"] = attempt + 1
        raw = call_ai(attempts[min(attempt, len(attempts) - 1)])
        try:
            return parse_protocol(raw, sectors)
        except Exception as exc:
            last_error = exc
            RUN_STATS.setdefault("codebuddy_parse_errors", []).append(str(exc))
            print(f"[WARN] 热点报告 AI 输出解析失败，第 {attempt + 1} 次: {exc}", file=sys.stderr)
            print(f"[DEBUG] AI 原始输出:\n{raw}", file=sys.stderr)
    RUN_STATS["codex_error"] = True
    print(f"[WARN] AI 多次输出失败，使用兜底报告: {last_error}", file=sys.stderr)
    return build_fallback_result(sectors)


def build_prompt(report_date, a_industry, a_concept, us_hot, us_data_date, market="all"):
    sectors = a_industry + a_concept + us_hot
    lines = [
        "机器协议模式：你的回复会被脚本逐行解析。只输出协议行，不要 Markdown、不要标题、不要编号、不要空行。",
        "字段分隔符必须使用 TAB。原因和摘要必须是单行文本，不能包含 TAB。",
        "第一行必须是 MARKET_SUMMARY<TAB>总体总结。",
        "A股热点行格式：A_HOTSPOT<TAB>sector_id<TAB>归因类型<TAB>原因<TAB>证据ID列表。",
        "美股热点行格式：US_HOTSPOT<TAB>sector_id<TAB>归因类型<TAB>原因<TAB>证据ID列表。",
        "归因类型只能是：政策催化、供需景气、公司事件、资金交易、宏观变量、弱证据待复核。",
        "证据ID列表最多 2 个，用英文逗号分隔；只能从对应板块的 NEWS 行选择；没有可靠证据则留空并标为弱证据待复核。",
        "不要把单纯涨跌幅描述包装成强因果；必须区分行情事实、候选新闻证据和推断。",
        "",
        f"# 任务：分析 {report_date} 股票板块热点",
    ]
    if market in ("all", "a"):
        lines.append(f"A股数据为中国交易日 {report_date} 收盘后东方财富延迟板块行情。")
    if market in ("all", "us"):
        lines.append(f"美股数据为最近一个美股交易日 {us_data_date or '未知'} 的ETF板块代理日线表现。")
    lines += [
        "",
        "## 输出骨架",
        "MARKET_SUMMARY\t待填写",
    ]
    for sector in a_industry + a_concept:
        lines.append(f"A_HOTSPOT\t{sector.get('id')}\t弱证据待复核\t待填写\t")
    for sector in us_hot:
        lines.append(f"US_HOTSPOT\t{sector.get('id')}\t弱证据待复核\t待填写\t")
    lines += ["", "## 数据", ""]

    def append_sector(sector):
        chg = fmt_pct(sector.get("change_pct"))
        if sector.get("market") == "A股":
            breadth = f"{sector.get('up_count') or 0}涨/{sector.get('down_count') or 0}跌"
            lead = f"领涨股 {sector.get('lead_stock') or '-'} {fmt_pct(sector.get('lead_stock_change_pct'))}"
            amount = fmt_amount(sector.get("amount"))
            flow = fmt_amount(sector.get("main_net_inflow"))
            lines.append(
                f"SECTOR\t{sector.get('id')}\tA股\t{sector.get('board_label')}\t{sector.get('name')}\t涨跌幅{chg}\t成交额{amount}\t主力净流入{flow}\t涨跌家数{breadth}\t{lead}"
            )
        else:
            lines.append(
                f"SECTOR\t{sector.get('id')}\t美股\t{sector.get('symbol')}\t{sector.get('name')}({sector.get('name_en')})\t涨跌幅{chg}\t收盘{sector.get('price')}\t成交量{fmt_amount(sector.get('volume'))}"
            )
        for idx, news in enumerate(sector.get("news", [])[:NEWS_PROMPT_LIMIT], 1):
            evidence_id = f"{sector.get('id')}-N{idx}"
            title = normalize_inline_text(news.get("title", ""))
            pub_date = normalize_inline_text(news.get("pub_date", ""))
            lines.append(f"NEWS\t{evidence_id}\t{pub_date}\t{title}")
        if not sector.get("news"):
            lines.append(f"NEWS\t{sector.get('id')}-N0\t\t暂无候选新闻")
        lines.append("")

    if a_industry:
        lines.append("### A股行业热点")
        for item in a_industry:
            append_sector(item)
    if a_concept:
        lines.append("### A股概念主题")
        for item in a_concept:
            append_sector(item)
    if us_hot:
        lines.append("### 美股板块热点")
        for item in us_hot:
            append_sector(item)
    return "\n".join(lines)


def analysis_for(result, sector):
    return result.get("items", {}).get(sector.get("id", ""), fallback_item(sector))


def append_hotspot_table(lines, title, sectors, result, include_board=False):
    lines += ["", f"## {title}", ""]
    if include_board:
        lines.append("| 排名 | 类型 | 板块 | 涨跌幅 | 成交额 | 主力净流入 | 涨跌家数 | 领涨股 | 归因类型 |")
        lines.append("|---:|---|---|---:|---:|---:|---|---|---|")
    else:
        lines.append("| 排名 | 板块 | 代理ETF | 数据日 | 涨跌幅 | 成交量 | 归因类型 |")
        lines.append("|---:|---|---|---|---:|---:|---|")
    for idx, sector in enumerate(sectors, 1):
        analysis = analysis_for(result, sector)
        if sector.get("market") == "A股":
            breadth = f"{sector.get('up_count') or 0}涨/{sector.get('down_count') or 0}跌"
            lead = sector.get("lead_stock") or "-"
            if sector.get("lead_stock_change_pct") is not None:
                lead = f"{lead} {fmt_pct(sector.get('lead_stock_change_pct'))}"
            lines.append(
                f"| {idx} | {sector.get('board_label')} | {sector.get('name')} | {fmt_pct(sector.get('change_pct'))} | "
                f"{fmt_amount(sector.get('amount'))} | {fmt_amount(sector.get('main_net_inflow'))} | {breadth} | {lead} | {analysis.get('attribution_type')} |"
            )
        else:
            lines.append(
                f"| {idx} | {sector.get('name')} | {sector.get('symbol')} | {sector.get('trade_date')} | "
                f"{fmt_pct(sector.get('change_pct'))} | {fmt_amount(sector.get('volume'))} | {analysis.get('attribution_type')} |"
            )
    lines.append("")
    for sector in sectors:
        analysis = analysis_for(result, sector)
        label = sector.get("name")
        if sector.get("market") == "美股":
            label = f"{sector.get('name')}（{sector.get('symbol')}）"
        lines += ["", f"### {label}", "", f"**归因类型：** {analysis.get('attribution_type')}", "", f"**原因：** {analysis.get('reason')}"]
        evidence = analysis.get("evidence") or []
        if evidence:
            lines += ["", "**证据：**"]
            for item in evidence[:2]:
                title_text = item.get("title") or "链接"
                url = item.get("url") or "#"
                pub_date = item.get("pub_date") or ""
                suffix = f" （{pub_date}）" if pub_date else ""
                lines.append(f"- [{title_text}]({url}){suffix}")


def append_weak_table(lines, title, sectors):
    lines += ["", f"## {title}", ""]
    if not sectors:
        lines.append("暂无数据。")
        return
    if sectors[0].get("market") == "A股":
        lines.append("| 排名 | 类型 | 板块 | 涨跌幅 | 成交额 | 涨跌家数 | 领涨/领跌参考 |")
        lines.append("|---:|---|---|---:|---:|---|---|")
        for idx, sector in enumerate(sectors, 1):
            breadth = f"{sector.get('up_count') or 0}涨/{sector.get('down_count') or 0}跌"
            lines.append(
                f"| {idx} | {sector.get('board_label')} | {sector.get('name')} | {fmt_pct(sector.get('change_pct'))} | "
                f"{fmt_amount(sector.get('amount'))} | {breadth} | {sector.get('lead_stock') or '-'} |"
            )
    else:
        lines.append("| 排名 | 板块 | 代理ETF | 数据日 | 涨跌幅 |")
        lines.append("|---:|---|---|---|---:|")
        for idx, sector in enumerate(sectors, 1):
            lines.append(f"| {idx} | {sector.get('name')} | {sector.get('symbol')} | {sector.get('trade_date')} | {fmt_pct(sector.get('change_pct'))} |")


def report_quality(sectors, result):
    candidate_count = sum(len(sector.get("news", []) or []) for sector in sectors)
    raw_candidate_count = sum(sector.get("raw_news_count", 0) or 0 for sector in sectors)
    selected_evidence_count = sum(len(item.get("evidence", []) or []) for item in result.get("items", {}).values())
    weak_count = sum(
        1 for item in result.get("items", {}).values()
        if item.get("attribution_type") == "弱证据待复核"
    )
    return {
        "sector_count": len(sectors),
        "candidate_count": candidate_count,
        "raw_candidate_count": raw_candidate_count,
        "selected_evidence_count": selected_evidence_count,
        "weak_evidence_count": weak_count,
    }


def format_report(report_date, a_industry, a_concept, a_weak, us_hot, us_weak, result, us_data_date, market="all"):
    sectors = a_industry + a_concept + us_hot
    quality = report_quality(sectors, result)
    if market == "a":
        title = f"A股板块热点分析 — {report_date}"
    elif market == "us":
        title = f"美股板块热点分析 — {report_date}"
    else:
        title = f"股票板块热点分析 — {report_date}"
    lines = [
        f"# {title}",
        "",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
    ]
    if market in ("all", "a"):
        lines.append("**A股口径：** 东方财富延迟行业/概念板块行情，按涨跌幅排序  ")
    if market in ("all", "us"):
        lines.append(f"**美股口径：** 最近一个美股交易日（{us_data_date or '未知'}）的公开ETF日线代理；计划在美股收盘后约3小时生成  ")
    lines += [
        (
            f"**数据质量：** 热点板块 {quality['sector_count']} 个；"
            f"候选新闻证据 {quality['candidate_count']} 条；"
            f"入选证据 {quality['selected_evidence_count']} 条；"
            f"弱证据待复核 {quality['weak_evidence_count']} 个"
        ),
        "",
        "---",
        "",
        "## 总体主线",
        "",
        result.get("market_summary", ""),
    ]
    if a_industry:
        append_hotspot_table(lines, "A股行业热点", a_industry, result, include_board=True)
    if a_concept:
        append_hotspot_table(lines, "A股概念主题热点", a_concept, result, include_board=True)
    if us_hot:
        append_hotspot_table(lines, "美股板块热点", us_hot, result, include_board=False)
    if a_weak:
        append_weak_table(lines, "A股回落/弱势板块", a_weak)
    if us_weak:
        append_weak_table(lines, "美股回落/弱势板块", us_weak)
    lines += [
        "",
        "---",
        "",
        "*报告由 AI 基于公开行情与候选新闻证据生成，仅供研究参考，不构成投资建议。*",
    ]
    return "\n".join(lines)


def write_status(report_date, result, sectors, report_path=None, latest_path=None, us_data_date=None, market="all", status_dir_name=None):
    status_dir = PROJECT_ROOT / "var" / (status_dir_name or "sector-hotspots-status")
    status_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "date": report_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": AI_MODEL,
        "ai_model_name": AI_MODEL_NAME,
        "market": market,
        "us_data_date": us_data_date,
        "news_lookback_days": NEWS_LOOKBACK_DAYS,
        "codex_error": bool(RUN_STATS.get("codex_error", False)),
        "fallback_used": bool(RUN_STATS.get("fallback_used", False)),
        "parse_attempts": int(RUN_STATS.get("parse_attempts", 0) or 0),
        "codebuddy_parse_errors": RUN_STATS.get("codebuddy_parse_errors", []),
        "source_error_count": int(RUN_STATS.get("source_error_count", 0) or 0),
        **report_quality(sectors, result),
        "output_path": str(report_path) if report_path else "",
        "latest_path": str(latest_path) if latest_path else "",
        "report_sha256": "",
        "publish_commit": "",
    }
    if report_path and Path(report_path).exists():
        status["report_sha256"] = hashlib.sha256(Path(report_path).read_bytes()).hexdigest()
    payload = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
    (status_dir / f"{report_date}.json").write_text(payload + "\n", encoding="utf-8")
    (status_dir / "latest.json").write_text(payload + "\n", encoding="utf-8")
    print(f"[INFO] 已写入热点状态: {status_dir / 'latest.json'}", file=sys.stderr)


def most_common(values):
    counts = {}
    for value in values:
        if value:
            counts[value] = counts.get(value, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]


def main():
    parser = argparse.ArgumentParser(description="A股和美股板块热点分析")
    parser.add_argument("--market", choices=("all", "a", "us"), default="all", help="生成范围: all, a, us")
    parser.add_argument("--date", default=None, help="报告日期 YYYY-MM-DD，默认按市场自动选择")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="每组热点数量")
    parser.add_argument("--output-dir", default=None, help="报告输出目录")
    parser.add_argument("--status-dir-name", default=None, help="var 下的状态目录名")
    parser.add_argument("--skip-ai", action="store_true", help="跳过 AI 归因")
    parser.add_argument("--no-news", action="store_true", help="跳过候选新闻证据")
    parser.add_argument("--no-status", action="store_true", help="不写 var/status，便于诊断运行")
    args = parser.parse_args()

    initial_date = args.date or datetime.now().strftime("%Y-%m-%d")
    report_date = initial_date
    print(f"[INFO] 开始生成 {report_date} 股票板块热点分析", file=sys.stderr)
    a_industry = []
    a_concept = []
    a_weak = []
    if args.market in ("all", "a"):
        print("[INFO] 获取A股板块排行...", file=sys.stderr)
        a_groups, a_weak = fetch_a_share_hotspots(args.top)
        a_industry = a_groups.get("industry", [])
        a_concept = a_groups.get("concept", [])

    us_hot = []
    us_weak = []
    us_data_date = ""
    if args.market in ("all", "us"):
        print("[INFO] 获取美股板块ETF代理行情...", file=sys.stderr)
        us_hot, us_weak = fetch_us_hotspots(args.top)
        us_data_date = most_common([item.get("trade_date") for item in us_hot + us_weak])
        if args.market == "us" and not args.date and us_data_date:
            report_date = us_data_date

    sectors = a_industry + a_concept + us_hot
    if not sectors:
        print("[ERROR] 未获取到任何板块数据", file=sys.stderr)
        sys.exit(1)

    if not args.no_news:
        print("[INFO] 获取候选新闻证据...", file=sys.stderr)
        if a_industry or a_concept:
            market_news = fetch_eastmoney_market_news(target_date=report_date)
            attach_news_candidates(a_industry + a_concept, report_date, market_news=market_news)
        if us_hot:
            attach_news_candidates(us_hot, initial_date, market_news=[])
    else:
        print("[INFO] 跳过候选新闻证据", file=sys.stderr)

    if args.skip_ai:
        print("[INFO] 跳过 AI 分析，生成基础报告", file=sys.stderr)
        result = build_fallback_result(sectors)
    else:
        prompt = build_prompt(report_date, a_industry, a_concept, us_hot, us_data_date, market=args.market)
        print(f"[INFO] 调用 AI ({AI_MODEL}) ...", file=sys.stderr)
        result = run_ai_analysis(prompt, sectors)

    report = format_report(report_date, a_industry, a_concept, a_weak, us_hot, us_weak, result, us_data_date, market=args.market)
    report_path = None
    latest_path = None
    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"{report_date}.md"
        latest_path = out_dir / "latest.md"
        report_path.write_text(report + "\n", encoding="utf-8")
        latest_path.write_text(report + "\n", encoding="utf-8")
        print(f"[INFO] 已写入报告: {report_path}", file=sys.stderr)
    else:
        print(report)

    if not args.no_status:
        write_status(
            report_date,
            result,
            sectors,
            report_path=report_path,
            latest_path=latest_path,
            us_data_date=us_data_date,
            market=args.market,
            status_dir_name=args.status_dir_name,
        )


if __name__ == "__main__":
    main()
