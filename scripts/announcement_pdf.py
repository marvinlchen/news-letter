"""Strict A3 PDF renderer for the A-share major-announcement daily report.

The renderer never invents a security to fill a page and never truncates content.
It preflights every card before atomically saving the PDF. Data collection and
the two factual audit passes belong to the calling report pipeline.
"""
from __future__ import annotations

from collections import Counter
from io import BytesIO
from pathlib import Path
import math
import os
import tempfile
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A3
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle


FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))
registerFontFamily(FONT, normal=FONT, bold=FONT, italic=FONT, boldItalic=FONT)
WIDTH, HEIGHT = A3
MARGIN = 28.0
GUTTER = 16.0
CARD_TOP = HEIGHT - 152.0
CARD_BOTTOM = 42.0
CARD_WIDTH = (WIDTH - 2 * MARGIN - GUTTER) / 2
CARD_HEIGHT = (CARD_TOP - CARD_BOTTOM - GUTTER) / 2
INNER_WIDTH = CARD_WIDTH - 24.0
BODY_HEIGHT = CARD_HEIGHT - 69.0
NAVY = colors.HexColor("#162b45")
INK = colors.HexColor("#203249")
MUTED = colors.HexColor("#627286")
BORDER = colors.HexColor("#dbe2eb")
PAPER = colors.HexColor("#f1f4f8")
RED = colors.HexColor("#d92b2b")
GREEN = colors.HexColor("#16a060")
GRAY = colors.HexColor("#788492")
DIRECTION_COLORS = {"利好": RED, "中性": GRAY, "利空": GREEN}
ORDER = {"利好": 0, "中性": 1, "利空": 2}


class LayoutOverflow(ValueError):
    """Content cannot fit without violating the minimum readable font size."""


