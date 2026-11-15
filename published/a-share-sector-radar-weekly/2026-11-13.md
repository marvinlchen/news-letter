# A股产业领先信号周报｜2026-11-13

> 产业证据与市场确认分开审计。PASS不等于买入；行业指数不可直接交易；本报告不构成投资建议。

## 运行质量与本周动作

| 项目 | 结果 |
|---|---|
| 样本性质 | **正式前瞻样本** |
| 本周动作 | 按冻结规则发布；新增激活从下一共同交易日开盘代理记账。 |
| 观察窗口 | 2026-11-07 至 2026-11-13 |
| 行情应到 / 实到 | 2026-11-13 / 2026-11-13 |
| 策略版本 | `v0.2-F.2-pilot` |
| 证据引擎 | `rules-recovery-v1 @ 3b7088cc9288` |
| 候选 / claim / 采用引用 | 214 / 47 / 45 |
| 候选行业覆盖 | 31/31 |
| 语义利用率 | 21.0% |
| 新激活 / 持有确认 | 0 / 0 |
| 本次检查时间 | 2026-11-15T10:48:10+08:00 |
| 数据源错误 | 1 |
| 广度成分股请求 / 缓存命中 | 122 / 0 |

数据源错误明细（最多3条，已清洗）：
- 801770/301718成分股日线失败: 301718成分股日线双源失败；腾讯: 腾讯sz301718缺少前复权日线（原始日线17条）；东财: 东财301718有效日线不足60条: 17

本周没有候选同时通过证据、质量、防追高与市场三选二，不为凑数激活。

## 市场概览

| 指标 | 结果 |
|---|---|
| 20日上涨行业 | 6/31（其余未计算0） |
| 31行业20日中位数 | -3.74% |
| 防追高行业 | 7 |
| 广度未计算 | 30/31；未计算不视为失败 |
| 20日排名前三 | 食品饮料 +5.05%（第1）；传媒 +4.60%（第2）；家用电器 +4.08%（第3） |

## 信号漏斗

| 阶段 | 行业数 | 说明 |
|---|---:|---|
| 有候选输入 | 31 | 共214条候选 |
| 硬证据PASS | 1 | 至少2类、2主体、2个独立URL、2个事件簇，且含成分公司 |
| 质量可用 | 1 | 少于2个质量旗标 |
| 排除拥挤后 | 0 | 不新增追逐成熟周期或短期急涨 |
| 市场三选二 | 0 | 未计算的广度不计通过、也不计失败 |
| 雷达 / 新激活 | 1 / 0 | 雷达上限8，新激活上限3 |

## 已通过证据门的雷达

| 雷达序号 | 行业 | S/O/E | 主体 | 独立URL | 市场三项 | 20日排名 | 状态 |
|---:|---|---|---:|---:|---|---:|---|
| 1 | 通信 | O,S | 4 | 3 | 相对通过 / 广度通过 / 成交未通过 | 31 | 周期成熟 |

### 通信｜结构化证据审计

