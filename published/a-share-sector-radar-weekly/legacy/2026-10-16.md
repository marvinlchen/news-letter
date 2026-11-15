# A股产业领先信号周报｜2026-10-16

> 产业证据与市场确认分开审计。PASS不等于买入；行业指数不可直接交易；本报告不构成投资建议。

## 运行质量与本周动作

| 项目 | 结果 |
|---|---|
| 样本性质 | **正式前瞻样本** |
| 本周动作 | 按冻结规则发布；新增激活从下一共同交易日开盘代理记账。 |
| 观察窗口 | 2026-10-10 至 2026-10-16 |
| 行情应到 / 实到 | 2026-10-16 / 2026-10-16 |
| 策略版本 | `v0.2-F.2-pilot` |
| 证据引擎 | `rules-recovery-v1 @ 3b7088cc9288` |
| 候选 / claim / 采用引用 | 260 / 62 / 60 |
| 候选行业覆盖 | 31/31 |
| 语义利用率 | 23.1% |
| 新激活 / 持有确认 | 2 / 0 |
| 本次检查时间 | 2026-10-18T10:12:38+08:00 |
| 数据源错误 | 2 |
| 广度成分股请求 / 缓存命中 | 394 / 0 |

数据源错误明细（最多3条，已清洗）：
- 801770/688387成分股日线失败: 688387成分股日线双源失败；腾讯: 腾讯sh688387缺少前复权日线（原始日线120条）；东财: Remote end closed connection without response
- 801770/688635成分股日线失败: 688635成分股日线双源失败；腾讯: 腾讯sh688635缺少前复权日线（原始日线96条）；东财: Remote end closed connection without response

本周新增激活：建筑装饰、交通运输。

## 市场概览

| 指标 | 结果 |
|---|---|
| 20日上涨行业 | 2/31（其余未计算0） |
| 31行业20日中位数 | -7.35% |
| 防追高行业 | 7 |
| 广度未计算 | 28/31；未计算不视为失败 |
| 20日排名前三 | 银行 +2.52%（第1）；食品饮料 +0.36%（第2）；煤炭 -1.32%（第3） |

## 信号漏斗

| 阶段 | 行业数 | 说明 |
|---|---:|---|
| 有候选输入 | 31 | 共260条候选 |
| 硬证据PASS | 3 | 至少2类、2主体、2个独立URL、2个事件簇，且含成分公司 |
| 质量可用 | 3 | 少于2个质量旗标 |
| 排除拥挤后 | 2 | 不新增追逐成熟周期或短期急涨 |
| 市场三选二 | 2 | 未计算的广度不计通过、也不计失败 |
| 雷达 / 新激活 | 3 / 2 | 雷达上限8，新激活上限3 |

## 已通过证据门的雷达

| 雷达序号 | 行业 | S/O/E | 主体 | 独立URL | 市场三项 | 20日排名 | 状态 |
|---:|---|---|---:|---:|---|---:|---|
| 1 | 建筑装饰 | E,O,S | 3 | 4 | 相对通过 / 广度未通过 / 成交通过 | 13 | 新激活 |
| 2 | 通信 | E,S | 3 | 3 | 相对未通过 / 广度未通过 / 成交未通过 | 31 | 周期成熟 |
| 3 | 交通运输 | O,S | 3 | 3 | 相对通过 / 广度未通过 / 成交通过 | 7 | 新激活 |

### 建筑装饰｜结构化证据审计

