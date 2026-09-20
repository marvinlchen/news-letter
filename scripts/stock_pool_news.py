#!/usr/bin/env python3
"""股票池重要新闻日报生成器。

读取 config/stock_pool.json 中的自选股票池，通过 Google News RSS 抓取“前一天”
（生成日的前 N 个自然日，默认 1 = 昨天）的候选新闻（中文源为主、英文源为辅），
先做一遍确定性“近似标题去重”（只合并措辞/来源不同但明显是同一条的新闻），
再交由 CodeBuddy 当前配置模型逐只股票筛选重要新闻、对仍可能存在的同类事件只保留一条，生成中文日报。
无重要新闻的股票保持小节留空。

新闻按自然日过滤：只保留 published_at 落在目标日（前一天）的条目，
不再使用滚动 24 小时窗口，便于按日期区分新闻。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from finance_digest.feeds import fetch_bytes, parse_feed  # noqa: E402

# ===== 交易所官方披露（P0 信息源：SEC EDGAR / A股公告）=====
import urllib.request as _urllib_req
import urllib.parse as _urllib_parse
import json as _json
import ssl as _ssl

_EDGAR_CTX = _ssl.create_default_context()
_EDGAR_CTX.check_hostname = False
_EDGAR_CTX.verify_mode = _ssl.CERT_NONE
_EDGAR_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
_CIK_MAP = None
_ASH_CACHE = {}


class Announcement:
    """轻量公告对象，兼容 Google News 文章在 assemble()/候选构建中使用的字段。"""

    def __init__(self, article_id, title, source, published_at, url):
        self.article_id = article_id
        self.title = title
        self.source = source
        self.published_at = published_at
        self.url = url


def _http_get(url, timeout=25, headers=None):
    h = {"User-Agent": _EDGAR_UA}
    if headers:
        h.update(headers)
    req = _urllib_req.Request(url, headers=h)
    with _urllib_req.urlopen(req, timeout=timeout, context=_EDGAR_CTX) as r:
        return r.read().decode("utf-8", "replace")


def exchange_of_ticker(t):
    t = t or ""
    if t.endswith(".HK"):
        return "hk"
    if t.endswith(".SI"):
        return "sg"
    if t.endswith(".SZ") or t.endswith(".SS"):
        return "ash"
    return "us"


def exchange_of(stock):
    return exchange_of_ticker(stock.get("ticker", "") or "")


def _load_cik_map():
    global _CIK_MAP
    if _CIK_MAP is None:
        try:
            data = _json.loads(_http_get("https://www.sec.gov/files/company_tickers.json"))
            _CIK_MAP = {k.upper(): v["cik_str"] for k, v in data.items()}
        except Exception as exc:
            print(f"[WARN] EDGAR CIK 映射加载失败（美股权威披露暂不可用，回退 Google News）: {exc}",
                  file=sys.stderr)
            _CIK_MAP = {}  # 失败缓存，避免每只美股重复请求被 403
    return _CIK_MAP


def fetch_edgar(ticker, tday):
    """SEC EDGAR 官方申报：ticker -> CIK -> 当日 filing 列表。"""
    ticker = (ticker or "").upper()
    if not ticker:
        return []
    try:
        cik = _load_cik_map().get(ticker)
        if not cik:
            return []
        cik10 = cik.zfill(10)
        sub = _json.loads(_http_get(f"https://data.sec.gov/submissions/CIK{cik10}.json"))
        rec = sub.get("filings", {}).get("recent", {})
        dates = rec.get("filingDate", [])
        forms = rec.get("form", [])
        docs = rec.get("primaryDocument", [])
        accns = rec.get("accessionNumber", [])
        items = rec.get("items", [])
        descs = rec.get("primaryDocDescription", [])
        out = []
        tday_s = tday.isoformat()
        for i in range(len(dates)):
            if dates[i] != tday_s:
                continue
            accn = accns[i]
            doc = docs[i]
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{doc}"
            it = items[i] if i < len(items) else ""
            de = descs[i] if i < len(descs) else ""
            title = forms[i]
            if it:
                title += f" — {it}"
            elif de:
                title += f" — {de}"
            out.append(Announcement(
                f"EDGAR-{accn}-{doc}", title, "SEC EDGAR",
                dt.datetime(tday.year, tday.month, tday.day), url))
        return out
    except Exception as exc:
        print(f"[WARN] EDGAR 抓取失败 {ticker}: {exc}", file=sys.stderr)
        return []


def _load_ashare(tday):
    if tday.isoformat() not in _ASH_CACHE:
        try:
            import akshare as ak
            df = ak.stock_notice_report(symbol="全部", date=tday.strftime("%Y%m%d"))
            _ASH_CACHE[tday.isoformat()] = df
        except Exception as exc:
            print(f"[WARN] A股公告抓取失败: {exc}", file=sys.stderr)
            _ASH_CACHE[tday.isoformat()] = None
    return _ASH_CACHE[tday.isoformat()]


def fetch_ashare_for_code(code, tday):
    df = _load_ashare(tday)
    if df is None or len(df) == 0:
        return []
    sub = df[df["代码"].astype(str).str.strip() == str(code).strip()]
    out = []
    for _, row in sub.iterrows():
        title = str(row.get("公告标题", ""))
        if not title:
            continue
        typ = str(row.get("公告类型", ""))
        url = str(row.get("网址", ""))
        try:
            d = dt.datetime.strptime(str(row.get("公告日期", ""))[:10], "%Y-%m-%d")
        except Exception:
            d = dt.datetime(tday.year, tday.month, tday.day)
        out.append(Announcement(f"ASH-{code}-{abs(hash(title))}", title, f"公告-{typ}", d, url))
    return out



CONFIG_PATH = PROJECT_ROOT / "config" / "stock_pool.json"
DEFAULT_MODEL = ""  # 空 = 使用 CodeBuddy 全局模型（~/.codebuddy/settings.json）
MAX_CANDIDATES = 12
MAX_RECORDS_PER_QUERY = 25
INTER_QUERY_DELAY = 3  # 秒，两次查询之间的礼貌间隔
# 近似标题去重阈值：两条标题的字符 bigram Jaccard 相似度达到该值即视为同一条新闻
LEXICAL_DUP_THRESHOLD = 0.8
CODEBUDDY_FALLBACK = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy"
NODE_FALLBACK = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/bin/node"


def effective_model_name(model):
    if model:
        return model
    try:
        settings = json.loads((Path.home() / ".codebuddy" / "settings.json").read_text(encoding="utf-8"))
        return settings.get("model") or "codebuddy"
    except (OSError, ValueError, TypeError):
        return "codebuddy"


def tz_now():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return dt.datetime.now()


def fmt_date(d):
    return d.strftime("%Y-%m-%d")


def _ah_sort_key(t):
    """A股(.SZ/.SS) 排在 H股(.HK) 前面，其它保持其后。"""
    tk = t.get("ticker", "") or ""
    if tk.endswith(".SZ") or tk.endswith(".SS"):
        return 0
    if tk.endswith(".HK"):
        return 1
    return 2


def merge_stock_groups(stocks):
    """把带有相同 group 的条目合并为一只逻辑股票（同一公司 A股/H股 合并来看）。

    - 约定：给同属一家公司的多个条目配置相同的 `group` 值（一般=公司主名，如“中联重科”）。
    - 无 `group` 字段的条目独立成组，行为与原来完全一致。
    - 合并后：单条 Google News 查询用公司主名+英文名（覆盖 A/H 两地新闻，交给去重处理）；
      交易所官方披露（EDGAR / A股公告）按组内每个 ticker 分别抓取后合并。
    - 展示名取 group 值；代码栏按 “A股 / H股” 顺序展示两个代码。
    """
    order = []
    groups = {}
    for s in stocks:
        key = s.get("group") or s.get("name_zh", "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(s)

    merged = []
    for key in order:
        members = groups[key]
        tickers = [{"ticker": m.get("ticker", ""), "market": m.get("market", "")} for m in members]
        if len(members) == 1:
            s = dict(members[0])
            s["tickers"] = tickers
            merged.append(s)
            continue
        # 多成员合并：优先选 name_zh==group 的成员作为主条目（其英文名/主名更干净）
        base = next((m for m in members if m.get("name_zh") == key), members[0])
        tickers_sorted = sorted(tickers, key=_ah_sort_key)
        merged.append({
            "name_zh": key,
            "name_en": base.get("name_en", ""),
            "ticker": " / ".join(t["ticker"] for t in tickers_sorted if t["ticker"]),
            "market": "+".join(dict.fromkeys(t["market"] for t in tickers_sorted if t["market"])),
            "tickers": tickers_sorted,
        })
    return merged


def load_config(path=None):
    cfg = Path(path) if path else CONFIG_PATH
    data = json.loads(cfg.read_text(encoding="utf-8"))
    stocks = data.get("stocks", [])
    if not stocks:
        raise SystemExit("stock_pool.json 中没有配置任何股票")
    stocks = merge_stock_groups(stocks)  # 合并同一公司的 A股/H股
    # window_days: 目标日相对生成日往前推的自然日数，默认 1 = 昨天
    return stocks, int(data.get("window_days", 1))


def target_day(window_days):
    """生成日（Asia/Shanghai）往前推 window_days 个自然日。"""
    return (tz_now() - dt.timedelta(days=window_days)).date()


def build_gnews_url(query, hl, gl, ceid, tday):
    # 用 after: 把抓取范围锚定到目标日 00:00 起，再在本地按自然日精确过滤
    q = f"{query} after:{tday.isoformat()}"
    params = {"q": q, "hl": hl, "gl": gl, "ceid": ceid}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _gnews_fetch(url, label):
    last = None
    for attempt in range(3):
        try:
            return parse_feed(fetch_bytes(url), {"name": "Google News", "category": "finance"})
        except Exception as exc:
            last = exc
            if attempt + 1 < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    if last is not None:
        raise last
    return []


def fetch_stock_articles(stock, tday):
    cn = stock.get("name_zh", "")
    en = stock.get("name_en", "")
    gn_articles = []
    if cn or en:
        q_cn = " OR ".join(f'"{n}"' for n in [cn, en] if n)
        url = build_gnews_url(q_cn, "zh-CN", "CN", "CN:zh-Hans", tday)
        try:
            gn_articles += _gnews_fetch(url, stock.get("name_zh"))
        except Exception as exc:
            print(f"[WARN] Google News 中文源抓取失败 {stock.get('name_zh')}: {exc}", file=sys.stderr)
        time.sleep(INTER_QUERY_DELAY)
    if en:
        url_en = build_gnews_url(f'"{en}"', "en-US", "US", "US:en", tday)
        try:
            gn_articles += _gnews_fetch(url_en, stock.get("name_zh"))
        except Exception as exc:
            print(f"[WARN] Google News 英文源抓取失败 {stock.get('name_zh')}: {exc}", file=sys.stderr)
    # 交易所官方披露（优先级高于新闻，前置以保证不被候选上限截断）
    # 合并后的公司可能同时有 A股/H股/美股多个 ticker，逐个按其所属交易所抓取官方披露。
    ann = []
    tickers = stock.get("tickers") or [{"ticker": stock.get("ticker", ""), "market": stock.get("market", "")}]
    for t in tickers:
        tk = t.get("ticker", "") or ""
        ex = exchange_of_ticker(tk)
        try:
            if ex == "us":
                ann += fetch_edgar(tk, tday)
            elif ex == "ash":
                ann += fetch_ashare_for_code(tk.split(".")[0], tday)
        except Exception as exc:
            print(f"[WARN] 公告源抓取失败 {stock.get('name_zh')} {tk}: {exc}", file=sys.stderr)
    articles = ann + gn_articles

    # 仅保留目标日（前一天）的条目，按自然日精确过滤（Google News 的 when/before 不可靠）
    seen = {}
    for a in articles:
        if a.published_at is not None and a.published_at.date() == tday:
            seen[a.article_id] = a
    return list(seen.values())


def _norm_title(t):
    t = (t or "").lower()
    t = re.sub(r"[\s\W_]+", "", t)
    return t


def _title_sim(a, b):
    na, nb = _norm_title(a), _norm_title(b)
    if not na or not nb:
        return False
    sa = set(na[i:i + 2] for i in range(len(na) - 1)) or {na}
    sb = set(nb[i:i + 2] for i in range(len(nb) - 1)) or {nb}
    if not sa or not sb:
        return False
    return len(sa & sb) / len(sa | sb) >= LEXICAL_DUP_THRESHOLD


def lexical_dedup(articles, threshold=LEXICAL_DUP_THRESHOLD):
    """确定性近似标题去重：只合并措辞/来源不同但明显是同一条的新闻，保留先出现的。

    阈值设得较高（默认 0.8），仅命中近乎相同标题时才合并，绝不误删独立事件。
    """
    kept = []
    for a in articles:
        if not any(_title_sim(a.title, k.title) for k in kept):
            kept.append(a)
    return kept


def build_candidate_block(idx, articles):
    if not articles:
        return "（无候选新闻）"
    lines = []
    for k, a in enumerate(articles[:MAX_CANDIDATES], 1):
        cid = f"S{idx}-{k}"
        lines.append(f"{cid} | {a.title} | {a.source} | {fmt_date(a.published_at)}")
    return "\n".join(lines)


def build_prompt(stocks, candidates, tday, start_idx=1):
    today = fmt_date(tday)  # 报告日=新闻日，标题与新闻日期一致
    blocks = []
    for local_i, s in enumerate(stocks):
        idx = start_idx + local_i  # 全局序号，保证候选 ID 与 candidates_map 一致
        arts = candidates.get(s["name_zh"], [])
        blocks.append(f"{idx}. {s['name_zh']} ({s.get('ticker','')})\n"
                      f"候选新闻（ID | 标题 | 来源 | 日期）：\n{build_candidate_block(idx, arts)}")
    stock_pool_text = "\n\n".join(blocks)
    n = len(stocks)
    return f"""你是一名中文财经新闻编辑。下面是针对一个自选股票池、日期为 {tday}（前一天）通过 Google News 搜集到的候选新闻（已按中文源为主、英文源为辅整理）。请逐只股票筛选“重要新闻”、并对同类事件去重，输出一份中文日报。
