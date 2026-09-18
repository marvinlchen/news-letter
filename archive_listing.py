#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archive the FULL detail page of every currently-active HDB listing:
photos, floor plans, the complete marketing description, and the raw HTML.

Why this exists
---------------
PropertyGuru deletes a listing's content the moment it goes off-market. The
detail page keeps returning HTTP 200, but `pageData.listingDetail` is gone —
no photos, no description, nothing (verified 2026-09-18 on listings sold
07-28 / 09-15 / 09-17). The daily report archive only ever captured one line
of text per listing, so photos are unrecoverable **unless we grab them while
the listing is still live**.

So: this runs against `state.json` -> `listings` (currently active only) and
writes into ./archive/<listing_id>/:

    meta.json         curated fields + the full raw listingDetail JSON
    page.html.gz      the raw detail page, gzipped
    photos/NN.jpg     listing photos at V800 (the largest variant PG serves)
    floorplans/NN.jpg floor plans

Photos come from the embedded __NEXT_DATA__ JSON. URL templates carry a
`${viewType}` placeholder; V800 is the largest that resolves (V1200/V1600
return HTTP 400).

Usage
-----
    python3 archive_listing.py                  # archive up to --limit new ones
    python3 archive_listing.py --limit 8 --push # + commit & push
    python3 archive_listing.py --refresh --push # re-fetch already-archived
    python3 archive_listing.py --id 500207099   # one specific listing

