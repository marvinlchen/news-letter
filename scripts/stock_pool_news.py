#!/usr/bin/env python3
"""股票池重要新闻日报生成器。

读取 config/stock_pool.json 中的自选股票池，通过 Google News RSS 抓取“前一天”
（生成日的前 N 个自然日，默认 1 = 昨天）的候选新闻（中文源为主、英文源为辅），
先做一遍确定性“近似标题去重”（只合并措辞/来源不同但明显是同一条的新闻），
再交由 hy3 逐只股票筛选重要新闻、对仍可能存在的同类事件只保留一条，生成中文日报。
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

CONFIG_PATH = PROJECT_ROOT / "config" / "stock_pool.json"
DEFAULT_MODEL = "hy3"
MAX_CANDIDATES = 12
MAX_RECORDS_PER_QUERY = 25
INTER_QUERY_DELAY = 3  # 秒，两次查询之间的礼貌间隔
# 近似标题去重阈值：两条标题的字符 bigram Jaccard 相似度达到该值即视为同一条新闻
LEXICAL_DUP_THRESHOLD = 0.8
CODEBUDDY_FALLBACK = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy"
NODE_FALLBACK = "/home/ME/.local/lib/nodejs/node-v22.22.3-linux-x64/bin/node"


def tz_now():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return dt.datetime.now()


def fmt_date(d):
    return d.strftime("%Y-%m-%d")


def load_config():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    stocks = data.get("stocks", [])
    if not stocks:
        raise SystemExit("stock_pool.json 中没有配置任何股票")
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
    articles = []
    if cn or en:
        q_cn = " OR ".join(f'"{n}"' for n in [cn, en] if n)
        url = build_gnews_url(q_cn, "zh-CN", "CN", "CN:zh-Hans", tday)
        try:
            articles += _gnews_fetch(url, stock.get("name_zh"))
        except Exception as exc:
            print(f"[WARN] Google News 中文源抓取失败 {stock.get('name_zh')}: {exc}", file=sys.stderr)
        time.sleep(INTER_QUERY_DELAY)
    if en:
        url_en = build_gnews_url(f'"{en}"', "en-US", "US", "US:en", tday)
        try:
            articles += _gnews_fetch(url_en, stock.get("name_zh"))
        except Exception as exc:
            print(f"[WARN] Google News 英文源抓取失败 {stock.get('name_zh')}: {exc}", file=sys.stderr)
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


def build_prompt(stocks, candidates, tday):
    today = fmt_date(tday)  # 报告日=新闻日，标题与新闻日期一致
    blocks = []
    for idx, s in enumerate(stocks, 1):
        arts = candidates.get(s["name_zh"], [])
        blocks.append(f"{idx}. {s['name_zh']} ({s.get('ticker','')})\n"
                      f"候选新闻（ID | 标题 | 来源 | 日期）：\n{build_candidate_block(idx, arts)}")
    stock_pool_text = "\n\n".join(blocks)
    n = len(stocks)
    return f"""你是一名中文财经新闻编辑。下面是针对一个自选股票池、日期为 {tday}（前一天）通过 Google News 搜集到的候选新闻（已按中文源为主、英文源为辅整理）。请逐只股票筛选“重要新闻”、并对同类事件去重，输出一份中文日报。

筛选标准（满足任一即算重要）：
- 影响公司基本面/业绩（财报、指引、盈利预警、分红、回购）
- 重大公司事件（并购、分拆、增发、债务、高管变动、诉讼、监管处罚）
- 股价/估值重大异动及其原因
- 行业政策、地缘或宏观对该公司有直接重大影响的
不重要的（无关软文、重复旧闻、纯行情播报无原因）不要列入。

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
        cmd = [exe, "-p", "--output-format", "json", "--input-format", "text"]
    else:
        cmd = [NODE_FALLBACK, CODEBUDDY_FALLBACK, "-p", "--output-format", "json", "--input-format", "text"]
    if model:
        cmd.append(f"--model={model}")
    cmd.append(prompt)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "no output")[-2000:])
    text = extract_text(r.stdout)
    if not text:
        raise RuntimeError("codebuddy 返回空内容")
    return text


def assemble(stocks, candidates_map, raw):
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
        sections[matched] = None if none_flag else items

    out = []
    for idx, s in enumerate(stocks, 1):
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
    return f"""# 股票池重要新闻日报 — {date_str}

> 生成模式：`{model}` · 新闻窗口：前一天（{tday}，自然日）· 生成时间：{fmt_date(tz_now())} · AI去重：开
> 新闻链接可能受订阅或付费墙限制。

{body}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=str(PROJECT_ROOT / "published" / "stock-pool"))
    ap.add_argument("--date", default=None, help="报告日期 YYYY-MM-DD，默认=新闻日(前一天)")
    ap.add_argument("--no-ai", action="store_true", help="仅抓取候选并打印，不调用 AI")
    args = ap.parse_args()

    model = os.environ.get("STOCK_POOL_AI_MODEL_NAME", DEFAULT_MODEL)
    stocks, window = load_config()
    tday = target_day(window)
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

    prompt = build_prompt(stocks, candidates, tday)
    try:
        raw = call_codebuddy(prompt, model)
        body = assemble(stocks, candidates_map, raw)
    except Exception as exc:
        print(f"[ERROR] AI 生成失败: {exc}", file=sys.stderr)
        body = "\n".join(
            f"## {i}. {s['name_zh']} ({s.get('ticker','')})\n暂无重要新闻（生成异常，请稍后重试）\n"
            for i, s in enumerate(stocks, 1)
        )

    report = render_report(report_date, model, tday, body)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{report_date}.md"
    out_file.write_text(report, encoding="utf-8")
    print(f"[INFO] 报告已生成: {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
