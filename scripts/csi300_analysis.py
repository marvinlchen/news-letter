#!/usr/bin/env python3
"""
沪深300每日涨跌分析
获取沪深300成分股涨跌幅 top10，并分析涨跌原因
"""

import json
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import urllib.parse
import re
import time

def fetch_url(url, headers=None):
    """简单的 URL 获取函数，使用标准库"""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def get_csi300_constituents():
    """获取沪深300成分股列表 - 使用新浪财经接口（分页获取）"""
    all_stocks = []
    page = 1
    
    while len(all_stocks) < 300:
        # 新浪财经沪深300成分股接口 - 分页获取
        url = f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=100&sort=changepercent&asc=0&node=hs300"
        
        content = fetch_url(url)
        if not content:
            print(f"错误: 无法从新浪财经获取数据 (page {page})", file=sys.stderr)
            break
        
        try:
            # 新浪返回的是 JSON 数组
            data = json.loads(content)
            
            if not data:
                break  # 没有更多数据
            
            for item in data:
                # 新浪返回的格式: {"symbol":"sh.600036","code":"600036","name":"招商银行",...}
                code = item.get('code', '')
                name = item.get('name', '')
                symbol = item.get('symbol', '')  # sh.600036 or sz.000001
                
                # 判断市场
                market = 1 if symbol.startswith('sh') else 0
                
                # 获取涨跌幅
                change_pct = float(item.get('changepercent', 0))
                price = float(item.get('trade', 0))
                change = float(item.get('pricechange', 0))
                
                all_stocks.append({
                    'code': code,
                    'market': market,
                    'name': name,
                    'price': price,
                    'change_pct': change_pct,
                    'change': change,
                    'volume': 0,
                    'amount': 0
                })
            
            page += 1
            time.sleep(0.5)  # 避免请求过快
            
        except Exception as e:
            print(f"解析数据失败 (page {page}): {e}", file=sys.stderr)
            break
    
    print(f"成功获取 {len(all_stocks)} 只沪深300成分股", file=sys.stderr)
    return all_stocks[:300]  # 确保只返回300只

def get_stock_realtime_quotes(stock_codes):
    """获取股票实时行情 - 批量获取"""
    # 新浪财经接口，支持批量查询
    # stock_codes: list of (code, market) tuples
    # market: 0 for SZ, 1 for SH
    
    if not stock_codes:
        return []
    
    # 构建查询字符串
    query_codes = []
    for code, market in stock_codes:
        prefix = 'sz' if market == 0 else 'sh'
        query_codes.append(f"{prefix}{code}")
    
    url = f"http://hq.sinajs.cn/list={','.join(query_codes)}"
    
    content = fetch_url(url)
    if not content:
        return []
    
    quotes = []
    lines = content.strip().split('\n')
    
    for line in lines:
        if '=' not in line:
            continue
        
        try:
            var_name, data_str = line.split('=', 1)
            data_str = data_str.strip('"')
            
            if not data_str:
                continue
            
            fields = data_str.split(',')
            if len(fields) < 32:
                continue
            
            # 解析新浪财经数据格式
            quote = {
                'name': fields[0],
                'open': float(fields[1]) if fields[1] else 0,
                'close_yesterday': float(fields[2]) if fields[2] else 0,
                'current': float(fields[3]) if fields[3] else 0,
                'high': float(fields[4]) if fields[4] else 0,
                'low': float(fields[5]) if fields[5] else 0,
                'volume': int(fields[8]) if fields[8] else 0,
                'amount': float(fields[9]) if fields[9] else 0,
                'change_pct': 0,
            }
            
            # 计算涨跌幅
            if quote['close_yesterday'] > 0:
                quote['change_pct'] = ((quote['current'] - quote['close_yesterday']) / quote['close_yesterday']) * 100
            
            quotes.append(quote)
            
        except Exception as e:
            print(f"Error parsing quote: {e}", file=sys.stderr)
            continue
    
    return quotes

def search_stock_news(stock_name, stock_code, limit=5, days=7):
    """搜索个股相关新闻 - 使用 Google News RSS，仅返回近N天的新闻"""
    # 使用 Google News RSS 搜索
    query = urllib.parse.quote(f"{stock_name} {stock_code}")
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    
    content = fetch_url(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    if not content:
        return []
    
    news_list = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    try:
        # 解析 RSS - 提取所有 <item>
        items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
        
        for item in items:
            # 提取标题
            title_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
            link_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
            pub_date_match = re.search(r'<pubDate>(.*?)</pubDate>', item, re.DOTALL)
            
            if title_match and link_match:
                title = title_match.group(1).strip()
                link = link_match.group(1).strip()
                
                # 清理标题中的 HTML 实体
                title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)
                
                # 解析发布日期
                pub_date = None
                if pub_date_match:
                    try:
                        # Google News RSS 日期格式: "Thu, 12 Jun 2026 08:30:00 GMT"
                        date_str = pub_date_match.group(1).strip()
                        pub_date = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z')
                    except Exception as e:
                        print(f"Error parsing date '{date_str}': {e}", file=sys.stderr)
                
                # 只保留近N天的新闻
                if pub_date and pub_date < cutoff_date:
                    continue  # 跳过旧新闻
                
                news_list.append({
                    'title': title,
                    'link': link,
                    'pub_date': pub_date
                })
                
                if len(news_list) >= limit:
                    break
        
    except Exception as e:
        print(f"Error parsing Google News RSS for {stock_name}: {e}", file=sys.stderr)
    
    return news_list

