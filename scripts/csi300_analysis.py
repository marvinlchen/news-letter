#!/usr/bin/env python3
"""
沪深300每日涨跌分析 v3
- 涨跌幅各取 top20
- 每个股票先检索互联网新闻，作为证据
- 调用 codex 综合分析，输出原因 + 证据链接
"""

import json, sys, time, subprocess, re, urllib.request, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

CODEX_BIN = "codebuddy"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def fetch_url(url, headers=None, timeout=10):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return None


def get_csi300_top_movers(n=20):
    all_stocks, page = [], 1
    while len(all_stocks) < 300:
        url = (f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"Market_Center.getHQNodeData?page={page}&num=100&sort=changepercent&asc=0&node=hs300")
        content = fetch_url(url)
        if not content:
            break
        try:
            data = json.loads(content)
            if not data:
                break
            for item in data:
                all_stocks.append({
                    "code":  item.get("code", ""),
                    "name":  item.get("name", ""),
                    "price": float(item.get("trade", 0) or 0),
                    "change_pct": float(item.get("changepercent", 0) or 0),
                })
            page += 1
            time.sleep(0.3)
        except Exception:
            break

    if not all_stocks:
        print("[ERROR] 无法获取沪深300数据", file=sys.stderr)
        sys.exit(1)

    all_stocks.sort(key=lambda x: x["change_pct"], reverse=True)
    return all_stocks[:20], all_stocks[-20:][::-1]


def search_stock_news(stock_name, stock_code, limit=5):
    """
    用 Google News RSS 搜索个股相关新闻，返回标题+链接列表。
    这是"证据"的来源。
    """
    query = urllib.parse.quote(f"{stock_name} {stock_code} 涨跌 原因")
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    content = fetch_url(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    if not content:
        return []

    news_list = []
    items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)
    for item in items[:limit]:
        t = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        l = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
        if t and l:
            title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t.group(1)).strip()
            link  = l.group(1).strip()
            news_list.append({"title": title, "link": link})
    return news_list


def build_prompt(gainers, losers, gainers_news, losers_news, target_date):
    """
    构建 prompt：把股票数据 + 检索到的证据新闻一起发给 codex，
    要求输出结构化的原因分析，并附上证据链接。
    """
    lines = [
        f"# 沪深300涨跌分析报告 — {target_date}",
        "",
        "你是一位资深A股分析师。请根据下方提供的涨跌幅数据以及",
        "每只股票对应的互联网新闻证据，撰写深度分析报告。",
        "",
        "## 输出要求",
        "- 涨幅、跌幅各取 top20 分析",
        "- 每个股票给出一句话原因（基于证据新闻归纳）",
        "- 每个股票附上 2-3 条证据链接（直接用下方提供的链接）",
        "- 先写板块总结，再逐个股票分析",
        "- 输出严格按 JSON Schema，不要输出其他内容",
        "",
        "## 涨幅 Top 20",
        "",
    ]
    for i, s in enumerate(gainers, 1):
        lines.append(f"{i}. {s['name']}（{s['code']}）  涨{s['change_pct']:+.2f}%")
        news = gainers_news.get(s["code"], [])
        if news:
            lines.append("   证据新闻：")
            for n in news:
                lines.append(f"   - [{n['title']}]({n['link']})")
        lines.append("")

    lines.append("## 跌幅 Top 20")
    lines.append("")
    for i, s in enumerate(losers, 1):
        lines.append(f"{i}. {s['name']}（{s['code']}）  跌{s['change_pct']:+.2f}%")
        news = losers_news.get(s["code"], [])
        if news:
            lines.append("   证据新闻：")
            for n in news:
                lines.append(f"   - [{n['title']}]({n['link']})")
        lines.append("")

    lines += [
        "",
        "## 输出 JSON Schema",
        "```json",
    ]
    schema = {
        "date": target_date,
        "summary": "沪深300当日整体走势总结",
        "gainers_analysis": {
            "sector_summary": "涨幅板块共性",
            "stocks": [{"code": "600036", "name": "招商银行",
                        "reason": "涨跌原因一句话",
                        "evidence": [{"title": "新闻标题", "url": "https://..."}]}]
        },
        "losers_analysis": {
            "sector_summary": "跌幅板块共性",
            "stocks": [{"code": "600000", "name": "浦发银行",
                        "reason": "涨跌原因一句话",
                        "evidence": [{"title": "新闻标题", "url": "https://..."}]}]
        }
    }
    lines.append(json.dumps(schema, indent=2, ensure_ascii=False))
    lines.append("```")
    return "\n".join(lines)


