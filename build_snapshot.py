#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a permanent HTML snapshot archive of the
"✅ 今日卖出 / 下架（先前在售，连续消失≥7天）" category from the
hdb_monitor daily report archive + state.json.

The daily report only prints a bare one-liner for sold listings
(block + price + url), and the PropertyGuru page is deleted by then.
This script reconstructs, for every listing ever flagged as sold,
what it looked like while it was still on the market.

Inputs : reports/report_YYYY-MM-DD.md , state.json
Output : hdb-sold-snapshot.html
"""

import json
import os
import re
import html
import argparse
from datetime import date, datetime

try:
    from dulwich import porcelain
    from dulwich.repo import Repo
    HAVE_DULWICH = True
except ImportError:
    HAVE_DULWICH = False

GIT_AUTHOR = b'marvinlchen <marvinlchen@users.noreply.github.com>'
GIT_REMOTE = 'origin'
GIT_REMOTE_URL = 'git@github.com:marvinlchen/news-letter.git'
GIT_LOCAL_REF = 'refs/heads/master'
GIT_REMOTE_REF = 'refs/heads/hdb-monitor'

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(HERE, "reports")
STATE_FILE = os.path.join(HERE, "state.json")
ARCHIVE_DIR = os.path.join(HERE, "archive")
OUT_FILE = os.path.join(HERE, "hdb-sold-snapshot.html")

REPO = "https://github.com/marvinlchen/news-letter"
BRANCH = "hdb-monitor"
# Absolute URLs so archived photos render no matter where this HTML is hosted
# (githack / Pages / htmlpreview all resolve an absolute raw URL identically).
REPO_RAW = "https://raw.githubusercontent.com/marvinlchen/news-letter/hdb-monitor/"

RE_DATE = re.compile(r"report_(\d{4}-\d{2}-\d{2})\.md$")
RE_ID = re.compile(r"-(\d+)$")
RE_HDR = re.compile(r"^- \*\*(.+?)\*\*\s*$")
RE_SUB = re.compile(r"^  - (.+?)(?: · 中介: (.+))?$")
RE_LISTED = re.compile(r"^  - \U0001F552 平台显示上架: (.+?)(?:（.*)?$")
RE_PRICEHIST = re.compile(r"^  - \U0001F4C8 历史价格: (.+)$")
RE_URL = re.compile(r"^  - (https?://\S+)$")
RE_SOLD_LINE = re.compile(r"^- \[(?P<block>[^\]]+)\]\s*(?P<price>[^·]*?)·\s*(?P<url>https?://\S+)")


def d2s(d):
    return d.isoformat() if isinstance(d, date) else str(d)


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def days_between(a, b):
    da, dbb = parse_date(a), parse_date(b)
    if not da or not dbb:
        return None
    return (dbb - da).days


def money(p):
    if not p:
        return None
    return "S${:,}".format(int(p))


def parse_price(tok):
    """'S$1,150,000' -> 1150000 ; '价格未公开' -> None"""
    if not tok:
        return None
    m = re.search(r"S\$([\d,]+)", tok)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_report(path):
    """Return (date_str, {listing_id: record}, [sold_id, ...])"""
    name = os.path.basename(path)
    m = RE_DATE.search(name)
    if not m:
        return None
    rdate = m.group(1)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    listings = {}
    sold = []

    mode = None
    cur = None

    def flush():
        nonlocal cur
        if cur and cur.get("id"):
            listings[cur["id"]] = cur
        cur = None

    for ln in lines:
        if ln.startswith("## "):
            flush()
            if "今日卖出" in ln:
                mode = "sold"
            elif "当前在售清单" in ln:
                mode = "active"
            else:
                mode = None
            continue

        if mode == "sold":
            sm = RE_SOLD_LINE.match(ln)
            if sm:
                mid = RE_ID.search(sm.group("url").rstrip("/"))
                if mid:
                    sold.append({
                        "id": mid.group(1),
                        "block": sm.group("block").strip(),
                        "url": sm.group("url"),
                        "price_text": sm.group("price").strip(),
                    })
            continue

        if mode != "active":
            continue

        if ln.startswith("- **"):
            flush()
            hm = RE_HDR.match(ln)
            if not hm:
                continue
            parts = [p.strip() for p in hm.group(1).split("·")]
            price = parse_price(parts[0]) if parts else None
            area = psf = floor = None
            for p in parts[1:]:
                am = re.match(r"^([\d,]+)\s*sqft$", p)
                pm = re.match(r"^S\$([\d,]+)/sqft$", p)
                if am:
                    area = int(am.group(1).replace(",", ""))
                elif pm:
                    psf = int(pm.group(1).replace(",", ""))
                elif p and p not in ("价格未公开",):
                    floor = p
            cur = {"date": rdate, "price": price, "area": area, "psf": psf,
                   "floor": floor, "price_text": parts[0] if parts else None}
            continue

        if cur is None:
            continue

        um = RE_URL.match(ln)
        if um:
            url = um.group(1)
            cur["url"] = url
            mid = RE_ID.search(url.rstrip("/"))
            if mid:
                cur["id"] = mid.group(1)
            continue

        lm = RE_LISTED.match(ln)
        if lm:
            cur["listed_on"] = lm.group(1).strip()
            continue

        phm = RE_PRICEHIST.match(ln)
        if phm:
            cur["price_hist_text"] = phm.group(1).strip()
            continue

        sm = RE_SUB.match(ln)
        if sm:
            txt = sm.group(1).strip()
            agent = (sm.group(2) or "").strip()
            if agent:
                cur["summary"] = txt
                cur["agent"] = agent
            else:
                cur["summary"] = txt
            continue

    flush()
    return rdate, listings, sold


LOG_PREFIX = "[hdb-sold-snapshot] "


def log(msg):
    print(LOG_PREFIX + msg, flush=True)


def git_commit_push(files, msg):
    """Commit the given files and push master -> origin/hdb-monitor.

    Mirrors hdb_monitor.py: pure-Python dulwich, no git binary needed on the
    non-interactive PATH. Never raises — the snapshot itself is already on disk.
    """
    if not HAVE_DULWICH:
        log("dulwich 不可用，跳过 git 提交/推送")
        return False
    if not os.path.exists(os.path.join(HERE, ".git")):
        log("本地无 .git 仓库，跳过 git 提交/推送")
        return False
    try:
        for p in files:
            fp = os.path.join(HERE, p)
            if os.path.exists(fp):
                porcelain.add(HERE, fp)
        st = porcelain.status(HERE)
        if not any(st.staged.get(k) for k in ("add", "modify", "delete")):
            log("无变更，跳过提交")
            return False
        porcelain.commit(HERE, msg, author=GIT_AUTHOR, committer=GIT_AUTHOR)
        log("已 git commit: " + msg)
        r = Repo(HERE)
        if not r.get_config().has_section((b"remote", GIT_REMOTE.encode())):
            porcelain.remote_add(HERE, GIT_REMOTE, GIT_REMOTE_URL)
        res = porcelain.push(HERE, GIT_REMOTE, [f"{GIT_LOCAL_REF}:{GIT_REMOTE_REF}"])
        log(f"已 git push -> {GIT_REMOTE}/{GIT_REMOTE_REF.split('/')[-1]} ({res})")
        return True
    except Exception as e:
        log("git 提交/推送跳过: " + str(e)[:160])
        return False


def load_archive_meta(lid):
    """Full detail-page archive captured while the listing was still live.

    Only exists for listings the archiver saw on-market. Listings that were
    already gone before archiving started have nothing — PropertyGuru deletes
    photos and description as soon as a listing goes off-market.
    """
    p = os.path.join(ARCHIVE_DIR, str(lid), "meta.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="HDB 卖出/下架 房源快照归档生成器")
    ap.add_argument("--push", action="store_true",
                    help="生成后提交并推送到 origin/hdb-monitor（在 memini 上由 cron 使用）")
    args = ap.parse_args()

    if not os.path.isdir(REPORT_DIR):
        raise SystemExit("reports/ not found next to this script")

    files = sorted(
        (os.path.join(REPORT_DIR, f) for f in os.listdir(REPORT_DIR)
         if RE_DATE.search(f)),
        key=lambda p: RE_DATE.search(os.path.basename(p)).group(1),
    )

    reports = []            # [(date, listings, sold)]
    sold_events = []        # [(date, sold_rec)]
    for p in files:
        r = parse_report(p)
        if not r:
            continue
        rdate, listings, sold = r
        reports.append((rdate, listings, sold))
        for s in sold:
            sold_events.append((rdate, s))

    state = json.load(open(STATE_FILE, encoding="utf-8"))
    history = state.get("history", {})
    cur_listings = state.get("listings", {})
    price_history = state.get("price_history", {})
    all_dates = [r[0] for r in reports]
    latest_date = all_dates[-1] if all_dates else d2s(date.today())

    # ---- assemble sold records -------------------------------------------
    out = []
    seen = set()
    for sold_date, s in sold_events:
        lid = s["id"]
        key = (lid, sold_date)
        if key in seen:
            continue
        seen.add(key)

        # latest snapshot while still on the market (strictly before sold date)
        snap, snap_date, first_date = None, None, None
        for rdate, listings, _ in reports:
            if lid in listings:
                if first_date is None:
                    first_date = rdate
                if rdate < sold_date:
                    snap, snap_date = listings[lid], rdate
        h = history.get(lid, {})
        if snap is None:  # never captured on-market (e.g. removed same day)
            snap = {}
            snap_date = None

        traj = price_history.get(lid) or []
        prices = [(d, p) for d, p in traj if p]
        first_price = prices[0][1] if prices else snap.get("price")
        last_price = prices[-1][1] if prices else snap.get("price")
        distinct = sorted({p for _, p in prices})
        last_seen = h.get("last_seen")
        block = s.get("block") or snap.get("block") or h.get("block") or "?"

        currently_active = lid in cur_listings
        status = "relisted" if currently_active else "gone"

        arc = load_archive_meta(lid) or {}

        out.append({
            "id": lid,
            "block": block,
            "url": s.get("url") or snap.get("url") or h.get("url"),
            "sold_date": sold_date,
            "last_seen": last_seen,
            "snap_date": snap_date,
            "first_date": first_date or h.get("first_seen"),
            "price": last_price,
            "first_price": first_price,
            "distinct_prices": distinct,
            "area": snap.get("area") or h.get("area"),
            "psf": snap.get("psf"),
            "floor": snap.get("floor"),
            "summary": snap.get("summary"),
            "agent": snap.get("agent"),
            "listed_on": snap.get("listed_on"),
            "price_hist_text": snap.get("price_hist_text"),
            "raw": snap,
            "obs_days": len(traj),
            "span_days": days_between(first_date or h.get("first_seen"), last_seen),
            "traj": traj,
            "photos": arc.get("photos") or [],
            "floorplans": arc.get("floorplans") or [],
            "description": arc.get("description"),
            "first_posted": arc.get("first_posted"),
            "agent_license": arc.get("agent_license"),
            "archived_at": arc.get("archived_at"),
            "raw_html_gz": os.path.exists(os.path.join(
                ARCHIVE_DIR, str(lid), "page.html.gz")),
            "status": status,
            "report_link": "%s/blob/%s/reports/report_%s.md" % (REPO, BRANCH, snap_date) if snap_date else None,
            "sold_report_link": "%s/blob/%s/reports/report_%s.md" % (REPO, BRANCH, sold_date),
        })

    out.sort(key=lambda r: (r["sold_date"], r["block"]), reverse=True)

    # ---- write html ------------------------------------------------------
    write_html(out, latest_date, len(reports), first_report=all_dates[0])
    log("sold events: %d" % len(out))
    log("reports parsed: %d (%s ~ %s)" % (len(reports), all_dates[0], all_dates[-1]))
    log("written: " + OUT_FILE)

    if args.push:
        gone = sum(1 for r in out if r["status"] == "gone")
        git_commit_push(
            ["build_snapshot.py", OUT_FILE.replace(HERE + os.sep, "")],
            "sold snapshot %s (%d sold / %d gone)" % (latest_date, len(out), gone),
        )


# ------------------------------------------------------------------ HTML ---

def esc(x):
    return html.escape(str(x)) if x is not None else ""


RE_TPL = re.compile(r"%\((\w+)\)s")


def sub_tpl(tpl, mapping):
    """Safely substitute %(name)s tokens without touching literal % in CSS."""
    def rep(m):
        v = mapping.get(m.group(1))
        return "" if v is None else str(v)
    return RE_TPL.sub(rep, tpl)


def build_sparkline(points, w=260, h=44):
    """points: [(date, price)] -> inline svg"""
    pts = [(d, p) for d, p in points if p]
    if len(pts) < 2 or len({p for _, p in pts}) < 2:
        return ""
    vals = [p for _, p in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = hi - 1, hi + 1
    n = len(pts)
    pad = 3
    coords = []
    for i, (_, p) in enumerate(pts):
        x = pad + (w - 2 * pad) * (i / (n - 1))
        y = h - pad - (h - 2 * pad) * ((p - lo) / (hi - lo))
        coords.append((round(x, 2), round(y, 2)))
    line = " ".join("%s,%s" % c for c in coords)
    area = "{},{} {} {},{}".format(coords[0][0], h, line, coords[-1][0], h)
    return (
        '<svg class="spark" viewBox="0 0 %d %d" preserveAspectRatio="none" aria-hidden="true">'
        '<polygon points="%s" fill="var(--spark-fill)"/>'
        '<polyline points="%s" fill="none" stroke="var(--spark)" stroke-width="1.8" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        "</svg>" % (w, h, area, line)
    )


def write_html(rows, latest_date, n_reports, first_report):
    gone = [r for r in rows if r["status"] == "gone"]
    relisted = [r for r in rows if r["status"] == "relisted"]
    priced = [r["price"] for r in gone if r["price"]]
    avg = int(sum(priced) / len(priced)) if priced else 0
    med = sorted(priced)[len(priced) // 2] if priced else 0
    psfs = [r["psf"] for r in gone if r["psf"]]
    avg_psf = int(sum(psfs) / len(psfs)) if psfs else 0
    dom = []
    for r in gone:
        if r["first_date"] and r["last_seen"]:
            v = days_between(r["first_date"], r["last_seen"])
            if v and v > 0:
                dom.append(v)
    avg_dom = int(sum(dom) / len(dom)) if dom else 0

    blocks = sorted({r["block"] for r in rows})
    block_counts = {b: sum(1 for r in rows if r["block"] == b) for b in blocks}

    cards = []
    for r in rows:
        badge = ('<span class="badge gone">已下架</span>' if r["status"] == "gone"
                 else '<span class="badge back">已重新上架 · 当前仍在售</span>')
        price_txt = money(r["price"]) or "价格未公开"
        price_note = ""
        if r["first_price"] and r["price"] and r["first_price"] != r["price"]:
            d = r["price"] - r["first_price"]
            price_note = ('<span class="delta %s">%s%s</span>' % (
                "down" if d > 0 else "up",
                "+" if d > 0 else "−",
                money(abs(d))[2:]))
        hist_note = ""
        if len(r["distinct_prices"]) > 1:
            hist_note = " · 挂牌期内 %d 次调价" % (len(r["distinct_prices"]) - 1)

        meta = []
        if r["area"]:
            meta.append("%s sqft" % format(r["area"], ","))
        if r["psf"]:
            meta.append("S$%s/sqft" % format(r["psf"], ","))
        if r["floor"]:
            meta.append(esc(r["floor"]))
        if r["span_days"]:
            meta.append("在售 ≥%d 天" % r["span_days"])

        facts = []
        if r["agent"]:
            facts.append(("中介", esc(r["agent"]) + (
                ' <span class="dim">执照 %s</span>' % esc(r["agent_license"])
                if r["agent_license"] else "")))
        if r["listed_on"]:
            facts.append(("平台显示上架", esc(r["listed_on"])))
        if r["first_posted"]:
            facts.append(("详情页真实发布时间", esc(r["first_posted"])))
        if r["first_date"]:
            facts.append(("首次出现在售", esc(r["first_date"])))
        if r["last_seen"]:
            facts.append(("最后一次在售", esc(r["last_seen"])))
        if r["span_days"]:
            facts.append(("在售时长", "≥ %d 天（%d 次抓取）" % (r["span_days"], r["obs_days"])))
        if r["price_hist_text"]:
            facts.append(("挂牌期价格轨迹", esc(r["price_hist_text"])))

        facts_html = "".join(
            '<div class="fact"><span class="k2">%s</span><span class="v">%s</span></div>' % kv
            for kv in facts)

        raw_block = []
        hdr_bits = []
        if r["price"]:
            hdr_bits.append("S$%s" % format(r["price"], ","))
        else:
            hdr_bits.append("价格未公开")
        if r["area"]:
            hdr_bits.append("%s sqft" % format(r["area"], ","))
        if r["psf"]:
            hdr_bits.append("S$%s/sqft" % format(r["psf"], ","))
        if r["floor"]:
            hdr_bits.append(r["floor"])
        if r["price"] or r["area"] or r["psf"] or r["floor"]:
            raw_block.append("- **" + " · ".join(hdr_bits) + "**")
        if r["summary"]:
            raw_block.append("  - " + r["summary"] + ((" · 中介: " + r["agent"]) if r["agent"] else ""))
        if r["listed_on"]:
            raw_block.append("  - 🕒 平台显示上架: " + r["listed_on"])
        if r["price_hist_text"]:
            raw_block.append("  - 📈 历史价格: " + r["price_hist_text"])
        if r["url"]:
            raw_block.append("  - " + r["url"])

        snap_link = ('<a class="btn" href="%s" target="_blank" rel="noopener">查看当日原始日报 ↗</a>'
                     % esc(r["report_link"])) if r["report_link"] else ""
        spark = build_sparkline(price_history_points(r))

        # --- archived photos / floor plans (only for listings archived while live)
        base = REPO_RAW + "archive/" + str(r["id"]) + "/"
        gal, plans = [], []
        for p in r["photos"]:
            gal.append('<a class="shot" href="%s" target="_blank" rel="noopener">'
                       '<img loading="lazy" src="%s" alt="%s %s photo"></a>'
                       % (esc(base + p), esc(base + p), esc(r["block"]), esc(r["id"])))
        for p in r["floorplans"]:
            plans.append('<a class="shot plan" href="%s" target="_blank" rel="noopener">'
                         '<img loading="lazy" src="%s" alt="floor plan"></a>'
                         % (esc(base + p), esc(base + p)))
        if gal or plans:
            gallery = ('<div class="galwrap"><div class="gallab">已归档的实拍照片'
                       '（%d 张）%s</div><div class="gallery">%s</div>%s</div>'
                       % (len(gal),
                          (' · 户型图 %d 张' % len(plans)) if plans else '',
                          "".join(gal),
                          ('<div class="gallery plano">%s</div>' % "".join(plans)) if plans else ''))
        else:
            gallery = ('<div class="galwrap nophoto">该房源下架前未被归档，'
                       'PropertyGuru 已删除照片与描述，照片不可恢复</div>')

        descblock = ""
        if r["description"]:
            descblock = ('<details class="snap desc"><summary>完整房源描述 <span class="dim">'
                         '（归档自详情页，日报里没有这一项）</span></summary>'
                         '<div class="descbox">%s</div></details>'
                         % esc(r["description"]).replace("\n", "<br>"))

        cards.append(sub_tpl("""