- 证据缺口/核对：类别：O,S（还缺0类）；主体：4/2（还缺0个）；独立URL：3/2（还缺0个）；相反证据：无；质量旗标：无。
- 市场核对：20日收益-20.75%；排名第31；相对端点（旧→新）：2026-10-30=-27.57%；2026-11-06=-26.51%；2026-11-13=-17.01%；相对连续改善：是（相对门通过）；成交分位86.1%；成交占比（前期→本期）：6.671%→7.760%（成交门未通过）；广度端点（旧→新）：2026-10-30=5.0%（覆盖99.2%）；2026-11-06=12.4%（覆盖99.2%）；2026-11-13=14.0%（覆盖99.2%）；广度连续改善：是（广度门通过）。
- 已绑定的部分claim：
  - [新易盛：订单交付需求持续增长 1.6T光模块进入持续放量阶段 - 东方财富](https://news.google.com/rss/articles/CBMiZkFVX3lxTE9kQXVMZHV6V3hjSWZBajUySTdEbXV0bUplRGJ4RDY0OXN0UGZsaGdLckZJSHR4dnhXUkUxQW0yRXVWUjR4SHNfQkNHWXhVNUttQWdWUmNLSVQzeW1UTUhNZEMzLWhyQQ?oc=5)；O / 新易盛；2026-11-12
  - [新易盛：订单交付需求持续增长 1.6T光模块进入持续放量阶段 - 东方财富](https://news.google.com/rss/articles/CBMiZkFVX3lxTE9kQXVMZHV6V3hjSWZBajUySTdEbXV0bUplRGJ4RDY0OXN0UGZsaGdLckZJSHR4dnhXUkUxQW0yRXVWUjR4SHNfQkNHWXhVNUttQWdWUmNLSVQzeW1UTUhNZEMzLWhyQQ?oc=5)；S / 光模块；2026-11-12
  - [中国联通手机直连卫星试验星项目，公示中标候选人 - C114通信网](https://news.google.com/rss/articles/CBMiUEFVX3lxTE5YWGFKQWJlUjhxSEp5c2RQcUJhUF9LZklhcnB2VUtxLTc5V2NlVXNERVFMaHp6bm5TaVlYOXh6SGZtYkpMRDloWDVOUWEyVWRV?oc=5)；O / 中国联通；2026-11-13
  - [从全球AI需求增长，解读中国数据中心市场的变与不变 - IDC \| Trusted Tech Intelligence](https://news.google.com/rss/articles/CBMi3wJBVV95cUxOSXU1WnQwNVhja19zeDlMck1MeHZMWldGNE40c20wVEZ4MjVqaVJzUEw2N1AxaG15SUVWenh2cG5URHZ4RlY2SkNVa0loQVU5NEM4ak5aY1VkNHFmaVFRbjRKTXNfVEt5NkNSeHl2eFBqNmhnQUJsNENHMEpwTlR4aVdjNFpQZEZQQTA2bTdNMTh1TmxVOW9jcW1hNW1RbUlxbkktalZYTWJiS1o1Q3Jib0ZLVmlCaHdVSzJGVG1hT2Rrby1vTDdPekRKaVdVcndyYWFuM0FfVDlWSlZnT3E5bmZFRm1MT2NVWFdXUGxHcUhKNmZva0Fhd3hQd1F3emIxUEk1SmktNEdTc0swM0hEOGtUaEh3Tmpqd2ZjanFrbGdWWV9YdmlmNjBBNXdqcUNSTGNOZVNGbjc3M1RHdEdBSkdUWEw1eTdOS1hFbWpWczM0czg4RGc4WTJkcHQ0VU0?oc=5)；S / 数据中心；2026-11-11

## 行情领先但证据未闭环（近失配 Top 5）

排序依次考虑市场通过数、证据缺口、质量旗标、证据覆盖、20日排名和行业代码；同一快照结果固定。

### 1. 轻工制造

- 行情：20日-3.74%、排名第16；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：O,S（还缺0类）；主体：2/2（还缺0个）；独立URL：3/2（还缺0个）；相反证据：无；质量旗标：ONE_OFF_OR_LOW_BASE,SINGLE_COMPANY。
- 已绑定的部分claim：
  - [纸托盘用木材市场展望2035：可持续包装需求支撑增长 - 新闻和统计 - IndexBox](https://news.google.com/rss/articles/CBMi0AFBVV95cUxQNDV5WmgtREMwOVl2YVFwdVZ4eF9CeGpJOXI3bDJrajhYQUY2eko1dFNNUHZ6UmxYVGFndVdrWmxkY1hDR2hfSzdZU3B0LTFPNEhlOFhzNy1rdkk4bkJRT1JXemR6QlYyYWszMG5kaGVLbW0wSHV2RC1oVWcyQkVUVmFKNWlzb3gzYVhyNG8tUzhnZ0FjUXc4UzIwSFFXRUliNGRwOVI0c1NRMm9OZ2pBbFZMa2V5eGJGcU9kamhZRkFwa1F2MFRZQUE0OEVhMmdt?oc=5)；S / 包装；2026-11-13
  - [软包装复合材料市场展望2035：食品包装需求与可回收趋势塑造增长 - 新闻和统计 - IndexBox](https://news.google.com/rss/articles/CBMi0wFBVV95cUxQQUV3WEpsXzk1MHRiR3RsS3ZydzdDal9zZzZ3Q0l5UkxMSFhxM1BGYk5tcUY3OWJVUnRXV2dRNld3YThNQ1pkTTBhTUdoaXZtT3JXUDByN1VNSUQtYWNKd2pEZUdYQ1J5ZUs0WDN2dmNoUmg3NEhXZ1BUSVF1RTQ0aU01ZjU1MUp0VjRXREQ1blpBMjhTMHk3OVcxeEppQ3BmcVdvWWhubzVJU0M2enRaXzhEWUVRTTcyd1Z2UnFjUVJzbjJkZlFpbUxlRUhnMHZYQXFz?oc=5)；S / 包装；2026-11-13
  - [京东11.11送装一体服务全面升级家电家居商品订单量同比增长200%\|消费者\|渠道\|成交额\|优惠_手机新浪网 - 新浪财经_金融信息服务商](https://news.google.com/rss/articles/CBMif0FVX3lxTE45SVpzSnEzMFV3YnNqM0lWSnoySWx1R3dVb2tfUTZ1b2NMd0p0V2hkV3RVd19GS2I1bU5TMnFBOG9HRjljR2dGM2NkN2ZwaVQ1WUc4RkFRdzlZYlR0TWZFUDNLWndHNVhhcEh0d1pXMnZ4al9nb3RSa0pHZ1FSOE0?oc=5)；O / 家居；2026-11-12

### 2. 国防军工

- 行情：20日-4.32%、排名第17；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：O（还缺1类）；主体：3/2（还缺0个）；独立URL：3/2（还缺0个）；相反证据：无；质量旗标：OCF_WEAK,ONE_OFF_OR_LOW_BASE。
- 已绑定的部分claim：
  - [中国船舶：中国船舶工业股份有限公司关于公司下属子公司签订重大合同的公告](https://static.cninfo.com.cn/finalpage/2026-11-12/1225667453.PDF)；O / 中国船舶；2026-11-12
  - [手持订单、船舶交付量大增 松发股份Q3归母净利增近四倍 \| 财报解读 - 财联社](https://news.google.com/rss/articles/CBMiSEFVX3lxTE9rdm1mOEFnZkFsS25CUDBBZnpJQ0M5ZS0xd0ptU3o5Wkx4N0xzQlpVbGQ1YURwSHJxaXVNSXJoVDNyM2lBRFF1dA?oc=5)；O / 松发股份；2026-10-28
  - [我国绿色船舶订单逆势增长 拆解背后转型密码 - China Daily](https://news.google.com/rss/articles/CBMif0FVX3lxTFBMQzNPaEVNaWZ2Y0gzdTV6TjVrOXl4aDZ3S3ZuWjlWcHd6b3dyZjRpOFg0dFppaGQ3MEIySi12SnBOZ0VjU0JhbTVfNHRZNHhRSkZtcGU5dk10Wmw1SldFQjdLMVBhMEJhZnlfMFp2ZERPb1VNRXdZbHB0NzVWQ1k?oc=5)；O / 船舶；2026-07-23

### 3. 纺织服饰

- 行情：20日-0.19%、排名第7；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：S（还缺1类）；主体：1/2（还缺1个）；独立URL：1/2（还缺1个）；相反证据：无；质量旗标：SINGLE_COMPANY。
- 已绑定的部分claim：
  - [稳健医疗：棉花涨价对全棉时代影响相对有限 - 东方财富](https://news.google.com/rss/articles/CBMiYEFVX3lxTE1vbHJQZm9ONldGUlZnemV0YkxiMTV2dmRkWGdNSmJVR2ZvTlhnY0h1d0FwaGlyaG1GalNObHdvV1F6QkdOUkNLaEtGbjlnTUdtQnhQOWpQNkxQanhoY0d1Rw?oc=5)；S / 棉花；2026-11-02

### 4. 汽车

- 行情：20日+0.63%、排名第6；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：O（还缺1类）；主体：1/2（还缺1个）；独立URL：1/2（还缺1个）；相反证据：无；质量旗标：ONE_OFF_OR_LOW_BASE,SINGLE_COMPANY。
- 已绑定的部分claim：
  - [同比大增346.9% 大众汽车品牌10月新能源汽车交付创新高 - 央视网](https://news.google.com/rss/articles/CBMieEFVX3lxTE1XdThkb0NyUXpPS1pZUndkYTJxb3ZTb3I3VTM4U2NFWWNVWTUwR3Y3Ykw4TWJITGRpbERIbDE2aXd0MGVlQ0laTTBKMVdNRDlCWE5CYVF1N1h3QUVvaWJpZGx4UEs0M1FpZ2lZWGN3NDZLZkpOOGdyTA?oc=5)；O / 新能源汽车；2026-11-12

### 5. 农林牧渔

- 行情：20日+3.03%、排名第5；相对通过 / 广度未计算 / 成交通过。
- 证据缺口：类别：无（还缺2类）；主体：0/2（还缺2个）；独立URL：0/2（还缺2个）；相反证据：无；质量旗标：无。
- 未被证据门采用的候选标题（最多2条）：
  - [生猪现货价格再度跌破前低 市场旺季成色或不足 - 证券之星](https://news.google.com/rss/articles/CBMiYEFVX3lxTE1IV0VMTFIxam0yQ2s0SHV4OEVPRG9QLW5xX3ltWWlua3daTGh4ajVaYjZ6b2p4bDRKc01jMVY5VzhYQVlCWkxMSmw4YzVkaFJuVW4zdFZHMnFBRUJBb0MzWA?oc=5)（2026-11-12）
  - [数字人解读 \| 关于印发《北京市生猪产能综合调控实施方案（2026年修订）》的通知政策解读 - 北京市人民政府门户网站](https://news.google.com/rss/articles/CBMieEFVX3lxTE03eTk2R1pJTEVIVnJ0VFB5U2lxSzhabGh3MkhfV0JsQ0liRXJPT0gtZF9MTGpfRV91T05wbVpNWXJwSU0xdktXS1ZTZEZkWlFTeXNDLTRRUjJvWDFJZ196TUkxNllHQmtPUDhvMU9McFhpVm42X2lWYQ?oc=5)（2026-11-09）

## 证据领先、市场尚未确认

本期无“证据PASS但市场少于两项确认”的非拥挤行业。

## 拥挤防追高

| 20日排名 | 行业 | 拥挤状态 | 触发原因 | 证据门 | 处理 |
|---:|---|---|---|---|---|
| 18 | 石油石化 | 周期成熟 | 本年已于2026-03-03触及E30 | WATCH | 禁止新增，不等于看空 |
| 19 | 煤炭 | 周期成熟 | 本年已于2026-08-31触及E30 | WATCH | 禁止新增，不等于看空 |
| 27 | 电子 | 周期成熟 | 本年已于2026-05-07触及E30 | WATCH | 禁止新增，不等于看空 |
| 28 | 建筑材料 | 周期成熟 | 本年已于2026-06-16触及E30 | WATCH | 禁止新增，不等于看空 |
| 29 | 有色金属 | 周期成熟 | 本年已于2026-01-28触及E30 | WATCH | 禁止新增，不等于看空 |
| 30 | 综合 | 周期成熟 | 本年已于2026-02-24触及E30 | WATCH | 禁止新增，不等于看空 |
| 31 | 通信 | 周期成熟 | 本年已于2026-04-17触及E30 | PASS | 禁止新增，不等于看空 |

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
| 2026-10-16 | 建筑装饰 | 2026-10-19 | -5.16% / 第21 | 未完成 | 20日已完成 |
| 2026-10-16 | 交通运输 | 2026-10-19 | -0.53% / 第11 | 未完成 | 20日已完成 |
| 2026-10-23 | 计算机 | 2026-10-26 | 未完成 | 未完成 | 观察中 |
| 2026-11-06 | 建筑装饰 | 2026-11-09 | 未完成 | 未完成 | 观察中 |

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
| 建筑装饰 | 2026-10-16 | 2026-10-30 | 证据门失效 |
| 计算机 | 2026-10-23 | 2026-10-30 | 证据门失效 |
| 建筑装饰 | 2026-11-06 | 2026-11-13 | 证据门失效 |

## 31行业完整附录

| 20日排名 | 行业 | 5日 | 20日 | 相对20日 | 成交分位 | 广度 | 市场通过数 | 证据门 | S/O/E | 主体 / URL | 拥挤 | 状态 |
|---:|---|---:|---:|---:|---:|---|---:|---|---|---|---|---|
| 1 | 食品饮料 | -1.54% | +5.05% | +8.79% | 36.1% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 2 | 传媒 | -0.78% | +4.60% | +8.35% | 90.3% | 未计算 | 1 | WATCH | E | 1 / 2 | - | 证据观察 |
| 3 | 家用电器 | +0.78% | +4.08% | +7.83% | 41.4% | 未计算 | 2 | WATCH | O | 1 / 1 | - | 证据观察 |
| 4 | 银行 | +2.11% | +3.76% | +7.51% | 55.7% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 5 | 农林牧渔 | +0.50% | +3.03% | +6.77% | 74.5% | 未计算 | 2 | WATCH | - | 0 / 0 | - | 证据观察 |
| 6 | 汽车 | -0.26% | +0.63% | +4.37% | 27.4% | 未计算 | 2 | WATCH | O | 1 / 1 | - | 证据观察 |
| 7 | 纺织服饰 | +0.24% | -0.19% | +3.55% | 68.0% | 未计算 | 2 | WATCH | S | 1 / 1 | - | 证据观察 |
| 8 | 医药生物 | -2.87% | -0.20% | +3.55% | 37.7% | 未计算 | 1 | WATCH | S | 1 / 2 | - | 证据观察 |
| 9 | 商贸零售 | -1.83% | -0.56% | +3.19% | 29.9% | 未计算 | 1 | WATCH | S | 1 / 1 | - | 证据观察 |
| 10 | 交通运输 | -2.24% | -0.90% | +2.85% | 23.7% | 未计算 | 1 | WATCH | O | 1 / 1 | - | 证据观察 |
| 11 | 计算机 | -1.22% | -1.00% | +2.75% | 7.1% | 未计算 | 1 | WATCH | E,O,S | 2 / 3 | - | 证据观察 |
| 12 | 公用事业 | -0.91% | -1.19% | +2.56% | 39.2% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 13 | 社会服务 | -1.76% | -1.89% | +1.85% | 15.3% | 未计算 | 1 | WATCH | - | 0 / 0 | - | 证据观察 |
| 14 | 非银金融 | -2.32% | -2.08% | +1.67% | 0.1% | 未计算 | 1 | WATCH | O | 1 / 1 | - | 证据观察 |
| 15 | 机械设备 | -0.97% | -3.50% | +0.24% | 89.9% | 未计算 | 1 | WATCH | O | 1 / 1 | - | 证据观察 |
| 16 | 轻工制造 | -0.30% | -3.74% | +0.00% | 18.4% | 未计算 | 2 | WATCH | O,S | 2 / 3 | - | 证据观察 |
| 17 | 国防军工 | -1.05% | -4.32% | -0.58% | 23.8% | 未计算 | 2 | WATCH | O | 3 / 3 | - | 证据观察 |
| 18 | 石油石化 | -2.80% | -4.49% | -0.75% | 48.3% | 未计算 | 0 | WATCH | S | 2 / 2 | 周期成熟 | 证据观察 |
| 19 | 煤炭 | +1.79% | -5.54% | -1.80% | 37.2% | 未计算 | 1 | WATCH | E | 1 / 1 | 周期成熟 | 证据观察 |
| 20 | 环保 | -2.37% | -5.63% | -1.89% | 0.8% | 未计算 | 1 | WATCH | O | 3 / 4 | - | 证据观察 |
| 21 | 建筑装饰 | -2.24% | -5.68% | -1.93% | 4.4% | 未计算 | 1 | WATCH | O | 3 / 3 | - | 证据观察 |
| 22 | 基础化工 | -3.52% | -6.07% | -2.33% | 34.5% | 未计算 | 2 | WATCH | S | 1 / 1 | - | 证据观察 |
| 23 | 电力设备 | -5.45% | -6.18% | -2.44% | 35.8% | 未计算 | 0 | WATCH | O | 1 / 1 | - | 证据观察 |
| 24 | 钢铁 | -3.00% | -6.84% | -3.09% | 0.3% | 未计算 | 0 | WATCH | - | 0 / 0 | - | 证据观察 |
| 25 | 房地产 | -2.72% | -8.50% | -4.75% | 0.8% | 未计算 | 0 | WATCH | S | 1 / 1 | - | 证据观察 |
| 26 | 美容护理 | -3.96% | -8.72% | -4.98% | 24.9% | 未计算 | 0 | WATCH | - | 0 / 0 | - | 证据观察 |
| 27 | 电子 | +1.87% | -9.10% | -5.35% | 88.6% | 未计算 | 1 | WATCH | S | 3 / 4 | 周期成熟 | 证据观察 |
| 28 | 建筑材料 | -2.63% | -9.47% | -5.72% | 76.3% | 未计算 | 2 | WATCH | E,S | 3 / 3 | 周期成熟 | 证据观察 |
| 29 | 有色金属 | -4.77% | -9.67% | -5.93% | 43.3% | 未计算 | 0 | WATCH | E | 1 / 1 | 周期成熟 | 证据观察 |
| 30 | 综合 | -0.60% | -11.83% | -8.09% | 13.5% | 未计算 | 0 | WATCH | O | 1 / 1 | 周期成熟 | 证据观察 |
| 31 | 通信 | +3.06% | -20.75% | -17.01% | 86.1% | 14.0% | 2 | PASS | O,S | 4 / 3 | 周期成熟 | 周期成熟 |

## 固定规则与数据限制

1. 硬证据PASS要求结构化claim覆盖S/O/E至少两类、两个独立主体、两个不同URL和两个事件簇，且至少一个主体为申万成分公司；标题候选本身不等于已采用证据。
2. 市场激活三选二：20日相对收益转正或持续改善；成分股站上60日均线比例连续两周上升；成交额占比上升且低于自身近三年85%分位。广度未计算时记为未知，不记失败。
3. 防追高任一命中即禁止新增：本年已触及E30；上年涨幅至少50%且当前20日前8；当前20日前3且涨幅至少15%。防追高不等于看空。
4. 证据与市场是两道独立门：WATCH即使行情领先也只能进入近失配，PASS但市场不足两项只能进入等待确认。
5. 候选新闻回看180日；claim仍受各字段TTL和报告截止时点约束。模型`codebuddy`只能分类冻结候选，不能补写事实。
6. 收盘后形成正式信号，下一共同交易日开盘仅作统一诊断代理；未计滑点、费用、涨跌停、容量和个股治理风险。
7. 每期冻结候选、结构化claim、行情派生值、状态、运行质量和哈希；修复回填或上游滞后样本不得混入前瞻统计。

行情来源：[申万指数官方数据](https://www.swsresearch.com/institute_sw/allIndex/releasedIndex)。

公开输入快照：[查看本期snapshot](./snapshots/2026-11-13.json)。