def run_codex(prompt, project_root, codex_bin="codex"):
    schema_path = project_root / "schemas/csi300.schema.json"
    cmd = [
        codex_bin, "exec",
        "--experimental-json",
        "--sandbox=read-only",
        "--skip-git-repo-check",
        "-",
    ]
    completed = subprocess.run(
        cmd,
        cwd=str(project_root),
        env={**__import__("os").environ, "PATH": "/home/ME/.local/bin:" + __import__("os").environ.get("PATH", "")},
        input=prompt, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=900, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"codex exited {completed.returncode}: {completed.stderr[-2000:]}")

    report_json_str = ""
    for line in (completed.stdout or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get("type") == "item.completed" and obj.get("item", {}).get("type") == "agent_message":
                report_json_str = obj["item"].get("text", "")
        except json.JSONDecodeError:
            continue

    if not report_json_str:
        m = re.search(r"\{[\s\S]*\}", completed.stdout)
        if m:
            report_json_str = m.group(0)

    if not report_json_str:
        raise RuntimeError(f"codex 未返回有效 JSON：{completed.stdout[-500:]}")

    m = re.search(r"```json\s*([\s\S]*?)\s*```", report_json_str)
    if m:
        report_json_str = m.group(1)
    else:
        s, e = report_json_str.find("{"), report_json_str.rfind("}")
        if s != -1 and e != -1:
            report_json_str = report_json_str[s:e+1]

    return json.loads(report_json_str)


def generate_md_report(result, output_path):
    date = result.get("date", datetime.now().strftime("%Y-%m-%d"))
    lines = [
        f"# 沪深300涨跌分析 — {date}",
        "",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 📝 市场总结",
        "",
        result.get("summary", "（暂无）"),
        "",
        "---",
        "",
        "## 📈 涨幅分析（Top 20）",
        "",
        f"**板块共性：** {result.get('gainers_analysis', {}).get('sector_summary', '（暂无）')}",
        "",
    ]
    for st in result.get("gainers_analysis", {}).get("stocks", []):
        lines.append(f"### {st.get('name')}（{st.get('code')}）")
        lines.append("")
        lines.append(f"**原因：** {st.get('reason', '（暂无）')}")
        evidence = st.get("evidence", [])
        if evidence:
            lines.append("")
            lines.append("**证据：**")
            for ev in evidence:
                lines.append(f"- [{ev.get('title', '链接')}]({ev.get('url', '#')})")
        lines.append("")

    lines += [
        "---",
        "",
        "## 📉 跌幅分析（Top 20）",
        "",
        f"**板块共性：** {result.get('losers_analysis', {}).get('sector_summary', '（暂无）')}",
        "",
    ]
    for st in result.get("losers_analysis", {}).get("stocks", []):
        lines.append(f"### {st.get('name')}（{st.get('code')}）")
        lines.append("")
        lines.append(f"**原因：** {st.get('reason', '（暂无）')}")
        evidence = st.get("evidence", [])
        if evidence:
            lines.append("")
            lines.append("**证据：**")
            for ev in evidence:
                lines.append(f"- [{ev.get('title', '链接')}]({ev.get('url', '#')})")
        lines.append("")

    lines += [
        "",
        "---",
        "",
        "*报告由 AI 分析生成，仅供参考，不构成投资建议。*",
    ]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[OK] 报告已写入 {output_path}")


def main():
    target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "published/csi300"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{datetime.now():%H:%M:%S}] 获取沪深300涨跌幅 top20…")
    gainers, losers = get_csi300_top_movers(20)
    print(f"  涨幅榜首：{gainers[0]['name']} {gainers[0]['change_pct']:+.2f}%")
    print(f"  跌幅榜首：{losers[0]['name']} {losers[0]['change_pct']:+.2f}%")

    print(f"[{datetime.now():%H:%M:%S}] 检索互联网证据新闻（每只股票约5条）…")
    gainers_news = {}
    for s in gainers:
        news = search_stock_news(s["name"], s["code"], limit=5)
        gainers_news[s["code"]] = news
        print(f"  {s['name']}：找到 {len(news)} 条新闻")
        time.sleep(0.8)
    losers_news = {}
    for s in losers:
        news = search_stock_news(s["name"], s["code"], limit=5)
        losers_news[s["code"]] = news
        print(f"  {s['name']}：找到 {len(news)} 条新闻")
        time.sleep(0.8)

    print(f"[{datetime.now():%H:%M:%S}] 调用 codex 综合分析…")
    prompt = build_prompt(gainers, losers, gainers_news, losers_news, target_date)
    result = run_codex(prompt, PROJECT_ROOT, CODEX_BIN)

    md_path = output_dir / f"{target_date}.md"
    generate_md_report(result, md_path)

    latest_path = output_dir / "latest.md"
    latest_path.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[{datetime.now():%H:%M:%S}] 完成。")

if __name__ == "__main__":
    main()
