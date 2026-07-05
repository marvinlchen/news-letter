#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指数涨跌分析脚本 - 完整版
支持沪深300(csi300)、中证500(csi500)、中证1000(csi1000)指数
获取：当日涨跌幅、本周涨幅、年初至今涨幅
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
import html
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

# ── 配置 ────────────────────────────────────────────────────────────────────────

# ── 多指数支持 ──────────────────────────────────────────────────────────────────
# INDEX_TYPE 在 main() 中通过 --index 参数设置，默认 csi300 保持向后兼容。
INDEX_TYPE = "csi300"
INDEX_DISPLAY_NAME = "沪深300"
INDEX_CODE = "000300"
INDEX_BOARD_FS = "b:BK0500"   # Eastmoney board code; None 表示无对应板块，需用 akshare
ENV_PREFIX = "CSI300"

_INDEX_PROFILES = {
    "csi300": {
        "index_code": "000300",
        "display_name": "沪深300",
        "board_fs": "b:BK0500",
        "env_prefix": "CSI300",
    },
    "csi500": {
        "index_code": "000905",
        "display_name": "中证500",
        "board_fs": None,
        "env_prefix": "CSI500",
    },
    "csi1000": {
        "index_code": "000852",
        "display_name": "中证1000",
        "board_fs": None,
        "env_prefix": "CSI1000",
    },
}


def configure_index(index_type):
    """Set globals for the chosen index and re-read environment variables."""
    global INDEX_TYPE, INDEX_DISPLAY_NAME, INDEX_CODE, INDEX_BOARD_FS, ENV_PREFIX
    global AI_MODEL, AI_MODEL_NAME, NEWS_FETCH_LIMIT, NEWS_PROMPT_LIMIT
    global NEWS_EVIDENCE_LIMIT, NEWS_LOOKBACK_DAYS, NEWS_SOURCE_LIMIT
    global ANNOUNCEMENT_FETCH_LIMIT, CNINFO_LOOKBACK_DAYS, TOP_N_DEFAULT
    global EASTMONEY_STOCK_NEWS_LIMIT, EASTMONEY_MARKET_NEWS_LIMIT
    global THS_HOT_REASON_LIMIT, MARKET_NEWS_PROMPT_LIMIT

    profile = _INDEX_PROFILES.get(index_type)
    if not profile:
        raise ValueError(f"Unknown index type: {index_type}. Choose from {list(_INDEX_PROFILES)}")

    INDEX_TYPE = index_type
    INDEX_DISPLAY_NAME = profile["display_name"]
    INDEX_CODE = profile["index_code"]
    INDEX_BOARD_FS = profile["board_fs"]
    ENV_PREFIX = profile["env_prefix"]

    p = ENV_PREFIX
    AI_MODEL = os.environ.get(f"{p}_AI_MODEL", "codebuddy")
    AI_MODEL_NAME = os.environ.get(f"{p}_AI_MODEL_NAME", "")
    NEWS_FETCH_LIMIT = int(os.environ.get(f"{p}_NEWS_FETCH_LIMIT", "8"))
    NEWS_PROMPT_LIMIT = int(os.environ.get(f"{p}_NEWS_PROMPT_LIMIT", "6"))
    NEWS_EVIDENCE_LIMIT = int(os.environ.get(f"{p}_NEWS_EVIDENCE_LIMIT", "2"))
    NEWS_LOOKBACK_DAYS = int(os.environ.get(f"{p}_NEWS_LOOKBACK_DAYS", "7"))
    NEWS_SOURCE_LIMIT = int(os.environ.get(f"{p}_NEWS_SOURCE_LIMIT", "6"))
    ANNOUNCEMENT_FETCH_LIMIT = int(os.environ.get(f"{p}_ANNOUNCEMENT_FETCH_LIMIT", "6"))
    CNINFO_LOOKBACK_DAYS = int(os.environ.get(f"{p}_CNINFO_LOOKBACK_DAYS", str(NEWS_LOOKBACK_DAYS)))
    TOP_N_DEFAULT = int(os.environ.get(f"{p}_TOP", "20"))
    EASTMONEY_STOCK_NEWS_LIMIT = int(os.environ.get(f"{p}_EASTMONEY_STOCK_NEWS_LIMIT", "8"))
    EASTMONEY_MARKET_NEWS_LIMIT = int(os.environ.get(f"{p}_EASTMONEY_MARKET_NEWS_LIMIT", "20"))
    THS_HOT_REASON_LIMIT = int(os.environ.get(f"{p}_THS_HOT_REASON_LIMIT", "300"))
    MARKET_NEWS_PROMPT_LIMIT = int(os.environ.get(f"{p}_MARKET_NEWS_PROMPT_LIMIT", "8"))

    print(f"[INFO] 配置指数: {INDEX_DISPLAY_NAME} (code={INDEX_CODE}, board={INDEX_BOARD_FS or 'akshare'})", file=sys.stderr)


