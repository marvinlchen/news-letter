"""A-share announcement evidence collection and date-bounded market indicators.

Public endpoints only. A missing source raises or becomes an explicit gap; an empty
collection is accepted only after all result pages have been checked.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import io
import json
import math
import re
import time
import urllib.parse
import urllib.request
import uuid
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo


class DataUnavailable(RuntimeError):
    pass


HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
ANN_API = "https://np-anotice-stock.eastmoney.com/api/security/ann"
DETAIL_API = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
MAJOR_PATTERNS = {
    "业绩": r"业绩预告|业绩快报|年度报告|半年度报告|季度报告|扭亏|亏损|业绩修正",
    "并购重组": r"收购|重组|资产出售|出售资产|资产置换|控制权|实际控制人|(?:第一大股东|控股股东).*变更|吸收合并|股权转让|要约",
    "回购增减持": r"回购|增持|减持|持股变动|权益变动|(?:控股股东|大股东).*持股",
    "经营合同": r"重大合同|重大订单|中标|重大项目|投资项目|项目投资|对外投资|共同投资|增资|投资协议|产业基金|设立.*(?:合资|子公司)|产能建设|生产基地|扩产|投产|停产|复产|战略合作|框架协议|销售合同|采购合同",
    "监管风险": r"立案|处罚|诉讼|仲裁|冻结|退市|风险警示|违约|破产|重整|审计意见|问询|监管|调查|失信|资金占用|违规担保|异常波动|澄清",
    "股权激励": r"股权激励|限制性股票|股票期权|激励计划",
    "研发资质": r"新药|临床|药品|注册证|专利|许可证|资质|定点通知|获批|认证|补助",
    "重大事项": r"重大事项|重大进展|重大变化|重大影响|终止|撤回|暂停|恢复交易|复牌|停牌",
}


def _date(value):
    return dt.date.fromisoformat(str(value))


def _request_json(url, params=None, attempts=3):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    error = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25) as response:
                return json.loads(response.read())
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.6 * (attempt + 1))
    raise DataUnavailable(f"{urllib.parse.urlsplit(url).netloc}: {type(error).__name__}: {error}")



def _post_json(url, params, attempts=3):
    error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(),
                headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://www.cninfo.com.cn/new/disclosure", "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.loads(response.read())
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.6 * (attempt + 1))
    raise DataUnavailable(f"cninfo: {type(error).__name__}: {error}")


def _official_announcements(date, cache_dir):
    day = _date(date).isoformat()
    records = []
    for plate in ("sh", "sz"):
        params = {"pageSize": 30, "column": "sse" if plate == "sh" else "szse", "tabName": "fulltext",
                  "plate": plate, "stock": "", "searchkey": "", "secid": "", "category": "", "trade": "",
                  "seDate": day + "~" + day, "sortName": "", "sortType": "", "isHLtitle": "true"}
        def page(number):
            value = _cached_json(Path(cache_dir) / "announcements" / day / f"cninfo-{plate}-stable-{number:04d}.json",
                lambda: _post_json("https://www.cninfo.com.cn/new/hisAnnouncement/query", {**params, "pageNum": number}))
            if not isinstance(value.get("announcements"), list) or "totalAnnouncement" not in value:
                raise DataUnavailable(f"巨潮{plate}第{number}页响应不完整")
            return value
        first = page(1)
        total = int(first["totalAnnouncement"])
        pages = max(1, math.ceil(total / 30))
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            remainder = list(pool.map(page, range(2, pages + 1)))
        all_pages = [first] + remainder
        values = [r for result in all_pages for r in result["announcements"]]
        identifiers = [str(r.get("announcementId")) for r in values]
        if len(values) != total or len(set(identifiers)) != total or any(int(r["totalAnnouncement"]) != total for r in all_pages):
            raise DataUnavailable(f"巨潮{plate}全量分页校验失败")
        records += values
    return records


def _normal_title(title, name):
    title = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", title))
    title = re.sub(r"\s+", "", title)
    name = unicodedata.normalize("NFKC", re.sub(r"\s+", "", name))
    if name:
        title = re.sub(r"^(?:" + re.escape(name) + r"[:：]?)+", "", title)
    return re.sub(r"[^\w\u4e00-\u9fff]", "", title)


def _cached_json(path, fetch):
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return result


def _is_shsz_a(code):
    """Use both market and six-digit prefix; exclude B/H/BSE/funds/bonds."""
    number = str(code.get("stock_code", ""))
    market = str(code.get("market_code", ""))
    return bool(re.fullmatch(r"\d{6}", number)) and (
        (market == "1" and number.startswith(("60", "68")))
        or (market == "0" and number.startswith(("00", "30")))
    )


def _category(title):
    return [name for name, pattern in MAJOR_PATTERNS.items() if re.search(pattern, title)]


def _all_announcement_pages(date, cache_dir):
    day = _date(date).isoformat()
    base = Path(cache_dir) / "announcements" / day
    params = {"sr": -1, "page_size": 100, "ann_type": "A", "begin_time": day,
              "end_time": day, "client_source": "web"}
    def page(number):
        result = _cached_json(base / f"list-{number:04d}.json", lambda: _request_json(ANN_API, {**params, "page_index": number}))
        data = result.get("data")
        if result.get("success") != 1 or not isinstance(data, dict) or "list" not in data:
            raise DataUnavailable(f"公告列表第{number}页响应无效")
        if int(data.get("page_index", number)) != number:
            raise DataUnavailable(f"公告列表页码错误: {number}")
        return data
    first = page(1)
    total = int(first.get("total_hits", -1))
    size = int(first.get("page_size", 0))
    if total < 0 or size <= 0:
        raise DataUnavailable("公告列表缺少total_hits/page_size，无法确认全量")
    count = max(1, math.ceil(total / size))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rest = list(pool.map(page, range(2, count + 1)))
    pages = [first] + rest
    if any(int(p.get("total_hits", -1)) != total for p in pages):
        raise DataUnavailable("公告列表分页期间总数发生变化，需要重新采集")
    records = [r for p in pages for r in p["list"]]
    ids = [r.get("art_code") for r in records]
    if len(records) != total or len(set(ids)) != total or None in ids:
        raise DataUnavailable(f"公告全量校验失败：total={total},rows={len(records)},unique={len(set(ids))}")
    return records, total, count


def _download_pdf(url, path):
    if path.exists():
        return path.read_bytes()
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=45) as response:
        content = response.read(30 * 1024 * 1024 + 1)
    if len(content) > 30 * 1024 * 1024 or not content.startswith(b"%PDF"):
        raise DataUnavailable("公告PDF无效或超过30MB")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return content


def _extract_complete_pdf_text(payload):
    """Remove exact layout boilerplate, then reject partly scanned PDFs.

    A genuine blank page has neither text nor images and is permitted. Page
    numbers are removed only if every first line forms the full 1..N sequence
    over at least two pages. No arbitrary standalone numeric line is deleted.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(payload))
    page_lines = [(page.extract_text() or "").splitlines(keepends=True) for page in reader.pages]
    numbered = len(page_lines) >= 2 and all(
        lines and lines[0].strip() == str(number)
        for number, lines in enumerate(page_lines, 1)
    )
    disclaimer = "本公司及董事会全体成员保证信息披露的内容真实、准确、完整，没有虚假记载、误导性陈述或重大遗漏。"
    disclaimer_pattern = r"\s*".join(re.escape(character) for character in disclaimer)
    texts = []
    for number, (page, lines) in enumerate(zip(reader.pages, page_lines), 1):
        text = "".join(lines[1:] if numbered else lines)
        text = re.sub(disclaimer_pattern, "", text)
        meaningful = re.sub(r"\s+", "", text)
        if len(meaningful) < 20 and page.images:
            raise DataUnavailable(f"PDF第{number}页含图像但正文可提取字符不足20，全文不完整，需OCR核验")
        texts.append(text)
    complete = "\n".join(texts)
    if len(re.sub(r"\s+", "", complete)) < 20:
        raise DataUnavailable("PDF无可提取正文")
    return complete


