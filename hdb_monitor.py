#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HDB 4-room 订阅监控 - Telok Blangah Parcview
blocks: 80A/80B/80C + 90A/90B/91A/92B/93A/93B (Telok Blangah Street 31)
每天抓取 PropertyGuru 在售 4-room HDB，排除低楼层(LOW)，生成日报（上新 / 卖出）。

实现要点：
- 数据来源：PropertyGuru 搜索页（curl_cffi 模拟 Chrome TLS 绕过 Cloudflare）。
- 楼层判断：用搜索页自带的 floorLevel 过滤参数（服务端生效）。
  每个 block 抓两次：全部4-room（NO过滤）与 floorLevel=LOW；
  最终 = 全部4-room 减去 确认LOW。无需抓取详情页。
  注：中/高楼层不做额外判定，统一标为"非低楼层"。
- 4-room 判定：floorArea 在 950~1055 sqft（HDB 4-room≈1001；3-room≈731）。
- 反爬：Cloudflare 会限流(HTTP 429)，fetch 带重试+退避+请求间隔。
"""
import os, re, json, sys, time, random, datetime, html

try:
    from curl_cffi import requests
except ImportError:
    sys.exit("缺少 curl_cffi，请先: pip install curl_cffi --break-system-packages")

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
GIT_REMOTE_REF = 'refs/heads/hdb-monitor'  # 独立分支，避免覆盖 finance-news-digest 的 main

# 新加的 block 放前面，优先在限流前抓到
BLOCKS = ['80A', '80B', '80C', '90A', '90B', '91A', '92B', '93A', '93B']
BASE = 'https://www.propertyguru.com.sg'
HDR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Accept-Language': 'en-SG,en;q=0.9',
}
HOME = os.path.expanduser('~/hdb_monitor')
STATE_FILE = os.path.join(HOME, 'state.json')
REPORT_DIR = os.path.join(HOME, 'reports')


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch(url, tries=4):
    """带重试+退避的抓取；成功返回 html，失败返回 None。"""
    for i in range(tries):
        try:
            r = requests.get(url, impersonate='chrome120', timeout=35, headers=HDR)
            t = r.text
            if r.status_code == 200 and 'just a moment' not in t.lower() and len(t) > 25000:
                time.sleep(2 + random.random())  # 礼貌间隔，降低限流概率
                return t
            wait = 4 * (i + 1)
            log(f"  fetch HTTP {r.status_code} len={len(t)} -> 重试 {wait}s")
            time.sleep(wait)
        except Exception as e:
            wait = 4 * (i + 1)
            log(f"  fetch err {e} -> 重试 {wait}s")
            time.sleep(wait)
    return None


def collect_objs(o, out):
    if isinstance(o, dict):
        if 'listingId' in o and ('price' in o or 'floorArea' in o or 'bedrooms' in o):
            out.append(o)
        for v in o.values():
            collect_objs(v, out)
    elif isinstance(o, list):
        for v in o:
            collect_objs(v, out)


def extract_listings(block, extra=''):
    """返回 (info_dict, allids_list)。info: id -> {price,area,beds,title,url}"""
    url = f'{BASE}/property-for-sale?freetext={block}%20Telok%20Blangah%20Street%2031{extra}'
    t = fetch(url)
    if not t:
        return {}, []
    urls = {}
    for full, slug, lid in re.findall(
            r'(https://www\.propertyguru\.com\.sg/listing/hdb-for-sale-([0-9a-z-]+)-(\d+))', t):
        if block.lower() not in slug.lower():
            continue
        urls[lid] = full
    objs = []
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', t, re.S):
        s = m.group(1)
        if '"listingId"' not in s:
            continue
        try:
            collect_objs(json.loads(s), objs)
        except Exception:
            a = s.find('{'); b = s.rfind('}')
            if a >= 0 and b > a:
                try:
                    collect_objs(json.loads(s[a:b + 1]), objs)
                except Exception:
                    pass
    info = {}
    for o in objs:
        lid = str(o.get('listingId'))
        if lid not in urls:
            continue
        info[lid] = {
            'id': lid, 'price': o.get('price'), 'area': o.get('floorArea'),
            'beds': o.get('bedrooms'), 'title': o.get('listingTitle'), 'url': urls[lid],
        }
    return info, list(urls.keys())


def is_four_room(d):
    a = d.get('area')
    if a and 950 <= a <= 1055:
        return True
    if d.get('beds') == 3:
        return True
    return False


def block_data(block):
    """返回 (kept, excluded_low)。kept: id->rec。每个 block 抓 2 次(全部 + LOW)。"""
    info, _ = extract_listings(block)
    time.sleep(1.5)
    low_set, _ = extract_listings(block, '&floorLevel=LOW')
    kept, excluded = {}, {}
    for lid, d in info.items():
        if not is_four_room(d):
            continue
        d['block'] = block
        if lid in low_set:
            d['floor'] = '低楼层(已排除)'
            excluded[lid] = d
        else:
            d['floor'] = '非低楼层'
            kept[lid] = d
    return kept, excluded


def fmt_price(p):
    return f"S${p:,}" if p else "价格未公开"


FLOOR_MAP = {'LOW': '低楼层', 'MIDDLE': '中楼层', 'MID': '中楼层', 'HIGH': '高楼层'}


def fetch_summary(url):
    """抓详情页，返回 {summary, agent, floor_desc}。失败返回 {}。"""
    t = fetch(url)
    if not t:
        return {}
    d = {}
    m = re.search(r'<h3 class="subtitle">(.*?)</h3>', t, re.S)
    if m:
        d['summary'] = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
    m = re.search(r'listed by ([^.\-]+?)(?:\.|\s*-\s*|")', t)
    if m:
        d['agent'] = m.group(1).strip()
    m = re.search(r'"floorLevel"\s*:\s*\{[^}]*"description"\s*:\s*"([^"]+)"', t)
    if m:
        d['floor_desc'] = m.group(1)
    else:
        m = re.search(r'"floorLevel"\s*:\s*\{[^}]*"code"\s*:\s*"([^"]+)"', t)
        if m:
            d['floor_desc'] = FLOOR_MAP.get(m.group(1).upper(), m.group(1))
    return d


def enrich_summaries(kept, prev):
    """为 kept 里的房源补充摘要。老房源(价格未变)复用 prev 缓存，只抓新/变价的。"""
    to_fetch = []
    for lid, r in kept.items():
        old = prev.get(lid)
        if old and old.get('summary') and old.get('price') == r.get('price'):
            r['summary'] = old.get('summary')
            r['agent'] = old.get('agent')
            r['floor_desc'] = old.get('floor_desc')
        else:
            to_fetch.append(lid)
    log(f"摘要：复用缓存 {len(kept) - len(to_fetch)} 套，需抓取 {len(to_fetch)} 套")
    for n, lid in enumerate(to_fetch, 1):
        r = kept[lid]
        log(f"  摘要 {n}/{len(to_fetch)}: {r['block']} {lid}")
        s = fetch_summary(r['url'])
        r['summary'] = s.get('summary', '')
        r['agent'] = s.get('agent', '')
        r['floor_desc'] = s.get('floor_desc', '')
        time.sleep(2 + random.random())  # 礼貌间隔，降低限流概率


def psf(r):
    p, a = r.get('price'), r.get('area')
    if p and a:
        return f"S${round(p / a):,}/sqft"
    return ""


def fmt_listing(r, with_block=True):
    """两行 markdown：第一行价格/面积/呎价/楼层，第二行摘要+中介。"""
    prefix = f"[{r['block']}] " if with_block else ""
    meta = [fmt_price(r.get('price')), f"{r.get('area')} sqft"]
    ps = psf(r)
    if ps:
        meta.append(ps)
    fd = r.get('floor_desc') or r.get('floor')
    if fd:
        meta.append(fd)
    line1 = f"- **{prefix}{' · '.join(meta)}**"
    # 第二行：摘要（中介卖点）+ 中介名 + 链接
    summ = r.get('summary') or "（无摘要）"
    agent = f" · 中介: {r['agent']}" if r.get('agent') else ""
    line2 = f"  - {summ}{agent}\n  - {r['url']}"
    return line1 + "\n" + line2


def build_report(date_str, kept, excluded, prev, new_ids, sold_ids):
    L = []
    L.append("# HDB 4-room 订阅日报 · Telok Blangah Parcview")
    L.append(f"**日期**: {date_str}  ")
    L.append("**范围**: blocks 80A/80B/80C + 90A/90B/91A/92B/93A/93B，4-room HDB 在售（已排除低楼层 LOW）")
    L.append("")
    L.append("## 📊 概览")
    L.append(f"- 当前在售(非低楼层): **{len(kept)}** 套")
    L.append(f"- 🆕 今日上新: **{len(new_ids)}** 套")
    L.append(f"- ✅ 今日卖出/下架: **{len(sold_ids)}** 套")
    excluded_total = sum(len(e) for e in excluded.values())
    L.append(f"- 🚫 已排除低楼层: {excluded_total} 套（不计入上方在售）")
    L.append("")
    if new_ids:
        L.append("## 🆕 今日上新")
        for i in new_ids:
            r = kept[i]
            L.append(fmt_listing(r))
        L.append("")
    if sold_ids:
        L.append("## ✅ 今日卖出 / 下架（先前在售，今日已消失）")
        for i in sold_ids:
            r = prev[i]
            L.append(f"- [{r['block']}] {fmt_price(r.get('price'))} · {r.get('url','')}")
        L.append("")
    L.append("## 📋 当前在售清单（按 block，已排除低楼层）")
    by_block = {}
    for r in kept.values():
        by_block.setdefault(r['block'], []).append(r)
    for b in BLOCKS:
        items = by_block.get(b, [])
        L.append(f"### {b} （{len(items)} 套）")
        if not items:
            L.append("- 无")
        for r in sorted(items, key=lambda x: (x['price'] or 0), reverse=True):
            L.append(fmt_listing(r, with_block=False))
        L.append("")
    L.append("---")
    L.append(f"_生成时间 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 数据来源 PropertyGuru（curl_cffi 抓取）_")
    return "\n".join(L)


def git_commit(msg):
    """用 dulwich（纯 Python，无需 git 二进制）把脚本/状态/报告提交到本地仓库。
    只追踪 hdb_monitor.py / state.json / reports/，忽略 cron.log。无变化则跳过。"""
    if not HAVE_DULWICH:
        log("dulwich 未安装，跳过 git 提交（pip install dulwich --break-system-packages）")
        return
    try:
        if not os.path.exists(os.path.join(HOME, '.git')):
            Repo.init(HOME)
        for p in ['hdb_monitor.py', 'state.json', 'reports']:
            fp = os.path.join(HOME, p)
            if os.path.exists(fp):
                porcelain.add(HOME, fp)
        st = porcelain.status(HOME)
        changed = any(st.staged.get(k) for k in ('add', 'modify', 'delete'))
        if not changed:
            return
        porcelain.commit(HOME, msg, author=GIT_AUTHOR, committer=GIT_AUTHOR)
        log("已 git commit: " + msg)
    except Exception as e:
        log("git commit 跳过: " + str(e)[:120])


def git_push():
    """把 master 推到远程 hdb-monitor 分支（dulwich，无需 git 二进制）。"""
    if not HAVE_DULWICH:
        log("dulwich 不可用，跳过 git push")
        return
    try:
        r = Repo(HOME)
        # 确保 remote 存在
        if not r.get_config().has_section((b'remote', GIT_REMOTE.encode())):
            porcelain.remote_add(HOME, GIT_REMOTE, GIT_REMOTE_URL)
        res = porcelain.push(HOME, GIT_REMOTE,
                             [f'{GIT_LOCAL_REF}:{GIT_REMOTE_REF}'])
        log(f"已 git push -> {GIT_REMOTE}/{GIT_REMOTE_REF.split('/')[-1]} ({res})")
    except Exception as e:
        log("git push 跳过: " + str(e)[:160])


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    kept, excluded = {}, {}
    for b in BLOCKS:
        log(f"block {b}: 抓取中...")
        k, e = block_data(b)
        kept.update(k)
        excluded[b] = e
    log(f"抓取完成：在售(非低楼层) {len(kept)} 套；排除低楼层 {sum(len(v) for v in excluded.values())} 套")

    if not kept:
        log("本次未抓到任何数据（可能 Cloudflare 拦截/限流），保留旧状态不更新。")
        print("NO_DATA")
        return

    prev = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    new_ids = [i for i in kept if i not in prev]
    sold_ids = [i for i in prev if i not in kept]
    enrich_summaries(kept, prev)
    report = build_report(date_str, kept, excluded, prev, new_ids, sold_ids)
    with open(STATE_FILE, 'w') as f:
        json.dump(kept, f, indent=2)
    with open(os.path.join(REPORT_DIR, f'report_{date_str}.md'), 'w') as f:
        f.write(report)
    with open(os.path.join(REPORT_DIR, 'latest.md'), 'w') as f:
        f.write(report)
    log("日报已生成")
    git_commit(f"daily report {date_str}")
    git_push()
    print("\n===== 日报摘要 =====")
    print(report)


if __name__ == '__main__':
    main()
