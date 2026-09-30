#!/usr/bin/env python3
"""每周投资总结（weekly-review）。

定位：回顾型全市场周总结。汇总本周一~周五（实际交易日）的：
  1. 指数周度表现（沪深300/中证500/中证1000/上证指数，周K口径直接拉取，数值权威）
  2. A股板块一周热点（权威 5 日榜 + 本周日报聚合：累计涨幅/连续上榜/主力净流入累计）
  3. 全市场个股周度 Top 涨跌（东方财富 5 日涨跌幅榜）+ 本周 CSI 日报高频强势/弱势股
  4. 美股板块一周表现（本周美股板块日报聚合）
  5. 股票池个股一周要闻（本周股票池日报合并精选）

设计原则（见 2026-09-30 设计方案）：
  - 数值双通道：周度数值以东方财富接口直拉为权威；日报 Markdown 仅解析作
    连续性/净流入累计/归因证据，解析失败自动降级，不阻塞发布。
  - AI 仅做综述与下周关注，失败降级为规则版，mode 记录在 status。
  - 不改动任何现有日报脚本。

用法：
  python3 scripts/weekly_review.py --project-root /home/ME/finance-news-digest \
      --output-dir published/weekly-review --status-dir var/weekly-review-status
可选：--date YYYY-MM-DD（默认=今天，周窗口自动取其前一个完整周）
      --skip-ai（纯规则版，用于诊断）
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ── 常量 ────────────────────────────────────────────────────────────────────────

EASTMONEY_PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_PUSH2_DELAY = "https://push2delay.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

PUSH2_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# 指数 secid → 展示名（周度表现章节）
INDEXES = [
    ("1.000001", "上证指数"),
    ("1.000300", "沪深300"),
    ("1.000905", "中证500"),
    ("1.000852", "中证1000"),
]

# 全市场 A 股（东财标准 fs），用于个股 5 日涨跌幅榜
FS_ALL_A = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
FS_INDUSTRY = "m:90+t:2"
FS_CONCEPT = "m:90+t:3"

DEFAULT_MODEL = ""  # 空 = 使用 CodeBuddy 全局模型
NODE_FALLBACK = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/bin/node"
CODEBUDDY_FALLBACK = (
    "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/lib/node_modules/"
    "@tencent-ai/codebuddy-code/bin/codebuddy"
)

SOURCE_ERRORS = []


# ── 基础工具 ────────────────────────────────────────────────────────────────────

def record_source_error(message):
    SOURCE_ERRORS.append(message)
    print(f"[WARN] {message}", file=sys.stderr)


def request_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or PUSH2_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_number(value):
    """东财字段 → float；'-'/''/None → None。"""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "—"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_cn_amount(text):
    """'2.70亿' / '1487.82万' / '17.32亿美元' / '-1.2亿' → 元；失败返回 None。"""
    if not text:
        return None
    text = str(text).strip().replace(",", "").replace("美元", "").replace("港元", "")
    m = re.match(r"^([+-]?[\d.]+)\s*(万亿|亿|万)?$", text)
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2)
    if unit == "万亿":
        value *= 1e12
    elif unit == "亿":
        value *= 1e8
    elif unit == "万":
        value *= 1e4
    return value


def fmt_pct(value, digits=2, signed=True):
    if value is None:
        return "—"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.{digits}f}%"


def fmt_amount_yuan(value):
    """元 → 'X.XX亿' / 'X.XX万' 展示。"""
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1e8:
        return f"{sign}{value / 1e8:.2f}亿"
    if value >= 1e4:
        return f"{sign}{value / 1e4:.2f}万"
    return f"{sign}{value:.0f}"


def atomic_write_text(path: Path, text: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload):
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


# ── 周窗口 ──────────────────────────────────────────────────────────────────────

def compute_week_window(run_date):
    """运行日 → 覆盖的 A 股周窗口 (monday..friday)。

    周六运行覆盖本周（monday=run-5）；周日/周一运行覆盖上一个完整周。
    """
    end = run_date - dt.timedelta(days=1)
    while end.weekday() != 4:  # 最近一个周五
        end -= dt.timedelta(days=1)
    monday = end - dt.timedelta(days=4)
    return monday, end


def week_dates(monday, friday):
    return [monday + dt.timedelta(days=i) for i in range(5)]


# ── 指数周度表现（数值权威：东财日K直接计算）────────────────────────────────────

def fetch_index_kline(secid, end_date, lmt=40):
    """日K（指数直接用），返回 [{date, open, high, low, close, amount}]；带重试。"""
    query = urllib.parse.urlencode(
        {
            "secid": secid,
            "klt": "101",
            "fqt": "1",
            "beg": (end_date - dt.timedelta(days=90)).strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "lmt": str(lmt),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
        }
    )
    last_error = None
    for attempt in range(3):
        try:
            payload = request_json(EASTMONEY_KLINE + "?" + query)
            klines = ((payload.get("data") or {}).get("klines")) or []
            break
        except Exception as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"日K重试3次仍失败: {last_error}")
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]),
            }
        )
    return rows


def index_week_metrics(secid, name, monday, friday):
    """窗口内实际交易日由 K 线日期决定；周涨幅=窗口末日收盘/窗口前一日收盘-1。"""
    rows = fetch_index_kline(secid, friday)
    if not rows:
        record_source_error(f"{name} 日K获取失败")
        return None
    window = [r for r in rows if monday.isoformat() <= r["date"] <= friday.isoformat()]
    if not window:
        record_source_error(f"{name} 周窗口 {monday}~{friday} 内无K线（假期？）")
        return None
    before = [r for r in rows if r["date"] < monday.isoformat()]
    base_close = before[-1]["close"] if before else window[0]["open"]
    week_change = (window[-1]["close"] / base_close - 1) * 100

    # 上一个等长窗口（同一批日历日的前一周）做成交对比
    prev_days = len(window)
    prev = before[-prev_days:] if len(before) >= prev_days else before
    avg_amount = sum(r["amount"] for r in window) / len(window)
    prev_avg_amount = sum(r["amount"] for r in prev) / len(prev) if prev else None

    return {
        "name": name,
        "secid": secid,
        "trading_dates": [r["date"] for r in window],
        "week_change": round(week_change, 2),
        "close": window[-1]["close"],
        "high": max(r["high"] for r in window),
        "low": min(r["low"] for r in window),
        "avg_amount": avg_amount,
        "prev_avg_amount": prev_avg_amount,
        "amount_change_pct": (
            (avg_amount / prev_avg_amount - 1) * 100 if prev_avg_amount else None
        ),
    }


# ── 东财 5 日榜（个股/板块，权威数值）────────────────────────────────────────────

def fetch_week_rank(fs, fields, limit=12, descending=True):
    """按 5 日涨跌幅（f109）排序的 clist 榜单。"""
    query = urllib.parse.urlencode(
        {
            "pn": "1",
            "pz": str(limit),
            "po": "1" if descending else "0",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f109",
            "fs": fs,
            "fields": fields,
        }
    )
    for endpoint in (EASTMONEY_PUSH2, EASTMONEY_PUSH2_DELAY):
        try:
            payload = request_json(endpoint + "?" + query)
            rows = (payload.get("data") or {}).get("diff") or []
            if rows:
                return rows
        except Exception as exc:
            record_source_error(f"东财5日榜({fs})请求失败({endpoint}): {exc}")
        time.sleep(0.3)
    return []


def stock_week_movers(limit=10):
    fields = "f12,f14,f109,f3,f100,f164"
    out = {"gainers": [], "losers": []}
    for key, desc in (("gainers", True), ("losers", False)):
        rows = fetch_week_rank(FS_ALL_A, fields, limit=limit, descending=desc)
        for item in rows:
            change5 = parse_number(item.get("f109"))
            if change5 is None:
                continue
            out[key].append(
                {
                    "code": str(item.get("f12", "")),
                    "name": str(item.get("f14", "")),
                    "week_change": change5,
                    "industry": str(item.get("f100", "") or "—"),
                    "main_inflow_5d": parse_number(item.get("f164")),
                }
            )
    if not out["gainers"] and not out["losers"]:
        record_source_error("全市场5日涨跌幅榜为空（f109 字段可能不可用），该章节将降级")
    return out


def board_week_rank():
    fields = "f12,f14,f109,f6,f164"
    result = {}
    for key, fs, label in (("industry", FS_INDUSTRY, "行业板块"), ("concept", FS_CONCEPT, "概念板块")):
        rows = fetch_week_rank(fs, fields, limit=10, descending=True)
        boards = []
        for item in rows:
            change5 = parse_number(item.get("f109"))
            if change5 is None:
                continue
            boards.append(
                {
                    "code": str(item.get("f12", "")),
                    "name": str(item.get("f14", "")),
                    "week_change": change5,
                    "amount": parse_number(item.get("f6")),
                    "main_inflow_5d": parse_number(item.get("f164")),
                }
            )
        result[key] = {"label": label, "boards": boards}
    return result


# ── 日报 Markdown 解析 ──────────────────────────────────────────────────────────

def split_markdown_tables(lines):
    """把行序列切成 [(header_cells, rows_before_next_blank_or_heading)]。"""
    tables = []
    current = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue  # 分隔行
            if current is None:
                current = {"header": cells, "rows": []}
            else:
                current["rows"].append(cells)
        else:
            if current is not None:
                tables.append(current)
                current = None
    if current is not None:
        tables.append(current)
    return tables


def col_index(header, *keywords):
    for kw in keywords:
        for i, cell in enumerate(header):
            if kw in cell:
                return i
    return None


def parse_pct_cell(text):
    if text is None:
        return None
    return parse_number(str(text).replace("%", "").replace("+", ""))


def existing_report_dates(report_dir, window_dates):
    """返回窗口内实际存在的日报路径 {date_str: path}。"""
    found = {}
    for d in window_dates:
        path = Path(report_dir) / f"{d.isoformat()}.md"
        if path.exists():
            found[d.isoformat()] = path
    return found


def parse_sector_hotspots_daily(path):
    """A股板块热点日报 → [{board, board_type, change_pct, main_inflow, attribution, lead_stock}]。

    解析失败返回 []（降级不影响权威通道）。
    """
    items = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        record_source_error(f"板块日报读取失败 {path}: {exc}")
        return []
    for table in split_markdown_tables(lines):
        b_idx = col_index(table["header"], "板块")
        c_idx = col_index(table["header"], "涨跌幅")
        if b_idx is None or c_idx is None or "板块" not in "|".join(table["header"]):
            continue
        if col_index(table["header"], "代理ETF") is not None:
            continue  # 美股表，不在本解析器处理
        t_idx = col_index(table["header"], "类型")
        i_idx = col_index(table["header"], "主力净流入")
        a_idx = col_index(table["header"], "归因类型")
        l_idx = col_index(table["header"], "领涨股")
        for row in table["rows"]:
            if len(row) <= max(x for x in (b_idx, c_idx) if x is not None):
                continue
            name = row[b_idx]
            if not name or name in ("—", "-"):
                continue
            items.append(
                {
                    "board": name,
                    "board_type": row[t_idx] if t_idx is not None else "",
                    "change_pct": parse_pct_cell(row[c_idx]),
                    "main_inflow": parse_cn_amount(row[i_idx]) if i_idx is not None else None,
                    "attribution": row[a_idx] if a_idx is not None and a_idx < len(row) else "",
                    "lead_stock": row[l_idx] if l_idx is not None and l_idx < len(row) else "",
                }
            )
    return items


def aggregate_sector_week(daily_paths):
    """聚合本周板块日报：累计涨幅（复利）、上榜天数、主力净流入累计。"""
    per_board = {}
    for date_str, path in sorted(daily_paths.items()):
        for item in parse_sector_hotspots_daily(path):
            entry = per_board.setdefault(
                item["board"],
                {
                    "board": item["board"],
                    "board_type": item["board_type"],
                    "days": 0,
                    "cum_return": 1.0,
                    "main_inflow_sum": 0.0,
                    "has_inflow": False,
                    "attributions": [],
                    "lead_stock": "",
                    "dates": [],
                },
            )
            entry["days"] += 1
            entry["dates"].append(date_str)
            if item["change_pct"] is not None:
                entry["cum_return"] *= 1 + item["change_pct"] / 100
            if item["main_inflow"] is not None:
                entry["main_inflow_sum"] += item["main_inflow"]
                entry["has_inflow"] = True
            if item["attribution"]:
                entry["attributions"].append(item["attribution"])
            if item["lead_stock"]:
                entry["lead_stock"] = item["lead_stock"]
    result = []
    for entry in per_board.values():
        entry["cum_change"] = (entry["cum_return"] - 1) * 100
        entry["top_attribution"] = (
            max(set(entry["attributions"]), key=entry["attributions"].count)
            if entry["attributions"]
            else ""
        )
        result.append(entry)
    return result


def parse_us_sector_daily(path):
    """美股板块日报 → [{sector, etf, change_pct, attribution}]。"""
    items = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        record_source_error(f"美股日报读取失败 {path}: {exc}")
        return []
    for table in split_markdown_tables(lines):
        if "代理ETF" not in "|".join(table["header"]):
            continue
        s_idx = col_index(table["header"], "板块")
        e_idx = col_index(table["header"], "代理ETF")
        c_idx = col_index(table["header"], "涨跌幅")
        a_idx = col_index(table["header"], "归因类型")
        if s_idx is None or c_idx is None:
            continue
        for row in table["rows"]:
            if len(row) <= c_idx:
                continue
            sector = row[s_idx]
            if not sector or sector in ("—", "-"):
                continue
            items.append(
                {
                    "sector": sector,
                    "etf": row[e_idx] if e_idx is not None and e_idx < len(row) else "",
                    "change_pct": parse_pct_cell(row[c_idx]),
                    "attribution": row[a_idx] if a_idx is not None and a_idx < len(row) else "",
                }
            )
    return items


def aggregate_us_week(daily_paths):
    per_sector = {}
    for date_str, path in sorted(daily_paths.items()):
        for item in parse_us_sector_daily(path):
            entry = per_sector.setdefault(
                item["sector"],
                {"sector": item["sector"], "etf": item["etf"], "days": 0,
                 "cum_return": 1.0, "attributions": []},
            )
            entry["days"] += 1
            if item["change_pct"] is not None:
                entry["cum_return"] *= 1 + item["change_pct"] / 100
            if item["attribution"]:
                entry["attributions"].append(item["attribution"])
    result = []
    for entry in per_sector.values():
        entry["cum_change"] = (entry["cum_return"] - 1) * 100
        entry["top_attribution"] = (
            max(set(entry["attributions"]), key=entry["attributions"].count)
            if entry["attributions"]
            else ""
        )
        result.append(entry)
    return result


def parse_stock_pool_daily(path):
    """股票池日报 → {stock_name: [{title, url, source, date, summary}]}。"""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        record_source_error(f"股票池日报读取失败 {path}: {exc}")
        return {}
    stocks = {}
    current = None
    item_re = re.compile(
        r"^-\s*\[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)\s*—\s*(?P<source>.*?)\s*·\s*(?P<date>\d{4}-\d{2}-\d{2})"
    )
    for line in lines:
        heading = re.match(r"^##\s+\d+\.\s+(?P<name>[^(（]+?)\s*[（(](?P<ticker>[^)）]+)[)）]\s*$", line.strip())
        if heading:
            current = heading.group("name").strip()
            stocks.setdefault(current, [])
            continue
        if current is None:
            continue
        m = item_re.match(line.strip())
        if m:
            stocks[current].append(m.groupdict())
            continue
        stripped = line.strip()
        if stripped and not stripped.startswith(("-", "#", ">")) and stocks[current]:
            last = stocks[current][-1]
            if not last.get("summary"):
                last["summary"] = stripped
    return stocks


def aggregate_stock_pool_week(daily_paths, per_stock_limit=3):
    """合并本周股票池日报：按标题近似去重，保留每只股票最新 N 条。"""
    merged = {}
    for date_str, path in sorted(daily_paths.items()):
        for name, items in parse_stock_pool_daily(path).items():
            bucket = merged.setdefault(name, [])
            for item in items:
                item["_date"] = date_str
                bucket.append(item)

    def norm_title(t):
        return re.sub(r"[\s\W_]+", "", (t or "").lower())[:40]

    result = {}
    for name, items in merged.items():
        seen = set()
        unique = []
        for item in sorted(items, key=lambda x: (x["_date"],), reverse=True):
            key = norm_title(item["title"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        result[name] = unique[:per_stock_limit]
    return result


def parse_csi_daily(path, index_label):
    """CSI 指数日报 → [{code, name, direction, change_pct, week_change, attribution}]。

    方向由表前最近的标题（涨幅分析/跌幅分析）判定。
    """
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        record_source_error(f"CSI日报读取失败 {path}: {exc}")
        return []
    items = []
    direction = "gainer"
    current_header = None
    current_rows = None

    def flush():
        if current_header is None:
            return
        code_i = col_index(current_header, "代码")
        name_i = col_index(current_header, "名称")
        chg_i = col_index(current_header, "涨跌幅")
        wk_i = col_index(current_header, "本周涨幅")
        attr_i = col_index(current_header, "归因类型")
        if code_i is None or chg_i is None:
            return
        for row in current_rows:
            if len(row) <= max(code_i, chg_i):
                continue
            items.append(
                {
                    "index": index_label,
                    "code": row[code_i],
                    "name": row[name_i] if name_i is not None else "",
                    "direction": direction,
                    "change_pct": parse_pct_cell(row[chg_i]),
                    "week_change": parse_pct_cell(row[wk_i]) if wk_i is not None else None,
                    "attribution": row[attr_i] if attr_i is not None and attr_i < len(row) else "",
                }
            )

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if "跌幅" in stripped:
                flush()
                direction = "loser"
                current_header = current_rows = None
            elif "涨幅" in stripped and "分析" in stripped:
                flush()
                direction = "gainer"
                current_header = current_rows = None
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            if current_header is None:
                if "股票代码" in "|".join(cells):
                    current_header = cells
                    current_rows = []
            else:
                current_rows.append(cells)
        else:
            flush()
            current_header = current_rows = None
    flush()
    return items


def aggregate_csi_week(daily_paths, index_label):
    """本周 CSI 日报聚合：出现≥2 天的持续强势/弱势股 + 最新周涨幅。"""
    per_stock = {}
    for date_str, path in sorted(daily_paths.items()):
        for item in parse_csi_daily(path, index_label):
            key = item["code"]
            entry = per_stock.setdefault(
                key,
                {"code": item["code"], "name": item["name"], "gain_days": 0,
                 "lose_days": 0, "week_change": None, "attribution": ""},
            )
            if item["direction"] == "gainer":
                entry["gain_days"] += 1
            else:
                entry["lose_days"] += 1
            if item["week_change"] is not None:
                entry["week_change"] = item["week_change"]
            if item["attribution"]:
                entry["attribution"] = item["attribution"]
    strong = [e for e in per_stock.values() if e["gain_days"] >= 2]
    weak = [e for e in per_stock.values() if e["lose_days"] >= 2]
    strong.sort(key=lambda e: (-(e["week_change"] if e["week_change"] is not None else -999)))
    weak.sort(key=lambda e: (e["week_change"] if e["week_change"] is not None else 999))
    return {"strong": strong[:10], "weak": weak[:10]}


# ── AI 周度综述（CodeBuddy；失败降级规则版）────────────────────────────────────

def call_codebuddy(prompt, model="", timeout=600):
    exe = None
    from shutil import which

    exe = which("codebuddy")
    if exe:
        cmd = [exe, "-p", "--output-format", "text", "--input-format", "text"]
    else:
        cmd = [NODE_FALLBACK, CODEBUDDY_FALLBACK, "-p", "--output-format", "text", "--input-format", "text"]
    if model:
        cmd.append(f"--model={model}")
    cmd.append(prompt)
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "no output")[-2000:])
    text = (proc.stdout or "").strip()
    if not text:
        raise RuntimeError("codebuddy 返回空内容")
    return text


def load_protocol(project_root):
    path = Path(project_root) / "prompts" / "weekly_review.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return "请用专业财经语言输出，分 `## 一周综述` 与 `## 下周关注` 两节。"


def strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n", "", text)
    text = re.sub(r"\n```$", "", text)
    return text.strip()


def parse_ai_sections(raw):
    """返回 (summary_text, outlook_lines)；协议：`## 一周综述` + `## 下周关注`。"""
    summary = outlook = ""
    sections = re.split(r"(?m)^##\s+", strip_code_fences(raw))
    for part in sections:
        if part.startswith("一周综述"):
            summary = "\n".join(l for l in part.splitlines()[0:1] + part.splitlines()[1:] if l.strip())
            summary = summary.replace("一周综述", "", 1).strip()
        elif part.startswith("下周关注"):
            lines = [l.strip().lstrip("-• ").strip() for l in part.splitlines()[1:] if l.strip()]
            outlook = "\n".join(f"{i}. {l}" for i, l in enumerate(lines[:6], 1))
    return summary, outlook


def ai_summary(payload, model):
    protocol = load_protocol(PROJECT_ROOT_ARG)
    data_json = json.dumps(payload, ensure_ascii=False, indent=1)
    prompt = (
        f"{protocol}\n\n## 本周聚合数据（唯一事实来源，禁止使用数据之外的信息）\n\n"
        f"```json\n{data_json}\n```\n\n"
        "请严格按协议输出 `## 一周综述` 与 `## 下周关注` 两节，不要输出其他内容。"
    )
    return parse_ai_sections(call_codebuddy(prompt, model))


def rules_summary(payload):
    idx = payload.get("indexes") or []
    bits = []
    for m in idx:
        amt = ""
        if m.get("amount_change_pct") is not None:
            amt = f"，日均成交较上周{'放大' if m['amount_change_pct'] >= 0 else '萎缩'} {abs(m['amount_change_pct']):.1f}%"
        bits.append(f"{m['name']}{fmt_pct(m['week_change'])}{amt}")
    top_boards = payload.get("sector_week_top") or []
    board_txt = "、".join(f"{b['board']}({fmt_pct(b['cum_change'])})" for b in top_boards[:5]) or "—"
    if bits:
        index_txt = "；".join(bits) + "。"
    else:
        index_txt = "指数周度数据本轮不可用（接口临时失败，详见 status）。"
    summary = (
        "本周（" + payload["window"]["start"] + " 至 " + payload["window"]["end"] + "，"
        + str(payload["window"].get("trading_days", 5)) + "个交易日）规则版综述："
        + index_txt
        + f"板块层面，{board_txt} 等方向周度表现领先。"
        "本条为规则生成，AI 综述未启用或生成失败。"
    )
    outlook = "3. 详见各分项数据（规则版不含 AI 提炼的下周关注）"
    return summary, outlook


# ── 渲染 ────────────────────────────────────────────────────────────────────────

def escape_cell(value):
    return str(value).replace("|", "\\|")


def render_report(report_date, window, indexes, boards_rank, sector_week,
                  movers, csi_week, us_week, pool_week, summary, outlook, mode):
    lines = []
    lines.append(f"# 每周投资总结 — {report_date}")
    lines.append("")
    lines.append(
        f"**窗口：** {window['start']} ~ {window['end']}（{len(window['trading_dates'])} 个交易日）  "
    )
    lines.append(f"**生成时间：** {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
    lines.append(f"**生成模式：** `{mode}`  ")
    lines.append("**口径：** 指数/个股/板块周度数值来自东方财富 5 日与日K接口；板块连续性与净流入累计来自本周日报聚合")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 一周综述
    lines.append("## 一、一周综述")
    lines.append("")
    lines.append(summary or "（暂无）")
    lines.append("")

    # 指数周度表现
    lines.append("## 二、指数周度表现")
    lines.append("")
    lines.append("| 指数 | 周涨跌幅 | 收盘 | 周内最高 | 周内最低 | 日均成交额 | 较上周 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for m in indexes or []:
        amt = fmt_amount_yuan(m["avg_amount"])
        amt_chg = fmt_pct(m.get("amount_change_pct")) if m.get("amount_change_pct") is not None else "—"
        lines.append(
            f"| {m['name']} | {fmt_pct(m['week_change'])} | {m['close']:.2f} | "
            f"{m['high']:.2f} | {m['low']:.2f} | {amt} | {amt_chg} |"
        )
    if not indexes:
        lines.append("| — | — | — | — | — | — | — |")
    lines.append("")

    # A股板块一周热点
    lines.append("## 三、A股板块一周热点")
    lines.append("")
    lines.append("### 3.1 板块 5 日涨幅榜（东方财富口径）")
    lines.append("")
    for key in ("industry", "concept"):
        section = (boards_rank or {}).get(key) or {}
        lines.append(f"**{section.get('label', key)} Top10**")
        lines.append("")
        lines.append("| 板块 | 5日涨跌幅 | 5日主力净流入 |")
        lines.append("|---|---:|---:|")
        for b in section.get("boards", [])[:10]:
            lines.append(
                f"| {escape_cell(b['name'])} | {fmt_pct(b['week_change'])} | "
                f"{fmt_amount_yuan(b.get('main_inflow_5d'))} |"
            )
        if not section.get("boards"):
            lines.append("| — | — | — |")
        lines.append("")
    lines.append("### 3.2 本周日报持续上榜板块（连续性信号，日报聚合口径）")
    lines.append("")
    lines.append("| 板块 | 类型 | 上榜天数 | 日报累计涨幅 | 主力净流入累计 | 主要归因 |")
    lines.append("|---|---|---:|---:|---:|---|")
    for b in (sector_week or [])[:12]:
        lines.append(
            f"| {escape_cell(b['board'])} | {escape_cell(b['board_type'])} | {b['days']} | "
            f"{fmt_pct(b['cum_change'])} | {fmt_amount_yuan(b['main_inflow_sum'] if b['has_inflow'] else None)} | "
            f"{escape_cell(b['top_attribution'])} |"
        )
    if not sector_week:
        lines.append("| — | — | — | — | — | — |")
    lines.append("")

    # 个股周度
    lines.append("## 四、全市场个股周度 Top 涨跌")
    lines.append("")
    lines.append("### 4.1 5 日涨幅 Top10（东方财富口径）")
    lines.append("")
    lines.append("| 代码 | 名称 | 5日涨跌幅 | 行业 | 5日主力净流入 |")
    lines.append("|---|---|---:|---|---:|")
    for s in (movers or {}).get("gainers", []):
        lines.append(
            f"| {s['code']} | {escape_cell(s['name'])} | {fmt_pct(s['week_change'])} | "
            f"{escape_cell(s['industry'])} | {fmt_amount_yuan(s.get('main_inflow_5d'))} |"
        )
    if not (movers or {}).get("gainers"):
        lines.append("| — | — | — | — | — |")
    lines.append("")
    lines.append("### 4.2 5 日跌幅 Top10（东方财富口径）")
    lines.append("")
    lines.append("| 代码 | 名称 | 5日涨跌幅 | 行业 | 5日主力净流入 |")
    lines.append("|---|---|---:|---|---:|")
    for s in (movers or {}).get("losers", []):
        lines.append(
            f"| {s['code']} | {escape_cell(s['name'])} | {fmt_pct(s['week_change'])} | "
            f"{escape_cell(s['industry'])} | {fmt_amount_yuan(s.get('main_inflow_5d'))} |"
        )
    if not (movers or {}).get("losers"):
        lines.append("| — | — | — | — | — |")
    lines.append("")
    lines.append("### 4.3 本周 CSI 日报持续强势/弱势股（≥2天上榜，日报聚合口径）")
    lines.append("")
    for label, key in (("持续强势", "strong"), ("持续弱势", "weak")):
        rows = (csi_week or {}).get(key) or []
        lines.append(f"**{label}（按最新本周涨幅排序）**")
        lines.append("")
        lines.append("| 代码 | 名称 | 上榜(涨/跌)天数 | 最新本周涨幅 | 最新归因 |")
        lines.append("|---|---|---|---:|---|")
        for s in rows:
            days = f"{s['gain_days']}涨/{s['lose_days']}跌"
            lines.append(
                f"| {s['code']} | {escape_cell(s['name'])} | {days} | "
                f"{fmt_pct(s.get('week_change'))} | {escape_cell(s['attribution'])} |"
            )
        if not rows:
            lines.append("| — | — | — | — | — |")
        lines.append("")

    # 美股板块
    lines.append("## 五、美股板块一周表现（日报聚合口径）")
    lines.append("")
    lines.append("| 板块 | 代理ETF | 上榜天数 | 日报累计涨跌幅 | 主要归因 |")
    lines.append("|---|---|---:|---:|---|")
    for s in sorted(us_week or [], key=lambda x: -x["cum_change"])[:15]:
        lines.append(
            f"| {escape_cell(s['sector'])} | {escape_cell(s['etf'])} | {s['days']} | "
            f"{fmt_pct(s['cum_change'])} | {escape_cell(s['top_attribution'])} |"
        )
    if not us_week:
        lines.append("| — | — | — | — | — |")
    lines.append("")
    lines.append("> 注：累计涨跌幅为本周各日报单日涨跌幅复利累乘，代理 ETF 口径存在跟踪误差。")
    lines.append("")

    # 股票池
    lines.append("## 六、股票池个股一周要闻精选")
    lines.append("")
    if pool_week:
        for idx, (name, items) in enumerate(sorted(pool_week.items()), 1):
            lines.append(f"### {idx}. {name}")
            lines.append("")
            if not items:
                lines.append("本周暂无重要新闻")
            else:
                for item in items:
                    lines.append(
                        f"- [{item['title']}]({item['url']}) — {item['source']} · {item['date']}"
                    )
                    if item.get("summary"):
                        lines.append(f"  {item['summary']}")
            lines.append("")
    else:
        lines.append("（本周股票池日报缺失或解析失败）")
        lines.append("")

    # 下周关注
    lines.append("## 七、下周关注")
    lines.append("")
    lines.append(outlook or "（暂无）")
    lines.append("")

    return "\n".join(lines)


# ── main ────────────────────────────────────────────────────────────────────────

PROJECT_ROOT_ARG = "."


def build_payload(window, indexes, boards_rank, sector_week, movers, csi_week, us_week, pool_week):
    """AI 输入的紧凑聚合数据（只含数值与短文本，不带长新闻列表）。"""
    return {
        "window": window,
        "indexes": [
            {k: m.get(k) for k in ("name", "week_change", "close", "amount_change_pct")}
            for m in indexes or []
        ],
        "board_week_rank": {
            key: [{"name": b["name"], "week_change": b["week_change"]}
                  for b in (boards_rank or {}).get(key, {}).get("boards", [])[:8]]
            for key in ("industry", "concept")
        },
        "sector_week_top": [
            {"board": b["board"], "days": b["days"], "cum_change": round(b["cum_change"], 2)}
            for b in (sector_week or [])[:8]
        ],
        "stock_movers": {
            key: [{"name": s["name"], "week_change": s["week_change"], "industry": s["industry"]}
                  for s in (movers or {}).get(key, [])[:8]]
            for key in ("gainers", "losers")
        },
        "csi_recurring": {
            key: [{"name": s["name"], "week_change": s.get("week_change"),
                   "gain_days": s["gain_days"], "lose_days": s["lose_days"]}
                  for s in (csi_week or {}).get(key, [])[:6]]
            for key in ("strong", "weak")
        },
        "us_sector_top": [
            {"sector": s["sector"], "days": s["days"], "cum_change": round(s["cum_change"], 2)}
            for s in sorted(us_week or [], key=lambda x: -x["cum_change"])[:8]
        ],
        "stock_pool_counts": {name: len(items) for name, items in (pool_week or {}).items()},
        "stock_pool_headlines": {
            name: [it["title"] for it in items[:2]] for name, items in (pool_week or {}).items()
        },
    }


def run(args):
    global PROJECT_ROOT_ARG
    PROJECT_ROOT_ARG = args.project_root
    run_date = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    monday, friday = compute_week_window(run_date)
    window_dates = week_dates(monday, friday)
    report_date = friday.isoformat()

    print(f"[INFO] 周窗口: {monday.isoformat()} ~ {friday.isoformat()}", file=sys.stderr)

    # 1. 指数周度（权威）
    indexes = []
    for secid, name in INDEXES:
        try:
            m = index_week_metrics(secid, name, monday, friday)
            if m:
                indexes.append(m)
        except Exception as exc:
            record_source_error(f"{name} 周度指标失败: {exc}")
        time.sleep(0.3)
    trading_dates = indexes[0]["trading_dates"] if indexes else [d.isoformat() for d in window_dates]
    window = {
        "start": monday.isoformat(),
        "end": friday.isoformat(),
        "trading_dates": trading_dates,
        "trading_days": len(trading_dates),
    }

    # 2. 东财 5 日榜（权威）
    try:
        movers = stock_week_movers(limit=10)
    except Exception as exc:
        record_source_error(f"个股5日榜失败: {exc}")
        movers = {"gainers": [], "losers": []}
    try:
        boards_rank = board_week_rank()
    except Exception as exc:
        record_source_error(f"板块5日榜失败: {exc}")
        boards_rank = {}

    # 3. 日报聚合（证据通道）
    root = Path(args.project_root)
    sector_paths = existing_report_dates(root / "published" / "sector-hotspots", window_dates)
    us_paths = existing_report_dates(root / "published" / "us-sector-hotspots", window_dates)
    pool_paths = existing_report_dates(root / "published" / "stock-pool", window_dates)
    print(
        f"[INFO] 本周日报：板块 {len(sector_paths)} 份、美股 {len(us_paths)} 份、股票池 {len(pool_paths)} 份",
        file=sys.stderr,
    )
    sector_week = aggregate_sector_week(sector_paths)
    sector_week.sort(key=lambda b: (-b["days"], -b["cum_change"]))
    us_week = aggregate_us_week(us_paths)
    pool_week = aggregate_stock_pool_week(pool_paths)

    csi_week = {}
    csi_paths_used = {}
    for index_type, label in (("csi300", "沪深300"), ("csi500", "中证500"), ("csi1000", "中证1000")):
        paths = existing_report_dates(root / "published" / index_type, window_dates)
        csi_paths_used[index_type] = sorted(paths)
        agg = aggregate_csi_week(paths, label)
        if agg["strong"] or agg["weak"]:
            csi_week[label] = agg
    # 合并各指数持续名单，供渲染与 payload 使用
    csi_flat = {"strong": [], "weak": []}
    for label, agg in csi_week.items():
        for s in agg["strong"]:
            csi_flat["strong"].append({**s, "index": label})
        for s in agg["weak"]:
            csi_flat["weak"].append({**s, "index": label})
    csi_flat["strong"].sort(key=lambda s: -(s.get("week_change") or -999))
    csi_flat["weak"].sort(key=lambda s: (s.get("week_change") or 999))
    csi_flat["strong"] = csi_flat["strong"][:12]
    csi_flat["weak"] = csi_flat["weak"][:12]

    payload = build_payload(window, indexes, boards_rank, sector_week, movers, csi_flat, us_week, pool_week)

    # 4. AI 综述
    model = os.environ.get("WEEKLY_REVIEW_AI_MODEL_NAME", DEFAULT_MODEL)
    mode = "rules-fallback"
    summary = outlook = ""
    if not args.skip_ai:
        try:
            summary, outlook = ai_summary(payload, model)
            if summary:
                mode = "codebuddy"
        except Exception as exc:
            record_source_error(f"AI 综述失败，降级规则版: {exc}")
    if not summary:
        summary, outlook = rules_summary(payload)
        mode = mode if mode == "codebuddy" else ("rules-fallback" if not args.skip_ai else "rules-only")

    # 5. 渲染与落盘
    report_md = render_report(
        report_date, window, indexes, boards_rank, sector_week,
        movers, csi_flat, us_week, pool_week, summary, outlook, mode,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output_dir / f"{report_date}.md", report_md)

    status = {
        "report_date": report_date,
        "window": window,
        "mode": mode,
        "skip_ai": bool(args.skip_ai),
        "source_errors": SOURCE_ERRORS,
        "daily_reports_used": {
            "sector-hotspots": sorted(sector_paths),
            "us-sector-hotspots": sorted(us_paths),
            "stock-pool": sorted(pool_paths),
            "csi": csi_paths_used,
        },
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    status_dir = Path(args.status_dir)
    status_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(status_dir / "latest-run.json", status)
    print(f"[INFO] 周报已写入 {output_dir / (report_date + '.md')}（mode={mode}）", file=sys.stderr)
    return status


def build_parser():
    ap = argparse.ArgumentParser(description="每周投资总结生成")
    ap.add_argument("--project-root", default=os.environ.get("PROJECT_ROOT", "."))
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--status-dir", default=None)
    ap.add_argument("--date", default=None, help="运行日 YYYY-MM-DD（默认今天）")
    ap.add_argument("--skip-ai", action="store_true", help="纯规则版（诊断用），不调用 CodeBuddy")
    return ap


def main():
    args = build_parser().parse_args()
    root = Path(args.project_root)
    if args.output_dir is None:
        args.output_dir = str(root / "published" / "weekly-review")
    if args.status_dir is None:
        args.status_dir = str(root / "var" / "weekly-review-status")
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