def _announcement_detail(announcement, base):
    result = dict(announcement)
    article = result["id"]
    folder = Path(base) / "evidence"
    folder.mkdir(parents=True, exist_ok=True)
    gaps = []
    if result.get("official_url"):
        try:
            pdf_path = folder / f"cninfo-{result['official_id']}.pdf"
            payload = _download_pdf(result["official_url"], pdf_path)
            text = _extract_complete_pdf_text(payload)
            text_path = folder / f"{article}.txt"
            text_path.write_text(text, encoding="utf-8")
            result.update(text=text, url=result["official_url"], text_complete=True, official_verified=True,
                          source_pdf=str(pdf_path), source_text=str(text_path), text_sha256=hashlib.sha256(text.encode()).hexdigest())
            return result, gaps
        except Exception as exc:
            gaps.append(f"官方交叉核验缺口: {result['code']} {article}官方PDF全文不可用（{type(exc).__name__}），使用东财正文镜像")
    else:
        gaps.append(f"官方交叉核验缺口: {result['code']} {article}未匹配巨潮官方原文，使用东财披露镜像")
    result["official_verified"] = False
    try:
        raw_path = folder / f"{article}.json"
        raw = _cached_json(raw_path, lambda: _request_json(DETAIL_API, {"art_code": article, "client_source": "web", "page_index": 1}))
        data = raw.get("data") or {}
        if raw.get("success") != 1 or data.get("art_code") != article:
            raise DataUnavailable("公告详情ID与响应不一致")
        text = data.get("notice_content") or ""
        result["url"] = data.get("attach_url") or result["url"]
        result["source_json"] = str(raw_path)
        result["text_complete"] = int(data.get("page_size", 1)) <= 1
        if not result["text_complete"] and data.get("attach_url"):
            try:
                pdf_path = folder / f"{article}.pdf"
                payload = _download_pdf(data["attach_url"], pdf_path)
                complete = _extract_complete_pdf_text(payload)
                text = complete
                result["source_pdf"] = str(pdf_path)
                result["text_complete"] = True
            except Exception as exc:
                gaps.append(f"{result['code']} {article}: 原始PDF全文待核（{type(exc).__name__}）")
        if not text.strip():
            raise DataUnavailable("公告正文为空")
        text_path = folder / f"{article}.txt"
        text_path.write_text(text, encoding="utf-8")
        result.update(text=text, source_text=str(text_path), text_sha256=hashlib.sha256(text.encode()).hexdigest())
        if not result["text_complete"]:
            gaps.append(f"{result['code']} {article}: 当前正文仅首段，禁止据此宣称全文核验")
    except Exception as exc:
        result.update(text="", text_complete=False)
        gaps.append(f"{result['code']} {article}: 公告正文待核（{exc}）")
    return result, gaps


