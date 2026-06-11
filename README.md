# Finance News Digest

A small, auditable daily pipeline for producing a Top 10 finance-news digest.

The pipeline deliberately separates deterministic work from LLM work:

1. Python fetches configured RSS feeds and trusted-source indexes.
2. Python normalizes URLs, filters by publication date, deduplicates stories,
   clusters related headlines, and ranks candidates.
3. Codex selects the final Top 10 plus Top 3 stories for shipping, commodities,
   technology, and consumer sectors, then writes Chinese summaries using only
   the supplied candidate data.
4. If Codex fails, the pipeline still writes a deterministic fallback digest.

## Source Policy

The default configuration uses publicly accessible sources:

- Professional publications: WSJ Markets and Google News indexes restricted to
  Reuters, Bloomberg, Financial Times, CNBC, and AP.
- Primary sources: Federal Reserve, SEC, ECB, Bank of England, BIS, and EIA.
- General business coverage: BBC Business.

Google News entries may link through Google and do not grant access to paid
article bodies. The pipeline does not bypass paywalls. Add licensed providers
later through a provider adapter.

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

Each story uses a Chinese headline and one Chinese summary paragraph limited to
200 characters. The output validator rejects non-Chinese headlines and summaries
outside the configured length range. Industry sections use keyword classification
and dedicated trusted-source indexes; a major story may appear in both the
overall Top 10 and its relevant industry section. Markdown reports use the
section heading as the Chinese headline and explicitly label the original
headline and summary for every story.

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

The cron entry uses `flock` to prevent overlapping runs. Logs are written to
`var/log/cron.log`.

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
Without valid Codex authentication, the scheduled job still writes the
rules-based Top 10 and industry sections, and records `mode: rules-fallback` in
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
