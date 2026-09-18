#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render ./archive/ into a browsable HTML gallery: hdb-archive.html

Every listing that `archive_listing.py` captured while it was still live —
photos, floor plans, price, agent, the full description, and the reliable
`firstPosted` date straight off the detail page.

This is the only place these photos exist once PropertyGuru removes a
listing, so the page is built to be read offline as well.

Usage:
    python3 build_archive_page.py            # write hdb-archive.html
    python3 build_archive_page.py --push     # + commit & push to hdb-monitor
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(HERE, 'archive')
OUT_FILE = os.path.join(HERE, 'hdb-archive.html')

GIT_AUTHOR = b'marvinlchen <marvinlchen@users.noreply.github.com>'
GIT_REMOTE = 'origin'
GIT_REMOTE_URL = 'git@github.com:marvinlchen/news-letter.git'
GIT_LOCAL_REF = 'refs/heads/master'
GIT_REMOTE_REF = 'refs/heads/hdb-monitor'

try:
    from dulwich import porcelain
    from dulwich.repo import Repo
    HAVE_DULWICH = True
except ImportError:
    HAVE_DULWICH = False

PREFIX = '[hdb-archive-page] '


def log(m):
    print(PREFIX + str(m), flush=True)


def esc(x):
    return html.escape(str(x)) if x is not None else ''


RE_TPL = re.compile(r'%\((\w+)\)s')


def sub_tpl(tpl, mapping):
    """Substitute %(name)s tokens without touching literal % in CSS."""
    return RE_TPL.sub(lambda m: str(mapping.get(m.group(1)) or ''), tpl)


def money(p):
    try:
        return 'S$%s' % format(int(p), ',')
    except Exception:
        return '—'


def load_all():
    rows = []
    if not os.path.isdir(ARCHIVE_DIR):
        return rows
    for name in sorted(os.listdir(ARCHIVE_DIR)):
        p = os.path.join(ARCHIVE_DIR, name, 'meta.json')
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding='utf-8') as f:
                m = json.load(f)
        except Exception:
            continue
        rows.append(m)
    rows.sort(key=lambda m: (m.get('block') or 'zz', str(m.get('id'))))
    return rows