候选里可能包含交易所官方披露（来源标注为 SEC EDGAR 或 公告-xxx 类型），属权威一级信源，通常应视为重要新闻；若与新闻条目重复，以官方披露为准并去重，不要重复列出。

筛选标准（满足任一即算重要）：
- 影响公司基本面/业绩（财报、指引、盈利预警、分红、回购）
- 重大公司事件（并购、分拆、增发、债务、高管变动、诉讼、监管处罚）
- 股价/估值重大异动及其原因
- 行业政策、地缘或宏观对该公司有直接重大影响的
不重要的（无关软文、重复旧闻、纯行情播报无原因）不要列入。
- 候选标题里的公司名/关键词若实际指向其它实体（如地名、人名、其它公司），属关键词误匹配，不得列为条目，也不要在摘要里解释为何排除；若该股票无其他真实新闻，整节输出"暂无重要新闻"。

去重规则（务必遵守）：
- 同一事件若被多条候选覆盖（不同来源、不同措辞，例如“腾讯减持快手套现百亿”在多家媒体的报道），只保留最具代表性的一条，绝不要同一条新闻重复列出。
- 跨股票出现的同一宏观/行业事件，只在最相关的一只股票下列出；其他股票若确实也受直接影响，用一句话带过即可，不要整条重复。