def generate_report(top_gainers, top_losers, output_dir):
    """生成涨跌分析报告"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    report_file = output_path / f"{today}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# 沪深300涨跌分析 - {today}\n\n")
        
        f.write("## 📈 涨幅 Top 10\n\n")
        f.write("| 排名 | 股票代码 | 股票名称 | 最新价 | 涨跌幅 |\n")
        f.write("|------|----------|----------|--------|--------|\n")
        
        for i, stock in enumerate(top_gainers, 1):
            f.write(f"| {i} | {stock['code']} | {stock['name']} | {stock['price']:.2f} | {stock['change_pct']:+.2f}% |\n")
        
        f.write("\n## 📉 跌幅 Top 10\n\n")
        f.write("| 排名 | 股票代码 | 股票名称 | 最新价 | 涨跌幅 |\n")
        f.write("|------|----------|----------|--------|--------|\n")
        
        for i, stock in enumerate(top_losers, 1):
            f.write(f"| {i} | {stock['code']} | {stock['name']} | {stock['price']:.2f} | {stock['change_pct']:+.2f}% |\n")
        
        f.write("\n## 🔍 涨跌原因分析\n\n")
        
        # 分析涨幅 top 股票
        f.write("### 涨幅原因分析\n\n")
        for i, stock in enumerate(top_gainers[:5], 1):  # 只分析前5个
            f.write(f"#### {i}. {stock['name']} ({stock['code']}) - {stock['change_pct']:+.2f}%\n\n")
            
            # 搜索相关新闻
            news = search_stock_news(stock['name'], stock['code'], limit=3)
            
            if news:
                f.write("**相关新闻：**\n\n")
                for item in news:
                    f.write(f"- [{item['title']}]({item['link']})\n")
            else:
                f.write("*暂无相关新闻*\n")
            
            f.write("\n")
            time.sleep(1)  # 避免请求过快
        
        # 分析跌幅 top 股票
        f.write("### 跌幅原因分析\n\n")
        for i, stock in enumerate(top_losers[:5], 1):  # 只分析前5个
            f.write(f"#### {i}. {stock['name']} ({stock['code']}) - {stock['change_pct']:+.2f}%\n\n")
            
            # 搜索相关新闻
            news = search_stock_news(stock['name'], stock['code'], limit=3)
            
            if news:
                f.write("**相关新闻：**\n\n")
                for item in news:
                    f.write(f"- [{item['title']}]({item['link']})\n")
            else:
                f.write("*暂无相关新闻*\n")
            
            f.write("\n")
            time.sleep(1)  # 避免请求过快
        
        f.write(f"\n---\n*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    
    print(f"Report generated: {report_file}")
    return str(report_file)

def main():
    """主函数"""
    print("正在获取沪深300成分股数据...")
    
    # 获取沪深300成分股
    stocks = get_csi300_constituents()
    
    if not stocks:
        print("错误: 无法获取沪深300成分股数据", file=sys.stderr)
        sys.exit(1)
    
    print(f"成功获取 {len(stocks)} 只成分股数据")
    
    # 按涨跌幅排序
    stocks_sorted = sorted(stocks, key=lambda x: x['change_pct'], reverse=True)
    
    # 获取 top10 涨幅和跌幅
    top_gainers = stocks_sorted[:10]
    top_losers = stocks_sorted[-10:][::-1]  # 反转顺序，让跌幅最大的排第一
    
    print("\n涨幅 Top 10:")
    for i, stock in enumerate(top_gainers, 1):
        print(f"  {i}. {stock['name']} ({stock['code']}): {stock['change_pct']:+.2f}%")
    
    print("\n跌幅 Top 10:")
    for i, stock in enumerate(top_losers, 1):
        print(f"  {i}. {stock['name']} ({stock['code']}): {stock['change_pct']:+.2f}%")
    
    # 生成报告
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "./reports/csi300"
    report_file = generate_report(top_gainers, top_losers, output_dir)
    
    print(f"\n报告已生成: {report_file}")

if __name__ == '__main__':
    main()