# 模块级默认值（向后兼容 csi300 直接运行）
AI_MODEL = os.environ.get("CSI300_AI_MODEL", "codebuddy")
AI_MODEL_NAME = os.environ.get("CSI300_AI_MODEL_NAME", "")
NEWS_FETCH_LIMIT = int(os.environ.get("CSI300_NEWS_FETCH_LIMIT", "8"))
NEWS_PROMPT_LIMIT = int(os.environ.get("CSI300_NEWS_PROMPT_LIMIT", "6"))
NEWS_EVIDENCE_LIMIT = int(os.environ.get("CSI300_NEWS_EVIDENCE_LIMIT", "2"))
NEWS_LOOKBACK_DAYS = int(os.environ.get("CSI300_NEWS_LOOKBACK_DAYS", "7"))
NEWS_SOURCE_LIMIT = int(os.environ.get("CSI300_NEWS_SOURCE_LIMIT", "6"))
ANNOUNCEMENT_FETCH_LIMIT = int(os.environ.get("CSI300_ANNOUNCEMENT_FETCH_LIMIT", "6"))
CNINFO_LOOKBACK_DAYS = int(os.environ.get("CSI300_CNINFO_LOOKBACK_DAYS", str(NEWS_LOOKBACK_DAYS)))
TOP_N_DEFAULT = int(os.environ.get("CSI300_TOP", "20"))
EASTMONEY_STOCK_NEWS_LIMIT = int(os.environ.get("CSI300_EASTMONEY_STOCK_NEWS_LIMIT", "8"))
EASTMONEY_MARKET_NEWS_LIMIT = int(os.environ.get("CSI300_EASTMONEY_MARKET_NEWS_LIMIT", "20"))
THS_HOT_REASON_LIMIT = int(os.environ.get("CSI300_THS_HOT_REASON_LIMIT", "300"))
MARKET_NEWS_PROMPT_LIMIT = int(os.environ.get("CSI300_MARKET_NEWS_PROMPT_LIMIT", "8"))
REJECT_SCORE = -100
EASTMONEY_PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_PUSH2_FALLBACK = "https://push2delay.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
HISTORICAL_RANK_CACHE = {}
CNINFO_STOCK_INDEX_CACHE = None
THS_HOT_REASON_CACHE = {}
EASTMONEY_MARKET_NEWS_CACHE = {}
CSI_RUN_STATS = {}
PUSH2_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json,text/plain,*/*",
}
NEWS_RELEVANCE_KEYWORDS = (
    "业绩", "净利润", "营收", "增长", "亏损", "订单", "合同", "扩产", "投产",
    "回购", "减持", "增持", "分红", "定增", "并购", "收购", "重组", "上市",
    "指数", "调入", "调出", "ETF", "资金", "主力", "北向", "龙虎榜",
    "评级", "买入", "目标价", "涨", "跌", "涨停", "跌停", "需求", "价格",
)
MARKET_NEWS_RELEVANCE_KEYWORDS = (
    "A股", "沪深", "中证", "上证", "深证", "创业板", "科创", "股票", "股市",
    "证券", "板块", "行业", "上市公司", "业绩", "订单", "资金", "ETF",
    "北向", "外资", "央行", "利率", "汇率", "人民币", "美元", "美联储",
    "财政", "政策", "关税", "出口", "进口", "PMI", "CPI", "PPI", "国债",
    "期货", "原油", "黄金", "铜", "有色", "化工", "半导体", "芯片", "AI",
    "算力", "新能源", "汽车", "机器人", "医药", "消费", "银行", "保险", "地产",
)
ATTRIBUTION_TYPES = ("直接催化", "行业带动", "资金交易", "弱证据待复核")
DIRECT_CATALYST_KEYWORDS = (
    "业绩", "预增", "预减", "净利润", "营收", "收入", "订单", "合同", "中标",
    "停产", "复产", "减持", "增持", "回购", "分红", "权益分派", "定增",
    "并购", "收购", "重组", "问询函", "审核问询", "监管", "处罚", "立案",
    "产销", "销量", "交付", "合作", "战略合作", "获批", "扩产", "投产",
    "涨价", "降价", "价格", "产能", "新产品", "挂牌", "上市交易",
)
INDUSTRY_CATALYST_KEYWORDS = (
    "板块", "行业", "概念", "产业链", "黄金", "有色", "半导体", "芯片",
    "CPO", "算力", "AI", "人工智能", "机器人", "新能源", "汽车", "医药",
    "消费电子", "军工", "航天", "化工", "物流", "快递", "银行", "地产",
    "央企改革", "低空经济", "EDA", "光伏", "储能",
)
FUND_TRADING_KEYWORDS = (
    "主力资金", "净买入", "净卖出", "资金流入", "资金流出", "北向资金",
    "机构净买", "机构净卖", "融资融券", "融资余额", "融券", "龙虎榜",
    "成交额", "换手率", "资金追捧",
)
AUXILIARY_EVIDENCE_KEYWORDS = (
    "触及涨停", "触及跌停", "涨停板", "跌停板", "异动快报", "ETF风向标",
    "ETF盘中", "成分股领涨", "成分股领跌", "盘中涨", "盘中跌",
    "前期涨幅", "获利回吐", "技术性回调", "市场情绪", "推进平稳",
    "治理规范", "担保进展", "余额维持",
)
TRUSTED_STOCK_NEWS_SITES = (
    ("东方财富", "site:eastmoney.com"),
    ("新浪财经", "site:finance.sina.com.cn"),
    ("证券时报", "site:stcn.com"),
    ("财联社", "site:cls.cn"),
    ("21财经", "site:21jingji.com"),
    ("每日经济新闻", "site:nbd.com.cn"),
    ("第一财经", "site:yicai.com"),
)
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
                        "required": ["code", "name", "attribution_type", "reason", "evidence"],
                        "properties": {
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "attribution_type": {"type": "string", "enum": list(ATTRIBUTION_TYPES)},
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
                        "required": ["code", "name", "attribution_type", "reason", "evidence"],
                        "properties": {
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "attribution_type": {"type": "string", "enum": list(ATTRIBUTION_TYPES)},
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


def strip_code_fences(text):
    """Remove surrounding Markdown code fences if present."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```[^\n]*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    return clean.strip()


def normalize_inline_text(text):
    """Collapse multiline AI text into a single clean line."""
    return re.sub(r"\s+", " ", (text or "").replace("\t", " ")).strip()


def parse_report_datetime(value):
    """Parse compact report/news timestamps used by the RSS collector."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:16] if fmt.endswith("%M") else value[:10], fmt)
        except ValueError:
            continue
    return None


def compact_news_title(title):
    """Normalize titles for deduping, keeping source suffixes for display elsewhere."""
    text = normalize_inline_text(title)
    text = re.sub(r"\s+-\s+[^-]+$", "", text)
    return text.lower()


def clean_html_text(text):
    """Strip HTML tags and normalize escaped text from web JSON payloads."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return normalize_inline_text(html.unescape(text))


def parse_jsonp_payload(text):
    """Parse plain JSON or a JSONP wrapper returned by Eastmoney endpoints."""
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    start = text.find("(")
    end = text.rfind(")")
    if start == -1 or end == -1 or end <= start:
        return {}
    return json.loads(text[start + 1:end])


def reset_csi_run_stats(target_date=None, top_n=None, skip_ai=False):
    CSI_RUN_STATS.clear()
    CSI_RUN_STATS.update({
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "date": target_date,
        "index": INDEX_TYPE,
        "index_display_name": INDEX_DISPLAY_NAME,
        "mode": "skip-ai" if skip_ai else AI_MODEL,
        "ai_model_name": AI_MODEL_NAME,
        "top_n": top_n,
        "codex_error": False,
        "fallback_used": False,
        "parse_attempts": 0,
        "codebuddy_parse_errors": [],
        "source_error_count": 0,
    })


def record_source_error(message):
    CSI_RUN_STATS["source_error_count"] = int(CSI_RUN_STATS.get("source_error_count", 0) or 0) + 1
    print(f"[WARN] {message}", file=sys.stderr)


def news_after_target_date(news, target_date=None):
    """Return True when a candidate is dated after the target trading day."""
    if not target_date:
        return False
    news_dt = parse_report_datetime(news.get("pub_date", ""))
    target_dt = parse_report_datetime(target_date or "")
    if not news_dt or not target_dt:
        return False
    return news_dt.date() > target_dt.date()


def text_has_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def classify_attribution_text(text, has_evidence=True):
    """Classify attribution strength from reason and evidence text."""
    text = normalize_inline_text(text)
    if not has_evidence:
        return "弱证据待复核"
    if text_has_any(text, DIRECT_CATALYST_KEYWORDS):
        return "直接催化"
    if text_has_any(text, INDUSTRY_CATALYST_KEYWORDS):
        return "行业带动"
    if text_has_any(text, FUND_TRADING_KEYWORDS):
        return "资金交易"
    return "弱证据待复核"


def normalize_attribution_type(value, reason="", evidence=None):
    """Keep model labels within the supported attribution taxonomy."""
    text = normalize_inline_text(value)
    evidence = evidence or []
    for item in ATTRIBUTION_TYPES:
        if item in text:
            return item
    evidence_text = " ".join(
        normalize_inline_text(ev.get("title", ""))
        for ev in evidence
        if isinstance(ev, dict)
    )
    return classify_attribution_text(
        f"{reason} {evidence_text}",
        has_evidence=bool(evidence),
    )


def news_candidate_category(news):
    """Return the attribution category implied by a candidate news item."""
    text = normalize_inline_text(
        f"{news.get('title', '')} {news.get('summary', '')}"
    )
    if text_has_any(text, DIRECT_CATALYST_KEYWORDS):
        return "直接催化"
    if text_has_any(text, INDUSTRY_CATALYST_KEYWORDS):
        return "行业带动"
    if text_has_any(text, FUND_TRADING_KEYWORDS):
        return "资金交易"
    return "弱证据待复核"


def weak_auxiliary_evidence(news):
    text = normalize_inline_text(f"{news.get('title', '')} {news.get('summary', '')}")
    return text_has_any(text, AUXILIARY_EVIDENCE_KEYWORDS)


def news_candidate_score(news, stock_name, stock_code, target_date=None):
    """Rank candidate news before sending a compact set to the model.

    Hard relevance gate: a candidate whose title mentions neither the stock
    name nor the stock code is rejected with REJECT_SCORE. This prevents
    broad-market wrap-ups and unrelated fund NAV announcements (which Google
    News RSS returns via full-text matching) from entering the model's
    evidence pool simply because they happen to contain generic finance
    keywords like "涨" and are recent.
    """
    title = normalize_inline_text(news.get("title", ""))
    if not title:
        return REJECT_SCORE

    source_type = news.get("source_type")
    name_hit = bool(stock_name) and stock_name in title
    code_hit = bool(stock_code) and stock_code in title
    stock_bound = (
        source_type in {"eastmoney_stock_news", "ths_hot_reason"}
        and news.get("stock_code") == stock_code
    )
    if not name_hit and not code_hit and not stock_bound:
        # Full-text RSS noise: title does not reference this stock at all.
        # Penalize below any plausible relevant score so rank_news_candidates
        # drops it unless the entire pool is equally irrelevant.
        return REJECT_SCORE

    score = 0
    if name_hit:
        score += 20
    if code_hit:
        score += 10
    if stock_bound:
        score += 12
    category = news_candidate_category(news)
    if source_type == "announcement":
        score += 6
    elif source_type == "trusted_news":
        score += 3
    elif source_type == "eastmoney_stock_news":
        score += 5
    elif source_type == "ths_hot_reason":
        score += 7
    elif source_type == "market_news":
        score += 4
    if INDEX_DISPLAY_NAME in title:
        score += 3
    for keyword in NEWS_RELEVANCE_KEYWORDS:
        if keyword in title:
            score += 2

    if category == "直接催化":
        score += 12
    elif category == "行业带动":
        score += 4
    elif category == "资金交易":
        score -= 4
    else:
        score -= 6
    if weak_auxiliary_evidence(news):
        score -= 10

    news_dt = parse_report_datetime(news.get("pub_date", ""))
    target_dt = parse_report_datetime(target_date or "")
    if news_dt and target_dt:
        age_days = (target_dt.date() - news_dt.date()).days
        if age_days < 0:
            return REJECT_SCORE
        elif age_days <= 7:
            score += 8
        elif age_days <= 30:
            score += 5
        elif age_days <= 180:
            score += 2
        elif age_days > 365:
            score -= 5

    return score


def rank_news_candidates(news_list, stock_name, stock_code, target_date=None, limit=None):
    """Deduplicate and keep the strongest news candidates for evidence selection.

    Candidates scoring REJECT_SCORE (title does not reference this stock) are
    dropped entirely rather than re-ranked, so the model never sees irrelevant
    full-text RSS noise. If every candidate is rejected the pool may be shorter
    than ``limit`` (possibly empty); the caller treats an empty pool as "no
    evidence available" instead of fabricating unrelated evidence.
    """
    if limit is None:
        limit = NEWS_PROMPT_LIMIT
    ranked = []
    seen = set()
    for original_index, news in enumerate(news_list):
        if not news_candidate_in_window(news, target_date=target_date):
            continue
        title_key = compact_news_title(news.get("title", ""))
        link_key = news.get("link", "")
        dedupe_key = title_key or link_key
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        score = news_candidate_score(news, stock_name, stock_code, target_date)
        if score <= REJECT_SCORE:
            # Hard reject: title does not mention this stock at all.
            continue
        ranked.append((
            score,
            -original_index,
            news,
        ))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in ranked[:limit]]


def news_candidate_in_window(news, target_date=None, lookback_days=None):
    """Keep dated candidates inside the unified lookback window.

    Reports explain the target trading day, so candidates dated after that day
    are excluded to avoid hindsight evidence.
    """
    if lookback_days is None:
        lookback_days = NEWS_LOOKBACK_DAYS
    if not target_date:
        return True
    news_dt = parse_report_datetime(news.get("pub_date", ""))
    target_dt = parse_report_datetime(target_date or "")
    if not news_dt or not target_dt:
        return True
    age_days = (target_dt.date() - news_dt.date()).days
    return 0 <= age_days <= lookback_days


def repair_unescaped_string_quotes(text):
    """Escape bare double quotes that appear inside JSON string values."""
    chars = []
    in_string = False
    escaped = False

    for i, ch in enumerate(text):
        if escaped:
            chars.append(ch)
            escaped = False
            continue

        if in_string and ch == "\\":
            chars.append(ch)
            escaped = True
            continue

        if ch == '"':
            if not in_string:
                in_string = True
                chars.append(ch)
                continue

            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            next_ch = text[j] if j < len(text) else ""
            if next_ch in {":", ",", "}", "]", ""}:
                in_string = False
                chars.append(ch)
            else:
                chars.append('\\"')
            continue

        chars.append(ch)

    return "".join(chars)


def parse_ai_json(raw):
    """Parse AI JSON output, repairing common CodeBuddy quote escaping mistakes."""
    cleaned = strip_code_fences(preprocess_json(raw))
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = repair_unescaped_string_quotes(cleaned)
        if repaired != cleaned:
            return json.loads(repaired)
        raise


def build_result(
    gainers,
    losers,
    market_summary,
    gainers_summary,
    losers_summary,
    gainer_reasons=None,
    loser_reasons=None,
    gainer_evidence=None,
    loser_evidence=None,
    gainer_attribution=None,
    loser_attribution=None,
    default_reason="暂无明确新闻归因，需人工复核",
):
    """Assemble the report structure expected by format_report()."""
    gainer_reasons = gainer_reasons or {}
    loser_reasons = loser_reasons or {}
    gainer_evidence = gainer_evidence or {}
    loser_evidence = loser_evidence or {}
    gainer_attribution = gainer_attribution or {}
    loser_attribution = loser_attribution or {}
    return {
        "gainers_analysis": {
            "summary": gainers_summary,
            "stocks": [
                {
                    "code": st["code"],
                    "name": st["name"],
                    "reason": gainer_reasons.get(st["code"], default_reason),
                    "attribution_type": normalize_attribution_type(
                        gainer_attribution.get(st["code"], ""),
                        reason=gainer_reasons.get(st["code"], default_reason),
                        evidence=gainer_evidence.get(st["code"], []),
                    ),
                    "evidence": gainer_evidence.get(st["code"], []),
                }
                for st in gainers
            ],
        },
        "losers_analysis": {
            "summary": losers_summary,
            "stocks": [
                {
                    "code": st["code"],
                    "name": st["name"],
                    "reason": loser_reasons.get(st["code"], default_reason),
                    "attribution_type": normalize_attribution_type(
                        loser_attribution.get(st["code"], ""),
                        reason=loser_reasons.get(st["code"], default_reason),
                        evidence=loser_evidence.get(st["code"], []),
                    ),
                    "evidence": loser_evidence.get(st["code"], []),
                }
                for st in losers
            ],
        },
        "market_summary": market_summary,
    }


def build_fallback_reason(stock, direction_label):
    """Return a readable fallback reason when AI output is missing or partial."""
    news = stock.get("news", [])
    if news:
        title = normalize_inline_text(news[0].get("title", ""))
        if title:
            return f"{direction_label}，可先参考候选新闻《{title}》，具体催化需人工复核。"
    return f"{direction_label}，但 AI 输出不完整，需结合候选新闻人工复核。"


def build_fallback_result(gainers, losers):
    """Produce a report even when AI output cannot be parsed reliably."""
    return build_result(
        gainers,
        losers,
        "AI 输出未完整返回，以下内容基于行情与候选新闻自动整理，需人工复核。",
        "涨幅股已按当日表现列出，板块共性需结合候选新闻进一步确认。",
        "跌幅股已按当日表现列出，板块共性需结合候选新闻进一步确认。",
        {
            st["code"]: build_fallback_reason(st, "当日涨幅居前")
            for st in gainers
        },
        {
            st["code"]: build_fallback_reason(st, "当日跌幅居前")
            for st in losers
        },
    )


def build_evidence_catalog(gainers, losers):
    """Map prompt evidence IDs back to script-owned news candidates."""
    catalog = {}
    for prefix, stocks in (("G", gainers), ("L", losers)):
        for stock_index, stock in enumerate(stocks, 1):
            code = stock.get("code", "")
            for news_index, news in enumerate(stock.get("news", [])[:NEWS_PROMPT_LIMIT], 1):
                evidence_id = f"{prefix}{stock_index}-{news_index}"
                catalog[evidence_id] = {
                    "code": code,
                    "title": news.get("title"),
                    "url": news.get("link"),
                    "pub_date": news.get("pub_date"),
                }
    return catalog


def parse_evidence_ids(text):
    """Extract model-selected evidence IDs from the protocol field."""
    return [item.upper() for item in re.findall(r"\b[GL]\d+-\d+\b", text or "", flags=re.IGNORECASE)]


def resolve_evidence_ids(stock, selected_ids, evidence_catalog):
    """Return at most NEWS_EVIDENCE_LIMIT evidence items owned by this stock."""
    code = stock.get("code", "")
    result = []
    seen = set()
    for evidence_id in selected_ids:
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        item = evidence_catalog.get(evidence_id)
        if not item or item.get("code") != code:
            continue
        result.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "pub_date": item.get("pub_date"),
        })
        if len(result) >= NEWS_EVIDENCE_LIMIT:
            break
    return result


def split_protocol_fields(line):
    """Split a CodeBuddy protocol line, preferring tabs but tolerating pipes."""
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    if "|" in line:
        return [part.strip() for part in line.split("|")]
    return []


def parse_codebuddy_protocol(raw, gainers, losers):
    """Parse compact line-oriented CodeBuddy output."""
    cleaned = strip_code_fences(raw)
    market_summary = ""
    gainers_summary = ""
    losers_summary = ""
    gainer_reasons = {}
    loser_reasons = {}
    gainer_evidence_ids = {}
    loser_evidence_ids = {}
    gainer_attribution = {}
    loser_attribution = {}
    summary_pattern = re.compile(
        r"^(MARKET_SUMMARY|GAINERS_SUMMARY|LOSERS_SUMMARY)\s*(?:\t|\||:|：)\s*(.+)$",
        re.IGNORECASE,
    )
    stock_pattern = re.compile(
        r"^(GAINER|LOSER)\s*(?:\t|\||:|：)\s*([0-9]{6})\s*(?:\t|\||:|：)\s*(.+)$",
        re.IGNORECASE,
    )
    evidence_catalog = build_evidence_catalog(gainers, losers)

    for raw_line in cleaned.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line.strip())
        if not line:
            continue

        match = summary_pattern.match(line)
        if match:
            tag = match.group(1).upper()
            value = normalize_inline_text(match.group(2))
            if tag == "MARKET_SUMMARY":
                market_summary = value
            elif tag == "GAINERS_SUMMARY":
                gainers_summary = value
            elif tag == "LOSERS_SUMMARY":
                losers_summary = value
            continue

        fields = split_protocol_fields(line)
        if len(fields) >= 3 and fields[0].upper() in {"GAINER", "LOSER"} and re.fullmatch(r"[0-9]{6}", fields[1]):
            tag = fields[0].upper()
            code = fields[1]
            if len(fields) >= 5 and any(item in fields[2] for item in ATTRIBUTION_TYPES):
                attribution_type = normalize_attribution_type(fields[2])
                reason = normalize_inline_text(fields[3])
                selected_ids = parse_evidence_ids(fields[4])
            else:
                attribution_type = ""
                reason = normalize_inline_text(fields[2])
                selected_ids = parse_evidence_ids(fields[3]) if len(fields) >= 4 else []
        else:
            match = stock_pattern.match(line)
            if not match:
                continue
            tag = match.group(1).upper()
            code = match.group(2)
            attribution_type = ""
            reason = normalize_inline_text(match.group(3))
            selected_ids = parse_evidence_ids(reason)
            if selected_ids:
                reason = normalize_inline_text(re.sub(
                    r"(?:\t|\||[,，;；])?\s*(?:[GL]\d+-\d+\s*[,，;；]?\s*)+$",
                    "",
                    reason,
                    flags=re.IGNORECASE,
                ))

        if tag == "GAINER":
            gainer_reasons[code] = reason
            gainer_evidence_ids[code] = selected_ids
            if attribution_type:
                gainer_attribution[code] = attribution_type
        else:
            loser_reasons[code] = reason
            loser_evidence_ids[code] = selected_ids
            if attribution_type:
                loser_attribution[code] = attribution_type

    gainer_evidence = {
        stock.get("code", ""): resolve_evidence_ids(
            stock,
            gainer_evidence_ids.get(stock.get("code", ""), []),
            evidence_catalog,
        )
        for stock in gainers
    }
    loser_evidence = {
        stock.get("code", ""): resolve_evidence_ids(
            stock,
            loser_evidence_ids.get(stock.get("code", ""), []),
            evidence_catalog,
        )
        for stock in losers
    }

    if not market_summary or not gainers_summary or not losers_summary:
        raise ValueError("missing summary lines in CodeBuddy output")

    missing_gainers = [
        stock.get("code", "")
        for stock in gainers
        if stock.get("code", "") not in gainer_reasons
    ]
    missing_losers = [
        stock.get("code", "")
        for stock in losers
        if stock.get("code", "") not in loser_reasons
    ]
    if missing_gainers or missing_losers:
        raise ValueError(
            "missing stock lines: "
            f"gainers={','.join(missing_gainers) or '-'}; "
            f"losers={','.join(missing_losers) or '-'}"
        )

    return build_result(
        gainers,
        losers,
        market_summary,
        gainers_summary,
        losers_summary,
        gainer_reasons,
        loser_reasons,
        gainer_evidence,
        loser_evidence,
        gainer_attribution,
        loser_attribution,
    )


def run_codebuddy_analysis(prompt, gainers, losers, max_attempts=2):
    """Call CodeBuddy with a compact protocol and tolerate partial outputs."""
    last_error = None
    attempts = [
        prompt,
        (
            prompt
            + "\n\n## 重新输出要求\n"
            + "上一次输出未能被脚本解析。请重新输出完整结果："
            + "只允许纯文本记录、TAB 分隔、不要 JSON、不要 Markdown、不要代码块、不要空行。"
            + "股票行必须为 5 列：TAG、股票代码、归因类型、原因、证据ID列表。"
            + "第三列归因类型只能是直接催化/行业带动/资金交易/弱证据待复核；"
            + "第五列填写 0-2 个候选证据 ID，用逗号分隔；没有合适证据时留空。"
        ),
    ]
    for attempt in range(max_attempts):
        CSI_RUN_STATS["parse_attempts"] = attempt + 1
        raw = call_ai(attempts[min(attempt, len(attempts) - 1)], max_tokens=4096, expect_json=False)
        try:
            return parse_codebuddy_protocol(raw, gainers, losers)
        except Exception as exc:
            last_error = exc
            CSI_RUN_STATS.setdefault("codebuddy_parse_errors", []).append(str(exc))
            print(f"[WARN] CodeBuddy 输出解析失败，第 {attempt + 1} 次尝试: {exc}", file=sys.stderr)
            print(f"[DEBUG] AI 原始输出:\n{raw}", file=sys.stderr)

    print(f"[WARN] CodeBuddy 多次输出失败，使用兜底报告: {last_error}", file=sys.stderr)
    CSI_RUN_STATS["codex_error"] = True
    CSI_RUN_STATS["fallback_used"] = True
    return build_fallback_result(gainers, losers)


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
            if AI_MODEL_NAME:
                cmd = [codebuddy_executable, "-p", "--output-format", "json", "--input-format", "text", f"--model={AI_MODEL_NAME}"]
            else:
                cmd = [codebuddy_executable, "-p", "--output-format", "json", "--input-format", "text"]
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
                    if AI_MODEL_NAME:
                        cmd = [node_path, cb_path, "-p", "--output-format", "json", "--input-format", "text", f"--model={AI_MODEL_NAME}"]
                    else:
                        cmd = [node_path, cb_path, "-p", "--output-format", "json", "--input-format", "text"]
                    break
                except Exception:
                    continue
        
        if cmd is None:
            # 如果都找不到，使用默认命令（会失败并抛出错误）
            if AI_MODEL_NAME:
                cmd = ["codebuddy", "-p", "--output-format", "json", "--input-format", "text", f"--model={AI_MODEL_NAME}"]
            else:
                cmd = ["codebuddy", "-p", "--output-format", "json", "--input-format", "text"]
        
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
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


def build_secid(stock_code):
    """Build Eastmoney secid (market.code) from a stock code."""
    market = "1" if stock_code.startswith(("6", "5", "9")) else "0"
    return f"{market}.{stock_code}"


def fetch_constituents_akshare(index_code):
    """通过 akshare 获取指数成分股代码和名称。"""
    import akshare as ak
    df = ak.index_stock_cons_csindex(symbol=index_code)
    result = []
    for _, row in df.iterrows():
        code = str(row.get("成分券代码", "")).strip()
        name = str(row.get("成分券名称", "")).strip()
        if code:
            result.append({"code": code, "name": name})
    return result


def fetch_constituents(max_retries=3):
    """获取当前指数成分股代码和名称（自动选择板块API或akshare）。"""
    if INDEX_BOARD_FS:
        return _fetch_constituents_via_board(INDEX_BOARD_FS, max_retries)
    else:
        print(f"[INFO] 通过 akshare 获取{INDEX_DISPLAY_NAME}成分股...", file=sys.stderr)
        constituents = fetch_constituents_akshare(INDEX_CODE)
        print(f"[INFO] akshare 返回 {len(constituents)} 只成分股", file=sys.stderr)
        return constituents


def _fetch_constituents_via_board(board_fs, max_retries=3):
    """通过东方财富板块接口获取成分股代码和名称。"""
    page_size = 100
    page = 1
    total = None
    result = []
    seen = set()

    while total is None or len(result) < total:
        query = (
            f"pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2&fid=f3&"
            f"fs={board_fs}&"
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
                    print(f"[WARN] 获取{INDEX_DISPLAY_NAME}成分股第 {page} 页失败（尝试 {attempt+1}/{max_retries}）: {e}，{wait_time}秒后重试...", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    print(f"[WARN] 获取{INDEX_DISPLAY_NAME}成分股第 {page} 页失败: {e}", file=sys.stderr)
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


def fetch_historical_rank(date_str, top_n=20, ascending=False):
    """按指定历史交易日重算指数涨跌幅排行。"""
    if date_str in HISTORICAL_RANK_CACHE:
        ranked = list(HISTORICAL_RANK_CACHE[date_str])
        ranked.sort(key=lambda x: x.get("change_pct", 0), reverse=not ascending)
        return ranked[:top_n]

    constituents = fetch_constituents()
    ranked = []
    print(f"[INFO] 计算 {len(constituents)} 只{INDEX_DISPLAY_NAME}成分股的 {date_str} 历史涨跌幅...", file=sys.stderr)
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


def fetch_live_rank(top_n=20, ascending=False, max_retries=3):
    """
    获取指数成分股实时涨跌幅排行。
    返回 list[dict]，包含：code, name, price, change_pct,
                      week_change（本周涨幅）, ytd_change（年初至今涨幅）
    """
    if INDEX_BOARD_FS:
        return _fetch_live_rank_via_board(INDEX_BOARD_FS, top_n, ascending, max_retries)
    else:
        return _fetch_live_rank_via_secids(top_n, ascending, max_retries)


def _fetch_live_rank_via_board(board_fs, top_n=20, ascending=False, max_retries=3):
    """通过东方财富板块接口获取实时涨跌幅排行。"""
    order = "0" if ascending else "1"
    query = (
        f"pn=1&pz={top_n}&po={order}&np=1&fltt=2&invt=2&fid=f3&"
        f"fs={board_fs}&"
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
                            "week_change": None,
                            "ytd_change":  None,
                        })
                    return result
                except Exception as e:
                    last_error = e
            raise last_error
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)
                print(f"[WARN] 获取{INDEX_DISPLAY_NAME}排行失败（尝试 {attempt+1}/{max_retries}）: {e}，{wait_time}秒后重试...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"[WARN] 获取{INDEX_DISPLAY_NAME}排行失败: {e}", file=sys.stderr)
                return []
    return []


def _fetch_live_rank_via_secids(top_n=20, ascending=False, max_retries=3):
    """通过扫描全A股涨跌幅排行，过滤出指数成分股的实时排行（用于无板块代码的指数）。

    由于 push2delay 不支持 secids 参数，改为按 f3（涨跌幅）排序逐页扫描全 A 股，
    过滤出成分股。CSI500/CSI1000 占全 A 股约 9%~18%，通常 3~8 页即可收集足够数据。
    """
    constituents = fetch_constituents()
    if not constituents:
        print(f"[WARN] 未获取到{INDEX_DISPLAY_NAME}成分股，无法查询实时排行", file=sys.stderr)
        return []

    # 构建成分股代码集合，同时保留名称映射
    constituent_codes = set()
    name_map = {}
    for c in constituents:
        code = c["code"]
        constituent_codes.add(code)
        name_map[code] = c.get("name", "")

    order = "0" if ascending else "1"  # po=0 升序(跌幅榜), po=1 降序(涨幅榜)
    max_pages = 15  # 最多扫描 1500 只股票
    buffer = max(top_n + 5, 25)  # 收集比 top_n 多一些以保证排序后有足够数据

    all_matches = []
    for page in range(1, max_pages + 1):
        query = (
            f"pn={page}&pz=100&po={order}&np=1&fltt=2&invt=2&fid=f3&"
            f"fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&"
            f"fields=f12,f14,f2,f3"
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
                    print(f"[WARN] 获取{INDEX_DISPLAY_NAME}排行第 {page} 页失败（尝试 {attempt+1}/{max_retries}）: {e}，{wait_time}秒后重试...", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    print(f"[WARN] 获取{INDEX_DISPLAY_NAME}排行第 {page} 页失败: {e}", file=sys.stderr)

        if page_data:
            data_section = page_data.get("data") or {}
            raw = data_section.get("diff", [])
            if not raw:
                break
            for item in raw:
                code = item.get("f12", "")
                if code in constituent_codes:
                    all_matches.append({
                        "code":        code,
                        "name":        name_map.get(code, item.get("f14", "")),
                        "price":       item.get("f2",  None),
                        "change_pct":  item.get("f3",  None),
                        "week_change": None,
                        "ytd_change":  None,
                    })

        if len(all_matches) >= buffer:
            break
        time.sleep(0.1)

    print(f"[INFO] 扫描 {page} 页，找到 {len(all_matches)} 只{INDEX_DISPLAY_NAME}成分股", file=sys.stderr)
    all_matches.sort(key=lambda x: x.get("change_pct", 0) or 0, reverse=not ascending)
    return all_matches[:top_n]


def get_top_gainers(date_str, top_n=20, max_retries=3):
    """获取指数成分股中涨幅最大的 top_n 只股票。"""
    if _is_live_data_date(date_str):
        return fetch_live_rank(top_n=top_n, ascending=False, max_retries=max_retries)
    return fetch_historical_rank(date_str, top_n=top_n, ascending=False)


def get_top_losers(date_str, top_n=20, max_retries=3):
    """获取指数成分股中跌幅最大的 top_n 只股票。"""
    if _is_live_data_date(date_str):
        return fetch_live_rank(top_n=top_n, ascending=True, max_retries=max_retries)
    return fetch_historical_rank(date_str, top_n=top_n, ascending=True)


def _is_live_data_date(date_str):
    """Check if the live API data reflects the target date.

    The Eastmoney push2 API returns the most recent trading day's data.
    If date_str is today or the most recent trading day, live data is valid.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if date_str == today:
        return True
    # Check if date_str is the most recent trading day (e.g., Friday on a weekend)
    trading_dates = get_trading_dates(1, include_today=True)
    return date_str == trading_dates[0]


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


def format_rss_pub_date(pub_date):
    """Format RSS/announcement timestamps as compact report time."""
    if not pub_date:
        return ""
    try:
        dt = parsedate_to_datetime(str(pub_date))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        return str(pub_date)


def parse_google_rss_items(xml, limit=NEWS_FETCH_LIMIT, source_type="google_news"):
    """Parse Google News RSS items into stock-news candidate dicts."""
    news_list = []
    try:
        root = ET.fromstring(xml)
        items = root.findall("./channel/item")
        for item in items[:limit]:
            title = normalize_inline_text(html.unescape(item.findtext("title") or ""))
            link = normalize_inline_text(html.unescape(item.findtext("link") or ""))
            pub_date = format_rss_pub_date(item.findtext("pubDate") or "")
            if title and link:
                news_list.append(
                    {
                        "title": title,
                        "link": link,
                        "pub_date": pub_date,
                        "source_type": source_type,
                    }
                )
        return news_list
    except Exception:
        pass

    items = re.split(r"<item>", xml)[1:]
    for item in items[:limit]:
        t = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        l = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", item, re.DOTALL)
        if t and l:
            title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t.group(1)).strip()
            title = normalize_inline_text(html.unescape(title))
            link = normalize_inline_text(html.unescape(l.group(1).strip()))
            pub_date = format_rss_pub_date(d.group(1).strip() if d else "")
            news_list.append(
                {
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "source_type": source_type,
                }
            )
    return news_list


def fetch_google_news_rss(query, limit=NEWS_FETCH_LIMIT, source_type="google_news"):
    """Fetch a Google News RSS query and parse candidate items."""
    rss_url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    )
    req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        xml = resp.read().decode("utf-8", errors="ignore")
    return parse_google_rss_items(xml, limit=limit, source_type=source_type)


def normalize_news_datetime(value, target_date=None):
    """Normalize common Eastmoney/THS timestamp formats to report datetime text."""
    text = normalize_inline_text(str(value or ""))
    if not text:
        return ""
    if re.fullmatch(r"\d{2}-\d{2}\s+\d{2}:\d{2}", text):
        year = (target_date or datetime.now().strftime("%Y-%m-%d"))[:4]
        return f"{year}-{text}"
    if re.fullmatch(r"\d{2}-\d{2}", text):
        year = (target_date or datetime.now().strftime("%Y-%m-%d"))[:4]
        return f"{year}-{text}"
    return text[:16] if re.match(r"\d{4}-\d{2}-\d{2}", text) else text


def fetch_eastmoney_stock_news(stock_name, stock_code, target_date=None, limit=None):
    """Fetch direct Eastmoney stock news from search-api-web."""
    if limit is None:
        limit = EASTMONEY_STOCK_NEWS_LIMIT
    try:
        inner_params = json.dumps(
            {
                "uid": "",
                "keyword": stock_code,
                "type": ["cmsArticleWebOld"],
                "client": "web",
                "clientType": "web",
                "clientVersion": "curr",
                "param": {
                    "cmsArticleWebOld": {
                        "searchScope": "default",
                        "sort": "default",
                        "pageIndex": 1,
                        "pageSize": limit,
                        "preTag": "",
                        "postTag": "",
                    }
                },
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        params = urllib.parse.urlencode({"cb": "jQuery_stocknews", "param": inner_params})
        req = urllib.request.Request(
            "https://search-api-web.eastmoney.com/search/jsonp?" + params,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://so.eastmoney.com/",
                "Accept": "application/javascript,application/json,text/plain,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = parse_jsonp_payload(resp.read().decode("utf-8", errors="ignore"))

        articles = (payload.get("result") or {}).get("cmsArticleWebOld") or []
        if isinstance(articles, dict):
            articles = articles.get("list") or articles.get("data") or []

        news_list = []
        for article in articles[:limit]:
            title = clean_html_text(article.get("title", ""))
            if not title:
                continue
            content = clean_html_text(article.get("content", ""))[:160]
            source = clean_html_text(article.get("mediaName", "")) or "东方财富"
            if source and source not in title:
                title = f"{title} - {source}"
            news_list.append(
                {
                    "title": title,
                    "link": article.get("url") or article.get("wapurl") or "https://so.eastmoney.com/",
                    "pub_date": normalize_news_datetime(
                        article.get("date") or article.get("time") or article.get("showTime"),
                        target_date=target_date,
                    ),
                    "summary": content,
                    "source_type": "eastmoney_stock_news",
                    "stock_code": stock_code,
                }
            )
        return news_list
    except Exception as e:
        record_source_error(f"搜索东方财富个股新闻失败 ({stock_name}): {e}")
        return []


def fetch_ths_hot_reasons(target_date=None, limit=None):
    """Fetch THS strong-stock topic reasons once per date."""
    if limit is None:
        limit = THS_HOT_REASON_LIMIT
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    cache_key = (date_str, limit)
    if cache_key in THS_HOT_REASON_CACHE:
        return THS_HOT_REASON_CACHE[cache_key]

    url = (
        "http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date_str}/orderby/date/orderway/desc/charset/GBK/"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "http://zx.10jqka.com.cn/event/",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        rows = payload.get("data") or []
        result = {}
        for row in rows[:limit]:
            code = normalize_inline_text(row.get("code", ""))
            match = re.search(r"(\d{6})", code)
            if not match:
                continue
            result[match.group(1)] = row
        THS_HOT_REASON_CACHE[cache_key] = result
        return result
    except Exception as e:
        record_source_error(f"搜索同花顺题材归因失败 ({date_str}): {e}")
        THS_HOT_REASON_CACHE[cache_key] = {}
        return {}


def ths_hot_reason_candidates(stock_name, stock_code, target_date=None):
    """Return a stock-bound THS topic-reason candidate when available."""
    row = fetch_ths_hot_reasons(target_date=target_date).get(stock_code)
    if not row:
        return []
    reason = clean_html_text(row.get("reason", ""))
    if not reason:
        return []
    return [
        {
            "title": f"{stock_name}：同花顺强势股题材归因：{reason}",
            "link": (
                "http://zx.10jqka.com.cn/event/api/getharden/"
                f"date/{target_date or datetime.now().strftime('%Y-%m-%d')}/"
                "orderby/date/orderway/desc/charset/GBK/"
            ),
            "pub_date": target_date or datetime.now().strftime("%Y-%m-%d"),
            "source_type": "ths_hot_reason",
            "stock_code": stock_code,
        }
    ]


def fetch_eastmoney_market_news(target_date=None, limit=None):
    """Fetch Eastmoney 7x24 market news for index and sector context."""
    if limit is None:
        limit = EASTMONEY_MARKET_NEWS_LIMIT
    cache_key = (target_date or "", limit)
    if cache_key in EASTMONEY_MARKET_NEWS_CACHE:
        return EASTMONEY_MARKET_NEWS_CACHE[cache_key]

    try:
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
        req = urllib.request.Request(
            "https://np-weblist.eastmoney.com/comm/web/getFastNewsList?" + params,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://kuaixun.eastmoney.com/",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

        rows = (payload.get("data") or {}).get("fastNewsList") or []
        result = []
        for item in rows[:limit]:
            title = clean_html_text(item.get("title", ""))
            if not title:
                continue
            summary = clean_html_text(item.get("summary", ""))[:180]
            relevance_text = f"{title} {summary}"
            if not any(keyword in relevance_text for keyword in MARKET_NEWS_RELEVANCE_KEYWORDS):
                continue
            pub_date = normalize_news_datetime(
                item.get("showTime") or item.get("time") or item.get("publishTime"),
                target_date=target_date,
            )
            news = {
                "title": f"{title} - 东方财富7x24",
                "link": item.get("url") or item.get("shareUrl") or "https://kuaixun.eastmoney.com/",
                "pub_date": pub_date,
                "summary": summary,
                "source_type": "market_news",
            }
            if news_candidate_in_window(news, target_date=target_date):
                result.append(news)
        EASTMONEY_MARKET_NEWS_CACHE[cache_key] = result
        return result
    except Exception as e:
        record_source_error(f"搜索东方财富7x24快讯失败: {e}")
        EASTMONEY_MARKET_NEWS_CACHE[cache_key] = []
        return []


def matching_market_news(stock_name, stock_code, market_news, limit=2):
    """Reuse market-news context as stock evidence only when its title names the stock."""
    matches = []
    for item in market_news or []:
        title = normalize_inline_text(item.get("title", ""))
        if (stock_name and stock_name in title) or (stock_code and stock_code in title):
            matches.append(dict(item))
        if len(matches) >= limit:
            break
    return matches


def stock_news_queries(stock_name, stock_code):
    """Build broad and trusted-site stock news queries."""
    trusted_sites = " OR ".join(site_query for _, site_query in TRUSTED_STOCK_NEWS_SITES)
    return [
        (
            f"{stock_name} {stock_code} {INDEX_DISPLAY_NAME} when:{NEWS_LOOKBACK_DAYS}d",
            NEWS_FETCH_LIMIT,
            "google_news",
        ),
        (
            f"{stock_name} {stock_code} ({trusted_sites}) when:{NEWS_LOOKBACK_DAYS}d",
            NEWS_SOURCE_LIMIT,
            "trusted_news",
        ),
    ]


def cninfo_headers():
    return {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        "Accept": "application/json,text/plain,*/*",
    }


