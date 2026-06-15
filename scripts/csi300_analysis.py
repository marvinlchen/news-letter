#!/usr/bin/env python3
"""
沪深300每日涨跌分析 v2
获取沪深300成分股涨跌幅 top10，用 AI 分析涨跌原因
"""

import json
import sys
import time
import subprocess
import re
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import urllib.parse

# ── 配置 ──────────────────────────────────────────────────────────────────────
CODEX_BIN = "codex"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_SCHEMA = PROJECT_ROOT / "schemas/csi300.schema.json"


def fetch_url(url, headers=None, timeout=10):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[WARN] fetch failed {url[:60]}: {e}", file=sys.stderr)
        return None


def get_csi300_top_movers():
    """
    获取沪深300成分股，返回涨跌幅 top10 涨幅和 top10 跌幅。
    使用新浪财经接口（已验证可用）。
    """
    all_stocks = []
    page = 1

    while len(all_stocks) < 300:
        url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeData?"
            f"page={page}&num=100&sort=changepercent&asc=0&node=hs300"
        )
        content = fetch_url(url)
        if not content:
            break

        try:
            data = json.loads(content)
            if not data:
                break

            for item in data:
                all_stocks.append({
                    "code":   item.get("code", ""),
                    "name":   item.get("name", ""),
                    "market":  1 if item.get("symbol", "").startswith("sh") else 0,
                    "price":  float(item.get("trade", 0) or 0),
                    "change":  float(item.get("pricechange", 0) or 0),
                    "change_pct": float(item.get("changepercent", 0) or 0),
                })

            page += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"[WARN] parse page {page} failed: {e}", file=sys.stderr)
            break

    if not all_stocks:
        print("[ERROR] 无法获取沪深300数据", file=sys.stderr)
        sys.exit(1)

    all_stocks.sort(key=lambda x: x["change_pct"], reverse=True)
    gainers = all_stocks[:10]
    losers = all_stocks[-10:][::-1]
    return gainers, losers


def build_prompt(gainers, losers, target_date):
    """
    构建给 codex 的 prompt，要求分析涨跌原因，而不是罗列新闻标题。
    """
    lines = [
        f"# 沪深300涨跌分析报告 — {target_date}",
        "",
        "你是一位资深A股分析师。请根据以下沪深300成分股涨跌幅数据，",
        "**深入分析涨跌原因**。要求：",
        "",
        "1. 不要罗列新闻标题，要对信息进行归纳、提炼和逻辑分析；",
        "2. 从宏观环境、行业板块、个股基本面、资金流向等维度分析原因；",
        "3. 涨幅和跌幅分开分析，各自归纳共性原因（如：某板块集体上涨/下跌）；",
        "4. 如果有明显催化剂（政策、财报、事件），指出具体是什么；",
        "5. 语言简洁专业，中文输出。",
        "",
        "## 涨幅 Top 10",
        "",
        "| 排名 | 代码 | 名称 | 最新价 | 涨跌幅 |",
        "|------|------|------|--------|--------|",
    ]
    for i, s in enumerate(gainers, 1):
        lines.append(f"| {i} | {s['code']} | {s['name']} | {s['price']:.2f} | {s['change_pct']:+.2f}% |")

    lines += [
        "",
        "## 跌幅 Top 10",
        "",
        "| 排名 | 代码 | 名称 | 最新价 | 涨跌幅 |",
        "|------|------|------|--------|--------|",
    ]
    for i, s in enumerate(losers, 1):
        lines.append(f"| {i} | {s['code']} | {s['name']} | {s['price']:.2f} | {s['change_pct']:+.2f}% |")

    lines += [
        "",
        "请按以下 JSON Schema 输出分析结果：",
        "```json",
        json.dumps({
            "date": target_date,
            "summary": "当日沪深300整体走势一句话总结",
            "gainers_analysis": {
                "sector_summary": "涨幅板块共性分析",
                "key_drivers": ["驱动因素1", "驱动因素2"],
                "stocks": [{"code": "600036", "name": "招商银行", "reason": "具体分析"}]
            },
            "losers_analysis": {
                "sector_summary": "跌幅板块共性分析",
                "key_drivers": ["驱动因素1", "驱动因素2"],
                "stocks": [{"code": "600000", "name": "浦发银行", "reason": "具体分析"}]
            }
        }, indent=2, ensure_ascii=False),
        "```",
        "",
        "只输出 JSON，不要输出其他内容。",
    ]
    return "\n".join(lines)


