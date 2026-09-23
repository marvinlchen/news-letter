#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给历史日报的 ✅ 卖出/下架 段落补上快照链接（幂等，可重复运行）。

PropertyGuru 会在房源下架后清空原页面，日报里只留一个会失效的原链接。
这里给每条下架记录追加：
    - 🗄 下架快照（价格/面积/楼层/中介/文案）: <sold-snapshot>#L<id>
    - 📷 照片归档: <archive-page>#L<id>（...）      # 仅当该房源在售期间被归档过

两种历史格式都处理：
    新（2026-09-18 起）  - **[90A] S$1,000,000 · 1001 sqft · High Floor**  + 缩进子行
    旧                  - [90A] 价格未公开 · https://...-500081935

只做插入，不改动任何已有行；已存在快照行的条目会跳过。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(HERE, "reports")
ARCHIVE_DIR = os.path.join(HERE, "archive")

SNAPSHOT_PAGE = ("https://raw.githack.com/marvinlchen/news-letter/"
                 "hdb-monitor/hdb-sold-snapshot.html")
ARCHIVE_PAGE = ("https://raw.githack.com/marvinlchen/news-letter/"
                "hdb-monitor/hdb-archive.html")

RE_ID = re.compile(r"-(\d+)/?\s*$")
RE_URL = re.compile(r"https?://\S+")
MARKER = "🗄 下架快照"


def snap_lines(lid):
    out = ["  - %s（价格/面积/楼层/中介/文案）: %s#L%s"
           % (MARKER, SNAPSHOT_PAGE, lid)]
    arc = os.path.join(ARCHIVE_DIR, lid)
    if os.path.isdir(arc):
        try:
            n_photo = len(os.listdir(os.path.join(arc, "photos")))
        except OSError:
            n_photo = 0
        bits = []
        if n_photo:
            bits.append("实拍照片 %d 张" % n_photo)
        if os.path.exists(os.path.join(arc, "page.html.gz")):
            bits.append("原始 HTML 存档")
        out.append("  - 📷 照片归档: %s#L%s%s"
                   % (ARCHIVE_PAGE, lid, ("（%s）" % " · ".join(bits)) if bits else ""))
    return out


def entry_id(lines):
    """从一条卖出记录的若干行里取出房源 ID（取最后一条 URL）。"""
    lid = None
    for ln in lines:
        if not ln.lstrip().startswith("- "):
            continue
        for u in RE_URL.findall(ln):
            m = RE_ID.search(u.rstrip("/"))
            if m:
                lid = m.group(1)
    return lid


def process(path):
    """返回 (改动条数, 是否写回)。"""
    orig = open(path, encoding="utf-8").read()
    lines = orig.splitlines()

    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and "今日卖出" in ln:
            start = i
            break
    if start is None:
        return 0, False
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1

    body = lines[start + 1:end]
    out = []
    entry = []
    changed = 0

    def flush():
        nonlocal changed, entry
        if not entry:
            return
        # 段落末尾的空行不属于记录本身，先摘掉，插完快照行再放回
        tail = []
        while entry and not entry[-1].strip():
            tail.insert(0, entry.pop())
        out.extend(entry)
        if MARKER not in "\n".join(entry):
            lid = entry_id(entry)
            if lid:
                out.extend(snap_lines(lid))
                changed += 1
        out.extend(tail)
        entry = []

    for ln in body:
        # 缩进 0 且以 "- " 开头 = 新条目开始（"- 无" 也走这里，entry_id 取不到 id 则不动）
        if ln.startswith("- "):
            flush()
            entry = [ln]
        elif entry:
            entry.append(ln)
        else:
            out.append(ln)
    flush()

    if not changed:
        return 0, False
    new = "\n".join(lines[:start + 1] + out + lines[end:])
    if orig.endswith("\n"):
        new += "\n"
    if new == orig:
        return 0, False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return changed, True


def main():
    total, files = 0, 0
    targets = sorted(f for f in os.listdir(REPORT_DIR) if f.endswith(".md"))
    for name in targets:
        path = os.path.join(REPORT_DIR, name)
        try:
            n, wrote = process(path)
        except Exception as e:
            print("  ! %s: %s" % (name, e))
            continue
        if wrote:
            total += n
            files += 1
            print("  + %s: 补 %d 条" % (name, n))
    print("backfill: %d 条记录 / %d 个文件" % (total, files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
