#!/usr/bin/env python3
"""
沪深300每日涨跌分析 v4
- 涨跌幅各取 top20
- 每个股票先检索互联网新闻（包含发布时间），作为证据
- 调用 codebuddy 综合分析，输出原因 + 证据链接（含发布时间）
"""

import json, sys, time, subprocess, re, urllib.request, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

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
        except Exception:
            break
        if not data:
            break
        for item in data:
            all_stocks.append({
                "code": item["code"],
                "name": item["name"],
                "change_pct": float(item["changepercent"]),
            })
        page += 1

    gainers = sorted([s for s in all_stocks if s["change_pct"] > 0], key=lambda x: x["change_pct"], reverse=True)[:n]
    losers = sorted([s for s in all_stocks if s["change_pct"] < 0], key=lambda x: x["change_pct"])[:n]
    return gainers, losers


def search_stock_news(stock_name, stock_code, limit=5):
    """
    用 Google News RSS 搜索个股相关新闻，返回标题+链接+发布时间。
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
        d = re.search(r"<pubDate>(.*?)</pubDate>", item, re.DOTALL)
        if t and l:
            title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t.group(1)).strip()
            link  = l.group(1).strip()
            pub_date = d.group(1).strip() if d else ""
            # 格式化时间：从 RFC 822 格式转为 YYYY-MM-DD HH:MM
            if pub_date:
                try:
                    dt = parsedate_to_datetime(pub_date)
                    pub_date = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            news_list.append({"title": title, "link": link, "pub_date": pub_date})
    return news_list


def build_prompt(target_date, gainers, losers, gainers_news, losers_news):
    lines = [
        f"# 任务：沪深300涨跌分析（{target_date}）",
        "",
        "你是一位资深 A 股分析师。请根据下方数据，生成一份专业、可读的沪深300涨跌分析。",
        "",
        "## 数据",
        "",
        "### 涨幅 Top 20",
        "",
    ]
    
    for i, s in enumerate(gainers, 1):
        lines.append(f"{i}. {s['name']}（{s['code']}）  涨{s['change_pct']:+.2f}%")
        news = gainers_news.get(s["code"], [])
        if news:
            lines.append("   证据新闻：")
            for n in news:
                pub_date_str = f" （{n['pub_date']}）" if n.get('pub_date') else ""
                lines.append(f"   - [{n['title']}]({n['link']}){pub_date_str}")
        lines.append("")
    
    lines += [
        "",
        "### 跌幅 Top 20",
        "",
    ]
    
    for i, s in enumerate(losers, 1):
        lines.append(f"{i}. {s['name']}（{s['code']}）  跌{s['change_pct']:+.2f}%")
        news = losers_news.get(s["code"], [])
        if news:
            lines.append("   证据新闻：")
            for n in news:
                pub_date_str = f" （{n['pub_date']}）" if n.get('pub_date') else ""
                lines.append(f"   - [{n['title']}]({n['link']}){pub_date_str}")
        lines.append("")
    
    lines += [
        "",
        "## 输出要求",
        "",
        "1. 用 JSON 格式输出，结构如下：",
        "```json",
    ]
    
    schema = {
        "date": target_date,
        "summary": "沪深300当日整体走势总结",
        "gainers_analysis": {
            "sector_summary": "涨幅板块共性",
            "stocks": [{"code": "600036", "name": "招商银行",
                        "reason": "涨跌原因一句话",
                        "evidence": [{"title": "新闻标题", "url": "https://...", "pub_date": "2026-06-14 09:30"}]}]
        },
        "losers_analysis": {
            "sector_summary": "跌幅板块共性",
            "stocks": [{"code": "600000", "name": "浦发银行",
                        "reason": "涨跌原因一句话",
                        "evidence": [{"title": "新闻标题", "url": "https://...", "pub_date": "2026-06-14 14:20"}]}]
        }
    }
    
    lines.append(json.dumps(schema, indent=2, ensure_ascii=False))
    lines.append("```")
    lines += [
        "",
        "2. 重要：输出必须是**有效的 JSON**，确保可以被 Python json.loads() 解析。",
        "   - 所有字符串中的双引号必须转义为 \\",
        "   - 不要使用弯引号（U+201C/U+201D）",
        "   - 每个键值对后用逗号，最后一个不用",
        "",
        "3. 在 evidence 中必须包含 pub_date 字段（新闻发布时间）。",
        "",
        "4. 分析要专业、简洁，原因一句话概括。",
        "",
    ]
    
    return "\n".join(lines)


def run_codex(prompt, project_root, codex_bin="codebuddy"):
    """调用 codebuddy 或 codex 生成 CSI300 分析"""
    is_codebuddy = "codebuddy" in codex_bin or codex_bin == "cbc"
    
    if is_codebuddy:
        cmd = [
            codex_bin,
            "--print",
            "--sandbox=container",
            "--dangerously-skip-permissions",
            "-",
        ]
    else:
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
    
    # 解析输出
    report_json_str = ""
    
    # 保存原始输出用于调试
    debug_dir = project_root / "var/tmp"
    debug_dir.mkdir(parents=True, exist_ok=True)
    with open(debug_dir / "csi300_codebuddy_raw.txt", "w") as f:
        f.write(completed.stdout)
    
    if is_codebuddy:
        report_json_str = completed.stdout
        
        # 尝试从输出中提取 JSON
        code_block_match = re.search(r'```json\s*\n(.*?)\n```', report_json_str, re.DOTALL)
        if code_block_match:
            report_json_str = code_block_match.group(1).strip()
        else:
            start_idx = report_json_str.find('{')
            end_idx = report_json_str.rfind('}')
            if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                report_json_str = report_json_str[start_idx:end_idx+1]
        
        # 保存提取的 JSON 用于调试
        with open(debug_dir / "csi300_extracted_json.txt", "w") as f:
            f.write(report_json_str)
        
        # 尝试解析 JSON
        try:
            result = json.loads(report_json_str)
            return result
        except json.JSONDecodeError as e:
            print(f"[WARNING] JSON 解析失败: {e}", file=sys.stderr)
            
            # 尝试使用 json5 库（如果可用）
            try:
                import json5
                result = json5.loads(report_json_str)
                print(f"[DEBUG] 使用 json5 解析成功", file=sys.stderr)
                return result
            except ImportError:
                raise RuntimeError(f"codebuddy 未返回有效 JSON: {e}\n\n提取的 JSON 前500字符:\n{report_json_str[:500]}")
    else:
        # codex 格式
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


def format_report(result, target_date):
    lines = [
        f"# 沪深300涨跌分析 — {target_date}",
        "",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**分析基于：** 沪深300指数成分股涨跌幅 top20",
        "",
        "---",
        "",
        f"## 一、指数概况",
        "",
        result.get("summary", "（暂无）"),
        "",
        "---",
        "",
        "## 二、涨幅分析（Top 20）",
        "",
        f"**板块共性：** {result.get('gainers_analysis', {}).get('sector_summary', '（暂无）')}",
        "",
    ]
    
    # 涨幅表格
    lines.append("| 排名 | 股票代码 | 股票名称 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |")
    lines.append("|------|----------|----------|--------|----------|--------------|")
    for i, st in enumerate(result.get("gainers_analysis", {}).get("stocks", []), 1):
        code = st.get('code', '')
        name = st.get('name', '')
        reason = st.get('reason', '')
        lines.append(f"| {i} | {code} | {name} | {reason} | 待补充 | 待补充 |")
    lines.append("")
    
    # 涨幅详细分析
    for st in result.get("gainers_analysis", {}).get("stocks", []):
        lines.append(f"### {st.get('name')}（{st.get('code')}）")
        lines.append("")
        lines.append(f"**原因：** {st.get('reason', '（暂无）')}")
        evidence = st.get("evidence", [])
        if evidence:
            lines.append("")
            lines.append("**证据：**")
            for ev in evidence:
                title = ev.get('title', '链接')
                url = ev.get('url', '#')
                pub_date = ev.get('pub_date', '')
                if pub_date:
                    lines.append(f"- [{title}]({url}) （{pub_date}）")
                else:
                    lines.append(f"- [{title}]({url})")
        lines.append("")
    
    lines += [
        "---",
        "",
        "## 三、跌幅分析（Top 20）",
        "",
        f"**板块共性：** {result.get('losers_analysis', {}).get('sector_summary', '（暂无）')}",
        "",
    ]
    
    # 跌幅表格
    lines.append("| 排名 | 股票代码 | 股票名称 | 涨跌幅 | 本周涨幅 | 年初至今涨幅 |")
    lines.append("|------|----------|----------|--------|----------|--------------|")
    for i, st in enumerate(result.get("losers_analysis", {}).get("stocks", []), 1):
        code = st.get('code', '')
        name = st.get('name', '')
        reason = st.get('reason', '')
        lines.append(f"| {i} | {code} | {name} | {reason} | 待补充 | 待补充 |")
    lines.append("")
    
    # 跌幅详细分析
    for st in result.get("losers_analysis", {}).get("stocks", []):
        lines.append(f"### {st.get('name')}（{st.get('code')}）")
        lines.append("")
        lines.append(f"**原因：** {st.get('reason', '（暂无）')}")
        evidence = st.get("evidence", [])
        if evidence:
            lines.append("")
            lines.append("**证据：**")
            for ev in evidence:
                title = ev.get('title', '链接')
                url = ev.get('url', '#')
                pub_date = ev.get('pub_date', '')
                if pub_date:
                    lines.append(f"- [{title}]({url}) （{pub_date}）")
                else:
                    lines.append(f"- [{title}]({url})")
        lines.append("")
    
    lines += [
        "---",
        "",
        f"*报告由 AI 生成，仅供参考。*",
    ]
    
    return "\n".join(lines)


def main():
    target_date = None
    output_dir = None
    
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--date" and i + 1 < len(sys.argv):
            target_date = sys.argv[i + 1]
            i += 2
        else:
            output_dir = Path(sys.argv[i])
            i += 1
    
    if not target_date:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if not output_dir:
        output_dir = PROJECT_ROOT / "published/csi300"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    t0 = time.time()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 获取沪深300涨跌幅 top20...")
    gainers, losers = get_csi300_top_movers(20)
    
    if not gainers and not losers:
        print("无法获取沪深300数据，请检查网络或数据源。")
        sys.exit(1)
    
    print(f"  涨幅榜首：{gainers[0]['name']} {gainers[0]['change_pct']:+.2f}%")
    print(f"  跌幅榜首：{losers[0]['name']} {losers[0]['change_pct']:+.2f}%")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 检索互联网证据新闻（每只股票约5条）...")
    gainers_news = {s["code"]: search_stock_news(s["name"], s["code"]) for s in gainers}
    losers_news = {s["code"]: search_stock_news(s["name"], s["code"]) for s in losers}
    
    for code, news in gainers_news.items():
        print(f"  {[s['name'] for s in gainers if s['code'] == code][0]}：找到 {len(news)} 条新闻")
    for code, news in losers_news.items():
        print(f"  {[s['name'] for s in losers if s['code'] == code][0]}：找到 {len(news)} 条新闻")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 调用 codex 综合分析...")
    prompt = build_prompt(target_date, gainers, losers, gainers_news, losers_news)
    
    # 保存 prompt 用于调试
    debug_dir = PROJECT_ROOT / "var/tmp"
    debug_dir.mkdir(parents=True, exist_ok=True)
    with open(debug_dir / "csi300_prompt.txt", "w") as f:
        f.write(prompt)
    
    result = run_codex(prompt, PROJECT_ROOT, CODEX_BIN)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 生成报告...")
    report = format_report(result, target_date)
    
    out_path = output_dir / f"{target_date}_with_table.md"
    out_path.write_text(report, encoding="utf-8")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 完成 ✅  {str(out_path)}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]  耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
