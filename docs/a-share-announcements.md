# A股重大公告利好利空日报

每天 05:00（Asia/Shanghai，UTC+8）触发，报告日期为前一自然日。先核验A股交易日；非交易日记录跳过，不生成PDF、不重复上一交易日报。覆盖用户2026-10-11交付标准的十大类；同股票多重大公告合并，按利好、中性、利空及评分绝对值排序。

公告通过东方财富全量分页索引、巨潮沪深官方披露原文获取。iFinD等付费金融插件未配置，使用公开源并在报告中披露。支持附件保留链接，独立融资/分红不在十大类内，不作为本任务候选。列表分页或候选正文不完整时停止发布。官方交叉核验或行情字段缺失会逐股标明数据待核并汇总缺口；不会补造数字。行业新闻仅有可信检索结果才加入，当前未接入iFinD行业新闻检索。

CodeBuddy采用主机全局模型，text格式、禁用工具；沿用主机既有调用形式，最多3批并行、单次5分钟上限；输出每个候选公司的入选或排除决策。确定性校验覆盖率、公告ID、方向评分和原文数据摘录。行情截至公告日收盘，前复权终值必须与截至日原始价一致；周线由截至日日线聚合。PDF为A3研报式四卡位布局，末页不足四只留空。文字不静默截断，放不下时拒绝输出。

输出：

- 项目主目录：`M月D日-A股重大公告利好利空日报.pdf`，重跑依次V2、V3。
- `published/a-share-announcements/`：日期PDF、`latest.pdf`、日期Markdown/JSON和`latest.md`，沿用GitHub main发布。
- `var/a-share-announcements-status/`：每日状态、`latest-run.json`、`latest-artifact.json`，含事实/版式审核和发布结果。
- `var/a-share-announcements-cache/`：全量列表、原文PDF/文本、行情、模型原始决策。
- `var/log/a-share-announcements.log`：定时运行日志。

运行依赖隔离在 `var/a-share-announcements-venv`（Python系统包继承，仅新增reportlab、pypdf）；Python运行预算55分钟，发布最多150秒。

安装或更新该项cron：

```bash
./scripts/install-cron.sh --a-share-announcements-only
```

此模式保留其它cron原文，仅替换本任务标记。默认完整安装模式也包含本任务。

诊断示例（不发布，独立输出和状态）：

```bash
PUBLISH_TO_GITHUB=0 var/a-share-announcements-venv/bin/python scripts/a_share_announcements.py --date 2026-10-16 --limit 4
```

定时wrapper默认发布；所有诊断参数强制禁止发布。发布校验两轮审核、PDF/Markdown/JSON哈希及latest一致性，并使用既有Git发布锁。所有新建提交带Co-authored-by trailer。