<article class="card %(status)s" data-block="%(block)s" data-price="%(pricev)s">
  <header class="card-h">
    <div class="card-title">
      <span class="blocktag">%(block)s</span>
      <span class="lid">#%(id)s</span>
      %(badge)s
    </div>
    <div class="card-price">
      <strong>%(price)s</strong>%(price_note)s
    </div>
  </header>
  <div class="card-body">
    <p class="summary">%(summary)s</p>
    <div class="meta">%(meta)s</div>
    %(sparkhtml)s
    %(gallery)s
    %(descblock)s
    <div class="facts">%(facts)s</div>
    <details class="snap">
      <summary>原始记录快照 <span class="dim">（%(snap_date)s 当日日报中的完整条目）</span></summary>
      <div class="snapbox"><pre>%(raw)s</pre></div>
    </details>
    <footer class="card-f">
      <span class="dates">卖出判定 <b>%(sold_date)s</b>%(hist_note)s</span>
      <span class="links">
        %(snap_link)s
        <a class="btn ghost" href="%(url)s" target="_blank" rel="noopener" title="PropertyGuru 原页面大概率已失效">原链接（多半已失效）↗</a>
        <a class="btn ghost" href="%(sold_link)s" target="_blank" rel="noopener">卖出当日日报 ↗</a>
      </span>
    </footer>
  </div>