def collect_announcements(date, cache_dir, limit_companies=None):
    """Fetch every source result page, filter SH/SZ A, then fetch major candidates."""
    day = _date(date).isoformat()
    records, total, pages = _all_announcement_pages(day, cache_dir)
    candidates = []
    all_a_count = 0
    for record in records:
        eligible = [code for code in record.get("codes", []) if _is_shsz_a(code)]
        if not eligible:
            continue
        all_a_count += 1
        categories = _category(record.get("title", ""))
        if not categories:
            continue
        for security in eligible:
            candidates.append({"id": record["art_code"], "code": security["stock_code"],
                               "name": security["short_name"], "title": record["title"],
                               "url": "https://data.eastmoney.com/notices/detail/" + security["stock_code"] + "/" + record["art_code"] + ".html",
                               "date": str(record.get("notice_date", ""))[:10],
                               "display_time": record.get("display_time", ""), "text": "",
                               "category_hint": categories, "market": security["market_code"]})
    support_pattern = r"法律意见书|律师事务所|核查意见|独立董事.*意见|独董.*意见|董事会.*决议|监事会.*决议|激励对象.*名单|审计报告|资产评估报告|验资报告|上市保荐书|发行保荐书"
    substantive_codes = {item["code"] for item in candidates if not re.search(support_pattern, item["title"])}
    supporting = {}
    for item in candidates:
        if item["code"] in substantive_codes and re.search(support_pattern, item["title"]):
            supporting.setdefault(item["code"], []).append({key: item[key] for key in ("id", "title", "url")})
    candidates = [item for item in candidates if not (item["code"] in substantive_codes and re.search(support_pattern, item["title"]))]
    for item in candidates:
        item["supporting_announcements"] = supporting.get(item["code"], [])
    total_candidates = len(candidates)
    official_notes = [f"同股存在实际事件公告时，法律/核查/决议/名单等支持附件共{sum(len(v) for v in supporting.values())}份仅保留链接，不重复分析。"]
    try:
        official = _official_announcements(day, cache_dir)
        official_notes.append(f"巨潮官方沪深公告全量分页核验：{len(official)}条；候选按代码及归一化标题精确匹配。")
        lookup = {}
        for record in official:
            key = (record.get("secCode"), _normal_title(record.get("announcementTitle", ""), record.get("secName", "")))
            lookup.setdefault(key, []).append(record)
        matched = 0
        for item in candidates:
            key = (item["code"], _normal_title(item["title"], item["name"]))
            matches = lookup.get(key) or []
            if len(matches) == 1:
                record = matches[0]
                item.update(official_url="https://static.cninfo.com.cn/" + record["adjunctUrl"],
                            official_id=str(record["announcementId"]), official_title=record["announcementTitle"])
                matched += 1
        official_notes.append(f"重大候选公告官方精确匹配{matched}/{len(candidates)}份；未匹配的逐项披露原文核验缺口。")
    except Exception as exc:
        official_notes.append(f"巨潮官方全量查询不可用（{exc}）；官方核验缺口将逐项披露。")
    if limit_companies is not None:
        if not isinstance(limit_companies, int) or limit_companies < 1:
            raise ValueError("limit_companies必须为正整数")
        selected_codes = set(list(dict.fromkeys(item["code"] for item in candidates))[:limit_companies])
        candidates = [item for item in candidates if item["code"] in selected_codes]
    base = Path(cache_dir) / "announcements" / day
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda item: _announcement_detail(item, base), candidates))
    return {"announcements": [item for item, _ in results], "total_count": all_a_count, "source_total_count": total,
            "a_share_count": all_a_count, "candidate_count": total_candidates,
            "processed_candidate_count": len(candidates), "complete": True,
            "diagnostic_limited": limit_companies is not None,
            "source_notes": [f"东方财富公告列表完整分页：{pages}页/{total}条，沪深A股{all_a_count}条；按notice_date={day}。",
                             "标题关键词用于候选筛选，最终利好/利空需公告正文判断；保留原始列表JSON及候选正文证据。",
                             "优先使用巨潮资讯官方披露PDF全文与链接；官方未匹配时使用东方财富披露PDF镜像并明确披露缺口。",
                             "行情来自腾讯截至日日K前复权序列，只有复权终值与该日原价一致才计算；历史查询如混入以后复权因子则标待核。",
                             "个股日线严格过滤截至日之后数据，周线由截至日日线聚合；MACD为12/26/9、柱=2×(DIF-DEA)。",
                             "公开数据用于公告原文及行情核验；iFinD MCP实际调用情况另见本日报核验说明。"
                             ] + official_notes + ([f"诊断限制：全量列表已核验，但只提取头{limit_companies}家公司候选正文，不能作为完整日报发布。"] if limit_companies is not None else []),
            "gaps": [gap for _, gaps in results for gap in gaps]}