对每个股票，输出小节。格式（严格遵守）：
## 序号. 中文名 (代码)
若有重要新闻，每条一行：
- 候选ID | 中文标题 | 摘要（中文1-2句，说明为什么重要）
若没有重要新闻：
- 暂无重要新闻

注意：
- “候选ID”必须原样复制自上面的候选列表（如 S1-3），不要编造；我会用它还原真实链接。
- 每只股票最多 5 条，按重要性排序。
- 必须包含全部 {n} 只股票小节，顺序与“股票池”完全一致。
- 只输出报告正文（从第一个 ## 开始），不要代码块或额外解释。

===== 股票池（{today}，覆盖 {tday} 新闻） =====
{stock_pool_text}
"""


def extract_text(output):
    t = output.strip()
    try:
        p = json.loads(t)
    except Exception:
        return t
    if isinstance(p, list):
        for m in reversed(p):
            if isinstance(m, dict) and m.get("role") == "assistant":
                c = m.get("content")
                if isinstance(c, str):
                    return c.strip()
                if isinstance(c, list):
                    for it in c:
                        if isinstance(it, dict) and it.get("type") in ("text", "output_text") and isinstance(it.get("text"), str):
                            return it["text"].strip()
    if isinstance(p, dict):
        for k in ("result", "response", "text", "content", "message"):
            v = p.get(k)
            if isinstance(v, str):
                return v.strip()
    return t


def call_codebuddy(prompt, model, timeout=900):
    exe = shutil.which("codebuddy")
    if exe:
        cmd = [exe, "-p", "--output-format", "text", "--input-format", "text"]
    else:
        cmd = [NODE_FALLBACK, CODEBUDDY_FALLBACK, "-p", "--output-format", "text", "--input-format", "text"]
    if model:
        cmd.append(f"--model={model}")
    cmd.append(prompt)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "no output")[-2000:])
    text = extract_text(r.stdout)
    if not text:
        raise RuntimeError("codebuddy 返回空内容")
    return text


_EXCLUSION_RE = re.compile(r"不列为|误匹配|地名|与.{1,12}无关|非公司新闻|不视为公司新闻")
def _is_exclusion(title, summary):
    """True if the AI marked this candidate as an excluded / false-positive match."""
    text = (title or "") + " " + (summary or "")
    return bool(_EXCLUSION_RE.search(text))


def assemble(stocks, candidates_map, raw, start_idx=1):
    parts = re.split(r"(?m)^##\s+", raw)
    sections = {}
    for part in parts[1:]:
        lines = part.splitlines()
        heading = lines[0].strip()
        body_lines = [l.strip() for l in lines[1:] if l.strip()]
        matched = None
        for s in stocks:
            if s["name_zh"] in heading or s.get("ticker", "") in heading:
                matched = s["name_zh"]
                break
        if matched is None:
            continue
        items = []
        none_flag = False
        for l in body_lines:
            if l.startswith("暂无重要新闻"):
                none_flag = True
                break
            m = re.match(r"^-\s*(S\d+-\d+)\s*\|\s*(.*?)\s*\|\s*(.*)$", l)
            if m:
                items.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
                continue
            m2 = re.match(r"^-\s*(S\d+-\d+)\s*\|\s*(.*)$", l)
            if m2:
                items.append((m2.group(1), m2.group(2).strip(), ""))
        if not none_flag:
            items = [it for it in items if not _is_exclusion(it[1], it[2])]
        sections[matched] = None if none_flag else items

    out = []
    for local_i, s in enumerate(stocks):
        idx = start_idx + local_i  # 全局序号，保证分批拼接后编号连续
        out.append(f"## {idx}. {s['name_zh']} ({s.get('ticker','')})")
        items = sections.get(s["name_zh"])
        if not items:
            out.append("暂无重要新闻")
        else:
            for (cid, title, summary) in items:
                art = candidates_map.get(cid)
                if art is None:
                    out.append(f"- {title}" if title else f"- {cid}")
                    if summary:
                        out.append(f"  {summary}")
                    continue
                dtxt = fmt_date(art.published_at)
                out.append(f"- [{title or art.title}]({art.url}) — {art.source} · {dtxt}")
                if summary:
                    out.append(f"  {summary}")
        out.append("")
    return "\n".join(out).strip() + "\n"


def render_report(date_str, model, tday, body):
    model_label = effective_model_name(model)
    return f"""# 股票池重要新闻日报 — {date_str}

