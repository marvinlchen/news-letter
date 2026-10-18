# A股重大公告利好利空日报

每天 05:00（Asia/Shanghai，UTC+8）触发，报告日期为前一自然日。先核验A股交易日；非交易日记录跳过，不生成日报、不重复上一交易日报。内容范围沿用用户2026-10-11交付标准；按2026-10-18最新要求，交付改为Markdown并上传Git，替代原PDF及版式要求。覆盖十大类；同股票多重大公告合并，按利好、中性、利空及评分绝对值排序。

公告通过东方财富全量分页索引、巨潮沪深官方披露原文获取。iFinD MCP按报告日期检索本批股票公告作交叉核验；公告事件、数字与单位仍严格以官方原文为依据。支持附件保留链接，独立融资/分红不在十大类内，不作为本任务候选。列表分页或候选正文不完整时停止发布。官方交叉核验或行情字段缺失会逐股标明数据待核并汇总缺口；不会补造数字。行业新闻仅有可信检索结果才加入，本任务暂不调用行业新闻工具。

CodeBuddy采用主机全局模型；配置iFinD后使用stream-json格式，仅授权search_notice与WaitForMcpServers，dontAsk拒绝其他工具。HTTP MCP首次连接最多等待60秒，最多3批并行、单次5分钟上限；输出每个候选公司的入选或排除决策。确定性校验覆盖率、公告ID、方向评分和原文数据摘录。行情截至公告日收盘，前复权终值必须与截至日原始价一致；周线由截至日日线聚合。Markdown逐股保留事件、结论、分析、关键数据表、公告原文链接、日/周技术指标、行业信息、后续关注及数据缺口，内容校验通过后发布。

输出：

- `published/a-share-announcements/`：`YYYY-MM-DD.md`、`latest.md`及同日结构化JSON，沿用GitHub main自动提交并推送。
- `var/a-share-announcements-status/`：每日状态、`latest-run.json`、`latest-artifact.json`，含事实/Markdown内容审核和发布结果。
- `var/a-share-announcements-cache/`：全量列表、原文PDF/文本、行情、模型原始决策。
- `var/log/a-share-announcements.log`：定时运行日志。

运行依赖隔离在 `var/a-share-announcements-venv`（Python系统包继承，pypdf用于读取公告原文）；Python运行预算55分钟，发布最多150秒。

安装或更新该项cron：

```bash
./scripts/install-cron.sh --a-share-announcements-only
```

此模式保留其它cron原文，仅替换本任务标记。默认完整安装模式也包含本任务。

诊断示例（不发布，独立输出和状态）：

```bash
PUBLISH_TO_GITHUB=0 var/a-share-announcements-venv/bin/python scripts/a_share_announcements.py --date 2026-10-16 --limit 4
```

定时wrapper默认发布；所有诊断参数强制禁止发布。发布校验事实与内容审核、Markdown/JSON哈希及latest一致性，并使用既有Git发布锁。所有新建提交带Co-authored-by trailer。

## iFinD连接

私有配置位于主机 `~/.config/finance-news-digest/ifind-mcp.json`，权限0600，密钥只保存在该文件，不进入Git或命令参数。仅A股公告日报wrapper自动加载此配置；可用 `ANNOUNCEMENTS_IFIND_MCP_CONFIG` 显式指定路径，空字符串停用。仅接受官方统一HTTP endpoint，单服务器ifind，alwaysLoad=true。

每批必须存在按调用ID配对的成功iFinD公告检索响应，且检索日期等于报告日、查询含本批股票代码；模型自称使用iFinD不能替代调用证据。原始stream和配对响应哈希保留在var私有缓存，状态记录真实成功次数。连接、工具响应或输出校验失败时不发布该日报。没有可靠一致预期，业绩仍标“无一致预期”；MA/MACD继续使用截至日历史行情计算。