def _fetch_daily(code, date, cache_dir, market=None):
    day = _date(date)
    symbol = ("sh" if market == "1" or code.startswith(("6", "BK")) else "sz") + code
    if code == "000001" and market == "1":
        symbol = "sh000001"
    start = day - dt.timedelta(days=1200)
    path = Path(cache_dir) / "market" / day.isoformat() / f"{symbol}-daily.json"
    params = {"param": f"{symbol},day,{start.isoformat()},{day.isoformat()},1000,qfq"}
    raw = _cached_json(path, lambda: _request_json("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params))
    data = (raw.get("data") or {}).get(symbol) or {}
    values = data.get("qfqday") or data.get("day") or []
    # Tencent may apply its *current* adjustment factor even when end is a
    # historical date. Verify that the terminal qfq close equals the raw close
    # on the same day; otherwise reject the history, rather than use future
    # corporate-action information in an as-of report.
    if data.get("qfqday"):
        raw_params = {"param": f"{symbol},day,{start.isoformat()},{day.isoformat()},1000,"}
        raw_prices = _cached_json(path.with_name(f"{symbol}-daily-unadjusted.json"),
                                 lambda: _request_json("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", raw_params))
        raw_values = ((raw_prices.get("data") or {}).get(symbol) or {}).get("day") or []
        raw_lookup = {v[0]: float(v[2]) for v in raw_values if _date(v[0]) <= day}
        bounded = [v for v in values if _date(v[0]) <= day]
        if not bounded or bounded[-1][0] not in raw_lookup:
            raise DataUnavailable(f"{symbol}无法核验截至日复权基准")
        last = bounded[-1]
        raw_close = raw_lookup[last[0]]
        if abs(float(last[2]) - raw_close) > max(0.005, raw_close * 0.0001):
            raise DataUnavailable(f"{symbol}历史qfq终值与当日原价不符，存在截至日之后复权因子，技术指标待核")
    rows = []
    for value in values:
        row_date = _date(value[0])
        if row_date <= day:
            rows.append({"date": row_date.isoformat(), "open": float(value[1]), "close": float(value[2]),
                         "high": float(value[3]), "low": float(value[4]), "volume": float(value[5])})
    rows.sort(key=lambda row: row["date"])
    if not rows:
        raise DataUnavailable(f"{symbol}截至{day}无日K数据")
    return rows


def is_trading_day(date, cache_dir):
    """Confirm historical sessions from actual SSE composite bars, not guessed holidays.

    For a weekday not yet covered by verifiable calendar/bars, raise instead of
    incorrectly reporting a holiday. The scheduled job normally checks yesterday.
    """
    day = _date(date)
    if day.weekday() >= 5:
        return False
    try:
        calendar_path = Path(cache_dir) / "calendar" / f"sina-trade-dates-{day.year}.json"
        def fetch_calendar():
            import akshare as ak
            return {"source": "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt",
                    "dates": [str(x)[:10] for x in ak.tool_trade_date_hist_sina()["trade_date"].tolist()]}
        raw = _cached_json(calendar_path, fetch_calendar)
        days = raw.get("dates", [])
        if days and min(days) <= day.isoformat() <= max(days):
            return day.isoformat() in set(days)
    except Exception:
        pass
    today = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    probe = min(today - dt.timedelta(days=1), day + dt.timedelta(days=14))
    if probe < day:
        raise DataUnavailable(f"{day}交易日历尚无法通过历史交易日核验")
    rows = _fetch_daily("000001", probe, cache_dir, market="1")
    days = {row["date"] for row in rows}
    if day.isoformat() in days:
        return True
    if rows[0]["date"] <= day.isoformat() < rows[-1]["date"]:
        return False
    raise DataUnavailable(f"{day}交易日历待核（最近可验证交易日{rows[-1]['date']}）")


def _ema(values, span):
    result = []
    alpha = 2.0 / (span + 1)
    for value in values:
        result.append(value if not result else alpha * value + (1 - alpha) * result[-1])
    return result



def _macd(values):
    if len(values) < 35:
        return {"dif": None, "dea": None, "histogram": None, "histogram_change": "数据待核", "bars": len(values)}
    dif = [a - b for a, b in zip(_ema(values, 12), _ema(values, 26))]
    dea = _ema(dif, 9)
    histogram = [2 * (a - b) for a, b in zip(dif, dea)]
    last, previous = histogram[-1], histogram[-2]
    if last > 0 and previous < 0:
        change = "由绿转红"
    elif last < 0 and previous > 0:
        change = "由红转绿"
    else:
        color = "红柱" if last >= 0 else "绿柱"
        change = color + ("放大" if abs(last) > abs(previous) else "收窄" if abs(last) < abs(previous) else "持平")
    return {"dif": dif[-1], "dea": dea[-1], "histogram": last, "previous_histogram": previous,
            "histogram_change": change, "bars": len(values)}


def _weekly_rows(rows, as_of):
    cutoff = _date(as_of)
    grouped = {}
    for row in rows:
        date = _date(row["date"])
        if date > cutoff:
            continue
        key = date.isocalendar()[:2]
        grouped.setdefault(key, []).append(row)
    result = []
    for group in grouped.values():
        result.append({"date": group[-1]["date"], "open": group[0]["open"], "close": group[-1]["close"],
                       "high": max(r["high"] for r in group), "low": min(r["low"] for r in group)})
    return result


def calculate_indicators(rows, as_of):
    """No row beyond as_of can affect any indicator, including unfinished weeks."""
    day = _date(as_of)
    rows = sorted((row for row in rows if _date(row["date"]) <= day), key=lambda row: row["date"])
    if not rows:
        raise DataUnavailable("没有截至日行情")
    close = [float(row["close"]) for row in rows]
    moving = {f"ma{period}": (sum(close[-period:]) / period if len(close) >= period else None) for period in (5, 10, 20, 60)}
    bullish = (close[-1] > moving["ma5"] > moving["ma10"] > moving["ma20"] > moving["ma60"]) if moving["ma60"] is not None else None
    weeks = _weekly_rows(rows, day)
    weekly_close = [float(row["close"]) for row in weeks]
    fast, slow = _ema(weekly_close, 12), _ema(weekly_close, 26)
    dif = [a - b for a, b in zip(fast, slow)]
    dea = _ema(dif, 9)
    histogram = [2 * (a - b) for a, b in zip(dif, dea)]
    sufficient = len(weeks) >= 35
    result = {"as_of": day.isoformat(), "price_date": rows[-1]["date"], "close": close[-1], "volume": rows[-1].get("volume"),
              **moving, "strict_bullish_alignment": bullish, "daily_bars": len(rows), "daily_macd": _macd(close),
              "weekly": {"as_of": weeks[-1]["date"], "bars": len(weeks), "sufficient_history": sufficient,
                         "dif": dif[-1] if sufficient else None, "dea": dea[-1] if sufficient else None,
                         "histogram": histogram[-1] if sufficient else None,
                         "previous_histogram": histogram[-2] if sufficient else None,
                         "above_zero_axis": dif[-1] > 0 and dea[-1] > 0 if sufficient else None,
                         "histogram_change": _macd(weekly_close)["histogram_change"],
                         "divergence": "待核（未采用未经验证的背离算法）"}}
    return result


def _profile(code, cache_dir):
    suffix = "SH" if code.startswith("6") else "SZ"
    params = {"reportName": "RPT_F10_BASIC_ORGINFO", "columns": "ALL", "filter": f'(SECUCODE="{code}.{suffix}")', "pageNumber": 1, "pageSize": 1}
    raw = _cached_json(Path(cache_dir) / "profiles" / f"{code}.json", lambda: _request_json("https://datacenter.eastmoney.com/securities/api/data/v1/get", params))
    values = (raw.get("result") or {}).get("data") or []
    if not values:
        raise DataUnavailable("公司行业信息为空")
    hierarchy = values[0].get("BOARD_NAME_LEVEL") or ""
    if not hierarchy:
        raise DataUnavailable("未返回申万行业层级")
    return {"level1": hierarchy.split("-")[0], "hierarchy": hierarchy, "source": "Eastmoney RPT_F10_BASIC_ORGINFO.BOARD_NAME_LEVEL"}


def _board_map(cache_dir):
    records = []
    for number in range(1, 12):
        params = {"pn": number, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f12", "fs": "m:90+t:2+f:!50", "fields": "f12,f14"}
        raw = _cached_json(Path(cache_dir) / "industries" / f"board-list-{number}.json", lambda: _request_json("https://push2.eastmoney.com/api/qt/clist/get", params))
        data = raw.get("data") or {}
        values = data.get("diff") or []
        if isinstance(values, dict):
            values = list(values.values())
        records += values
        if len(records) >= int(data.get("total", 0)):
            return {x["f14"]: x["f12"] for x in records}
        if not values:
            break
    raise DataUnavailable("行业板块列表分页不完整")


def _board_daily(board, as_of, cache_dir):
    day = _date(as_of)
    params = {"secid": "90." + board, "klt": 101, "fqt": 1, "beg": (day-dt.timedelta(days=1200)).strftime("%Y%m%d"),
              "end": day.strftime("%Y%m%d"), "lmt": 1000, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56"}
    raw = _cached_json(Path(cache_dir) / "industries" / day.isoformat() / f"{board}.json", lambda: _request_json("https://push2his.eastmoney.com/api/qt/stock/kline/get", params, attempts=2))
    values = (raw.get("data") or {}).get("klines") or []
    rows = []
    for line in values:
        value = line.split(",")
        if _date(value[0]) <= day:
            rows.append({"date": value[0], "open": float(value[1]), "close": float(value[2]), "high": float(value[3]), "low": float(value[4]), "volume": float(value[5])})
    if not rows:
        raise DataUnavailable("行业指数日K为空")
    return rows


def _limit_pool(as_of, cache_dir):
    day = _date(as_of).strftime("%Y%m%d")
    params = {"ut": "7eea3edcaed734bea9cbfc24409ed989", "pageindex": 0, "pagesize": 1000, "sort": "fbt:asc", "date": day}
    raw = _cached_json(Path(cache_dir) / "market" / day / "limit-up-pool.json", lambda: _request_json("https://push2ex.eastmoney.com/getTopicZTPool", params))
    data = raw.get("data")
    if raw.get("rc") != 0 or not isinstance(data, dict) or "pool" not in data:
        raise DataUnavailable("当日涨停池不支持该历史日或来源不可用")
    pool = data.get("pool") or []
    if len(pool) < int(data.get("tc", 0)):
        raise DataUnavailable("涨停池返回不完整")
    return pool


def enrich_technical(items, date, cache_dir):
    if not items:
        return [], []
    day = _date(date).isoformat()
    gaps, results = [], []
    market_day = None
    try:
        if is_trading_day(day, cache_dir):
            market_day = day
        else:
            index_rows = _fetch_daily("000001", day, cache_dir, market="1")
            sessions = [_date(row["date"]) for row in index_rows if _date(row["date"]) <= _date(day)]
            if not sessions or max(sessions) >= _date(day):
                raise DataUnavailable("截至报告日无可核验的最近上证交易日")
            market_day = max(sessions).isoformat()
    except Exception as exc:
        gaps.append(f"最近市场交易日待核（{exc}）")
    unique = {item["code"]: item for item in items}
    profiles, indicators = {}, {}
    for code, item in unique.items():
        market = str(item.get("market", "1" if code.startswith("6") else "0"))
        try:
            rows = _fetch_daily(code, day, cache_dir, market)
            indicators[code] = calculate_indicators(rows, day)
            if market_day is not None and indicators[code]["price_date"] != market_day:
                gaps.append(f"{code}: 最近市场交易日{market_day}无成交行情，技术数据停留在{indicators[code]['price_date']}，不作为最近交易日确认")
        except Exception as exc:
            indicators[code] = {"status": "待核", "reason": str(exc)}
            gaps.append(f"{code}: 个股MA/周MACD待核（{exc}）")
        try:
            profiles[code] = _profile(code, cache_dir)
        except Exception as exc:
            profiles[code] = {"level1": "待核", "status": "待核", "reason": str(exc)}
            gaps.append(f"{code}: 申万一级行业待核（{exc}）")
    industries = {p["level1"] for p in profiles.values() if p.get("level1") != "待核"}
    industry_metrics = {}
    try:
        boards = _board_map(cache_dir) if industries else {}
    except Exception as exc:
        boards = {}
        gaps.append(f"行业指数映射待核（{exc}）")
    for name in sorted(industries):
        try:
            if name not in boards:
                raise DataUnavailable("无同名申万一级板块代码")
            industry_metrics[name] = {"board_code": boards[name], **calculate_indicators(_board_daily(boards[name], day, cache_dir), day)}
        except Exception as exc:
            industry_metrics[name] = {"status": "待核", "reason": str(exc)}
            gaps.append(f"{name}: 行业指数MA/日MACD待核（{exc}）")
    try:
        if market_day is None:
            raise DataUnavailable("最近市场交易日尚未核验")
        pool = _limit_pool(market_day, cache_dir)
        codes = {str(value.get("c")) for value in pool}
        # Derive breadth only from stock-level Shenwan profiles; pool.hybk may
        # use a different industry taxonomy and must not be silently relabeled.
        shsz_codes = {code for code in codes if _is_shsz_a({"stock_code": code, "market_code": "1" if code.startswith("6") else "0"})}
        missing_profiles = sorted(shsz_codes - set(profiles))
        def pool_profile(code):
            try:
                return code, _profile(code, cache_dir), None
            except Exception as exc:
                return code, None, str(exc)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            extra_profiles = list(executor.map(pool_profile, missing_profiles))
        pool_profiles = {code: profiles[code] for code in shsz_codes if code in profiles}
        unmapped = []
        for code, profile, error in extra_profiles:
            if profile is not None:
                pool_profiles[code] = profile
            else:
                unmapped.append(code)
                gaps.append(f"涨停股{code}: 申万一级行业映射待核（{error}）")
        unmapped += [code for code, profile in pool_profiles.items() if not profile.get("level1") or profile["level1"] == "待核"]
        industry_counts = {}
        if not unmapped:
            for profile in pool_profiles.values():
                name = profile["level1"]
                industry_counts[name] = industry_counts.get(name, 0) + 1
        else:
            gaps.append("申万行业涨停数待核：涨停池行业未全部映射（" + ",".join(sorted(set(unmapped))) + "）")
        limit_info = {"status": "available", "date": market_day, "market_count": len(shsz_codes), "codes": shsz_codes,
                      "industry_counts": industry_counts if not unmapped else None}
    except Exception as exc:
        limit_info = {"status": "待核", "reason": str(exc)}
        gaps.append(f"当日涨停及申万行业涨停数待核（{exc}）")
    for item in items:
        result = dict(item)
        code = item["code"]
        industry = dict(profiles[code])
        industry["technical"] = industry_metrics.get(industry.get("level1"), {"status": "待核"})
        industry["limit_up_count"] = limit_info["industry_counts"].get(industry.get("level1"), 0) if limit_info.get("industry_counts") is not None and industry.get("level1") != "待核" else "数据待核"
        technical = dict(indicators[code])
        technical["audit"] = dict(indicators[code])
        for number in ("close", "ma5", "ma10", "ma20", "ma60"):
            if isinstance(technical.get(number), (int, float)):
                technical[number] = round(technical[number], 3)
        weekly = technical.get("weekly") or {}
        current = market_day is not None and technical.get("price_date") == market_day
        latest_volume = technical.get("volume") if current else None
        status = "停牌" if current and latest_volume == 0 else "正常" if current else "数据待核"
        bullish = technical.get("strict_bullish_alignment") if current and status != "停牌" else None
        dif, dea = weekly.get("dif"), weekly.get("dea")
        weekly_trend = "金叉" if dif is not None and dea is not None and dif > dea else "死叉" if dif is not None and dea is not None and dif < dea else "零轴重合" if dif is not None else "数据待核"
        axis = "零轴上方" if dif is not None and dea is not None and dif > 0 and dea > 0 else "零轴下方" if dif is not None and dea is not None and dif < 0 and dea < 0 else "跨零轴" if dif is not None else "数据待核"
        index_technical = industry["technical"]
        if index_technical.get("status") == "待核":
            index_description = "数据待核"
        else:
            index_daily = index_technical.get("daily_macd") or {}
            index_bull = "是" if index_technical.get("strict_bullish_alignment") is True else "否" if index_technical.get("strict_bullish_alignment") is False else "待核"
            index_macd = "金叉" if index_daily.get("dif") is not None and index_daily.get("dea") is not None and index_daily["dif"] > index_daily["dea"] else "死叉" if index_daily.get("dif") is not None and index_daily.get("dea") is not None and index_daily["dif"] < index_daily["dea"] else "待核"
            index_close = index_technical.get("close")
            relative = []
            for period in (20, 60):
                value = index_technical.get(f"ma{period}")
                relative.append(f"MA{period}" + ("上方" if index_close is not None and value is not None and index_close > value else "下方" if index_close is not None and value is not None and index_close < value else "重合" if value is not None else "待核"))
            index_description = f"指数点位{index_close}（{'、'.join(relative)}）；日线多头：{index_bull}；日MACD：{index_macd}（{index_daily.get('histogram_change', '待核')}）；MA5/10/20/60=" + "/".join(str(round(index_technical[f"ma{period}"], 3)) if index_technical.get(f"ma{period}") is not None else "待核" for period in (5,10,20,60))
        technical.update(status=status, bullish=bullish, market_date=market_day, limit_up_date=limit_info.get("date"), weekly_trend=weekly_trend,
                         weekly_dif=round(dif, 4) if dif is not None else None, weekly_dea=round(dea, 4) if dea is not None else None,
                         weekly_macd=round(weekly["histogram"], 4) if weekly.get("histogram") is not None else None,
                         weekly_axis=axis, weekly_hist_change=weekly.get("histogram_change", "数据待核"),
                         divergence=weekly.get("divergence", "数据待核"), industry=industry.get("level1", "数据待核"),
                         industry_technical=index_description, limit_up_count=industry["limit_up_count"])
        result["technical"] = technical
        result["industry"] = industry
        result["limit_up"] = (code in limit_info["codes"]) if limit_info["status"] == "available" else "待核"
        results.append(result)
    return results, gaps