- 证据缺口/核对：类别：E,O,S（还缺0类）；主体：3/2（还缺0个）；独立URL：4/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-6.39%；排名第13；相对端点（旧→新）：2026-09-23=-0.59%；2026-10-08=+0.91%；2026-10-16=+0.96%；相对连续改善：是（相对门通过）；成交分位7.3%；成交占比（前期→本期）：1.180%→1.251%（成交门通过）；广度端点（旧→新）：2026-09-23=58.9%（覆盖99.3%）；2026-10-08=52.4%（覆盖100.0%）；2026-10-16=32.0%（覆盖100.0%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [中国电建：中国电力建设股份有限公司关于签署重大合同的公告](https://static.cninfo.com.cn/finalpage/2026-10-14/1225603143.PDF)；O / 中国电建；2026-10-14
  - [中国能建：中国能源建设股份有限公司重大工程中标公告](https://static.cninfo.com.cn/finalpage/2026-09-10/1225555700.PDF)；O / 中国能建；2026-09-10
  - [受益于全球AI算力基建扩容，腾景科技第三季度净利同比预增超六成 - 东方财富](https://news.google.com/rss/articles/CBMiZkFVX3lxTE1ZSHBUQkdfcEdXRk5BYkJxRTlhd1BnWEVnM1hyTDhCc25MNnlkQ0xINFI1UzQ1UDVBXzJ2eV82QTREbWgtZ0NwRWgzQ25PbTEtdG4tc2tZMldUM3pDMW1oVVpqZVVRZw?oc=5)；E / 基建；2026-10-16
  - [基建提速带动大宗商品仓储需求回暖\|库存\|品种\|百分点\|价格\|业务量 - finance.sina.com.cn](https://news.google.com/rss/articles/CBMieEFVX3lxTE9xN1d1RVcxYklHSnQtTTV6V2pwNDVFclhFdy1NekxqaHA0QXo4N3NrSG9MdE82NThvdzh2dlJTVTVLQXJ1QlFnQ2dnNlhvOEowSmFNeHBWWlZra3NlQ0F0ZmhPZGtOLW13TUE4UVhTeE9VaEpZQktkUw?oc=5)；S / 基建；2026-10-16

### 通信｜结构化证据审计

- 证据缺口/核对：类别：E,S（还缺0类）；主体：3/2（还缺0个）；独立URL：3/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-20.99%；排名第31；相对端点（旧→新）：2026-09-23=+8.14%；2026-10-08=-2.60%；2026-10-16=-13.64%；相对连续改善：否（相对门未通过）；成交分位71.2%；成交占比（前期→本期）：7.419%→6.465%（成交门未通过）；广度端点（旧→新）：2026-09-23=73.9%（覆盖98.3%）；2026-10-08=31.1%（覆盖98.3%）；2026-10-16=10.1%（覆盖98.3%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [亨通光电：前三季度净利润同比预增151%-168% 光通信市场需求增长、价格上涨 - 东方财富](https://news.google.com/rss/articles/CBMiYEFVX3lxTE9yRjFzZXlUdWl3QnBKMjhSNmZ3UE5lTDFvNDkzMng5M0lVakVDVVRTem94dkVEZVZLZFRVWVB3cTdqVHdzNFl4Zks1Y0dKcVU2b2VMWTc2c3hNOGxnUEllZw?oc=5)；E / 亨通光电；2026-10-16
  - [亨通光电：前三季度净利润同比预增151%-168% 光通信市场需求增长、价格上涨 - 东方财富](https://news.google.com/rss/articles/CBMiYEFVX3lxTE9yRjFzZXlUdWl3QnBKMjhSNmZ3UE5lTDFvNDkzMng5M0lVakVDVVRTem94dkVEZVZLZFRVWVB3cTdqVHdzNFl4Zks1Y0dKcVU2b2VMWTc2c3hNOGxnUEllZw?oc=5)；S / 亨通光电；2026-10-16
  - [数通光模块需求增长，光迅科技前三季度净利预增超六成，年内股价涨约90% - 东方财富](https://news.google.com/rss/articles/CBMiYEFVX3lxTE5RY2pJMHpYRHJHYUhRa3hwT1hLTjV4Sl8tYXpINnNMd2M3VVU5SFBtcWFvVzc4NWUxckRJOFVVUGRwWDdVbDBqc1VpTndhazM1d2VweTJ2RGljTHlzbF9aYw?oc=5)；E / 光迅科技；2026-10-15
  - [AI算力驱动光模块景气度上行 光库科技前三季度净利预增超1.4倍｜财报解读 - 财联社](https://news.google.com/rss/articles/CBMiSEFVX3lxTE5hRUJpWmYxUVJMdTh2cGlORmktbmNIQ2g3Nkw1eW1wV2JhdXRtclRrdEZQYkpvZXI5bWVfUXRMeFk4M052WHdJdQ?oc=5)；E / 光库科技；2026-10-15

### 交通运输｜结构化证据审计

- 证据缺口/核对：类别：O,S（还缺0类）；主体：3/2（还缺0个）；独立URL：3/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-3.00%；排名第7；相对端点（旧→新）：2026-09-23=-0.85%；2026-10-08=+5.04%；2026-10-16=+4.34%；相对连续改善：否（相对门通过）；成交分位50.5%；成交占比（前期→本期）：1.268%→1.590%（成交门通过）；广度端点（旧→新）：2026-09-23=64.3%（覆盖100.0%）；2026-10-08=67.5%（覆盖100.0%）；2026-10-16=54.8%（覆盖100.0%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [招商轮船：招商轮船关于下属全资子公司签署日常经营重大合同的公告](https://static.cninfo.com.cn/finalpage/2026-10-01/1225590002.PDF)；O / 招商轮船；2026-10-01
  - [双11叠加“反内卷”政策，义乌等多地快递掀新一轮涨价潮 - 东方财富](https://news.google.com/rss/articles/CBMiZkFVX3lxTE9sbWVzNUxFZ1E0T3FXa0dyaEdyQi1KYWMwSUxPeEp1Wjc2eWxvNHNjLTBSaGhiV1BmNGRqdzZIOGFyRGtqQmtNb0VJdS1XTmlnTTRRWGVxbzNtTkFxblNQSlh0UTdiUQ?oc=5)；S / 快递；2026-10-15
  - [中国蓝观察丨物流需求回暖，释放了什么信号？ - 新蓝网](https://news.google.com/rss/articles/CBMiT0FVX3lxTFBuX3cyS0FyTTZmTmlUa1duVm5RbG96X2l4Ull3eWVCOE9JRXNIWGZ2cWtfdnZZSVZIbjdWTzBqQnFmRkVoN29sVUVvX0R3RDQ?oc=5)；S / 物流；2026-10-12

## 行情领先但证据未闭环（近失配 Top 5）

排序依次考虑市场通过数、证据缺口、质量旗标、证据覆盖、20日排名和行业代码；同一快照结果固定。

### 1. 公用事业

- 行情：20日-1.73%、排名第4；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：S（还缺1类）；主体：1/2（还缺1个）；独立URL：2/2（还缺0个）；相反证据：无；质量旗标：无。
- 已绑定的部分claim：
  - [海关总署：中企为应对全球算力、电力需求增长提供坚实支撑\|固态硬盘\|风力发电\|国新办\|财联社\|充电宝 - 新浪财经](https://news.google.com/rss/articles/CBMi9wJBVV95cUxNbTFacGFqZ3JjWDBrM1pjWWpFeVVDNHhjOElfUDhlRlZacjlKV2NDRVN2LWdwWWw3SVVtbGtVRmV2bjlhUEcyQVVOMkxMb2tRWlM5Mm9fTHI2MGhfOTQydUROOHpNUk1Ic3hRWWhKcHloZlRoYkhER080MUp5a2NzSG43VzRieTJvYXNlckkyNnJyVWxtdDlYRUllSFNiMy1zLW1uX2FFS00zWXAzWFNib3lKYmptc2k1amREbDVoWU5iTmFDVDl0ZVl1RVV6ekMtRkpmaEtHakd5cW1aTzNKQklKdVBQVElzMEJvWVc2MS14VFkzRGYySXljMFF5TnREdG5KUWJGb3JPSTRXXzFnTnExTjY2dGNST0U3dnlYYzZ6RFcwcW5VUTE1Zk8wZ0Z3cE9ENHFvbWU5eUlMRFgyYTB0SjFVSGJYeGI2UjVjc3FfdDFjbUlJYmNwUEtuSnJSY05sc3R5VVZ6U3FrQlA2VXhqUmZQREE?oc=5)；S / 电力；2026-10-15
  - [海关总署：我国为应对全球算力和电力需求增长提供坚实的支撑 - 搜狐](https://news.google.com/rss/articles/CBMi1gFBVV95cUxQcXRZdWx6WG1iM0NrV3lFV21EOF9NWkY5aXdYRTZVUWZkemNFLVB5ZDlrYXIxVzRPSjNsWktBSlZEaXFqVVBNY1lwcm4tc0lIYjZOSHFtX1NVeERwY09oTDhZUXlVRnVFWWFaaVFtN0o4bktEdUN6endKRUNiOFhkeWZxVVpxeXR2a09LWmJrMVVJaVhVRU9oa1BTN3hCXzVIeHJaNzFDUnBQMjlOb1J2U1M4blZPeDBGUmhia0ZxUGVraFVqNkpqMGw1aWFldlN5WDNWRV9R?oc=5)；S / 电力；2026-10-14

### 2. 食品饮料

- 行情：20日+0.36%、排名第2；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：S（还缺1类）；主体：2/2（还缺0个）；独立URL：2/2（还缺0个）；相反证据：1条；质量旗标：SINGLE_COMPANY。
- 已绑定的部分claim：
  - [皇台酒业、金种子酒直线涨停！明年白酒需求或改善，关注这些机会 - 东方财富](https://news.google.com/rss/articles/CBMiZkFVX3lxTFA3dTAyQjUyMkpaZEtPeGtEbzRtbGZpcmpmRDhSU1Q3OVZLeFhReXFINEZabkdIenhNbi1rX2pVLUM2anczcGN4d044MlJDRmt4d0JfUHY0dEtVR0pZYWo2WTZ2X2p1UQ?oc=5)；S / 皇台酒业；2026-10-13
  - [受天气和运输受阻影响 粮农组织食品价格指数9月上涨 - UN News](https://news.google.com/rss/articles/CBMiV0FVX3lxTFBwaHAwbDFWcHVaYVNuVkJjTDdDX3BVNGJicjFLY1JFWWdQWS1KSkxQUXZZUHVNOTREaWJuRGRaYlpORnVzVi1DdmctTGdyYjBMT0xFNWxFbw?oc=5)；S / 食品；2026-10-02

### 3. 美容护理

- 行情：20日-2.01%、排名第5；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：S（还缺1类）；主体：2/2（还缺0个）；独立URL：1/2（还缺1个）；相反证据：无；质量旗标：SINGLE_COMPANY。
- 已绑定的部分claim：
  - [中信证券：中秋国庆假期出游需求或旺盛 关注美妆医美珠宝旺季 - 观点网](https://news.google.com/rss/articles/CBMiYkFVX3lxTE02RS1oMHJIM0lrbE1DSWsxMVBwV3BaQ3ZpUi1FaEl4UFNBUGYyVTM2cXZOREpTZzFzMC1xUDRzdEptamZpOXNwaThET1N1UkJISlFRZjd4WThxMTZnUVY3REl3?oc=5)；S / 美妆；2026-09-29
  - [中信证券：中秋国庆假期出游需求或旺盛 关注美妆医美珠宝旺季 - 观点网](https://news.google.com/rss/articles/CBMiYkFVX3lxTE02RS1oMHJIM0lrbE1DSWsxMVBwV3BaQ3ZpUi1FaEl4UFNBUGYyVTM2cXZOREpTZzFzMC1xUDRzdEptamZpOXNwaThET1N1UkJISlFRZjd4WThxMTZnUVY3REl3?oc=5)；S / 医美；2026-09-29

### 4. 传媒

- 行情：20日-4.06%、排名第10；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：E（还缺1类）；主体：2/2（还缺0个）；独立URL：3/2（还缺0个）；相反证据：3条；质量旗标：无。
- 已绑定的部分claim：
  - [广告收入增长28%，哔哩哔哩能否把内容优势变成利润优势？-证券之星 - 证券之星](https://news.google.com/rss/articles/CBMiXkFVX3lxTE96QWdWZDlyUU5rZnh3YUw2eDBFbk9UWUdwcEhvMkFqN2NlaUc0MGlMN01INTVnVWFVQXN1azdRQ3VqQUEySTBHcHlhVWYwWllsNkkzNzZ0NlNMclhva2c?oc=5)；E / 广告；2026-10-16
  - [欢聚25Q4财报：BIGO Ads收入同比增长61.5% 三方广告同比大增82.5% - 霞光社](https://news.google.com/rss/articles/CBMiSEFVX3lxTFBKb0I5N1VERzdTUHNISU1lYnN0X3hCMDdUMVlzOWVHWU1xN0duUkVzUG5CVVRvWHBtUTllRkRpaGhjdC1sNm5iWg?oc=5)；E / 广告；2026-10-15
  - [8月国内游戏市场收入316.27亿元 同比增长8.08% - 观点网](https://news.google.com/rss/articles/CBMiYkFVX3lxTE1GUW1GU2RteFpwdTBweFJJd1NiWEMwS0MyY3Y4QnF0N1JERC0xOEh5a19sMi1iZzc5RklLbUlSTU52RHlidEJ5ZFUydkk0akxZME1IZ3ZYR3htaFcwQ2d3RndR?oc=5)；E / 游戏；2026-09-30

### 5. 银行

- 行情：20日+2.52%、排名第1；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：O（还缺1类）；主体：1/2（还缺1个）；独立URL：1/2（还缺1个）；相反证据：无；质量旗标：SINGLE_COMPANY。
- 已绑定的部分claim：
  - [玉禾田与三家银行签署四份保证合同为子公司授信提供担保 - 观点网](https://news.google.com/rss/articles/CBMiYkFVX3lxTE0yUmhKVVF3N1RUOGYxNlE5UXBHTXVQY18xQXgxb2ZlUnE1ZmRpQkNOc0FWV2xkTngydnR2MWp1YVNYRklpblFzVG1qaFZQRHVFcUduSnlTWGtqWWFjQTZyMzln?oc=5)；O / 银行；2026-10-16

## 证据领先、市场尚未确认

本期无“证据PASS但市场少于两项确认”的非拥挤行业。

## 拥挤防追高

| 20日排名 | 行业 | 拥挤状态 | 触发原因 | 证据门 | 处理 |
|---:|---|---|---|---|---|
| 3 | 煤炭 | 周期成熟 | 本年已于2026-08-31触及E30 | WATCH | 禁止新增，不等于看空 |
| 11 | 石油石化 | 周期成熟 | 本年已于2026-03-03触及E30 | WATCH | 禁止新增，不等于看空 |
| 21 | 建筑材料 | 周期成熟 | 本年已于2026-06-16触及E30 | WATCH | 禁止新增，不等于看空 |
| 25 | 综合 | 周期成熟 | 本年已于2026-02-24触及E30 | WATCH | 禁止新增，不等于看空 |
| 29 | 电子 | 周期成熟 | 本年已于2026-05-07触及E30 | WATCH | 禁止新增，不等于看空 |
| 30 | 有色金属 | 周期成熟 | 本年已于2026-01-28触及E30 | WATCH | 禁止新增，不等于看空 |
| 31 | 通信 | 周期成熟 | 本年已于2026-04-17触及E30 | PASS | 禁止新增，不等于看空 |

## 前瞻激活账本

收益从信号后的下一共同交易日开盘代理计算；20/60日窗口未完成时不能提前判为成功或失败。修复回填样本不进入该分母。

| 信号日 | 行业 | 代理入场日 | 20日收益 / 排名 | 60日收益 / 排名 | 状态 |
|---|---|---|---|---|---|
| 2026-08-14 | 国防军工 | 2026-08-17 | +1.94% / 第7 | 未完成 | 20日已完成 |
| 2026-08-14 | 煤炭 | 2026-08-17 | +3.07% / 第4 | 未完成 | 20日已完成 |
| 2026-08-14 | 基础化工 | 2026-08-17 | -3.19% / 第20 | 未完成 | 20日已完成 |
| 2026-08-21 | 交通运输 | 2026-08-24 | +0.74% / 第14 | 未完成 | 20日已完成 |
| 2026-09-11 | 建筑装饰 | 2026-09-14 | 未完成 | 未完成 | 观察中 |
| 2026-09-11 | 社会服务 | 2026-09-14 | 未完成 | 未完成 | 观察中 |
| 2026-10-16 | 建筑装饰 | 待定 | 未完成 | 未完成 | 等待下一交易日 |
| 2026-10-16 | 交通运输 | 待定 | 未完成 | 未完成 | 等待下一交易日 |

### 持有确认观察（不进入新激活分母）

| 确认日 | 行业 | 代理起点 | 20日收益 / 排名 | 60日收益 / 排名 | 状态 |
|---|---|---|---|---|---|
| 2026-08-21 | 煤炭 | 2026-08-24 | -2.25% / 第26 | 未完成 | 20日已完成 |
| 2026-08-28 | 煤炭 | 2026-08-31 | -5.39% / 第25 | 未完成 | 20日已完成 |

### 已关闭周期

| 行业 | 激活日 | 关闭日 | 原因 |
|---|---|---|---|
| 基础化工 | 2026-08-14 | 2026-08-21 | 证据门失效 |
| 国防军工 | 2026-08-14 | 2026-08-21 | 证据门失效 |
| 交通运输 | 2026-08-21 | 2026-08-28 | 证据门失效 |
| 煤炭 | 2026-08-14 | 2026-09-11 | 本年已于2026-08-31触及E30 |
| 社会服务 | 2026-09-11 | 2026-09-18 | 证据门失效 |
| 建筑装饰 | 2026-09-11 | 2026-09-18 | 证据门失效 |

## 31行业完整附录

| 20日排名 | 行业 | 5日 | 20日 | 相对20日 | 成交分位 | 广度 | 市场通过数 | 证据门 | S/O/E | 主体 / URL | 拥挤 | 状态 |
|---:|---|---:|---:|---:|---:|---|---:|---|---|---|---|---|
| 1 | 银行 | +0.43% | +2.52% | +9.86% | 67.1% | 未计算 | 2 | WATCH | O | 1 / 1 | - | 证据观察 |
| 2 | 食品饮料 | +2.57% | +0.36% | +7.70% | 31.6% | 未计算 | 2 | WATCH | S | 2 / 2 | - | 证据观察 |
| 3 | 煤炭 | +1.43% | -1.32% | +6.03% | 59.1% | 未计算 | 2 | WATCH | E,S | 2 / 2 | 周期成熟 | 证据观察 |
| 4 | 公用事业 | -1.53% | -1.73% | +5.62% | 60.1% | 未计算 | 2 | WATCH | S | 1 / 2 | - | 证据观察 |
| 5 | 美容护理 | -1.12% | -2.01% | +5.33% | 48.9% | 未计算 | 2 | WATCH | S | 2 / 1 | - | 证据观察 |
| 6 | 房地产 | -6.27% | -2.36% | +4.98% | 34.5% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 7 | 交通运输 | -1.65% | -3.00% | +4.34% | 50.5% | 54.8% | 2 | PASS | O,S | 3 / 3 | - | 新激活 |
| 8 | 医药生物 | -4.63% | -3.85% | +3.50% | 70.9% | 未计算 | 1 | WATCH | S | 1 / 1 | - | 证据观察 |
| 9 | 家用电器 | -0.24% | -3.94% | +3.41% | 13.5% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 10 | 传媒 | +3.83% | -4.06% | +3.29% | 77.2% | 未计算 | 2 | WATCH | E | 2 / 3 | - | 证据观察 |
| 11 | 石油石化 | -1.02% | -5.45% | +1.90% | 64.2% | 未计算 | 2 | WATCH | S | 2 / 3 | 周期成熟 | 证据观察 |
| 12 | 纺织服饰 | -1.95% | -5.69% | +1.66% | 37.2% | 未计算 | 2 | WATCH | S | 1 / 1 | - | 证据观察 |
| 13 | 建筑装饰 | -2.15% | -6.39% | +0.96% | 7.3% | 32.0% | 2 | PASS | E,O,S | 3 / 4 | - | 新激活 |
| 14 | 非银金融 | +0.17% | -6.41% | +0.94% | 13.6% | 未计算 | 2 | WATCH | O | 1 / 1 | - | 证据观察 |
| 15 | 钢铁 | -1.66% | -6.75% | +0.60% | 11.4% | 未计算 | 2 | WATCH | E | 1 / 1 | - | 证据观察 |
| 16 | 轻工制造 | -4.15% | -7.35% | +0.00% | 35.7% | 未计算 | 0 | WATCH | S | 1 / 1 | - | 证据观察 |
| 17 | 计算机 | -2.80% | -8.50% | -1.15% | 6.5% | 未计算 | 1 | WATCH | O | 2 / 4 | - | 证据观察 |
| 18 | 汽车 | -4.22% | -9.03% | -1.68% | 15.5% | 未计算 | 0 | WATCH | O | 1 / 1 | - | 证据观察 |
| 19 | 国防军工 | -3.57% | -9.28% | -1.93% | 25.3% | 未计算 | 1 | WATCH | O,S | 2 / 3 | - | 证据观察 |
| 20 | 社会服务 | -3.50% | -9.81% | -2.47% | 18.9% | 未计算 | 0 | WATCH | S | 1 / 1 | - | 证据观察 |
| 21 | 建筑材料 | -7.19% | -9.91% | -2.56% | 85.8% | 未计算 | 0 | WATCH | E,S | 3 / 3 | 周期成熟 | 证据观察 |
| 22 | 商贸零售 | -2.12% | -10.02% | -2.68% | 28.2% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 23 | 环保 | -6.38% | -10.39% | -3.04% | 31.5% | 未计算 | 1 | WATCH | O | 3 / 4 | - | 证据观察 |
| 24 | 农林牧渔 | -1.34% | -10.63% | -3.28% | 94.4% | 未计算 | 0 | WATCH | - | 0 / 0 | - | 证据观察 |
| 25 | 综合 | -5.70% | -11.01% | -3.66% | 82.5% | 未计算 | 1 | WATCH | O | 1 / 1 | 周期成熟 | 证据观察 |
| 26 | 基础化工 | -6.31% | -12.58% | -5.23% | 77.5% | 未计算 | 1 | WATCH | E,S | 4 / 4 | - | 证据观察 |
| 27 | 电力设备 | -6.86% | -13.07% | -5.72% | 71.7% | 未计算 | 1 | WATCH | O,S | 3 / 3 | - | 证据观察 |
| 28 | 机械设备 | -7.84% | -16.42% | -9.07% | 33.9% | 未计算 | 0 | WATCH | - | 0 / 0 | - | 证据观察 |
| 29 | 电子 | -10.09% | -17.11% | -9.76% | 86.1% | 未计算 | 0 | WATCH | E,S | 4 / 4 | 周期成熟 | 证据观察 |
| 30 | 有色金属 | -5.31% | -17.22% | -9.88% | 44.8% | 未计算 | 1 | WATCH | E,S | 2 / 3 | 周期成熟 | 证据观察 |
| 31 | 通信 | -11.63% | -20.99% | -13.64% | 71.2% | 10.1% | 0 | PASS | E,S | 3 / 3 | 周期成熟 | 周期成熟 |

## 固定规则与数据限制

1. 硬证据PASS要求结构化claim覆盖S/O/E至少两类、两个独立主体、两个不同URL和两个事件簇，且至少一个主体为申万成分公司；标题候选本身不等于已采用证据。
2. 市场激活三选二：20日相对收益转正或持续改善；成分股站上60日均线比例连续两周上升；成交额占比上升且低于自身近三年85%分位。广度未计算时记为未知，不记失败。
3. 防追高任一命中即禁止新增：本年已触及E30；上年涨幅至少50%且当前20日前8；当前20日前3且涨幅至少15%。防追高不等于看空。
4. 证据与市场是两道独立门：WATCH即使行情领先也只能进入近失配，PASS但市场不足两项只能进入等待确认。
5. 候选新闻回看180日；claim仍受各字段TTL和报告截止时点约束。模型`codebuddy`只能分类冻结候选，不能补写事实。
6. 收盘后形成正式信号，下一共同交易日开盘仅作统一诊断代理；未计滑点、费用、涨跌停、容量和个股治理风险。
7. 每期冻结候选、结构化claim、行情派生值、状态、运行质量和哈希；修复回填或上游滞后样本不得混入前瞻统计。

行情来源：[申万指数官方数据](https://www.swsresearch.com/institute_sw/allIndex/releasedIndex)。

公开输入快照：[查看本期snapshot](./snapshots/2026-10-16.json)。