def card(m):
    if m.get('unavailable'):
        return ('<article class="card dead"><header class="h">'
                '<span class="blk">%s</span><span class="id">#%s</span>'
                '<span class="bad">已下架 · 未归档</span></header>'
                '<p class="note">归档时 PropertyGuru 已删除该房源内容，'
                '照片与描述均不可恢复。</p></article>'
                % (esc(m.get('block')), esc(m.get('id'))))

    photos = m.get('photos') or []
    plans = m.get('floorplans') or []
    shots = ''.join(
        '<a class="shot" href="%s" target="_blank" rel="noopener">'
        '<img loading="lazy" src="%s" alt="%s photo %d"></a>'
        % (esc(p), esc(p), esc(m.get('block')), i)
        for i, p in enumerate(photos, 1))
    plan_shots = ''.join(
        '<a class="shot plan" href="%s" target="_blank" rel="noopener">'
        '<img loading="lazy" src="%s" alt="floor plan %d"></a>'
        % (esc(p), esc(p), i) for i, p in enumerate(plans, 1))

    desc = m.get('description') or ''
    desc_html = ('<details class="desc"><summary>完整房源描述</summary>'
                 '<div class="descbox">%s</div></details>'
                 % esc(desc).replace('\n', '<br>')) if desc else ''

    facts = []
    for k, v in [('中介', m.get('agent')),
                 ('执照', m.get('agent_license')),
                 ('首次发布', (m.get('first_posted') or '')[:10]),
                 ('房型', ' · '.join(x for x in [m.get('bedrooms'),
                                                 m.get('bathrooms')] if x)),
                 ('装修', m.get('furnishing')),
                 ('地址', m.get('address')),
                 ('邮编', m.get('postal_code')),
                 ('归档于', m.get('archived_at'))]:
        if v:
            facts.append('<div class="f"><span class="fk">%s</span>'
                         '<span class="fv">%s</span></div>' % (esc(k), esc(v)))

    return sub_tpl("""<article class="card">
  <header class="h">
    <span class="blk">%(blk)s</span><span class="id">#%(id)s</span>
    <span class="pr">%(price)s</span>
    <span class="cnt">%(np)d 照片%(plans)s</span>
  </header>
  <p class="head">%(headline)s</p>
  <p class="meta">%(psf)s%(area)s</p>
  <div class="gallery">%(shots)s</div>
  %(planshtml)s
  <div class="facts">%(facts)s</div>
  %(desc)s
  <footer class="f2">
    <a class="btn" href="%(url)s" target="_blank" rel="noopener">原链接（多半已失效）↗</a>
    <a class="btn ghost" href="archive/%(id)s/page.html.gz" target="_blank" rel="noopener">原始 HTML 存档 (.gz)</a>
  </footer>
</article>""", {
        'blk': esc(m.get('block')), 'id': esc(m.get('id')),
        'price': money(m.get('price')),
        'np': len(photos), 'plans': (' · 户型图 %d 张' % len(plans)) if plans else '',
        'headline': esc(m.get('headline') or m.get('address') or ''),
        'psf': esc(m.get('psf') or ''),
        'area': '',
        'shots': shots,
        'planshtml': ('<div class="gallery plano">%s</div>' % plan_shots) if plan_shots else '',
        'facts': ''.join(facts), 'desc': desc_html,
        'url': esc(m.get('url') or ''),
    })


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HDB 实拍照片归档 · Telok Blangah Parcview</title>
<style>
  :root{
    --bg:#0e1116;--card:#161c26;--line:#252d3c;--line2:#323c4e;
    --fg:#e8edf5;--fg2:#a8b3c5;--fg3:#6f7c92;
    --acc:#5b9dff;--acc2:#8bb8ff;--gone:#ff6b6b;--gonebg:rgba(255,107,107,.12);
    --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 18% -10%,#1a2333 0%,var(--bg) 55%) no-repeat,var(--bg);
    color:var(--fg);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1240px;margin:0 auto;padding:40px 24px 80px}
  .eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--acc);font-weight:600}
  h1{font-size:29px;margin:10px 0 8px;letter-spacing:-.01em}
  .sub{color:var(--fg2);font-size:14px;max-width:900px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(126px,1fr));gap:12px;margin:24px 0 28px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px}
  .kv{display:block;font-size:19px;font-weight:650;white-space:nowrap}
  .kl{display:block;font-size:11.5px;color:var(--fg3);margin-top:3px}
  .cards{display:flex;flex-direction:column;gap:18px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px 15px;border-left:3px solid var(--acc)}
  .card.dead{border-left-color:var(--gone)}
  .h{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:9px}
  .blk{font-family:var(--mono);font-weight:700;background:#222b3a;border:1px solid var(--line2);border-radius:7px;padding:2px 8px}
  .id{font-family:var(--mono);font-size:11.5px;color:var(--fg3)}
  .pr{font-weight:650;font-size:17px;margin-left:4px}
  .cnt{font-size:11.5px;color:var(--fg3);margin-left:auto}
  .bad{font-size:11px;background:var(--gonebg);color:var(--gone);border:1px solid rgba(255,107,107,.3);border-radius:999px;padding:3px 9px}
  .head{margin:0 0 3px;font-size:14.5px}
  .meta{margin:0 0 12px;font-family:var(--mono);font-size:12px;color:var(--fg2)}
  .note{margin:0;font-size:13px;color:var(--fg3)}
  .gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:8px}
  .gallery.plano{grid-template-columns:repeat(auto-fill,minmax(190px,1fr));margin-top:8px}
  .shot{display:block;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:#0d1219;line-height:0;transition:.15s}
  .shot:hover{border-color:var(--acc);transform:translateY(-2px)}
  .shot img{width:100%;height:96px;object-fit:cover;display:block}
  .shot.plan img{height:140px;object-fit:contain}
  .facts{display:grid;gap:4px;margin-top:13px}
  .f{display:grid;grid-template-columns:86px 1fr;gap:10px;font-size:12.5px}
  .fk{color:var(--fg3);font-size:12px}
  .fv{color:var(--fg2);font-family:var(--mono);word-break:break-word}
  details.desc{margin-top:12px;border-top:1px dashed var(--line);padding-top:11px}
  details.desc summary{cursor:pointer;font-size:13px;color:var(--acc2);list-style:none}
  details.desc summary::-webkit-details-marker{display:none}
  details.desc summary:before{content:"▸ "}
  details.desc[open] summary:before{content:"▾ "}
  .descbox{margin-top:9px;background:#10151d;border:1px solid var(--line);border-radius:9px;padding:12px 14px;
    font-size:13px;color:var(--fg2);line-height:1.7;max-height:320px;overflow:auto}
  .f2{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
  .btn{font-size:12.5px;text-decoration:none;border-radius:8px;padding:6px 11px;
    background:rgba(91,157,255,.13);border:1px solid rgba(91,157,255,.35);color:var(--acc2)}
  .btn.ghost{background:#1a212d;border-color:var(--line2);color:var(--fg2)}
  footer.bottom{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);color:var(--fg3);font-size:12.5px}
  footer.bottom a{color:var(--acc2);text-decoration:none}
  @media(max-width:640px){.f{grid-template-columns:1fr;gap:1px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">HDB Resale Monitor · 实拍照片归档</div>
  <h1>房源实拍照片档案</h1>
  <p class="sub">
    Telok Blangah Parcview（80A/80B/80C · 90A/90B/91A/92B/93A/93B，Telok Blangah Street 31）4-room 非低楼层。
    这些照片、户型图与完整描述，是在房源<b>还在 PropertyGuru 上挂着的时候</b>抓下来存进本仓库的 ——
    一旦房源下架，PropertyGuru 会清空详情页内容（页面仍返回 200，但照片和数据全部消失），届时再也取不回来。
  </p>
  <div class="kpis">%(kpis)s</div>
  <div class="cards">%(cards)s</div>
  <footer class="bottom">
    生成于 %(generated)s ｜ 共 %(n)d 套房源 · %(np)d 张照片 · %(nf)d 张户型图 · 归档体积 %(mb)s MB<br>
    原始 HTML 存档为 <code>archive/&lt;id&gt;/page.html.gz</code>，解压后即为完整的详情页源码。
  </footer>
</div>
</body>
</html>
"""


def build_html(rows):
    ok = [m for m in rows if not m.get('unavailable')]
    photos = sum(len(m.get('photos') or []) for m in ok)
    plans = sum(len(m.get('floorplans') or []) for m in ok)
    mb = sum(m.get('archive_bytes') or 0 for m in rows) / 1048576.0
    priced = [m['price'] for m in ok if m.get('price')]
    avg = 'S$%s' % format(int(sum(priced) / len(priced)), ',') if priced else '—'
    kpis = ''.join(
        '<div class="kpi"><span class="kv">%s</span><span class="kl">%s</span></div>'
        % (v, k) for k, v in [
            (len(ok), '已归档房源'),
            (photos, '实拍照片'),
            (plans, '户型图'),
            (avg, '平均挂牌价'),
            ('%.1f MB' % mb, '归档体积'),
        ])
    return sub_tpl(TEMPLATE, {
        'kpis': kpis,
        'cards': ''.join(card(m) for m in rows),
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'n': len(ok), 'np': photos, 'nf': plans, 'mb': '%.1f' % mb,
    })


def git_commit_push(files, msg):
    if not HAVE_DULWICH or not os.path.exists(os.path.join(HERE, '.git')):
        log('dulwich/.git 不可用，跳过提交推送')
        return False
    try:
        for p in files:
            fp = os.path.join(HERE, p)
            if os.path.exists(fp):
                porcelain.add(HERE, fp)
        st = porcelain.status(HERE)
        if not any(st.staged.get(k) for k in ('add', 'modify', 'delete')):
            log('无变更，跳过提交')
            return False
        porcelain.commit(HERE, msg, author=GIT_AUTHOR, committer=GIT_AUTHOR)
        r = Repo(HERE)
        if not r.get_config().has_section((b'remote', GIT_REMOTE.encode())):
            porcelain.remote_add(HERE, GIT_REMOTE, GIT_REMOTE_URL)
        res = porcelain.push(HERE, GIT_REMOTE,
                             ['%s:%s' % (GIT_LOCAL_REF, GIT_REMOTE_REF)])
        log('已 git push -> %s/%s (%s)' % (GIT_REMOTE,
                                          GIT_REMOTE_REF.split('/')[-1], res))
        return True
    except Exception as e:
        log('git 提交/推送跳过: ' + str(e)[:160])
        return False


def main():
    ap = argparse.ArgumentParser(description='把 archive/ 渲染成可浏览的照片归档页')
    ap.add_argument('--push', action='store_true', help='生成后提交并推送')
    args = ap.parse_args()

    rows = load_all()
    if not rows:
        log('archive/ 为空，跳过')
        return
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(build_html(rows))
    log('已写出 %s（%d 套）' % (OUT_FILE, len(rows)))
    if args.push:
        git_commit_push(
            ['build_archive_page.py', 'hdb-archive.html'],
            'archive gallery %s (%d listings)'
            % (datetime.now().strftime('%Y-%m-%d'), len(rows)))


if __name__ == '__main__':
    main()
