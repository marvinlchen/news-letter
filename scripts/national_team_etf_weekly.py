#!/usr/bin/env python3
"""Generate a weekly broad-index ETF share-flow report.

The report tracks a fixed observation basket of large China broad-index ETFs.
It uses ETF total share changes as a public-data proxy for institutional
allocation pressure. It does not claim to identify the beneficial holder of any
ETF shares.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import re
import sys
import time
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

try:
    import requests
except ImportError as exc:  # pragma: no cover - deployment guard
    raise SystemExit("requests is required for national_team_etf_weekly.py") from exc

CN_TZ = timezone(timedelta(hours=8))
HTTP_TIMEOUT = 20
SSE_SCALE_URL = "https://query.sse.com.cn/commonQuery.do"
SZSE_SCALE_URL = "https://www.szse.cn/api/report/ShowReport"
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"


@dataclass(frozen=True)
class WatchETF:
    code: str
    display_name: str
    family: str
    exchange: str


@dataclass(frozen=True)
class ScalePoint:
    code: str
    name: str
    trade_date: date
    shares: float
    source: str


WATCHLIST: tuple[WatchETF, ...] = (
    WatchETF("510300", "沪深300ETF华泰柏瑞", "沪深300", "SSE"),
    WatchETF("510310", "沪深300ETF易方达", "沪深300", "SSE"),
    WatchETF("510330", "沪深300ETF华夏", "沪深300", "SSE"),
    WatchETF("159919", "沪深300ETF嘉实", "沪深300", "SZSE"),
    WatchETF("510050", "上证50ETF华夏", "上证50", "SSE"),
    WatchETF("510500", "中证500ETF南方", "中证500", "SSE"),
    WatchETF("512100", "中证1000ETF南方", "中证1000", "SSE"),
    WatchETF("159915", "创业板ETF易方达", "创业板", "SZSE"),
    WatchETF("588080", "科创50ETF易方达", "科创50", "SSE"),
    WatchETF("159845", "中证1000ETF华夏", "中证1000", "SZSE"),
    WatchETF("588000", "科创50ETF华夏", "科创50", "SSE"),
    WatchETF("560010", "中证1000ETF广发", "中证1000", "SSE"),
    WatchETF("512050", "A500ETF华夏", "中证A500", "SSE"),
    WatchETF("159352", "A500ETF南方", "中证A500", "SZSE"),
    WatchETF("563360", "A500ETF华泰柏瑞", "中证A500", "SSE"),
)


def parse_date(value: str) -> date:
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date()
    return date.fromisoformat(value)


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ymd(day: date) -> str:
    return day.strftime("%Y-%m-%d")


def iter_days(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch.upper()) - 64
    return max(n - 1, 0)


def read_xlsx_rows(content: bytes) -> list[list[str]]:
    """Read the first worksheet of a simple xlsx file using stdlib only."""
    rows: list[list[str]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = set(zf.namelist())
        shared_strings: list[str] = []
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("x:si", ns):
                parts = [t.text or "" for t in si.findall(".//x:t", ns)]
                shared_strings.append("".join(parts))

        sheet_path = "xl/worksheets/sheet1.xml"
        if sheet_path not in names:
            sheet_paths = sorted(name for name in names if name.startswith("xl/worksheets/sheet"))
            if not sheet_paths:
                return rows
            sheet_path = sheet_paths[0]

        root = ET.fromstring(zf.read(sheet_path))
        for row in root.findall(".//x:sheetData/x:row", ns):
            values: list[str] = []
            for cell in row.findall("x:c", ns):
                idx = col_index(cell.attrib.get("r", "A1"))
                while len(values) <= idx:
                    values.append("")
                cell_type = cell.attrib.get("t")
                value_node = cell.find("x:v", ns)
                if cell_type == "s" and value_node is not None and value_node.text is not None:
                    value = shared_strings[int(value_node.text)]
                elif cell_type == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//x:t", ns))
                elif value_node is not None and value_node.text is not None:
                    value = value_node.text
                else:
                    value = ""
                values[idx] = value.strip()
            if any(values):
                rows.append(values)
    return rows


def get_json(url: str, params: dict[str, str], headers: dict[str, str]) -> dict[str, Any]:
    response = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_sse_scale_for_date(day: date, watch_codes: set[str]) -> dict[str, ScalePoint]:
    params = {
        "isPagination": "true",
        "pageHelp.pageSize": "10000",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": "1",
        "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
        "STAT_DATE": ymd(day),
    }
    headers = {
        "Referer": "https://www.sse.com.cn/",
        "User-Agent": "Mozilla/5.0 (compatible; finance-news-digest/1.0)",
    }
    payload = get_json(SSE_SCALE_URL, params, headers)
    rows = payload.get("result") or payload.get("pageHelp", {}).get("data") or []
    records: dict[str, ScalePoint] = {}
    for row in rows:
        code = str(row.get("SEC_CODE", "")).strip()
        if code not in watch_codes:
            continue
        raw_shares = parse_float(row.get("TOT_VOL"))
        if raw_shares is None:
            continue
        stat_date = parse_date(str(row.get("STAT_DATE") or ymd(day)))
        records[code] = ScalePoint(
            code=code,
            name=str(row.get("SEC_NAME") or code).strip(),
            trade_date=stat_date,
            shares=raw_shares * 10000.0,
            source="SSE ETF scale",
        )
    return records


def fetch_sse_scale_history(start: date, end: date, watch_codes: set[str]) -> tuple[dict[str, list[ScalePoint]], list[str]]:
    history: dict[str, list[ScalePoint]] = defaultdict(list)
    errors: list[str] = []
    sse_codes = {code for code in watch_codes if code.startswith(("5", "6"))}
    for day in iter_days(start, end):
        if day.weekday() >= 5:
            continue
        try:
            records = fetch_sse_scale_for_date(day, sse_codes)
        except Exception as exc:  # noqa: BLE001 - report diagnostics, keep going
            errors.append(f"SSE {ymd(day)}: {exc}")
            continue
        for point in records.values():
            history[point.code].append(point)
        time.sleep(0.1)
    return history, errors


def fetch_szse_scale_history(start: date, end: date, watch_codes: set[str]) -> tuple[dict[str, list[ScalePoint]], list[str]]:
    history: dict[str, list[ScalePoint]] = defaultdict(list)
    errors: list[str] = []
    szse_codes = {code for code in watch_codes if code.startswith(("0", "1", "2", "3"))}
    if not szse_codes:
        return history, errors
    params = {
        "SHOWTYPE": "xlsx",
        "CATALOGID": "scsj_fund_jjgm",
        "TABKEY": "tab1",
        "txtStart": ymd(start),
        "txtEnd": ymd(end),
        "jjlb": "ETF",
        "random": str(random.random()),
    }
    headers = {
        "Host": "www.szse.cn",
        "Referer": "https://www.szse.cn/market/fund/volume/etf/index.html",
        "User-Agent": "Mozilla/5.0 (compatible; finance-news-digest/1.0)",
    }
    try:
        response = requests.get(SZSE_SCALE_URL, params=params, headers=headers, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        rows = read_xlsx_rows(response.content)
    except Exception as exc:  # noqa: BLE001
        return history, [f"SZSE {ymd(start)}..{ymd(end)}: {exc}"]

    if not rows:
        return history, [f"SZSE {ymd(start)}..{ymd(end)}: empty xlsx"]
    header = [item.strip() for item in rows[0]]
    col = {name: idx for idx, name in enumerate(header)}
    required = {"日期", "基金代码", "基金简称", "基金规模(份)"}
    if not required.issubset(col):
        return history, [f"SZSE xlsx missing columns: {sorted(required - set(col))}"]

    for row in rows[1:]:
        code = row[col["基金代码"]].strip() if col["基金代码"] < len(row) else ""
        code = code.split()[0].zfill(6)
        if code not in szse_codes:
            continue
        trade_day_text = row[col["日期"]].strip() if col["日期"] < len(row) else ""
        shares_text = row[col["基金规模(份)"]].strip() if col["基金规模(份)"] < len(row) else ""
        shares = parse_float(shares_text)
        if not trade_day_text or shares is None:
            continue
        name = row[col["基金简称"]].strip() if col["基金简称"] < len(row) else code
        history[code].append(
            ScalePoint(
                code=code,
                name=name,
                trade_date=parse_date(trade_day_text),
                shares=shares,
                source="SZSE ETF scale",
            )
        )
    return history, errors


def eastmoney_market_id(code: str) -> str:
    return "1" if code.startswith(("5", "6")) else "0"


def fetch_eastmoney_quotes(watchlist: tuple[WatchETF, ...]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    secids = ",".join(f"{eastmoney_market_id(item.code)}.{item.code}" for item in watchlist)
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f2,f3,f6,f12,f13,f14,f18,f20,f21,f38,f124,f297,f402,f441",
        "secids": secids,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    }
    headers = {"User-Agent": "Mozilla/5.0 (compatible; finance-news-digest/1.0)"}
    try:
        payload = get_json(EASTMONEY_QUOTE_URL, params, headers)
    except Exception as exc:  # noqa: BLE001
        return {}, [f"Eastmoney quote: {exc}"]
    rows = payload.get("data", {}).get("diff") or []
    quotes: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("f12", "")).strip()
        price = parse_float(row.get("f2"))
        shares = parse_float(row.get("f38"))
        market_value = parse_float(row.get("f20"))
        if price is None and shares and market_value:
            price = market_value / shares
        quote_date = None
        raw_date = row.get("f297")
        if raw_date:
            try:
                quote_date = parse_date(str(int(raw_date)))
            except Exception:  # noqa: BLE001
                quote_date = None
        quotes[code] = {
            "name": row.get("f14"),
            "price": price,
            "pct_change": parse_float(row.get("f3")),
            "turnover": parse_float(row.get("f6")),
            "eastmoney_shares": shares,
            "eastmoney_market_value": market_value,
            "discount_pct": parse_float(row.get("f402")),
            "iopv": parse_float(row.get("f441")),
            "quote_date": ymd(quote_date) if quote_date else None,
            "updated_at_epoch": row.get("f124"),
        }
    return quotes, []


def latest_point(points: list[ScalePoint]) -> ScalePoint | None:
    if not points:
        return None
    return max(points, key=lambda item: item.trade_date)


def point_on_or_before(points: list[ScalePoint], target: date) -> ScalePoint | None:
    candidates = [point for point in points if point.trade_date <= target]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.trade_date)


def previous_point(points: list[ScalePoint], latest_day: date) -> ScalePoint | None:
    candidates = [point for point in points if point.trade_date < latest_day]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.trade_date)


def pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100.0


def build_payload(
    history: dict[str, list[ScalePoint]],
    quotes: dict[str, dict[str, Any]],
    errors: list[str],
    start: date,
    end: date,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    all_latest_dates: list[date] = []
    missing_codes: list[str] = []

    for item in WATCHLIST:
        points = sorted(history.get(item.code, []), key=lambda point: point.trade_date)
        latest = latest_point(points)
        if latest is None:
            missing_codes.append(item.code)
            continue
        all_latest_dates.append(latest.trade_date)
        baseline = point_on_or_before(points, latest.trade_date - timedelta(days=7))
        previous = previous_point(points, latest.trade_date)
        quote = quotes.get(item.code, {})
        price = quote.get("price")
        week_share_delta = latest.shares - baseline.shares if baseline else None
        day_share_delta = latest.shares - previous.shares if previous else None
        scale_yi = latest.shares * price / 1e8 if price is not None else None
        week_flow_yi = week_share_delta * price / 1e8 if week_share_delta is not None and price is not None else None
        day_flow_yi = day_share_delta * price / 1e8 if day_share_delta is not None and price is not None else None
        records.append(
            {
                "code": item.code,
                "name": quote.get("name") or item.display_name,
                "display_name": item.display_name,
                "family": item.family,
                "exchange": item.exchange,
                "latest_date": ymd(latest.trade_date),
                "latest_shares": latest.shares,
                "latest_shares_yi": latest.shares / 1e8,
                "latest_source_name": latest.name,
                "price": price,
                "quote_date": quote.get("quote_date"),
                "pct_change": quote.get("pct_change"),
                "discount_pct": quote.get("discount_pct"),
                "iopv": quote.get("iopv"),
                "turnover_yi": quote.get("turnover") / 1e8 if quote.get("turnover") is not None else None,
                "estimated_scale_yi": scale_yi,
                "baseline_date": ymd(baseline.trade_date) if baseline else None,
                "baseline_shares_yi": baseline.shares / 1e8 if baseline else None,
                "week_share_delta_yi": week_share_delta / 1e8 if week_share_delta is not None else None,
                "week_estimated_flow_yi": week_flow_yi,
                "week_flow_pct_of_scale": pct(week_flow_yi, scale_yi),
                "previous_date": ymd(previous.trade_date) if previous else None,
                "day_share_delta_yi": day_share_delta / 1e8 if day_share_delta is not None else None,
                "day_estimated_flow_yi": day_flow_yi,
                "source": latest.source,
            }
        )

    if not records:
        raise SystemExit("No ETF scale records were collected for the watchlist")

    report_latest_date = max(all_latest_dates)
    valid_flows = [row for row in records if row["week_estimated_flow_yi"] is not None]
    valid_scales = [row for row in records if row["estimated_scale_yi"] is not None]
    total_flow_yi = sum(row["week_estimated_flow_yi"] for row in valid_flows)
    total_scale_yi = sum(row["estimated_scale_yi"] for row in valid_scales)
    total_share_delta_yi = sum(row["week_share_delta_yi"] for row in records if row["week_share_delta_yi"] is not None)

    family_map: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["family"]].append(row)
    for family, rows in grouped.items():
        flow_rows = [row for row in rows if row["week_estimated_flow_yi"] is not None]
        family_map[family] = {
            "family": family,
            "etf_count": len(rows),
            "estimated_scale_yi": sum(row["estimated_scale_yi"] for row in rows if row["estimated_scale_yi"] is not None),
            "week_estimated_flow_yi": sum(row["week_estimated_flow_yi"] for row in flow_rows),
            "week_share_delta_yi": sum(row["week_share_delta_yi"] for row in rows if row["week_share_delta_yi"] is not None),
            "members": sorted(
                flow_rows,
                key=lambda row: abs(row["week_estimated_flow_yi"]),
                reverse=True,
            )[:3],
        }

    records_sorted = sorted(
        records,
        key=lambda row: (
            row["week_estimated_flow_yi"] is None,
            row["week_estimated_flow_yi"] if row["week_estimated_flow_yi"] is not None else 0,
        ),
    )
    families_sorted = sorted(
        family_map.values(),
        key=lambda row: row["week_estimated_flow_yi"],
    )

    payload = {
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "report_date": ymd(report_latest_date),
        "collection_window": {"start": ymd(start), "end": ymd(end)},
        "watchlist_count": len(WATCHLIST),
        "record_count": len(records),
        "missing_codes": missing_codes,
        "source_errors": errors,
        "source_error_count": len(errors),
        "data_sources": [
            "SSE ETF scale: https://query.sse.com.cn/commonQuery.do",
            "SZSE ETF daily scale: https://www.szse.cn/api/report/ShowReport",
            "Eastmoney delayed ETF quote: https://push2.eastmoney.com/api/qt/ulist.np/get",
        ],
        "methodology": "Weekly share delta uses latest official ETF shares minus the latest available official shares on or before T-7 calendar days. Estimated flow uses latest Eastmoney delayed price.",
        "totals": {
            "estimated_scale_yi": total_scale_yi,
            "week_estimated_flow_yi": total_flow_yi,
            "week_share_delta_yi": total_share_delta_yi,
            "week_flow_pct_of_scale": pct(total_flow_yi, total_scale_yi),
        },
        "records": records_sorted,
        "families": families_sorted,
    }
    return payload


def fmt_number(value: float | None, digits: int = 1, signed: bool = False) -> str:
    if value is None:
        return "-"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:,.{digits}f}"


def fmt_pct(value: float | None, digits: int = 1, signed: bool = False) -> str:
    if value is None:
        return "-"
    return f"{fmt_number(value, digits, signed)}%"


def describe_flow(value: float | None) -> str:
    if value is None:
        return "数据不足"
    if value > 0:
        return "净申购"
    if value < 0:
        return "净赎回"
    return "基本持平"


def render_major_members(members: list[dict[str, Any]]) -> str:
    if not members:
        return "-"
    parts = []
    for item in members[:2]:
        flow = fmt_number(item.get("week_estimated_flow_yi"), 1, signed=True)
        parts.append(f"{item['name']} {flow}亿")
    return "；".join(parts)


def render_report(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    records = payload["records"]
    valid_flows = [row for row in records if row["week_estimated_flow_yi"] is not None]
    top_out = min(valid_flows, key=lambda row: row["week_estimated_flow_yi"]) if valid_flows else None
    top_in = max(valid_flows, key=lambda row: row["week_estimated_flow_yi"]) if valid_flows else None
    report_date = payload["report_date"]

    lines: list[str] = []
    lines.append(f"# 国家队ETF观察周报（截至 {report_date}）")
    lines.append("")
    lines.append(
        "> 口径说明：这里的“国家队 ETF”是宽基 ETF 观察池，不是账户穿透后的中央汇金、证金或其他特定主体持仓。公开数据只能看到 ETF 总份额变化，本报告把份额申赎变化作为稳市资金/机构配置压力的 proxy。"
    )
    lines.append("")
    lines.append("## 本周结论")
    lines.append("")
    lines.append(
        f"- 观察池合计估算规模 {fmt_number(totals['estimated_scale_yi'], 1)} 亿元，周度{describe_flow(totals['week_estimated_flow_yi'])} {fmt_number(totals['week_estimated_flow_yi'], 1, signed=True)} 亿元，约占观察池规模 {fmt_pct(totals['week_flow_pct_of_scale'], 2, signed=True)}。"
    )
    lines.append(
        f"- 周份额合计变化 {fmt_number(totals['week_share_delta_yi'], 1, signed=True)} 亿份；估算金额用最新价折算，实际申赎价格会与估算值有偏差。"
    )
    if top_out:
        lines.append(
            f"- 减配压力最大：{top_out['name']}（{top_out['code']}），周估算 {fmt_number(top_out['week_estimated_flow_yi'], 1, signed=True)} 亿元，份额变化 {fmt_number(top_out['week_share_delta_yi'], 1, signed=True)} 亿份。"
        )
    if top_in and top_in is not top_out:
        lines.append(
            f"- 增配最明显：{top_in['name']}（{top_in['code']}），周估算 {fmt_number(top_in['week_estimated_flow_yi'], 1, signed=True)} 亿元，份额变化 {fmt_number(top_in['week_share_delta_yi'], 1, signed=True)} 亿份。"
        )
    if payload["missing_codes"]:
        lines.append(f"- 缺少份额数据的代码：{', '.join(payload['missing_codes'])}。")
    if payload["source_errors"]:
        lines.append(f"- 数据源异常 {payload['source_error_count']} 项，详见文末状态。")
    lines.append("")

    lines.append("## 指数族汇总")
    lines.append("")
    lines.append("| 指数族 | ETF数量 | 估算规模(亿元) | 周估算净流入(亿元) | 周份额变化(亿份) | 主要变化 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for family in payload["families"]:
        lines.append(
            "| {family} | {count} | {scale} | {flow} | {shares} | {members} |".format(
                family=family["family"],
                count=family["etf_count"],
                scale=fmt_number(family["estimated_scale_yi"], 1),
                flow=fmt_number(family["week_estimated_flow_yi"], 1, signed=True),
                shares=fmt_number(family["week_share_delta_yi"], 1, signed=True),
                members=render_major_members(family["members"]),
            )
        )
    lines.append("")

    lines.append("## ETF明细")
    lines.append("")
    lines.append("按周估算净流入从低到高排列，便于先看到减配方向。")
    lines.append("")
    lines.append("| 排名 | 代码 | ETF | 指数族 | 最新份额(亿份) | 估算规模(亿元) | 周份额变化(亿份) | 周估算净流入(亿元) | 日涨跌幅 | 数据日期 |")
    lines.append("| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for idx, row in enumerate(records, start=1):
        lines.append(
            "| {idx} | {code} | {name} | {family} | {shares} | {scale} | {delta} | {flow} | {pct} | {date} |".format(
                idx=idx,
                code=row["code"],
                name=row["name"],
                family=row["family"],
                shares=fmt_number(row["latest_shares_yi"], 1),
                scale=fmt_number(row["estimated_scale_yi"], 1),
                delta=fmt_number(row["week_share_delta_yi"], 1, signed=True),
                flow=fmt_number(row["week_estimated_flow_yi"], 1, signed=True),
                pct=fmt_pct(row["pct_change"], 2, signed=True),
                date=row["latest_date"],
            )
        )
    lines.append("")

    lines.append("## 单只ETF细节")
    lines.append("")
    for row in records:
        baseline = row["baseline_date"] or "-"
        quote_date = row["quote_date"] or "-"
        lines.append(
            f"- **{row['name']}（{row['code']}）**：{baseline} -> {row['latest_date']}，份额 {fmt_number(row['baseline_shares_yi'], 1)} -> {fmt_number(row['latest_shares_yi'], 1)} 亿份，变化 {fmt_number(row['week_share_delta_yi'], 1, signed=True)} 亿份；最新价 {fmt_number(row['price'], 3)} 元，估算规模 {fmt_number(row['estimated_scale_yi'], 1)} 亿元，周估算资金变化 {fmt_number(row['week_estimated_flow_yi'], 1, signed=True)} 亿元；行情日期 {quote_date}。"
        )
    lines.append("")

    lines.append("## 数据源与方法")
    lines.append("")
    lines.append("- 份额主源：上交所 ETF 基金规模接口 `query.sse.com.cn/commonQuery.do`，深交所基金规模日频接口 `www.szse.cn/api/report/ShowReport`。")
    lines.append("- 行情补充：东方财富 ETF 延时行情 `push2.eastmoney.com/api/qt/ulist.np/get`，用于最新价、日涨跌幅、折溢价和估算规模。")
    lines.append("- 周度变化：最新官方份额减去 T-7 日或之前最近一个可用交易日的官方份额。")
    lines.append("- 周估算净流入：周份额变化乘以最新价。它是资金方向估算，不等同于交易所逐日申赎金额，也不能识别最终持有人。")
    lines.append("")
    lines.append("## 运行状态")
    lines.append("")
    lines.append(f"- 生成时间：{payload['generated_at']}")
    lines.append(f"- 采集窗口：{payload['collection_window']['start']} 至 {payload['collection_window']['end']}")
    lines.append(f"- 覆盖 ETF：{payload['record_count']} / {payload['watchlist_count']}")
    if payload["source_errors"]:
        for err in payload["source_errors"][:10]:
            lines.append(f"- 数据源异常：{err}")
    else:
        lines.append("- 数据源异常：无")
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], markdown: str, project_root: Path, output_dir: Path) -> Path:
    report_date = payload["report_date"]
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{report_date}.md"
    latest_path = output_dir / "latest.md"
    report_path.write_text(markdown, encoding="utf-8")
    latest_path.write_text(markdown, encoding="utf-8")

    raw_dir = project_root / "var" / "national-team-etf"
    status_dir = project_root / "var" / "national-team-etf-status"
    raw_dir.mkdir(parents=True, exist_ok=True)
    status_dir.mkdir(parents=True, exist_ok=True)
    raw_payload = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    (raw_dir / f"{report_date}.json").write_text(raw_payload + "\n", encoding="utf-8")
    (raw_dir / "latest.json").write_text(raw_payload + "\n", encoding="utf-8")
    status = {
        "date": report_date,
        "generated_at": payload["generated_at"],
        "watchlist_count": payload["watchlist_count"],
        "record_count": payload["record_count"],
        "missing_codes": payload["missing_codes"],
        "source_error_count": payload["source_error_count"],
        "total_estimated_scale_yi": payload["totals"]["estimated_scale_yi"],
        "total_week_estimated_flow_yi": payload["totals"]["week_estimated_flow_yi"],
        "total_week_share_delta_yi": payload["totals"]["week_share_delta_yi"],
        "mode": "rules",
    }
    (status_dir / "latest.json").write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate weekly national-team ETF observation report")
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--date", help="Collection end date, YYYY-MM-DD or YYYYMMDD; defaults to China today")
    parser.add_argument("--lookback-days", type=int, default=14)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    project_root = args.project_root.resolve()
    output_dir = args.output_dir or project_root / "published" / "national-team-etf"
    end = parse_date(args.date) if args.date else datetime.now(CN_TZ).date()
    start = end - timedelta(days=max(args.lookback_days, 8))
    watch_codes = {item.code for item in WATCHLIST}

    sse_history, sse_errors = fetch_sse_scale_history(start, end, watch_codes)
    szse_history, szse_errors = fetch_szse_scale_history(start, end, watch_codes)
    history: dict[str, list[ScalePoint]] = defaultdict(list)
    for source in (sse_history, szse_history):
        for code, points in source.items():
            history[code].extend(points)
    for code in list(history):
        seen: dict[date, ScalePoint] = {}
        for point in history[code]:
            seen[point.trade_date] = point
        history[code] = sorted(seen.values(), key=lambda point: point.trade_date)

    quotes, quote_errors = fetch_eastmoney_quotes(WATCHLIST)
    errors = sse_errors + szse_errors + quote_errors
    payload = build_payload(history, quotes, errors, start, end)
    markdown = render_report(payload)
    report_path = write_outputs(payload, markdown, project_root, output_dir.resolve())
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