def run_codex(prompt, project_root, codex_bin="codex"):
    """调用 codex exec --experimental-json 获取分析结果"""
    schema = project_root / "schemas/csi300.schema.json"
    if not schema.exists():
        schema = ""

    cmd = [
        codex_bin,
        "exec",
        "--experimental-json",
        "--sandbox=read-only",
        "--skip-git-repo-check",
        "-",
    ]
    completed = subprocess.run(
        cmd,
        cwd=str(project_root),
        env={**__import__("os").environ, "PATH": "/home/ME/.local/bin:" + __import__("os").environ.get("PATH", "")},
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"codex exited {completed.returncode}: {completed.stderr[-2000:]}")

    # 解析 --experimental-json 输出
    report_json_str = ""
    for line in (completed.stdout or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "item.completed" and obj.get("item", {}).get("type") == "agent_message":
            report_json_str = obj["item"].get("text", "")

    if not report_json_str:
        # 兜底：直接取 stdout 最后一个大括号块
        match = re.search(r"\{.*\}", completed.stdout, re.DOTALL)
        if match:
            report_json_str = match.group(0)

    if not report_json_str:
        raise RuntimeError(f"codex 未返回有效 JSON：{completed.stdout[-500:]}")

    # 去掉 markdown 包裹
    m = re.search(r"```json\s*([\s\S]*?)\s*```", report_json_str)
    if m:
        report_json_str = m.group(1)
    else:
        start = report_json_str.find("{")
        end = report_json_str.rfind("}")
        if start != -1 and end != -1:
            report_json_str = report_json_str[start:end + 1]

    return json.loads(report_json_str)


def generate_md_report(result, output_path):
    """将 JSON 分析结果渲染为 Markdown 报告"""
    date = result.get("date", datetime.now().strftime("%Y-%m-%d"))
    lines = [
        f"# 沪深300涨跌分析 — {date}",
        "",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        "",
        "---",
        "",
        "## 📝 市场总结",
        "",
        result.get("summary", "（暂无总结）"),
        "",
        "---",
        "",
        "## 📈 涨幅分析",
        "",
        f"**板块共性：** {result.get('gainers_analysis', {}).get('sector_summary', '（暂无）')}",
        "",
        "**核心驱动因素：**",
    ]
    for d in result.get("gainers_analysis", {}).get("key_drivers", []):
        lines.append(f"- {d}")
    lines += ["", "**个股分析：**", ""]
    for st in result.get("gainers_analysis", {}).get("stocks", []):
        lines.append(f"### {st.get('name')}（{st.get('code')}）")
        lines.append("")
        lines.append(st.get("reason", "（暂无分析）"))
        lines.append("")

    lines += [
        "---",
        "",
        "## 📉 跌幅分析",
        "",
        f"**板块共性：** {result.get('losers_analysis', {}).get('sector_summary', '（暂无）')}",
        "",
        "**核心驱动因素：**",
    ]
    for d in result.get("losers_analysis", {}).get("key_drivers", []):
        lines.append(f"- {d}")
    lines += ["", "**个股分析：**", ""]
    for st in result.get("losers_analysis", {}).get("stocks", []):
        lines.append(f"### {st.get('name')}（{st.get('code')}）")
        lines.append("")
        lines.append(st.get("reason", "（暂无分析）"))
        lines.append("")

    lines += [
        "",
        "---",
        "",
        f"*报告由 AI 分析生成，仅供参考，不构成投资建议。*",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[OK] 报告已写入 {output_path}")


def main():
    target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "published/csi300"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{datetime.now():%H:%M:%S}] 开始获取沪深300涨跌数据…")
    gainers, losers = get_csi300_top_movers()
    print(f"  涨幅 Top10: {gainers[0]['name']} +{gainers[0]['change_pct']:.2f}%")
    print(f"  跌幅 Top10: {losers[0]['name']} {losers[0]['change_pct']:.2f}%")

    print(f"[{datetime.now():%H:%M:%S}] 调用 codex 分析涨跌原因…")
    prompt = build_prompt(gainers, losers, target_date)
    result = run_codex(prompt, PROJECT_ROOT, CODEX_BIN)

    md_path = output_dir / f"{target_date}.md"
    generate_md_report(result, md_path)

    # 更新 latest.md
    latest_path = output_dir / "latest.md"
    latest_path.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[{datetime.now():%H:%M:%S}] 完成。")


if __name__ == "__main__":
    main()