> 生成模式：`{model_label}` · 新闻窗口：前一天（{tday}，自然日）· 生成时间：{fmt_date(tz_now())} · AI去重：开
> 新闻链接可能受订阅或付费墙限制。

{body}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=str(PROJECT_ROOT / "published" / "stock-pool"))
    ap.add_argument("--date", default=None, help="报告日期 YYYY-MM-DD，默认=新闻日(前一天)")
    ap.add_argument("--no-ai", action="store_true", help="仅抓取候选并打印，不调用 AI")
    ap.add_argument("--config", default=None, help="股票池配置文件路径，默认 config/stock_pool.json")
    args = ap.parse_args()

    model = os.environ.get("STOCK_POOL_AI_MODEL_NAME", DEFAULT_MODEL)
    stocks, window = load_config(args.config)
    tday = target_day(window)
    if args.date:
        # 指定报告日期时，新闻窗口也锚定到该日，使标题日期与内容日期一致
        tday = dt.date.fromisoformat(args.date)
    report_date = args.date or fmt_date(tday)  # 文件名=新闻日，使标题日期与新闻日期一致

    candidates = {}
    candidates_map = {}
    for idx, s in enumerate(stocks, 1):
        arts = fetch_stock_articles(s, tday)
        before = len(arts)
        arts = lexical_dedup(arts)  # 确定性近似标题去重（同事件不同来源）
        candidates[s["name_zh"]] = arts
        for k, a in enumerate(arts[:MAX_CANDIDATES], 1):
            candidates_map[f"S{idx}-{k}"] = a
        print(f"[INFO] {s['name_zh']}: 候选 {before} -> 去重后 {len(arts)} 条", file=sys.stderr)
        time.sleep(INTER_QUERY_DELAY)

    if args.no_ai:
        for idx, s in enumerate(stocks, 1):
            print(f"### {idx}. {s['name_zh']}")
            print(build_candidate_block(idx, candidates[s['name_zh']]))
        return

    # 分批调用 AI：单次提示词/输出过大会触发 64KB 截断（position 65535 解码失败）或响应退化。
    # 每批 12 只，既保证单批输出远小于 64KB，也降低单批失败影响范围。
    BATCH = 12
    bodies = []
    for bi in range(0, len(stocks), BATCH):
        batch = stocks[bi:bi + BATCH]
        prompt = build_prompt(batch, candidates, tday, start_idx=bi + 1)
        try:
            raw = call_codebuddy(prompt, model)
            bodies.append(assemble(batch, candidates_map, raw, start_idx=bi + 1))
            print(f"[INFO] AI 批次 {bi // BATCH + 1} 完成（{bi + 1}-{bi + len(batch)}/{len(stocks)}）", file=sys.stderr)
        except Exception as exc:
            print(f"[ERROR] AI 批次生成失败 {bi + 1}-{bi + len(batch)}: {exc}", file=sys.stderr)
            bodies.append("\n".join(
                f"## {bi + j}. {s['name_zh']} ({s.get('ticker','')})\n暂无重要新闻（生成异常，请稍后重试）\n"
                for j, s in enumerate(batch, 1)
            ))
    body = "\n".join(bodies)

    report = render_report(report_date, model, tday, body)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{report_date}.md"
    out_file.write_text(report, encoding="utf-8")
    print(f"[INFO] 报告已生成: {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