def _value(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return "数据待核"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "数据待核"
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _xml(value):
    return escape(_value(value)).replace("\n", "<br/>")


def _style(size=8.5, color=INK, leading=None):
    return ParagraphStyle("report", fontName=FONT, fontSize=size,
                          leading=leading or size * 1.32, textColor=color,
                          alignment=TA_LEFT, wordWrap="CJK", spaceAfter=0,
                          allowWidows=0, allowOrphans=0)


class _EmphasizedParagraph(Paragraph):
    """Simulate a modest bold weight for the built-in CJK light font."""
    def draw(self):
        super().draw()
        self.canv.saveState()
        self.canv.translate(0.14, 0)
        super().draw()
        self.canv.restoreState()


def _para(text, size, *, emphasis=False, color=INK):
    cls = _EmphasizedParagraph if emphasis else Paragraph
    return cls(text, _style(size, color))


def _section(label, value, size, *, emphasis=False):
    return _para(f'<font color="#627286">{escape(label)}</font>　{_xml(value)}',
                 size, emphasis=emphasis)


def _links(announcements, size):
    result = []
    for number, entry in enumerate(announcements, 1):
        title = _xml(entry.get("title"))
        url = entry.get("url")
        # Only real web URLs are activated; arbitrary PDF actions are disallowed.
        if isinstance(url, str) and urlparse(url).scheme.lower() in {"http", "https"}:
            safe_url = escape(url, {'"': "&quot;", "'": "&apos;"})
            title = f'<link href="{safe_url}" color="#355e8a">{title}</link>'
        else:
            title += "（原文链接数据待核）"
        result.append(_para(f'<font color="#627286">公告{number}</font>　{title}', size))
        if entry.get("event"):
            result.append(_section("事项", entry["event"], size))
    return result


def _table(rows, size):
    data = [[_para(_xml(row.get("label")), size, color=MUTED),
             _para(_xml(row.get("value")), size)] for row in rows]
    if not data:
        data = [[_para("关键数据", size, color=MUTED), _para("数据待核", size)]]
    table = Table(data, colWidths=[76, INNER_WIDTH - 76], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f7fa")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, colors.HexColor("#e6ebf1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _card_flowables(item, size):
    t = item.get("technical") or {}
    categories = " / ".join(str(v) for v in item.get("categories") or []) or "数据待核"
    flow = [_section("类别", f"{categories} ｜ 重要性：重大 ｜ 公告日：{_value(item.get('date'))}", size)]
    if "业绩" in (item.get("categories") or []) or item.get("expectation"):
        flow.append(_section("预期差", item.get("expectation"), size))
    flow += _links(item.get("announcements") or [{}], size)
    if item.get("source_note"):
        flow.append(_section("来源复核", item["source_note"], size))
    if item.get("event"):
        flow.append(_section("事件", item["event"], size))
    flow += [Spacer(1, 3), _section("核心结论", item.get("conclusion"), size, emphasis=True)]
    analysis = item.get("analysis") or ["数据待核"]
    if isinstance(analysis, str):
        analysis = [analysis]
    flow += [_para(_xml(line), size) for line in analysis]
    flow += [Spacer(1, 4), _table(item.get("key_data") or [], size), Spacer(1, 4)]
    flow.append(_section("日线", "收盘 {close} ｜ MA5 {ma5} ｜ MA10 {ma10}<br/>MA20 {ma20} ｜ MA60 {ma60}".format(
        **{key: _value(t.get(key)) for key in ("close", "ma5", "ma10", "ma20", "ma60")}).replace("<br/>", "\n"), size))
    status = t.get("status") or "数据待核"
    weekly_label = "停牌" if status == "停牌" else _value(t.get("weekly_trend"))
    trend_color = "#d92b2b" if weekly_label == "金叉" else "#16a060" if weekly_label == "死叉" else "#788492"
    flow.append(_para('<font color="#627286">周MACD</font>　'
                      f'<font color="{trend_color}">{_xml(weekly_label)}</font> ｜ '
                      f'DIF {_xml(t.get("weekly_dif"))} ｜ DEA {_xml(t.get("weekly_dea"))} ｜ 柱 {_xml(t.get("weekly_macd"))}', size))
    flow.append(_para("；".join(_xml(t.get(k)) for k in ("weekly_axis", "weekly_hist_change", "divergence")), size))
    flow.append(_section("申万一级行业", t.get("industry"), size))
    flow.append(_section("行业技术", t.get("industry_technical"), size))
    flow.append(_para(f'当日涨停{_xml(t.get("limit_up_count"))}家', size))
    if item.get("industry_news"):
        flow += [Spacer(1, 3), _section("行业消息", item["industry_news"], size)]
    focus = item.get("focus") or ["数据待核"]
    if isinstance(focus, str):
        focus = [focus]
    flow += [Spacer(1, 3), _section("关注要点", "；".join(str(v) for v in focus), size)]
    return flow


def _measure(flowables):
    heights = []
    for flow in flowables:
        _, height = flow.wrap(INNER_WIDTH, 100000)
        heights.append(height)
    return heights


def _layout_card(item):
    for size in (8.5, 8.25, 8.0, 7.75, 7.5):
        flow = _card_flowables(item, size)
        heights = _measure(flow)
        if sum(heights) <= BODY_HEIGHT:
            return {"flowables": flow, "heights": heights, "font_size": size,
                    "body_height": round(sum(heights), 2)}
    raise LayoutOverflow(f"股票 {_value(item.get('code'))} 卡片内容溢出：7.5pt 仍需 {sum(heights):.1f}pt，允许 {BODY_HEIGHT:.1f}pt。请保留事实并精简表述。")


def _overview(report, counts):
    sources = "；".join(str(v) for v in report.get("source_notes") or []) or "数据待核"
    gaps = "；".join(str(v) for v in report.get("gaps") or []) or "无已知缺口（以两轮复核结果为准）"
    scope = f"采集公告 {_value(report.get('collection_count'))}份 ｜ 入选重大公告 {_value(report.get('announcement_count'))}份 ｜ 同股合并后 {len(report.get('items') or [])}只"
    paragraph = _para(f'{_xml(scope)}<br/><font color="#627286">数据来源与口径</font>　{_xml(sources)}<br/><font color="#627286">数据缺口</font>　{_xml(gaps)}', 8)
    _, height = paragraph.wrap(WIDTH - 2 * MARGIN - 20, 10000)
    if height > 57:
        raise LayoutOverflow(f"概览文字溢出：需要 {height:.1f}pt，允许57pt。请精简来源口径与缺口说明。")
    return paragraph, height


def _draw_header(c, report, counts, overview, page_number, page_count):
    c.setFillColor(NAVY)
    c.rect(0, HEIGHT - 9, WIDTH, 9, fill=1, stroke=0)
    c.setFont(FONT, 21)
    c.drawString(MARGIN, HEIGHT - 39, "A股重大公告利好利空日报")
    c.setFont(FONT, 9)
    c.setFillColor(MUTED)
    c.drawRightString(WIDTH - MARGIN, HEIGHT - 32, f"公告日期 {_value(report.get('date'))}")
    c.drawRightString(WIDTH - MARGIN, HEIGHT - 45, f"生成 {_value(report.get('generated_at'))}")
    y = HEIGHT - 69
    c.setFillColor(INK)
    c.setFont(FONT, 10)
    c.drawString(MARGIN, y, f"重大公告股票 {sum(counts.values())}只")
    for x, label in [(MARGIN + 163, "利好"), (MARGIN + 274, "中性"), (MARGIN + 385, "利空")]:
        color = DIRECTION_COLORS[label]
        c.setFillColor(color)
        c.roundRect(x, y - 5, 90, 21, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(FONT, 10)
        c.drawCentredString(x + 45, y + 1, f"{label}  {counts[label]}只")
    c.setFillColor(colors.HexColor("#e9eef5"))
    c.roundRect(MARGIN, HEIGHT - 140, WIDTH - 2 * MARGIN, 59, 5, fill=1, stroke=0)
    paragraph, height = overview
    paragraph.drawOn(c, MARGIN + 10, HEIGHT - 88 - height)


def _draw_card(c, item, layout, x, y_top, new_group=False):
    bottom = y_top - CARD_HEIGHT
    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.setLineWidth(.6)
    c.roundRect(x, bottom, CARD_WIDTH, CARD_HEIGHT, 6, fill=1, stroke=1)
    direction = item["direction"]
    color = DIRECTION_COLORS[direction]
    c.setFillColor(color)
    c.roundRect(x + 1, y_top - 48, CARD_WIDTH - 2, 47, 5, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.rect(x + 1, y_top - 48, CARD_WIDTH - 2, 7, fill=1, stroke=0)
    name = _para(f'{_xml(item.get("name"))}  {_xml(item.get("code"))}', 11, emphasis=True, color=colors.white)
    _, nh = name.wrap(CARD_WIDTH - 142, 1000)
    if nh > 29:
        raise LayoutOverflow(f"股票名称过长导致标题溢出：{_value(item.get('code'))}")
    name.drawOn(c, x + 12, y_top - 10 - nh)
    t = item.get("technical") or {}
    status = t.get("status")
    bull = "停牌" if status == "停牌" else "是" if t.get("bullish") is True else "否" if t.get("bullish") is False else "数据待核"
    badge_red = bull == "是"
    c.setFillColor(RED if badge_red else colors.HexColor("#e5e9ee"))
    c.roundRect(x + CARD_WIDTH - 125, y_top - 29, 113, 20, 4, fill=1, stroke=0)
    c.setFillColor(colors.white if badge_red else colors.HexColor("#627286"))
    c.setFont(FONT, 8)
    c.drawCentredString(x + CARD_WIDTH - 68.5, y_top - 22.2, f"日线多头排列：{bull}")
    c.setFillColor(color)
    c.setFont(FONT, 8)
    score = item["score"]
    group_label = f"{direction}分区" if new_group else direction
    c.drawString(x + 12, y_top - 54, f"{group_label} ｜ 影响评分 {score:+d}" if score else f"{group_label} ｜ 影响评分 0")
    cursor = y_top - 64
    for flow, height in zip(layout["flowables"], layout["heights"]):
        flow.drawOn(c, x + 12, cursor - height)
        cursor -= height


def _empty_card(c, x, y_top):
    c.setFillColor(colors.HexColor("#f7f9fb"))
    c.setStrokeColor(BORDER)
    c.setDash(3, 3)
    c.roundRect(x, y_top - CARD_HEIGHT, CARD_WIDTH, CARD_HEIGHT, 6, fill=1, stroke=1)
    c.setDash()
    c.setFillColor(GRAY)
    c.setFont(FONT, 12)
    c.drawCentredString(x + CARD_WIDTH / 2, y_top - CARD_HEIGHT / 2 + 6, "无更多条目")
    c.setFont(FONT, 8)
    c.drawCentredString(x + CARD_WIDTH / 2, y_top - CARD_HEIGHT / 2 - 12, "保留固定卡位，实际股票数量以概览为准")


def render_report(report: dict, path: Path) -> dict:
    """Create a fully preflighted PDF and return machine-readable layout audit.

    Raises ValueError on unsorted input or LayoutOverflow when full content
    cannot fit at >=7.5pt. Existing files are untouched if generation fails.
    """
    items = report.get("items") or []
    keys = []
    for item in items:
        direction, score = item.get("direction"), item.get("score")
        if direction not in ORDER or not isinstance(score, int) or isinstance(score, bool):
            raise ValueError("方向或评分无效：方向须为利好/中性/利空，评分须为整数")
        if not -5 <= score <= 5 or (direction == "利好" and score <= 0) or (direction == "利空" and score >= 0) or (direction == "中性" and score != 0):
            raise ValueError("方向与评分不一致")
        keys.append((ORDER[direction], -abs(score)))
    if keys != sorted(keys):
        raise ValueError("股票排序不符合利好、中性、利空及组内评分绝对值降序规则")
    counts = Counter(item["direction"] for item in items)
    page_count = max(1, math.ceil(len(items) / 4))
    layouts = [_layout_card(item) for item in items]
    overview = _overview(report, counts)
    stream = BytesIO()
    c = canvas.Canvas(stream, pagesize=A3, pageCompression=1)
    c.setTitle(f'{_value(report.get("date"))} A股重大公告利好利空日报')
    c.setAuthor("Finance News Digest")
    for page in range(page_count):
        c.setFillColor(PAPER)
        c.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        _draw_header(c, report, counts, overview, page + 1, page_count)
        for slot in range(4):
            index = page * 4 + slot
            x = MARGIN + (slot % 2) * (CARD_WIDTH + GUTTER)
            y_top = CARD_TOP - (slot // 2) * (CARD_HEIGHT + GUTTER)
            if index < len(items):
                new_group = index == 0 or items[index]["direction"] != items[index - 1]["direction"]
                _draw_card(c, items[index], layouts[index], x, y_top, new_group)
            else:
                _empty_card(c, x, y_top)
        c.setFillColor(MUTED)
        c.setFont(FONT, 8)
        c.drawString(MARGIN, 23, f'公告日期 {_value(report.get("date"))} ｜ 日线/周线/行业数据截至该日收盘')
        c.drawRightString(WIDTH - MARGIN, 23, f"第{page + 1}页/共{page_count}页")
        c.showPage()
    c.save()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False) as temporary:
            temporary.write(stream.getvalue())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    cards = [min(4, max(0, len(items) - 4 * page)) for page in range(page_count)]
    return {"page_count": page_count, "cards_per_page": cards,
            "slots_per_page": [4] * page_count,
            "empty_slots_per_page": [4 - count for count in cards],
            "stock_order": [item.get("code") for item in items],
            "direction_counts": {key: counts[key] for key in ORDER},
            "card_font_sizes": [layout["font_size"] for layout in layouts],
            "card_content_heights": [layout["body_height"] for layout in layouts],
            "card_height": round(CARD_HEIGHT, 2), "minimum_font_size": 7.5,
            "format": "A3 portrait", "overflow": False,
            "path": str(destination)}
