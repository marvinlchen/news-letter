# A股产业领先信号周报｜2026-10-23

> 产业证据与市场确认分开审计。PASS不等于买入；行业指数不可直接交易；本报告不构成投资建议。

## 运行质量与本周动作

| 项目 | 结果 |
|---|---|
| 样本性质 | **正式前瞻样本** |
| 本周动作 | 按冻结规则发布；新增激活从下一共同交易日开盘代理记账。 |
| 观察窗口 | 2026-10-17 至 2026-10-23 |
| 行情应到 / 实到 | 2026-10-23 / 2026-10-23 |
| 策略版本 | `v0.2-F.2-pilot` |
| 证据引擎 | `rules-recovery-v1 @ 3b7088cc9288` |
| 候选 / claim / 采用引用 | 272 / 56 / 55 |
| 候选行业覆盖 | 30/31 |
| 语义利用率 | 20.2% |
| 新激活 / 持有确认 | 1 / 0 |
| 本次检查时间 | 2026-10-25T10:14:27+08:00 |
| 数据源错误 | 46 |
| 广度成分股请求 / 缓存命中 | 1531 / 1 |

数据源错误明细（最多3条，已清洗）：
- 801030/301565成分股日线失败: 301565成分股日线双源失败；腾讯: 腾讯sz301565缺少前复权日线（原始日线120条）；东财: Remote end closed connection without response
- 801030/603435成分股日线失败: 603435成分股日线双源失败；腾讯: 腾讯sh603435缺少前复权日线（原始日线104条）；东财: Remote end closed connection without response
- 801030/301688成分股日线失败: 301688成分股日线双源失败；腾讯: 腾讯sz301688缺少前复权日线（原始日线32条）；东财: Remote end closed connection without response

本周新增激活：计算机。

## 市场概览

| 指标 | 结果 |
|---|---|
| 20日上涨行业 | 3/31（其余未计算0） |
| 31行业20日中位数 | -4.36% |
| 防追高行业 | 7 |
| 广度未计算 | 26/31；未计算不视为失败 |
| 20日排名前三 | 食品饮料 +2.96%（第1）；美容护理 +1.95%（第2）；银行 +1.00%（第3） |

## 信号漏斗

| 阶段 | 行业数 | 说明 |
|---|---:|---|
| 有候选输入 | 30 | 共272条候选 |
| 硬证据PASS | 5 | 至少2类、2主体、2个独立URL、2个事件簇，且含成分公司 |
| 质量可用 | 5 | 少于2个质量旗标 |
| 排除拥挤后 | 3 | 不新增追逐成熟周期或短期急涨 |
| 市场三选二 | 1 | 未计算的广度不计通过、也不计失败 |
| 雷达 / 新激活 | 5 / 1 | 雷达上限8，新激活上限3 |

## 已通过证据门的雷达

| 雷达序号 | 行业 | S/O/E | 主体 | 独立URL | 市场三项 | 20日排名 | 状态 |
|---:|---|---|---:|---:|---|---:|---|
| 1 | 建筑装饰 | O,S | 3 | 4 | 相对未通过 / 广度未通过 / 成交通过 | 19 | 早期雷达（周期仍开） |
| 2 | 基础化工 | E,O,S | 4 | 4 | 相对未通过 / 广度未通过 / 成交未通过 | 24 | 早期雷达 |
| 3 | 计算机 | O,S | 3 | 4 | 相对通过 / 广度未通过 / 成交通过 | 9 | 新激活 |
| 4 | 电子 | E,S | 3 | 3 | 相对未通过 / 广度未通过 / 成交未通过 | 30 | 周期成熟 |
| 5 | 有色金属 | E,S | 2 | 2 | 相对未通过 / 广度未通过 / 成交未通过 | 29 | 周期成熟 |

### 建筑装饰｜结构化证据审计