Bounded on purpose: one page fetch + ~15 image fetches per listing, with a
sleep between listings, so a run cannot stampede PropertyGuru.
"""

import argparse
import gzip
import io
import json
import os
import random
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdb_monitor as H  # noqa: E402  (reuse fetch/HDR/requests/log/STATE_FILE)

try:
    from dulwich import porcelain
    from dulwich.repo import Repo
    HAVE_DULWICH = True
except ImportError:
    HAVE_DULWICH = False

HOME = H.HOME
ARCHIVE_DIR = os.path.join(HOME, 'archive')
INDEX_FILE = os.path.join(ARCHIVE_DIR, 'index.json')

GIT_AUTHOR = b'marvinlchen <marvinlchen@users.noreply.github.com>'
GIT_REMOTE = 'origin'
GIT_REMOTE_URL = 'git@github.com:marvinlchen/news-letter.git'
GIT_LOCAL_REF = 'refs/heads/master'
GIT_REMOTE_REF = 'refs/heads/hdb-monitor'

VIEW_TYPE = 'V800'          # largest variant PropertyGuru serves
MAX_IMAGES = 30             # safety cap
IMG_MIN_BYTES = 1200        # below this it is an error/placeholder, not a photo
STALE_DAYS = 2              # last_seen older than this => page is already gone
PREFIX = '[hdb-archive] '


def log(msg):
    print(PREFIX + str(msg), flush=True)


def load_state():
    with open(H.STATE_FILE, encoding='utf-8') as f:
        return json.load(f)


def parse_next_data(html_text):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                  html_text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def extract_listing_detail(nd):
    """Return the listingDetail dict, or None when the listing is off-market."""
    try:
        pd = nd['props']['pageProps']['pageData']['data']
    except Exception:
        return None
    ld = pd.get('listingDetail')
    if not isinstance(ld, dict) or not ld.get('media'):
        return None
    return ld


def image_urls(media):
    """(photos, floorplans) as lists of resolved URLs, best variant available."""
    def resolve(items):
        out = []
        for it in items or []:
            t = (it or {}).get('urlTemplate') or (it or {}).get('src') or ''
            if not t:
                continue
            out.append(t.replace('${viewType}', VIEW_TYPE))
        return out[:MAX_IMAGES]

    photos = resolve(media.get('listingImages'))
    if not photos:
        cover = resolve(media.get('cover'))
        photos = cover
    plans = resolve(media.get('listingFloorPlans'))
    if not plans:
        plans = resolve(media.get('listingSitePlans'))
    return photos, plans


def download_image(url, dest):
    """Download one image. Returns (ok, bytes, error)."""
    try:
        r = H.requests.get(url, impersonate='chrome120', timeout=40,
                           headers=H.HDR)
        if r.status_code != 200 or len(r.content) < IMG_MIN_BYTES:
            return False, len(r.content), 'HTTP %s / %d bytes' % (
                r.status_code, len(r.content))
        ctype = (r.headers.get('Content-Type') or '').lower()
        if 'image' not in ctype and not url.lower().split('?')[0].endswith(
                ('.jpg', '.jpeg', '.png', '.webp')):
            return False, len(r.content), 'not an image: ' + ctype[:40]
        ext = '.jpg'
        if '.png' in url.lower() and '.jpg' not in url.lower():
            ext = '.png'
        dest = dest + ext
        with open(dest, 'wb') as f:
            f.write(r.content)
        time.sleep(0.6 + random.random() * 0.4)
        return True, len(r.content), ext
    except Exception as e:
        return False, 0, str(e)[:120]


def curated_meta(lid, block, ld, photos, plans, counts, fallback_url=None):
    """Flatten listingDetail into a small, human-readable record.

    Field shapes (verified 2026-09-18 against a live listing):
      price   -> {min, max, formatted, currency, perArea.floor[].text}
      urls    -> {listing: {desktop, mobile, internal}}
      dates   -> {firstPosted, contentUpdated, expiry, ...}.date  (RELIABLE)
      unitDetails.configuration.{bedrooms,bathrooms}.text
      location.address.formatted / postalCode / point{lat,lon}
      lister.metaByType.agent.{name,license}
      headlines -> [{text}]
    """
    price = ld.get('price') or {}
    urls = ld.get('urls') or {}
    url = ((urls.get('listing') or {}).get('desktop')
           or (urls.get('listing') or {}).get('mobile')
           or fallback_url)
    dates = ld.get('dates') or {}
    unit = ld.get('unitDetails') or {}
    conf = unit.get('configuration') or {}
    loc = (ld.get('location') or {}).get('address') or {}
    point = (ld.get('location') or {}).get('point') or {}
    lister = ld.get('lister') or {}
    agent = ((lister.get('metaByType') or {}).get('agent') or {})
    heads = ld.get('headlines') or []
    headline = heads[0].get('text') if heads and isinstance(heads[0], dict) else None

    desc = ld.get('descriptions')
    if isinstance(desc, list) and desc and isinstance(desc[0], dict):
        desc = desc[0].get('text')
    elif isinstance(desc, dict):
        desc = desc.get('text') or desc.get('description')

    def dt(key):
        v = dates.get(key)
        return (v or {}).get('date') if isinstance(v, dict) else None

    return {
        'id': lid,
        'block': block,
        'url': url,
        'archived_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'price': price.get('min') or price.get('max'),
        'price_display': price.get('formatted'),
        'psf': (((price.get('perArea') or {}).get('floor') or [{}])[0] or {}).get('text'),
        'headline': headline,
        'title': ld.get('title'),
        'description': desc,
        'bedrooms': (conf.get('bedrooms') or {}).get('text'),
        'bathrooms': (conf.get('bathrooms') or {}).get('text'),
        'furnishing': (unit.get('furnishing') or {}).get('description'),
        'address': loc.get('formatted'),
        'postal_code': loc.get('postalCode'),
        'lat': point.get('lat'),
        'lon': point.get('lon'),
        'agent': agent.get('name'),
        'agent_license': agent.get('license'),
        'agent_verified': agent.get('isVerified'),
        'first_posted': dt('firstPosted'),
        'content_updated': dt('contentUpdated'),
        'expiry': dt('expiry'),
        'reference_note': ld.get('referenceNote'),
        'status_code': ld.get('statusCode'),
        'photo_count': counts['photos'],
        'floorplan_count': counts['plans'],
        'photos': photos,
        'floorplans': plans,
        'raw_listing_detail': ld,
    }


def git_commit_push(files, msg):
    if not HAVE_DULWICH:
        log('dulwich 不可用，跳过 git 提交/推送')
        return False
    if not os.path.exists(os.path.join(HOME, '.git')):
        log('本地无 .git 仓库，跳过 git 提交/推送')
        return False
    try:
        for p in files:
            fp = os.path.join(HOME, p)
            if os.path.exists(fp):
                porcelain.add(HOME, fp)
        st = porcelain.status(HOME)
        if not any(st.staged.get(k) for k in ('add', 'modify', 'delete')):
            log('无变更，跳过提交')
            return False
        porcelain.commit(HOME, msg, author=GIT_AUTHOR, committer=GIT_AUTHOR)
        log('已 git commit: ' + msg)
        r = Repo(HOME)
        if not r.get_config().has_section((b'remote', GIT_REMOTE.encode())):
            porcelain.remote_add(HOME, GIT_REMOTE, GIT_REMOTE_URL)
        res = porcelain.push(HOME, GIT_REMOTE,
                             ['%s:%s' % (GIT_LOCAL_REF, GIT_REMOTE_REF)])
        log('已 git push -> %s/%s (%s)' % (GIT_REMOTE,
                                          GIT_REMOTE_REF.split('/')[-1], res))
        return True
    except Exception as e:
        log('git 提交/推送跳过: ' + str(e)[:160])
        return False


def archive_one(lid, rec, refresh=False):
    """Archive a single listing. Returns a result dict."""
    out_dir = os.path.join(ARCHIVE_DIR, str(lid))
    meta_path = os.path.join(out_dir, 'meta.json')
    block = rec.get('block') or '?'
    url = rec.get('url') or ''

    if os.path.exists(meta_path) and not refresh:
        return {'id': lid, 'block': block, 'skipped': True}

    html_text = H.fetch(url) if url else None
    if not html_text:
        log('  %s: 详情页抓取失败' % lid)
        return {'id': lid, 'block': block, 'error': 'fetch failed'}

    nd = parse_next_data(html_text)
    ld = extract_listing_detail(nd) if nd else None
    if not ld:
        log('  %s: 页面已无 listingDetail（房源已下架，内容不可恢复）' % lid)
        os.makedirs(out_dir, exist_ok=True)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({'id': lid, 'block': block, 'url': url,
                       'unavailable': True,
                       'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                      f, ensure_ascii=False, indent=1)
        return {'id': lid, 'block': block, 'unavailable': True}

    photos, plans = image_urls(ld.get('media') or {})
    os.makedirs(os.path.join(out_dir, 'photos'), exist_ok=True)
    os.makedirs(os.path.join(out_dir, 'floorplans'), exist_ok=True)

    saved_p, saved_f, bytes_total, errs = [], [], 0, []
    for i, u in enumerate(photos, 1):
        ok, n, info = download_image(u, os.path.join(out_dir, 'photos',
                                                     '%02d' % i))
        if ok:
            saved_p.append('photos/%02d%s' % (i, info))
            bytes_total += n
        else:
            errs.append('photo %d: %s' % (i, info))
    for i, u in enumerate(plans, 1):
        ok, n, info = download_image(u, os.path.join(out_dir, 'floorplans',
                                                     '%02d' % i))
        if ok:
            saved_f.append('floorplans/%02d%s' % (i, info))
            bytes_total += n
        else:
            errs.append('plan %d: %s' % (i, info))

    gz = gzip.compress(html_text.encode('utf-8', 'replace'), 9)
    with open(os.path.join(out_dir, 'page.html.gz'), 'wb') as f:
        f.write(gz)
    bytes_total += len(gz)

    meta = curated_meta(lid, block, ld, saved_p, saved_f,
                        {'photos': len(saved_p), 'plans': len(saved_f)},
                        fallback_url=url)
    meta['archive_bytes'] = bytes_total
    meta['html_bytes'] = len(html_text)
    meta['image_errors'] = errs
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    log('  %s [%s]: %d 张照片 + %d 张户型图, %.0f KB%s'
        % (lid, block, len(saved_p), len(saved_f), bytes_total / 1024.0,
           ('  错误: ' + '; '.join(errs[:3])) if errs else ''))
    return {'id': lid, 'block': block, 'photos': len(saved_p),
            'plans': len(saved_f), 'bytes': bytes_total, 'errors': errs}


def rebuild_index():
    idx = {}
    if os.path.isdir(ARCHIVE_DIR):
        for name in sorted(os.listdir(ARCHIVE_DIR)):
            p = os.path.join(ARCHIVE_DIR, name, 'meta.json')
            if not os.path.exists(p):
                continue
            try:
                with open(p, encoding='utf-8') as f:
                    m = json.load(f)
            except Exception:
                continue
            idx[name] = {
                'block': m.get('block'),
                'price': m.get('price'),
                'url': m.get('url'),
                'unavailable': bool(m.get('unavailable')),
                'photos': len(m.get('photos') or []),
                'floorplans': len(m.get('floorplans') or []),
                'archived_at': m.get('archived_at') or m.get('checked_at'),
                'bytes': m.get('archive_bytes') or 0,
            }
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=1, sort_keys=True)
    return idx


def main():
    ap = argparse.ArgumentParser(
        description='归档在售房源的完整详情页（照片 / 户型图 / 描述 / 原始 HTML）')
    ap.add_argument('--limit', type=int, default=4,
                    help='本次最多归档多少套新房源（默认 4，控制抓取量）')
    ap.add_argument('--sleep', type=float, default=6.0,
                    help='每套之间的间隔秒数（默认 6）')
    ap.add_argument('--refresh', action='store_true',
                    help='重新抓取已归档的房源（默认跳过）')
    ap.add_argument('--id', action='append', default=None,
                    help='只处理指定 listing id（可重复）')
    ap.add_argument('--push', action='store_true',
                    help='归档后提交并推送到 origin/hdb-monitor')
    args = ap.parse_args()

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    state = load_state()
    listings = state.get('listings') or {}
    log('在售房源: %d 套' % len(listings))

    # Only bother with listings actually seen recently: a listing whose
    # last_seen is stale is almost certainly already off-market, and
    # PropertyGuru has nothing left to give (wastes a fetch per dead page).
    from datetime import date as _date

    def days_since(d):
        try:
            y, m, dd = [int(x) for x in str(d).split('-')]
            return (_date.today() - _date(y, m, dd)).days
        except Exception:
            return 999

    targets, stale = [], []
    for lid, rec in listings.items():
        if args.id and str(lid) not in [str(x) for x in args.id]:
            continue
        item = (str(lid), rec)
        if days_since(rec.get('last_seen')) > STALE_DAYS and not args.id:
            stale.append(item)
        else:
            targets.append(item)
    targets.sort(key=lambda t: t[1].get('last_seen') or '', reverse=True)
    stale.sort(key=lambda t: t[1].get('last_seen') or '', reverse=True)
    if stale:
        log('跳过 %d 套 last_seen 超过 %d 天的房源（页面多半已删除）: %s'
            % (len(stale), STALE_DAYS,
               ', '.join('%s(%s)' % (i, r.get('last_seen'))
                         for i, r in stale[:8])))
    log('候选: %d 套（本次上限 %d）' % (len(targets), args.limit))

    results, done_pages = [], 0
    for lid, rec in targets:
        if done_pages >= args.limit:
            break
        if os.path.exists(os.path.join(ARCHIVE_DIR, lid, 'meta.json')) \
                and not args.refresh:
            continue
        log('%s [%s] 归档中...' % (lid, rec.get('block')))
        results.append(archive_one(lid, rec, refresh=args.refresh))
        done_pages += 1
        time.sleep(args.sleep)

    idx = rebuild_index()
    available = sum(1 for v in idx.values() if not v['unavailable'])
    with_photos = sum(1 for v in idx.values() if v['photos'] > 0)
    total_mb = sum(v['bytes'] for v in idx.values()) / 1048576.0
    log('索引: %d 条（%d 条有内容 / %d 条有照片）· 合计 %.1f MB'
        % (len(idx), available, with_photos, total_mb))
    log('本次处理 %d 套' % len(results))

    if args.push and results:
        git_commit_push(
            ['archive_listing.py', 'archive'],
            'archive listings %s (%d new, %d total)'
            % (datetime.now().strftime('%Y-%m-%d'), len(results), len(idx)))


if __name__ == '__main__':
    main()
