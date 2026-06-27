# Finance News Digest

A small, auditable daily pipeline for producing a professional topic-based
finance and technology briefing.

The pipeline deliberately separates deterministic work from LLM work:

1. Python fetches configured RSS feeds and trusted-source indexes.
2. Python normalizes URLs, filters by publication date, deduplicates stories,
   clusters related headlines, and ranks candidates.
3. Codex selects up to three consequential stories for each configured topic
   and country section, then writes Chinese summaries using only the supplied
   candidate data.
4. If Codex fails, the pipeline still writes a deterministic fallback digest.

The daily report contains time-sensitive news only, with no overall Top 10. It
covers eight topics:

- Macroeconomics
- Shipping
- Commodities
- Stock Market
- Technology
- Consumer
- Cloud Infra Engineering
- AI Frontier

It also contains an independent country-news section with up to three
consequential stories each for Singapore, China, and the United States. Country
selection prioritizes economic, business, policy, market, and corporate events
with durable implications for investors.

The repository also produces a separate weekly technical deep-reading report
for Cloud Infra Engineering and AI Frontier. It is intentionally not mixed into
the daily news report. The deep-reading pipeline searches only the previous
seven days and selects up to five professional articles per topic based on
technical depth, evidence, source authority, and engineering value.

It also produces a separate daily Reddit community intelligence report across
the same eight topics for a multi-industry, long-term value investor. The Reddit
report selects up to three discussions per topic based on their relevance to
fundamentals, industry economics, capital allocation, competitive advantage,
valuation, and long-term cash flows. Each item separates community signal,
fundamental impact, the value-investor takeaway, key risks, and evidence still
required. Reddit content is treated as unverified community discussion rather
than a factual news source.

It also produces a weekly China broad-index ETF share-flow report for a
fixed "national team ETF" observation basket. The report tracks official ETF
total share changes from SSE and SZSE and uses delayed Eastmoney ETF quotes
to estimate scale and weekly flow. This is a public-data proxy for allocation
pressure, not a holder-level disclosure of Central Huijin, CSF, or any other
specific account.

The Reddit candidate ranker boosts discussions that mention durable fundamental
signals such as revenue, margins, free cash flow, capital allocation, pricing
power, competitive advantage, industry supply and demand, regulation, and
valuation. It rejects day-trading, technical-analysis, price-prediction, and
similar speculative content. Popularity alone is not sufficient for selection.

Reddit Top 3 selection uses two stages:

1. The collector fetches each configured subreddit independently so large
   communities cannot crowd specialist communities out of a combined daily
   listing. Deterministic ranking then combines the subreddit weight, daily
   listing rank, available engagement metrics, and a value-investing relevance
   score. Up to twelve diverse candidates per topic are sent to Codex.
2. Codex selects up to three discussions only when the supplied evidence has a
   plausible long-term fundamental implication. It may return fewer than three
   or an empty topic. Each selected item must explain fundamental impact, the
   value-investor takeaway, key risks, and evidence still required.

For daily news, specialist semiconductor, technology-platform, cloud-platform,
cloud-native, and AI-lab indexes use an authoritative topic binding. Their
stories can enter the topic candidate pool even when a concise headline does not
repeat a generic topic keyword. Broad search indexes still require keyword
relevance, preventing unrelated search results from entering a topic.

## Source Policy

The default configuration uses publicly accessible sources:

- Professional publications: WSJ Markets and Google News indexes restricted to
  Reuters, Bloomberg, Financial Times, CNBC, and AP.
- Macroeconomics: central banks, World Bank, IMF, OECD, BLS, BEA, Eurostat,
  FRED, China NBS, MAS, and high-quality financial media.
- Shipping: IMO, UNCTAD, and specialist searches restricted to Reuters,
  Bloomberg, Financial Times, and CNBC.
- Commodities: EIA, IEA, USDA, CFTC, UNCTAD, and trusted financial media.
- Stock market: trusted financial media coverage of consequential daily index,
  sector, and individual-stock moves and their reported catalysts.
- Technology and consumer: trusted financial and business publications.
- Cloud Infra Engineering: first-party engineering sources from major cloud,
  cloud-native, database, networking, and infrastructure projects.
- AI Frontier: first-party AI lab and research sources, plus specialist
  reporting when it adds material context.
- General business coverage: BBC Business.

Google News entries may link through Google and do not grant access to paid
article bodies. The pipeline does not bypass paywalls. Add licensed providers
later through a provider adapter. Official sources without stable RSS feeds are
queried through Google News indexes restricted to their official domains.
The raw SEC EDGAR index is configured but disabled until a company watchlist and
filing-event parser can distinguish material filings from routine documents.

## Run Locally

No Python packages are required.

```bash
PYTHONPATH=src python3 -m finance_digest run --date 2026-06-10 --use-codex
```

Generated files:

```text
var/raw/YYYY-MM-DD-candidates.json
var/digests/YYYY-MM-DD.json
var/digests/YYYY-MM-DD.md
var/status/latest.json
```

Published Markdown reports are tracked in:

```text
reports/YYYY-MM-DD.md
reports/latest.md
```

Generate the standalone technical deep-reading report:

```bash
PYTHONPATH=src python3 -m finance_digest.deep_reads --use-codex
```

Deep-reading artifacts are written to:

```text
var/deep-raw/YYYY-MM-DD-candidates.json
var/deep-reads/YYYY-MM-DD.json
var/deep-reads/YYYY-MM-DD.md
var/deep-status/latest.json
deep-reports/YYYY-MM-DD.md
deep-reports/latest.md
```

Generate the standalone Reddit community report:

```bash
PYTHONPATH=src python3 -m finance_digest.reddit_digest --use-codex
```

Reddit artifacts are written to:

```text
var/reddit-raw/YYYY-MM-DD-candidates.json
var/reddit-digests/YYYY-MM-DD.json
var/reddit-digests/YYYY-MM-DD.md
var/reddit-status/latest.json
reddit-reports/YYYY-MM-DD.md
reddit-reports/latest.md
```

Generate the standalone weekly national-team ETF observation report:

```bash
./scripts/run-national-team-etf-weekly.sh
```

ETF weekly artifacts are written to:

```text
var/national-team-etf/YYYY-MM-DD.json
var/national-team-etf/latest.json
var/national-team-etf-status/latest.json
published/national-team-etf/YYYY-MM-DD.md
published/national-team-etf/latest.md
```

Without credentials, the collector uses Reddit's public Topic `top/day` RSS
feeds at a deliberately conservative request rate. RSS mode does not fetch
thread comments. For accurate scores, total comment counts, sampled Top
comments, and official OAuth access, configure an approved Reddit Data API
application:

```bash
export REDDIT_CLIENT_ID=...
export REDDIT_CLIENT_SECRET=...
export REDDIT_USER_AGENT='linux:finance-news-digest:v1.0.0 (by /u/your-account)'
```

For scheduled runs, place those assignments in
`~/.config/finance-news-digest/reddit.env` and restrict the file to the user:

```bash
chmod 600 ~/.config/finance-news-digest/reddit.env
```

The pipeline never stores usernames or sampled comment bodies in raw artifacts
or published reports.
The scheduled Reddit job defaults to `REDDIT_CODEX_REQUIRED=1`, so it records
diagnostics but does not publish a rules-only placeholder report when Codex is
unavailable. Set `REDDIT_CODEX_REQUIRED=0` only for diagnostics.

Each story uses a Chinese headline and one Chinese summary paragraph limited to
200 characters. The output validator rejects non-Chinese headlines and summaries
outside the configured length range. Topic sections combine explicit source
bindings with keyword relevance and prioritize authoritative specialist sources.
Markdown reports use the story heading as the Chinese headline and explicitly
label the original headline and summary for every story.

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Scheduling

The recommended deployment uses user `crontab` because it keeps running even
when no interactive user session is active. It runs daily at `04:00` in the
machine's China Standard Time timezone and produces the previous calendar day's
digest.

```bash
scripts/install-cron.sh
```

Both scheduled reports use the previous China Standard Time calendar day as
their report date. The cron entry uses `flock` to prevent overlapping runs. Logs are written to
`var/log/cron.log`. The separate technical deep-reading report runs every Sunday
at `05:00` China Standard Time, searches the previous seven days, and writes
logs to `var/log/deep-reads.log`.
The Reddit community report runs every day at `04:30` China Standard Time,
searches the previous China calendar day, and writes logs to
`var/log/reddit-digest.log`.
The national-team ETF observation report runs every Saturday at `09:10`
China Standard Time, uses the latest official ETF share data available in the
previous two weeks, and writes logs to
`var/log/national-team-etf-weekly.log`.

After a successful digest run, `scripts/publish-report.sh` commits and pushes
the dated report and `reports/latest.md` to the configured `origin` remote.
Set `PUBLISH_TO_GITHUB=0` to disable publishing.
The default target branch is `main`; override it with `PUBLISH_BRANCH`.

User-level systemd templates are also included. They require the user's systemd
manager to remain active, usually through `loginctl enable-linger`.

Scheduled runs use the machine's default `~/.codex` authentication. Complete a
direct ChatGPT login on the machine rather than copying an active login file from
another client. For stricter automation isolation, set `CODEX_HOME` to a
dedicated directory containing an API key or enterprise Codex Access Token.
Without valid Codex authentication, the scheduled job still writes rules-based
Topic Top 3 sections and records `mode: rules-fallback` in
`var/status/latest.json`.

Set `CODEX_REQUIRED=1` only when the scheduler should fail instead of accepting
the rules-based fallback.

```bash
mkdir -p ~/.config/systemd/user
cp systemd/finance-news-digest.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now finance-news-digest.timer
```

The deployment path expected by the units is:

```text
/home/ME/finance-news-digest
```

## Add Licensed Data

Implement another collector returning the same candidate shape used by
`finance_digest.models.Article`, then register it in `collect.py`. Suitable
future providers include OpenBB-backed Benzinga, Intrinio, Trading Economics,
or licensed LSEG Reuters feeds.