- 证据缺口/核对：类别：O,S（还缺0类）；主体：3/2（还缺0个）；独立URL：4/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-6.07%；排名第19；相对端点（旧→新）：2026-10-08=+0.91%；2026-10-16=+0.96%；2026-10-23=-1.71%；相对连续改善：否（相对门未通过）；成交分位10.8%；成交占比（前期→本期）：1.251%→1.279%（成交门通过）；广度端点（旧→新）：2026-10-08=52.4%（覆盖100.0%）；2026-10-16=32.0%（覆盖100.0%）；2026-10-23=17.8%（覆盖99.3%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [中国电建：中国电力建设股份有限公司关于签署重大合同的公告](https://static.cninfo.com.cn/finalpage/2026-10-14/1225603143.PDF)；O / 中国电建；2026-10-14
  - [江河集团：江河集团关于重大工程中标的公告](https://static.cninfo.com.cn/finalpage/2026-10-09/1225597105.PDF)；O / 江河集团；2026-10-09
  - [科技需求出现回暖信号？德州仪器上调营收预期，IBM软件与基建订单恢复 港美股资讯 - 华盛通](https://news.google.com/rss/articles/CBMiYkFVX3lxTE5lWWFxOU9ISTB6QXhycEI2bEhkdURfSTVPNDZpY0lvenRORVlDbnJtU19xc2gzSV9UdnNsVkQ2dlVRWDBsNGZEQTEtbmxrWElFQVBKZWZGUl9Mc1RTYmtid0VB?oc=5)；S / 基建；2026-10-22
  - [中东基建需求外溢多家中国公司斩获订单\|穆罕默德·本·萨勒曼\|中国电建\|方大集团\|江河集团\|德才股份_手机新浪网 - ZAKER新闻](https://news.google.com/rss/articles/CBMid0FVX3lxTE5xVms2RDBNU2tSYUh4b0UtZUMtdEplLVNJMGhZUjczYnlTYS1CZTJwS3hTbGpKSFNJVjlMOWNaOWJnOVVkUG1YZGJZR0FUOS1FODhOM21QbzFuNm0wLS0wZ0tPR2xZb0dhT2RtdlBiWEtkODAzcjRr?oc=5)；O / 中国电建；2026-10-21

### 基础化工｜结构化证据审计

- 证据缺口/核对：类别：E,O,S（还缺0类）；主体：4/2（还缺0个）；独立URL：4/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-10.71%；排名第24；相对端点（旧→新）：2026-10-08=-1.66%；2026-10-16=-5.23%；2026-10-23=-6.35%；相对连续改善：否（相对门未通过）；成交分位53.0%；成交占比（前期→本期）：5.452%→4.559%（成交门未通过）；广度端点（旧→新）：2026-10-08=52.3%（覆盖98.8%）；2026-10-16=22.3%（覆盖99.0%）；2026-10-23=11.3%（覆盖99.0%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [宝丰能源：宁夏宝丰能源集团股份有限公司2026年半年度业绩预增公告](https://static.cninfo.com.cn/finalpage/2026-07-14/1225420709.PDF)；E / 宝丰能源；2026-07-14
  - [万华化学：万华化学2026年半年度业绩预增公告](https://static.cninfo.com.cn/finalpage/2026-07-07/1225411166.PDF)；E / 万华化学；2026-07-07
  - [记者走市场丨轮胎厂家集体涨价 零售市场价格如何？ - 河北广播电视台](https://news.google.com/rss/articles/CBMiakFVX3lxTE5rZlJNb1ZXQXpyVkZtS2ViZE96dGU2MEVCR0x2YUcwcW11TW01TWJtV0Q4V21acnM4d2ROSU9uaVZFU0FFX3piYWVtbmdFX2pGRWlTSEtOUFhJYUdaUnBBcmMzZzNuQUdkbnc?oc=5)；S / 轮胎；2026-10-21
  - [迪尔化工：中标约2.44亿元光热项目熔盐采购项目 - 东方财富](https://news.google.com/rss/articles/CBMiZkFVX3lxTFBNYVVLUVlLX3BJMkVIRnFhZ1VqYXM4RlRpUlBXX0ZteXp0U1F2cDJhTDJGVnJPS1otRFhWZ1dxUzJMN2xnak9TazE3R1B2dHV3Vkh2N3dUeXlSVGp2WkVicG1vb2FPQQ?oc=5)；O / 化工；2026-10-21

### 计算机｜结构化证据审计

- 证据缺口/核对：类别：O,S（还缺0类）；主体：3/2（还缺0个）；独立URL：4/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-1.60%；排名第9；相对端点（旧→新）：2026-10-08=-4.83%；2026-10-16=-1.15%；2026-10-23=+2.76%；相对连续改善：是（相对门通过）；成交分位14.3%；成交占比（前期→本期）：4.899%→5.850%（成交门通过）；广度端点（旧→新）：2026-10-08=34.8%（覆盖98.2%）；2026-10-16=24.4%（覆盖98.2%）；2026-10-23=34.1%（覆盖98.2%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [科技需求出现回暖信号？德州仪器上调营收预期，IBM软件与基建订单恢复 港美股资讯 - 华盛通](https://news.google.com/rss/articles/CBMiYkFVX3lxTE5lWWFxOU9ISTB6QXhycEI2bEhkdURfSTVPNDZpY0lvenRORVlDbnJtU19xc2gzSV9UdnNsVkQ2dlVRWDBsNGZEQTEtbmxrWElFQVBKZWZGUl9Mc1RTYmtid0VB?oc=5)；S / 软件；2026-10-22
  - [硬件涨价周期下，超融合软件模式为何更有韧性 - 搜狐](https://news.google.com/rss/articles/CBMiiAFBVV95cUxNZkJieWdHMm1wV2J4VDJubkxBMjJoUWZfMzBzejdSdkN3YzRnbDNrVTRhbklWLWt1OFR0dG90X1g2TTUzRWFwMVV4Ul9seUVpc19rNDhXZXFwZ3dzUXBIU3J3WFVqbnBhUjh2ZjdPaGthLWRYTVJncXJmc05VampITjhOSDJZbzlh?oc=5)；S / 软件；2026-10-20
  - [远光软件中标中国华能融资系统建设项目 - 凤凰网财经](https://news.google.com/rss/articles/CBMiUEFVX3lxTFBTSjVWN19hQ3FXbzBHU3RxdFpZRWlPMEdqNlFXZnpjVDJxMTdTUDRDT0RJUnRUdVJHTExnUktfbmkwQ2gzNE9xTmZHcmlya1FS?oc=5)；O / 远光软件；2026-10-21
  - [宝信软件中标金钼集团智能化工厂建设EPC项目 - 中国有色网](https://news.google.com/rss/articles/CBMiXEFVX3lxTE4xVVVsajN2VmZlaXhfMlctaGFmSkFIV3FpN254NlVfcUR5OEJjN0VZMnRmQ0taTkxSN3pEYThGQ2RkN1ZDYnFYRHFUenRZeVhDVGhpckNzTjZQTnFT?oc=5)；O / 宝信软件；2026-09-30

### 电子｜结构化证据审计

- 证据缺口/核对：类别：E,S（还缺0类）；主体：3/2（还缺0个）；独立URL：3/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-18.84%；排名第30；相对端点（旧→新）：2026-10-08=-4.16%；2026-10-16=-9.76%；2026-10-23=-14.48%；相对连续改善：否（相对门未通过）；成交分位88.0%；成交占比（前期→本期）：23.322%→24.628%（成交门未通过）；广度端点（旧→新）：2026-10-08=27.9%（覆盖93.2%）；2026-10-16=11.7%（覆盖93.0%）；2026-10-23=16.2%（覆盖93.2%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [高端PCB需求旺盛，深南电路Q3营收同比增66%、净利大增94%｜财报见闻 - 华尔街见闻](https://news.google.com/rss/articles/CBMiU0FVX3lxTE1remhtSDROcTUtci1hSlF1WW92X0o1bnRmMEdQUjFGU01oRXJ6OEloRmtoLVJ5N3F4akk2MjBGbjYwWGRId1d6VHFteEhxTnRjQ25F?oc=5)；E / 深南电路；2026-10-22
  - [国科微年内第二次上调合封KGD存储产品价格，11月起按美元绝对值提价 - 电子工程专辑](https://news.google.com/rss/articles/CBMiXEFVX3lxTE85NHhNQ09KRjZuZjl1Z3JuWlJxTTREX2JuY3hpVzliMndoYi15OUN4b1R5SjRDdzBvWi1XakJpeEM0QlBHMTI1bmFkbVpiUVhIQWFITEdCaUF0WnA2?oc=5)；S / 国科微；2026-10-23
  - [高端PCB需求大幅增长 东威科技前三季度净利润增长91% - 东方财富](https://news.google.com/rss/articles/CBMiZkFVX3lxTE1tMmtFSGM3MWFDYldYWkhKLU13SnJyTm9EdFVxXzU0eTBKc0haOER2enplRWUtV2d1U0pPdWtKbDkzVVZVT3J1eXhuTVFrOFFiNk1YOVZDT3gwcC00QXFseFRIMThjQQ?oc=5)；E / PCB；2026-10-23

### 有色金属｜结构化证据审计

- 证据缺口/核对：类别：E,S（还缺0类）；主体：2/2（还缺0个）；独立URL：2/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-15.17%；排名第29；相对端点（旧→新）：2026-10-08=-7.02%；2026-10-16=-9.88%；2026-10-23=-10.81%；相对连续改善：否（相对门未通过）；成交分位38.6%；成交占比（前期→本期）：4.246%→3.985%（成交门未通过）；广度端点（旧→新）：2026-10-08=19.6%（覆盖97.9%）；2026-10-16=5.8%（覆盖97.9%）；2026-10-23=5.1%（覆盖97.9%）；广度连续改善：否（广度门未通过）。
- 已绑定的部分claim：
  - [北方稀土：北方稀土2026年前三季度业绩预增公告](https://static.cninfo.com.cn/finalpage/2026-10-13/1225601284.PDF)；E / 北方稀土；2026-10-13
  - [金属价格上涨驱动，紫金矿业Q3归母净利润同比增长25.97% \| 财报见闻 - 华尔街见闻](https://news.google.com/rss/articles/CBMiU0FVX3lxTE9GMmxnNUVTLWFCcTZyem40SFBhZV9CbEJiT2gyQzh2MEZraDNvYWFuWmtxMkRkYk1oWEo0VTMyZDIzTDZkZXlsXzhyMDFpdDJTUmFF?oc=5)；E / 紫金矿业；2026-10-23
  - [金属价格上涨驱动，紫金矿业Q3归母净利润同比增长25.97% \| 财报见闻 - 华尔街见闻](https://news.google.com/rss/articles/CBMiU0FVX3lxTE9GMmxnNUVTLWFCcTZyem40SFBhZV9CbEJiT2gyQzh2MEZraDNvYWFuWmtxMkRkYk1oWEo0VTMyZDIzTDZkZXlsXzhyMDFpdDJTUmFF?oc=5)；S / 紫金矿业；2026-10-23

## 行情领先但证据未闭环（近失配 Top 5）

排序依次考虑市场通过数、证据缺口、质量旗标、证据覆盖、20日排名和行业代码；同一快照结果固定。

### 1. 银行

- 行情：20日+1.00%、排名第3；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：O（还缺1类）；主体：2/2（还缺0个）；独立URL：2/2（还缺0个）；相反证据：无；质量旗标：OCF_WEAK。
- 已绑定的部分claim：
  - [深业运营中标宁波银行深圳分行物业服务项目 覆盖本部及22家支行 - finance.sina.com.cn](https://news.google.com/rss/articles/CBMilwFBVV95cUxPblpHSXpjQklCX0RvU01JUklUNGctdjNxSTRFTXFCMThWcjUtYTZjUTZsLTIxRlJtY2VZT2dtbzRjTTh2YnRCTGxwY05rLVBhWW1yaE9YYVhESUhYRHBXOHpzd0E4aGlpUFd0NjZmb2xnNnd1azVYVUpJcVdrTXlyQ0xRUGMyQ0xNRnlCTzBEdzJHT3NMZlpn?oc=5)；O / 宁波银行；2026-10-22
  - [玉禾田与三家银行签署四份保证合同为子公司授信提供担保 - 观点网](https://news.google.com/rss/articles/CBMiYkFVX3lxTE0yUmhKVVF3N1RUOGYxNlE5UXBHTXVQY18xQXgxb2ZlUnE1ZmRpQkNOc0FWV2xkTngydnR2MWp1YVNYRklpblFzVG1qaFZQRHVFcUduSnlTWGtqWWFjQTZyMzln?oc=5)；O / 银行；2026-10-16

### 2. 家用电器

- 行情：20日-1.54%、排名第8；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：O（还缺1类）；主体：2/2（还缺0个）；独立URL：2/2（还缺0个）；相反证据：无；质量旗标：ONE_OFF_OR_LOW_BASE。
- 已绑定的部分claim：
  - [喜报\|\|格力中央空调中标前海合作区区域集中供冷4号冷站(二期)设备工程项目 - 新浪财经](https://news.google.com/rss/articles/CBMieEFVX3lxTFB1aVZZd2VqOGZzRVJUUkYzcTVVYkFhb0phakFONklrMEJRZWJaQXNyNWU0R1BRbEYwMERQRnNWajU4akJSdjVJQlJWSUFGLXZQUDNwbTVzeUY4ZlFkaUZFQ1ZWaldpUGE2bkxqc1I5RGhqR3FYbUpIcw?oc=5)；O / 空调；2026-10-22
  - [广交会观察：智能家电“智”造吸睛 海外订单持续增长 - 中新经纬](https://news.google.com/rss/articles/CBMiZEFVX3lxTE5MMWNEQUoxcnRxT3puRVgxbllTeldkLTlpSzI3aUxHTW83SmxqQkRqOGR3MnpyT1Z6cHRoRDFQWTB4THJFdVd5dlJONnluYUNEMTlKLWp0cEs3bGlHV2FVVEQ1OHU?oc=5)；O / 家电；2026-10-19

### 3. 食品饮料

- 行情：20日+2.96%、排名第1；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：无（还缺2类）；主体：0/2（还缺2个）；独立URL：0/2（还缺2个）；相反证据：无；质量旗标：无。
- 未被证据门采用的候选标题（最多2条）：
  - [农产品等成立深微食品供应链公司 - 东方财富](https://news.google.com/rss/articles/CBMiY0FVX3lxTFBCWFlmMXk3RE5oa2FCTExDQnprenY2M2Rhc0VFekpiVm9GNmQyUUN5MWpMMmlJcnpNbW05YlNiRnFLTmt2b084Q3hob0prZFpndXRhYUpROFVjSFMzbXJWeHdqbw?oc=5)（2026-10-23）
  - [日本9月食品价格同比涨2.8% 创2022年2月以来最慢增速_环球股市 - 证券之星](https://news.google.com/rss/articles/CBMiYEFVX3lxTE9kcE5Wb1Rrcmw0ak4zTWZBY3VOblpGdlg1WmJ6dHpXZVM4d1lvajNvLVRNZDNDb211Y3h1YXNDd1IxbGFzckc1NkhQTUpieVpZd0VnalEtaGpqODBRVEgwaw?oc=5)（2026-10-23）

### 4. 汽车

- 行情：20日-3.70%、排名第15；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：无（还缺2类）；主体：0/2（还缺2个）；独立URL：0/2（还缺2个）；相反证据：无；质量旗标：无。
- 未被证据门采用的候选标题（最多2条）：
  - [2026中国汽车供应链大会在开封举行 - 新华网客户端](https://news.google.com/rss/articles/CBMimgFBVV95cUxQWHpnVkZqNkdNTlVKRlNqMTFXZmhjdUhTcmw0eGMyTURKUmJJRGx6eHhVb3Blc2hMWDk5U1BtOWhqemdrTkJaRDU0S2hQR3JHNjRmQlJ4R1duaU1Ud1FnbFIxTEZSZVJEZzUzQzRmWWExT3plaENBb2RGdDVVcGY2LWUxU0xYRElfei1iQjI2UE5FVkVlWXpJMkp3?oc=5)（2026-10-23）
  - [中国汽车驶向中亚：当地需求变了，产业合作也在加深 - 观察者网](https://news.google.com/rss/articles/CBMiYkFVX3lxTE8xZ2tGdjNuaXIwYVFfRUJBelZUVHVCX2RfOTlkS2VMdnRxZWxWUmFYb0dacGViZTZRXzNIQXY2Q2dwend3QzBHc1VYN0xNSGZlY0dPelBra21QOXlJeWcxSlpn?oc=5)（2026-10-23）

## 证据领先、市场尚未确认

| 行业 | S/O/E | 主体 / URL | 市场三项 | 处理 |
|---|---|---|---|---|
| 基础化工 | E,O,S | 4 / 4 | 相对未通过 / 广度未通过 / 成交未通过 | 继续观察，不提前激活 |
| 建筑装饰 | O,S | 3 / 4 | 相对未通过 / 广度未通过 / 成交通过 | 继续观察，不提前激活 |

## 拥挤防追高

| 20日排名 | 行业 | 拥挤状态 | 触发原因 | 证据门 | 处理 |
|---:|---|---|---|---|---|
| 5 | 石油石化 | 周期成熟 | 本年已于2026-03-03触及E30 | WATCH | 禁止新增，不等于看空 |
| 7 | 煤炭 | 周期成熟 | 本年已于2026-08-31触及E30 | WATCH | 禁止新增，不等于看空 |
| 25 | 综合 | 周期成熟 | 本年已于2026-02-24触及E30 | WATCH | 禁止新增，不等于看空 |
| 28 | 建筑材料 | 周期成熟 | 本年已于2026-06-16触及E30 | WATCH | 禁止新增，不等于看空 |
| 29 | 有色金属 | 周期成熟 | 本年已于2026-01-28触及E30 | PASS | 禁止新增，不等于看空 |
| 30 | 电子 | 周期成熟 | 本年已于2026-05-07触及E30 | PASS | 禁止新增，不等于看空 |
| 31 | 通信 | 周期成熟 | 本年已于2026-04-17触及E30 | WATCH | 禁止新增，不等于看空 |

## 前瞻激活账本

收益从信号后的下一共同交易日开盘代理计算；20/60日窗口未完成时不能提前判为成功或失败。修复回填样本不进入该分母。

| 信号日 | 行业 | 代理入场日 | 20日收益 / 排名 | 60日收益 / 排名 | 状态 |
|---|---|---|---|---|---|
| 2026-08-14 | 国防军工 | 2026-08-17 | +1.94% / 第7 | 未完成 | 20日已完成 |
| 2026-08-14 | 煤炭 | 2026-08-17 | +3.07% / 第4 | 未完成 | 20日已完成 |
| 2026-08-14 | 基础化工 | 2026-08-17 | -3.19% / 第20 | 未完成 | 20日已完成 |
| 2026-08-21 | 交通运输 | 2026-08-24 | +0.74% / 第14 | 未完成 | 20日已完成 |
| 2026-09-11 | 建筑装饰 | 2026-09-14 | -4.71% / 第17 | 未完成 | 20日已完成 |
| 2026-09-11 | 社会服务 | 2026-09-14 | -6.66% / 第21 | 未完成 | 20日已完成 |
| 2026-10-16 | 建筑装饰 | 2026-10-19 | 未完成 | 未完成 | 观察中 |
| 2026-10-16 | 交通运输 | 2026-10-19 | 未完成 | 未完成 | 观察中 |
| 2026-10-23 | 计算机 | 待定 | 未完成 | 未完成 | 等待下一交易日 |

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
| 交通运输 | 2026-10-16 | 2026-10-23 | 证据门失效 |

## 31行业完整附录

| 20日排名 | 行业 | 5日 | 20日 | 相对20日 | 成交分位 | 广度 | 市场通过数 | 证据门 | S/O/E | 主体 / URL | 拥挤 | 状态 |
|---:|---|---:|---:|---:|---:|---|---:|---|---|---|---|---|
| 1 | 食品饮料 | -0.56% | +2.96% | +7.32% | 39.6% | 未计算 | 2 | WATCH | - | 0 / 0 | - | 证据观察 |
| 2 | 美容护理 | -0.47% | +1.95% | +6.31% | 41.0% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 3 | 银行 | -1.58% | +1.00% | +5.36% | 73.1% | 未计算 | 2 | WATCH | O | 2 / 2 | - | 证据观察 |
| 4 | 传媒 | -0.53% | -0.31% | +4.05% | 70.9% | 未计算 | 1 | WATCH | E | 2 / 3 | - | 证据观察 |
| 5 | 石油石化 | -1.54% | -0.67% | +3.69% | 50.7% | 未计算 | 1 | WATCH | - | 0 / 0 | 周期成熟 | 证据观察 |
| 6 | 医药生物 | +0.75% | -1.27% | +3.09% | 58.1% | 未计算 | 1 | WATCH | S | 1 / 2 | - | 证据观察 |
| 7 | 煤炭 | -4.12% | -1.41% | +2.95% | 38.6% | 未计算 | 1 | WATCH | E,S | 2 / 2 | 周期成熟 | 证据观察 |
| 8 | 家用电器 | +0.44% | -1.54% | +2.82% | 34.1% | 未计算 | 2 | WATCH | O | 2 / 2 | - | 证据观察 |
| 9 | 计算机 | +5.21% | -1.60% | +2.76% | 14.3% | 34.1% | 2 | PASS | O,S | 3 / 4 | - | 新激活 |
| 10 | 房地产 | -3.61% | -2.05% | +2.31% | 10.8% | 未计算 | 1 | WATCH | E,O,S | 3 / 3 | - | 证据观察 |
| 11 | 农林牧渔 | -0.40% | -2.24% | +2.11% | 75.5% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 12 | 交通运输 | -2.90% | -2.86% | +1.50% | 27.5% | 未计算 | 1 | WATCH | E | 1 / 1 | - | 证据观察 |
| 13 | 纺织服饰 | -1.66% | -3.56% | +0.80% | 22.5% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 14 | 公用事业 | -1.99% | -3.70% | +0.66% | 43.9% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 15 | 汽车 | +1.51% | -3.70% | +0.66% | 23.1% | 未计算 | 2 | WATCH | - | 0 / 0 | - | 证据观察 |
| 16 | 商贸零售 | -0.94% | -4.36% | +0.00% | 17.2% | 未计算 | 0 | WATCH | - | 0 / 0 | - | 证据观察 |
| 17 | 非银金融 | -1.32% | -4.43% | -0.07% | 16.1% | 未计算 | 1 | WATCH | O,S | 2 / 2 | - | 证据观察 |
| 18 | 钢铁 | -2.56% | -5.11% | -0.75% | 2.8% | 未计算 | 0 | WATCH | S | 1 / 1 | - | 证据观察 |
| 19 | 建筑装饰 | -2.50% | -6.07% | -1.71% | 10.8% | 17.8% | 1 | PASS | O,S | 3 / 4 | - | 早期雷达（周期仍开） |
| 20 | 社会服务 | -1.87% | -6.28% | -1.92% | 14.9% | 未计算 | 0 | WATCH | E | 2 / 3 | - | 证据观察 |
| 21 | 国防军工 | +0.32% | -6.81% | -2.45% | 41.1% | 未计算 | 1 | WATCH | O | 2 / 2 | - | 证据观察 |
| 22 | 轻工制造 | -2.43% | -6.81% | -2.45% | 22.8% | 未计算 | 0 | WATCH | S | 1 / 1 | - | 证据观察 |
| 23 | 环保 | -1.76% | -9.26% | -4.90% | 2.2% | 未计算 | 0 | WATCH | O | 3 / 3 | - | 证据观察 |
| 24 | 基础化工 | -1.74% | -10.71% | -6.35% | 53.0% | 11.3% | 0 | PASS | E,O,S | 4 / 4 | - | 早期雷达 |
| 25 | 综合 | -4.12% | -11.13% | -6.77% | 41.4% | 未计算 | 0 | WATCH | O | 1 / 1 | 周期成熟 | 证据观察 |
| 26 | 机械设备 | +3.01% | -11.77% | -7.41% | 75.9% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 27 | 电力设备 | -3.54% | -13.08% | -8.72% | 54.5% | 未计算 | 0 | WATCH | O | 2 / 3 | - | 证据观察 |
| 28 | 建筑材料 | -2.21% | -14.26% | -9.90% | 78.8% | 未计算 | 0 | WATCH | E,S | 2 / 3 | 周期成熟 | 证据观察 |
| 29 | 有色金属 | -2.25% | -15.17% | -10.81% | 38.6% | 5.1% | 0 | PASS | E,S | 2 / 2 | 周期成熟 | 周期成熟 |
| 30 | 电子 | +0.15% | -18.84% | -14.48% | 88.0% | 16.2% | 0 | PASS | E,S | 3 / 3 | 周期成熟 | 周期成熟 |
| 31 | 通信 | -3.60% | -24.77% | -20.41% | 82.8% | 未计算 | 1 | WATCH | E,O,S | 2 / 4 | 周期成熟 | 证据观察 |

## 固定规则与数据限制

1. 硬证据PASS要求结构化claim覆盖S/O/E至少两类、两个独立主体、两个不同URL和两个事件簇，且至少一个主体为申万成分公司；标题候选本身不等于已采用证据。
2. 市场激活三选二：20日相对收益转正或持续改善；成分股站上60日均线比例连续两周上升；成交额占比上升且低于自身近三年85%分位。广度未计算时记为未知，不记失败。
3. 防追高任一命中即禁止新增：本年已触及E30；上年涨幅至少50%且当前20日前8；当前20日前3且涨幅至少15%。防追高不等于看空。
4. 证据与市场是两道独立门：WATCH即使行情领先也只能进入近失配，PASS但市场不足两项只能进入等待确认。
5. 候选新闻回看180日；claim仍受各字段TTL和报告截止时点约束。模型`codebuddy`只能分类冻结候选，不能补写事实。
6. 收盘后形成正式信号，下一共同交易日开盘仅作统一诊断代理；未计滑点、费用、涨跌停、容量和个股治理风险。
7. 每期冻结候选、结构化claim、行情派生值、状态、运行质量和哈希；修复回填或上游滞后样本不得混入前瞻统计。

行情来源：[申万指数官方数据](https://www.swsresearch.com/institute_sw/allIndex/releasedIndex)。

公开输入快照：[查看本期snapshot](./snapshots/2026-10-23.json)。