</article>""", {
        "status": r["status"],
        "block": esc(r["block"]),
        "id": esc(r["id"]),
        "badge": badge,
        "price": price_txt,
        "price_note": price_note,
        "pricev": r["price"] or 0,
        "summary": esc(r["summary"] or "（当日日报未记录营销文案）"),
        "meta": " · ".join(meta),
        "sparkhtml": ('<div class="sparkwrap">%s<span class="sparklab">挂牌期价格走势</span></div>'
                      % spark) if spark else "",
        "facts": facts_html,
        "snap_date": esc(r["snap_date"] or "—"),
        "raw": esc("\n".join(raw_block)) or "（无完整快照）",
        "hist_note": esc(hist_note),
        "sold_date": esc(r["sold_date"]),
        "snap_link": snap_link,
        "url": esc(r["url"]),
        "sold_link": esc(r["sold_report_link"]),
        "gallery": gallery,
        "descblock": descblock,
    }))

    key_rows = "".join(
        '<div class="kpi"><span class="kv">%s</span><span class="kl">%s</span></div>'
        % (v, k) for k, v in [
            (len(rows), "累计卖出"),
            (len(gone), "已彻底下架"),
            (len(relisted), "重新上架"),
            (money(avg) or "—", "平均挂牌价"),
            (money(med) or "—", "中位挂牌价"),
            ("S$%s" % format(avg_psf, ",") if avg_psf else "—", "平均单价"),
            ("%d 天" % avg_dom if avg_dom else "—", "平均在售时长"),
        ])

    block_chips = "".join(
        '<button class="chip" data-b="%s">%s <b>%d</b></button>' % (esc(b), esc(b), block_counts[b])
        for b in blocks)
    block_chips = ('<button class="chip active" data-b="all">全部 <b>%d</b></button>' % len(rows)) + block_chips

    doc = sub_tpl(HTML_TEMPLATE, {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "latest": latest_date,
        "kpis": key_rows,
        "chips": block_chips,
        "cards": "".join(cards),
        "nrows": len(rows),
        "nreports": n_reports,
        "first_report": first_report,
        "repo": REPO,
        "branch": BRANCH,
    })
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(doc)


def price_history_points(r):
    return r.get("traj") or []


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HDB 卖出/下架 房源快照 · Telok Blangah Parcview</title>
<style>
  :root{
    --bg:#0e1116; --bg2:#141922; --card:#161c26; --card2:#1b2230;
    --line:#252d3c; --line2:#323c4e;
    --fg:#e8edf5; --fg2:#a8b3c5; --fg3:#6f7c92;
    --acc:#5b9dff; --acc2:#8bb8ff;
    --gone:#ff6b6b; --gone-bg:rgba(255,107,107,.12);
    --back:#ffc247; --back-bg:rgba(255,194,71,.12);
    --up:#ff5f56; --down:#35c46a;
    --spark:#5b9dff; --spark-fill:rgba(91,157,255,.14);
    --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  body{
    margin:0; background:radial-gradient(1200px 600px at 20% -10%,#1a2333 0%,var(--bg) 55%) no-repeat,var(--bg);
    color:var(--fg); font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1120px;margin:0 auto;padding:40px 24px 80px}
  header.top{margin-bottom:28px}
  .eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--acc);font-weight:600}
  h1{font-size:30px;line-height:1.25;margin:10px 0 8px;letter-spacing:-.01em}
  .sub{color:var(--fg2);font-size:14px;max-width:820px}
  .sub code{font-family:var(--mono);font-size:12.5px;background:#1d2532;border:1px solid var(--line);
    padding:1px 6px;border-radius:5px;color:var(--acc2)}
  .note{
    margin:22px 0 26px;padding:14px 16px;border:1px solid var(--line);border-left:3px solid var(--acc);
    background:linear-gradient(180deg,#151c28,#131924);border-radius:10px;color:var(--fg2);font-size:13.5px;
  }
  .note b{color:var(--fg)}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(138px,1fr));gap:12px;margin:0 0 26px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
  .kv{display:block;font-size:19px;font-weight:650;letter-spacing:-.02em;white-space:nowrap}
  .kl{display:block;font-size:11.5px;color:var(--fg3);margin-top:3px;white-space:nowrap}
  .toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:20px}
  .chip{
    background:var(--card);border:1px solid var(--line);color:var(--fg2);border-radius:999px;
    padding:6px 13px;font-size:13px;cursor:pointer;font-family:inherit;transition:.15s;
  }
  .chip:hover{border-color:var(--line2);color:var(--fg)}
  .chip.active{background:rgba(91,157,255,.14);border-color:var(--acc);color:var(--acc2)}
  .chip b{font-weight:600;opacity:.85;margin-left:3px}
  .cards{display:flex;flex-direction:column;gap:14px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;transition:.15s}
  .card:hover{border-color:var(--line2)}
  .card.gone{border-left:3px solid var(--gone)}
  .card.relisted{border-left:3px solid var(--back)}
  .card-h{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;
    padding:15px 18px 12px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#1a2130,#161c26)}
  .card-title{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  .blocktag{font-family:var(--mono);font-weight:700;font-size:15px;color:var(--fg);
    background:#222b3a;border:1px solid var(--line2);border-radius:7px;padding:2px 8px}
  .lid{font-family:var(--mono);font-size:11.5px;color:var(--fg3)}
  .badge{font-size:11px;font-weight:600;border-radius:999px;padding:3px 9px;letter-spacing:.02em}
  .badge.gone{background:var(--gone-bg);color:var(--gone);border:1px solid rgba(255,107,107,.3)}
  .badge.back{background:var(--back-bg);color:var(--back);border:1px solid rgba(255,194,71,.3)}
  .card-price{text-align:right;white-space:nowrap}
  .card-price strong{font-size:19px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
  .delta{display:block;font-size:11.5px;margin-top:2px}
  .delta.up{color:var(--up)} .delta.down{color:var(--down)}
  .card-body{padding:15px 18px 16px}
  .summary{margin:0 0 8px;font-size:14.5px;color:var(--fg)}
  .meta{font-family:var(--mono);font-size:12.5px;color:var(--fg2)}
  .sparkwrap{margin:14px 0 4px;position:relative}
  .spark{width:100%;height:46px;display:block}
  .sparklab{font-size:11px;color:var(--fg3)}
  .facts{margin-top:14px;display:grid;gap:5px}
  .fact{display:grid;grid-template-columns:118px 1fr;gap:10px;font-size:13px;align-items:baseline}
  .fact .k2{color:var(--fg3);font-size:12px}
  .fact .v{color:var(--fg2);font-family:var(--mono);font-size:12.5px;word-break:break-word}
  details.snap{margin-top:14px;border-top:1px dashed var(--line);padding-top:12px}
  details.snap summary{cursor:pointer;font-size:13px;color:var(--acc2);list-style:none;user-select:none}
  details.snap summary::-webkit-details-marker{display:none}
  details.snap summary:before{content:"▸ ";display:inline-block;transition:.15s}
  details.snap[open] summary:before{content:"▾ "}
  .dim{color:var(--fg3);font-size:12px}
  .snapbox{margin-top:9px;background:#10151d;border:1px solid var(--line);border-radius:9px;padding:12px 14px;overflow-x:auto}
  .snapbox pre{margin:0;font-family:var(--mono);font-size:12.5px;color:var(--fg2);white-space:pre-wrap;word-break:break-all}
  .galwrap{margin-top:16px}
  .gallab{font-size:12px;color:var(--fg3);margin-bottom:8px}
  .gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:7px}
  .gallery.plano{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));margin-top:7px}
  .shot{display:block;border:1px solid var(--line);border-radius:8px;overflow:hidden;
    background:#0d1219;line-height:0;transition:.15s}
  .shot:hover{border-color:var(--acc);transform:translateY(-1px)}
  .shot img{width:100%;height:78px;object-fit:cover;display:block}
  .shot.plan img{height:110px;object-fit:contain;background:#0d1219}
  .galwrap.nophoto{font-size:12.5px;color:var(--fg3);background:#12171f;
    border:1px dashed var(--line2);border-radius:9px;padding:10px 12px}
  .descbox{margin-top:9px;background:#10151d;border:1px solid var(--line);border-radius:9px;
    padding:12px 14px;font-size:13px;color:var(--fg2);line-height:1.7;max-height:340px;overflow:auto}
  .card-f{display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap;
    margin-top:15px;padding-top:13px;border-top:1px solid var(--line)}
  .dates{font-size:12.5px;color:var(--fg2)}
  .dates b{color:var(--fg);font-family:var(--mono)}
  .links{display:flex;gap:8px;flex-wrap:wrap}
  .btn{font-size:12.5px;text-decoration:none;border-radius:8px;padding:6px 11px;
    background:rgba(91,157,255,.13);border:1px solid rgba(91,157,255,.35);color:var(--acc2);transition:.15s}
  .btn:hover{background:rgba(91,157,255,.22)}
  .btn.ghost{background:#1a212d;border-color:var(--line2);color:var(--fg2)}
  .btn.ghost:hover{color:var(--fg);border-color:#46536b}
  footer.bottom{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);color:var(--fg3);font-size:12.5px}
  footer.bottom a{color:var(--acc2);text-decoration:none}
  .empty{padding:40px;text-align:center;color:var(--fg3)}
  @media(max-width:640px){
    .card-h{flex-direction:column} .card-price{text-align:left}
    .fact{grid-template-columns:1fr;gap:1px}
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="eyebrow">HDB Resale Monitor · 永久快照</div>
    <h1>✅ 今日卖出 / 下架 —— 房源快照档案</h1>
    <p class="sub">
      Telok Blangah Parcview（80A/80B/80C · 90A/90B/91A/92B/93A/93B，Telok Blangah Street 31）4-room 非低楼层。
      日报里这一栏只有一行 <code>[block] 价格未公开 · 链接</code>，等房源真的卖掉后 PropertyGuru 页面会被删除，
      原链接点进去就什么都没有了。本页把每一条"卖出/下架"记录**还原成它在挂牌期间的样子**——
      价格、面积、单价、楼层、中介、营销文案、挂牌天数与价格走势——全部取自当日日报归档，不可再生的数据。
    </p>
  </header>

  <div class="note">
    <b>判定口径：</b>某房源连续消失 ≥ 7 天后才记为"卖出/下架"（宽限期用于过滤 PropertyGuru 限流/漏抓造成的假消失）。
    因此"卖出判定日"是<b>最后一次被看到在售之后约一周</b>，并非真实成交日；<b>挂牌价 ≠ 成交价</b>，本页不含任何成交价数据。
    <br><br><b>为什么原链接打不开：</b>房源下架后 PropertyGuru 会删除详情页（返回 200 但内容清空）。
    本页的"原始记录快照"、"完整房源描述"与实拍照片是本仓库独有的存档，也是目前唯一能回看当时房源长什么样的地方。
    <br><br><b>照片是怎么来的：</b>由 <code>archive_listing.py</code> 在房源<b>还在售时</b>抓取并归档（照片 / 户型图 / 完整描述 / 原始 HTML）。
    监控开始归档之前就已下架的房源，PropertyGuru 那边已经清空，照片<b>永久不可恢复</b>——这类卡片会明确标注。
  </div>

  <div class="kpis">%(kpis)s</div>

  <div class="toolbar" id="chips">%(chips)s</div>

  <div class="cards" id="cards">%(cards)s</div>

  <div class="empty" id="empty" style="display:none">该 block 没有卖出/下架记录。</div>

  <footer class="bottom">
    快照生成于 %(generated)s ｜ 数据源：%(nreports)s 份日报归档（%(first_report)s ~ %(latest)s）+ state.json ｜
    <a href="%(repo)s/tree/%(branch)s/reports" target="_blank" rel="noopener">在 GitHub 查看全部日报归档 ↗</a>
    <br>本页为静态快照文件，可离线保存；重新生成不会丢失历史，只会补入新的卖出记录。
  </footer>
</div>

<script>
(function(){
  var wrap = document.getElementById('cards');
  var chips = document.getElementById('chips');
  var empty = document.getElementById('empty');
  chips.addEventListener('click', function(e){
    var b = e.target.closest('.chip'); if(!b) return;
    [].forEach.call(chips.querySelectorAll('.chip'), function(c){ c.classList.remove('active'); });
    b.classList.add('active');
    var want = b.dataset.b, shown = 0;
    [].forEach.call(wrap.querySelectorAll('.card'), function(card){
      var ok = (want === 'all' || card.dataset.block === want);
      card.style.display = ok ? '' : 'none';
      if(ok) shown++;
    });
    empty.style.display = shown ? 'none' : '';
  });
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
