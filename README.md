# Finance News Digest

A small, auditable daily pipeline for producing a professional topic-based
finance and technology briefing.

The pipeline deliberately separates deterministic work from LLM work:

1. Python fetches configured RSS feeds and trusted-source indexes.
2. Python normalizes URLs, filters by publication date, deduplicates stories,
   clusters related headlines, and ranks candidates.
3. Codex selects up to three consequential stories for each configured topic,
   then writes Chinese summaries using only the supplied candidate data.
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

The repository also produces a separate weekly technical deep-reading report
for Cloud Infra Engineering and AI Frontier. It is intentionally not mixed into
the daily news report. The deep-reading pipeline searches only the previous
seven days and selects up to five professional articles per topic based on
technical depth, evidence, source authority, and engineering value.

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