def load_cninfo_stock_index():
    """Load and cache CNInfo stock code to orgId mapping."""
    global CNINFO_STOCK_INDEX_CACHE
    if CNINFO_STOCK_INDEX_CACHE is not None:
        return CNINFO_STOCK_INDEX_CACHE

    url = "http://www.cninfo.com.cn/new/data/szse_stock.json"
    req = urllib.request.Request(url, headers=cninfo_headers())
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

    stock_map = {}
    for item in payload.get("stockList", []):
        code = item.get("code")
        org_id = item.get("orgId")
        if code and org_id:
            stock_map[code] = {
                "org_id": org_id,
                "name": item.get("zwjc", ""),
            }
    CNINFO_STOCK_INDEX_CACHE = stock_map
    return stock_map


def cninfo_market_params(stock_code):
    if stock_code.startswith("6"):
        return "sse", "sh"
    return "szse", "sz"


def cninfo_date_window(target_date):
    target_dt = parse_report_datetime(target_date or "") or datetime.now()
    start = (target_dt - timedelta(days=CNINFO_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    end = (target_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{start}~{end}"


def format_cninfo_timestamp(value):
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""


def clean_cninfo_title(title):
    title = re.sub(r"</?em>", "", title or "")
    return normalize_inline_text(html.unescape(title))


def search_cninfo_announcements(stock_name, stock_code, target_date=None, limit=None):
    """Fetch official company announcements from CNInfo."""
    if limit is None:
        limit = ANNOUNCEMENT_FETCH_LIMIT
    try:
        stock_meta = load_cninfo_stock_index().get(stock_code)
        if not stock_meta:
            return []

        column, plate = cninfo_market_params(stock_code)
        params = {
            "pageNum": "1",
            "pageSize": str(limit),
            "column": column,
            "tabName": "fulltext",
            "plate": plate,
            "stock": f"{stock_code},{stock_meta['org_id']}",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": cninfo_date_window(target_date),
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        req = urllib.request.Request(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=urllib.parse.urlencode(params).encode(),
            headers=cninfo_headers(),
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

        news_list = []
        for item in (payload.get("announcements") or [])[:limit]:
            title = clean_cninfo_title(item.get("announcementTitle", ""))
            adjunct_url = item.get("adjunctUrl", "")
            if not title or not adjunct_url:
                continue
            news_list.append(
                {
                    "title": f"{stock_name}：{title} - 巨潮资讯公告",
                    "link": "http://static.cninfo.com.cn/" + adjunct_url.lstrip("/"),
                    "pub_date": format_cninfo_timestamp(item.get("announcementTime")),
                    "source_type": "announcement",
                }
            )
        return news_list
    except Exception as e:
        record_source_error(f"搜索巨潮公告失败 ({stock_name}): {e}")
        return []


def search_stock_news(stock_name, stock_code, target_date=None, limit=None, market_news_context=None):
    """Search stock news from direct, topic, Google News, market-news, and announcement sources."""
    if limit is None:
        limit = NEWS_FETCH_LIMIT
    news_list = []
    news_list.extend(
        fetch_eastmoney_stock_news(
            stock_name,
            stock_code,
            target_date=target_date,
            limit=EASTMONEY_STOCK_NEWS_LIMIT,
        )
    )
    news_list.extend(ths_hot_reason_candidates(stock_name, stock_code, target_date=target_date))
    for query, query_limit, source_type in stock_news_queries(stock_name, stock_code):
        try:
            news_list.extend(
                fetch_google_news_rss(query, limit=query_limit, source_type=source_type)
            )
        except Exception as e:
            record_source_error(f"搜索新闻失败 ({stock_name}, {source_type}): {e}")

    news_list.extend(matching_market_news(stock_name, stock_code, market_news_context))
    news_list.extend(
        search_cninfo_announcements(
            stock_name,
            stock_code,
            target_date=target_date,
            limit=ANNOUNCEMENT_FETCH_LIMIT,
        )
    )
    return news_list


def attach_news_candidates(stocks, target_date=None, fetch_limit=None, prompt_limit=None, market_news_context=None):
    """Attach ranked news and announcement candidates for evidence selection."""
    if fetch_limit is None:
        fetch_limit = NEWS_FETCH_LIMIT
    if prompt_limit is None:
        prompt_limit = NEWS_PROMPT_LIMIT
    for i, stock in enumerate(stocks, 1):
        print(f"  [news {i}/{len(stocks)}] {stock['code']} {stock['name']}", file=sys.stderr)
        raw_news = search_stock_news(
            stock["name"],
            stock["code"],
            target_date=target_date,
            limit=fetch_limit,
            market_news_context=market_news_context,
        )
        stock["news"] = rank_news_candidates(
            raw_news,
            stock["name"],
            stock["code"],
            target_date=target_date,
            limit=prompt_limit,
        )
        stock["raw_news_count"] = len(raw_news)
        time.sleep(0.2)
    return stocks


# ── Prompt 构建 ──────────────────────────────────────────────────────────────────

def build_prompt(date_str, gainers, losers, market_news_context=None):
    """
    构建发送给 AI 的 prompt。
    包含：当日涨跌幅、本周涨幅、年初至今涨幅。
    """
    if AI_MODEL == "codebuddy":
        return build_codebuddy_prompt(date_str, gainers, losers, market_news_context=market_news_context)

    top_n = max(len(gainers), len(losers))
    lines = [
        "# 任务",
        f"你是专业财经分析师。请分析 {date_str} {INDEX_DISPLAY_NAME}指数成分股涨跌幅 Top {top_n}。",
        "只能基于下方行情数据、新闻候选和市场/板块快讯做归因；证据链接必须从该股票新闻候选中选取，不要编造链接。",
        "最终只输出一个 JSON 对象，不要输出 Markdown 代码块或额外说明。",
        "",
        "## 数据",
        "",
    ]

    if market_news_context:
        lines += [
            "### 市场/板块快讯候选",
            "这些快讯只用于 market_summary 和板块共性判断；个股 evidence 仍必须从对应股票的新闻候选中选择。",
        ]
        for news in market_news_context[:MARKET_NEWS_PROMPT_LIMIT]:
            title = normalize_inline_text(news.get("title", ""))
            summary = normalize_inline_text(news.get("summary", ""))
            pub_date = normalize_inline_text(news.get("pub_date", ""))
            if summary:
                lines.append(f"- {title} | {summary} | {pub_date}")
            else:
                lines.append(f"- {title} | {pub_date}")
        lines.append("")

    lines += [
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
            category = news_candidate_category(news)
            lines.append(f"  - [{category}] {news.get('title')} | {news.get('link')} | {news.get('pub_date')}")
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
            category = news_candidate_category(news)
            lines.append(f"  - [{category}] {news.get('title')} | {news.get('link')} | {news.get('pub_date')}")
        if not st.get("news"):
            lines.append("  - （暂无候选新闻）")
        lines.append("")

    lines += [
        "",
        "## 要求",
        "1. market_summary 写成一段指数概况，结合市场/板块快讯概括板块分化、资金主线和核心驱动力。",
        "2. gainers_analysis.summary 和 losers_analysis.summary 分别总结板块共性。",
        "3. 每只股票必须给 attribution_type，只能是：直接催化、行业带动、资金交易、弱证据待复核。",
        "4. 原因要结合行业、公司事件、资金风格或基本面；触及涨跌停、ETF风向标、主力资金净买入、融资融券只能作为辅助，不要包装成强因果。",
        "5. 证据优先级：公告/业绩/订单/停产/减持/监管问询 > 权威媒体个股新闻 > 题材归因 > 行业快讯 > 资金/行情描述。",
        "6. evidence 最多 2 条，只能使用该股票新闻候选里的标题、链接和发布时间；没有合适证据时返回空数组，并将 attribution_type 设为弱证据待复核。",
        "7. 必须输出可被 json.loads 直接解析的合法 JSON；字符串内部不要使用未转义的英文双引号，可改用中文引号。",
        "",
        "## 输出 JSON Schema",
        "{",
        f'  "gainers_analysis": {{',
        f'    "summary": "涨幅板总结",',
        f'    "stocks": [{{"code": "000001", "name": "平安银行", "attribution_type": "直接催化", "reason": "…", "evidence": [{{"title": "…", "url": "…", "pub_date": "YYYY-MM-DD HH:MM"}}]}}]',
        f'  }},',
        f'  "losers_analysis": {{',
        f'    "summary": "跌幅板总结",',
        f'    "stocks": [{{"code": "000002", "name": "万科A", "attribution_type": "弱证据待复核", "reason": "…", "evidence": [{{"title": "…", "url": "…", "pub_date": "YYYY-MM-DD HH:MM"}}]}}]',
        f'  }},',
        f'  "market_summary": "当日市场主线总结"',
        "}",
    ]

    return "\n".join(lines)


def build_codebuddy_prompt(date_str, gainers, losers, market_news_context=None):
    """Build a compact line-based prompt for CodeBuddy."""
    top_n = max(len(gainers), len(losers))
    lines = [
        "# 任务",
        f"你是专业财经分析师。请分析 {date_str} {INDEX_DISPLAY_NAME}指数成分股涨跌幅 Top {top_n}。",
        "只能基于下方行情数据、新闻候选和市场/板块快讯做归因，不要编造信息。",
        "最终输出必须是纯文本记录，每行一条，不要 JSON，不要 Markdown，不要代码块，不要空行。",
        "字段分隔符统一使用 TAB。",
        "summary 和 reason 必须是单行文本，不能包含 TAB 或换行。",
        "严格按照以下顺序输出：",
        "MARKET_SUMMARY<TAB>指数概况",
        "GAINERS_SUMMARY<TAB>涨幅板块共性",
        "LOSERS_SUMMARY<TAB>跌幅板块共性",
        f"随后输出 {len(gainers)} 行涨幅股：GAINER<TAB>股票代码<TAB>归因类型<TAB>原因<TAB>证据ID列表",
        f"随后输出 {len(losers)} 行跌幅股：LOSER<TAB>股票代码<TAB>归因类型<TAB>原因<TAB>证据ID列表",
        "每个代码只能出现一次，必须覆盖所有给定代码。",
        "归因类型只能是：直接催化、行业带动、资金交易、弱证据待复核。",
        "公告/业绩/订单/停产/减持/监管问询优先标为直接催化；板块/产业链/题材带动标为行业带动；主力资金、北向、龙虎榜、融资融券标为资金交易；只看到触及涨跌停、ETF风向标、行情描述或证据不足时标为弱证据待复核。",
        "触及涨跌停、ETF风向标、主力资金净买入、融资融券只能作为辅助，不要包装成强因果。",
        "证据ID列表最多 2 个，用英文逗号分隔；只能从该股票下方 NEWS 行选择，不要编造 ID；没有合适证据时第五列留空。",
        "MARKET_NEWS 行只用于 MARKET_SUMMARY、GAINERS_SUMMARY、LOSERS_SUMMARY，不得作为个股证据ID输出。",
        "",
        "## 输出骨架",
        "必须按下列骨架逐行输出，TAG 和股票代码必须保持不变；把“待填写”替换为你的分析。",
        "MARKET_SUMMARY\t待填写",
        "GAINERS_SUMMARY\t待填写",
        "LOSERS_SUMMARY\t待填写",
    ]
    for st in gainers:
        lines.append(f"GAINER\t{st.get('code', '')}\t弱证据待复核\t待填写\t")
    for st in losers:
        lines.append(f"LOSER\t{st.get('code', '')}\t弱证据待复核\t待填写\t")
    lines += [
        "",
        "## 数据",
        "",
    ]

    if market_news_context:
        lines.append("### 市场/板块快讯候选")
        for idx, news in enumerate(market_news_context[:MARKET_NEWS_PROMPT_LIMIT], 1):
            title = normalize_inline_text(news.get("title", ""))
            summary = normalize_inline_text(news.get("summary", ""))
            pub_date = normalize_inline_text(news.get("pub_date", ""))
            if summary:
                title = f"{title}；摘要：{summary}"
            lines.append(f"MARKET_NEWS\tM{idx}\t{pub_date}\t{title}".strip())
        lines.append("")

    lines += [
        f"### Top {len(gainers)} 涨幅股",
    ]

    for i, st in enumerate(gainers, 1):
        chg = f"{st['change_pct']:+.2f}%" if st.get("change_pct") is not None else "（暂无）"
        week = f"{st['week_change']:+.2f}%" if st.get("week_change") is not None else "（暂无）"
        ytd = f"{st['ytd_change']:+.2f}%" if st.get("ytd_change") is not None else "（暂无）"
        lines.append(f"{i}. {st['code']} {st['name']} 当日{chg} 本周{week} 年初至今{ytd}")
        for news_index, news in enumerate(st.get("news", [])[:NEWS_PROMPT_LIMIT], 1):
            evidence_id = f"G{i}-{news_index}"
            title = normalize_inline_text(news.get("title", ""))
            pub_date = normalize_inline_text(news.get("pub_date", ""))
            category = news_candidate_category(news)
            lines.append(f"NEWS\t{evidence_id}\t{pub_date}\t{category}\t{title}".strip())
        if not st.get("news"):
            lines.append("NEWS （暂无候选新闻）")
        lines.append("")

    lines += [
        f"### Top {len(losers)} 跌幅股",
    ]

    for i, st in enumerate(losers, 1):
        chg = f"{st['change_pct']:+.2f}%" if st.get("change_pct") is not None else "（暂无）"
        week = f"{st['week_change']:+.2f}%" if st.get("week_change") is not None else "（暂无）"
        ytd = f"{st['ytd_change']:+.2f}%" if st.get("ytd_change") is not None else "（暂无）"
        lines.append(f"{i}. {st['code']} {st['name']} 当日{chg} 本周{week} 年初至今{ytd}")
        for news_index, news in enumerate(st.get("news", [])[:NEWS_PROMPT_LIMIT], 1):
            evidence_id = f"L{i}-{news_index}"
            title = normalize_inline_text(news.get("title", ""))
            pub_date = normalize_inline_text(news.get("pub_date", ""))
            category = news_candidate_category(news)
            lines.append(f"NEWS\t{evidence_id}\t{pub_date}\t{category}\t{title}".strip())
        if not st.get("news"):
            lines.append("NEWS （暂无候选新闻）")
        lines.append("")

    return "\n".join(lines)


# ── 报告生成 ─────────────────────────────────────────────────────────────────────

def iter_result_stocks(result):
    for section in ("gainers_analysis", "losers_analysis"):
        for item in result.get(section, {}).get("stocks", []) or []:
            yield item


def build_report_quality(result, gainers=None, losers=None, target_date=None, market_news_context=None):
    stocks = list(iter_result_stocks(result))
    source_stocks = {
        stock.get("code", ""): stock
        for stock in (gainers or []) + (losers or [])
    }
    attribution_counts = {item: 0 for item in ATTRIBUTION_TYPES}
    selected_evidence_count = 0
    future_evidence_count = 0
    missing_reason_count = 0
    evidence_source_counts = {
        "google_news": 0,
        "cninfo": 0,
        "eastmoney": 0,
        "sina": 0,
        "stcn": 0,
        "other": 0,
    }

    for item in stocks:
        attribution_type = normalize_attribution_type(
            item.get("attribution_type", ""),
            reason=item.get("reason", ""),
            evidence=item.get("evidence") or [],
        )
        attribution_counts[attribution_type] = attribution_counts.get(attribution_type, 0) + 1
        if not item.get("reason"):
            missing_reason_count += 1
        code = item.get("code", "")
        source_news = [
            news
            for news in source_stocks.get(code, {}).get("news", []) or []
            if news_candidate_in_window(news, target_date=target_date)
        ][:NEWS_EVIDENCE_LIMIT]
        display_evidence = item.get("evidence") or [
            {"title": news.get("title"), "url": news.get("link"), "pub_date": news.get("pub_date")}
            for news in source_news
        ]
        for ev in display_evidence:
            selected_evidence_count += 1
            if news_after_target_date({"pub_date": ev.get("pub_date", "")}, target_date=target_date):
                future_evidence_count += 1
            url = ev.get("url") or ev.get("link") or ""
            if "news.google.com" in url:
                evidence_source_counts["google_news"] += 1
            elif "cninfo.com.cn" in url:
                evidence_source_counts["cninfo"] += 1
            elif "eastmoney.com" in url:
                evidence_source_counts["eastmoney"] += 1
            elif "sina.com.cn" in url:
                evidence_source_counts["sina"] += 1
            elif "stcn.com" in url:
                evidence_source_counts["stcn"] += 1
            else:
                evidence_source_counts["other"] += 1

    candidate_count = sum(
        1
        for stock in (gainers or []) + (losers or [])
        for news in stock.get("news", []) or []
        if news_candidate_in_window(news, target_date=target_date)
    )
    raw_candidate_count = sum(stock.get("raw_news_count", 0) or 0 for stock in (gainers or []) + (losers or []))
    return {
        "stock_count": len(stocks),
        "gainer_count": len(gainers or []),
        "loser_count": len(losers or []),
        "candidate_count": candidate_count,
        "raw_candidate_count": raw_candidate_count,
        "market_news_count": len(market_news_context or []),
        "selected_evidence_count": selected_evidence_count,
        "weak_evidence_count": attribution_counts.get("弱证据待复核", 0),
        "missing_reason_count": missing_reason_count,
        "future_evidence_count": future_evidence_count,
        "attribution_counts": attribution_counts,
        "evidence_source_counts": evidence_source_counts,
    }


def write_csi_status(target_date, result, gainers, losers, market_news_context, report_path=None, latest_path=None):
    project_root = Path(__file__).resolve().parents[1]
    status_dir = project_root / "var" / "csi-status" / INDEX_TYPE
    status_dir.mkdir(parents=True, exist_ok=True)
    quality = build_report_quality(
        result,
        gainers=gainers,
        losers=losers,
        target_date=target_date,
        market_news_context=market_news_context,
    )
    status = {
        "date": target_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "index": INDEX_TYPE,
        "index_display_name": INDEX_DISPLAY_NAME,
        "mode": CSI_RUN_STATS.get("mode", AI_MODEL),
        "ai_model_name": CSI_RUN_STATS.get("ai_model_name", AI_MODEL_NAME),
        "top_n": CSI_RUN_STATS.get("top_n"),
        "codex_error": bool(CSI_RUN_STATS.get("codex_error", False)),
        "fallback_used": bool(CSI_RUN_STATS.get("fallback_used", False)),
        "parse_attempts": int(CSI_RUN_STATS.get("parse_attempts", 0) or 0),
        "codebuddy_parse_errors": CSI_RUN_STATS.get("codebuddy_parse_errors", []),
        "source_error_count": int(CSI_RUN_STATS.get("source_error_count", 0) or 0),
        "news_cutoff": {
            "target_date": target_date,
            "rule": "exclude candidates dated after target_date",
            "lookback_days": NEWS_LOOKBACK_DAYS,
        },
        **quality,
        "output_path": str(report_path) if report_path else "",
        "latest_path": str(latest_path) if latest_path else "",
        "report_sha256": "",
        "publish_commit": "",
    }
    if report_path and Path(report_path).exists():
        status["report_sha256"] = hashlib.sha256(Path(report_path).read_bytes()).hexdigest()
    payload = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
    (status_dir / f"{target_date}.json").write_text(payload + "\n", encoding="utf-8")
    (status_dir / "latest.json").write_text(payload + "\n", encoding="utf-8")
    print(f"[INFO] 已写入 CSI 状态: {status_dir / 'latest.json'}", file=sys.stderr)


def format_report(result, target_date, gainers=None, losers=None):
    """
    生成报告 Markdown。
    如果传入 gainers/losers，则从原始数据获取涨跌幅百分比和扩展数据。
    """
    top_n = max(len(gainers or []), len(losers or []))
    quality = build_report_quality(result, gainers=gainers, losers=losers, target_date=target_date)

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

    def fallback_evidence_for_code(code):
        return [
            {"title": news.get("title"), "url": news.get("link"), "pub_date": news.get("pub_date")}
            for news in [
                item
                for item in news_map.get(code, [])
                if news_candidate_in_window(item, target_date=target_date)
            ][:2]
        ]

    def attribution_for_stock(code, item):
        evidence = item.get("evidence") or fallback_evidence_for_code(code)
        return normalize_attribution_type(
            item.get("attribution_type", ""),
            reason=item.get("reason", ""),
            evidence=evidence,
        )

    def append_stock_details(lines, stocks, section):
        ai_items = analysis_by_code(section)
        for stock in stocks or []:
            code = stock.get("code", "")
            name = stock.get("name", "")
            item = ai_items.get(code, {})
            evidence = item.get("evidence") or fallback_evidence_for_code(code)
            attribution_type = attribution_for_stock(code, item)

            lines += [
                "",
                f"### {name}（{code}）",
                "",
                f"**归因类型：** {attribution_type}",
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
        f"# {INDEX_DISPLAY_NAME}涨跌分析 — {target_date}",
        f"",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**分析基于：** {INDEX_DISPLAY_NAME}指数成分股涨跌幅 top{top_n}  ",
        f"**新闻截止：** 仅使用不晚于 {target_date} 的候选新闻，目标日之后信息不进入个股证据  ",
        (
            f"**数据质量：** 候选新闻 {quality['candidate_count']} 条；"
            f"入选证据 {quality['selected_evidence_count']} 条；"
            f"弱证据待复核 {quality['weak_evidence_count']} 只；"
            f"未来日期证据 {quality['future_evidence_count']} 条"
        ),
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
        f"| 排名 | 股票代码 | 股票名称 | 归因类型 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |",
        f"|------|----------|----------|----------|--------|----------|--------------|",
    ]

    gainer_ai_items = analysis_by_code("gainers_analysis")
    for i, st in enumerate(gainers or [], 1):
        code = st.get("code", "")
        name = st.get("name", "")
        attribution_type = attribution_for_stock(code, gainer_ai_items.get(code, {}))
        lines.append(
            f"| {i} | {code} | {name} | {attribution_type} | {fmt_pct(change_map.get(code))} | "
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
        f"| 排名 | 股票代码 | 股票名称 | 归因类型 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |",
        f"|------|----------|----------|----------|--------|----------|--------------|",
    ]

    loser_ai_items = analysis_by_code("losers_analysis")
    for i, st in enumerate(losers or [], 1):
        code = st.get("code", "")
        name = st.get("name", "")
        attribution_type = attribution_for_stock(code, loser_ai_items.get(code, {}))
        lines.append(
            f"| {i} | {code} | {name} | {attribution_type} | {fmt_pct(change_map.get(code))} | "
            f"{fmt_pct(week_map.get(code))} | {fmt_pct(ytd_map.get(code))} |"
        )

    append_stock_details(lines, losers, "losers_analysis")

    lines += ["", "---", "", "*报告由 AI 生成，仅供参考。*"]

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="指数涨跌分析（支持沪深300/中证500/中证1000）")
    parser.add_argument("--index", default="csi300", choices=list(_INDEX_PROFILES.keys()),
                        help="指数类型: csi300, csi500, csi1000 (default: csi300)")
    parser.add_argument("output_dir", nargs="?", default=None, help="报告输出目录（兼容旧 run 脚本）")
    parser.add_argument("--date", default=None, help="分析日期 (YYYY-MM-DD)，默认最近交易日")
    parser.add_argument("--top", type=int, default=None, help="涨跌榜选取数量 (default: 20)")
    parser.add_argument("--output-dir", dest="output_dir_opt", default=None, help="报告输出目录")
    parser.add_argument("--skip-extended", action="store_true", help="跳过扩展数据获取（本周、YTD）")
    parser.add_argument("--skip-ai", action="store_true", help="跳过 AI 分析（快速生成基础报告）")
    parser.add_argument("--no-news", action="store_true", help="跳过新闻候选获取")
    parser.add_argument("--input-json", default=None, help="从JSON文件读取预计算数据（跳过API调用）")
    args = parser.parse_args()

    # 配置指数类型（必须在读取其他全局变量之前）
    configure_index(args.index)

    top_n = args.top or TOP_N_DEFAULT

    if args.date:
        target_date = args.date
    else:
        target_date = get_trading_dates(1, include_today=True)[0]

    reset_csi_run_stats(target_date=target_date, top_n=top_n, skip_ai=args.skip_ai)
    print(f"[INFO] 开始分析 {target_date} ...", file=sys.stderr)

    # 1. 获取基础数据
    if args.input_json:
        # 从JSON文件读取
        print(f"[INFO] 从JSON文件读取数据: {args.input_json}", file=sys.stderr)
        with open(args.input_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        gainers = data.get("gainers", [])[:top_n]
        losers  = data.get("losers", [])[:top_n]
        print(f"[INFO] 读取到涨幅榜 {len(gainers)} 只、跌幅榜 {len(losers)} 只", file=sys.stderr)
    else:
        # 从API获取
        gainers = get_top_gainers(target_date, top_n)
        losers  = get_top_losers(target_date, top_n)

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

    market_news_context = []
    if not args.no_news:
        print("[INFO] 开始获取新闻候选...", file=sys.stderr)
        market_news_context = fetch_eastmoney_market_news(target_date=target_date)
        if market_news_context:
            print(f"[INFO] 获取到东方财富7x24快讯 {len(market_news_context)} 条", file=sys.stderr)
        gainers = attach_news_candidates(
            gainers,
            target_date=target_date,
            market_news_context=market_news_context,
        )
        losers  = attach_news_candidates(
            losers,
            target_date=target_date,
            market_news_context=market_news_context,
        )
        print("[INFO] 新闻候选获取完成", file=sys.stderr)
    else:
        print("[INFO] 跳过新闻候选获取", file=sys.stderr)

    # 3. 构建 prompt 并调用 AI（或跳过）
    if args.skip_ai:
        print(f"[INFO] 跳过 AI 分析，生成基础报告...", file=sys.stderr)
        result = build_result(
            gainers,
            losers,
            "（AI 分析跳过，请手动补充）",
            "（AI 分析跳过，请手动补充）",
            "（AI 分析跳过，请手动补充）",
            default_reason="（AI 分析跳过）",
        )
    else:
        prompt = build_prompt(target_date, gainers, losers, market_news_context=market_news_context)
        print(f"[INFO] 调用 AI ({AI_MODEL}) ...", file=sys.stderr)
        if AI_MODEL == "codebuddy":
            result = run_codebuddy_analysis(prompt, gainers, losers)
        else:
            raw = call_ai(prompt, max_tokens=4096, expect_json=True)

            # 4. 解析 JSON（带预处理）
            try:
                result = parse_ai_json(raw)
            except Exception as e:
                CSI_RUN_STATS["codex_error"] = True
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
        latest_path = out_dir / "latest.md"
        latest_path.write_text(report + "\n", encoding="utf-8")
        print(f"[INFO] 已写入报告: {report_path}", file=sys.stderr)
        write_csi_status(
            target_date,
            result,
            gainers,
            losers,
            market_news_context,
            report_path=report_path,
            latest_path=latest_path,
        )
    else:
        print(report)
        write_csi_status(target_date, result, gainers, losers, market_news_context)


if __name__ == "__main__":
    main()
