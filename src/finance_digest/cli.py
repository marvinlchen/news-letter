from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .codex import run_codex
from .collect import collect_articles, load_sources
from .render import fallback_digest, pretty_json, render_markdown


TIMEZONE = ZoneInfo("Asia/Shanghai")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def load_successful_digest(path: Path, target_date: date) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        digest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if digest.get("date") != target_date.isoformat():
        return None
    if digest.get("metadata", {}).get("mode") not in {"codex", "codex-preserved"}:
        return None
    if not digest.get("topics"):
        return None
    return digest


def default_target_date() -> date:
    return datetime.now(TIMEZONE).date() - timedelta(days=1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a daily finance-news digest")
    parser.add_argument("command", choices=["collect", "run"])
    parser.add_argument("--date", type=date.fromisoformat, default=default_target_date())
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--use-codex", action="store_true")
    parser.add_argument("--require-codex", action="store_true")
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", "codex"))
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = args.project_root.resolve()
    output_root = (args.output_root or project_root / "var").resolve()
    sources = load_sources(project_root / "config/sources.json")
    articles, source_errors = collect_articles(sources, args.date)

    candidates_payload: dict[str, Any] = {
        "date": args.date.isoformat(),
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "source_count": len(sources),
        "candidate_count": len(articles),
        "source_errors": source_errors,
        "candidates": [article.to_dict() for article in articles],
    }
    candidate_path = output_root / "raw" / f"{args.date.isoformat()}-candidates.json"
    atomic_write(candidate_path, pretty_json(candidates_payload))
    if args.command == "collect":
        print(candidate_path)
        return 0 if articles else 2

    mode = "rules-fallback"
    codex_error = ""
    digest = fallback_digest(args.date, articles)
    if args.use_codex and articles:
        try:
            digest = run_codex(project_root, args.date, articles, args.codex_bin)
            mode = "codex"
        except Exception as exc:
            codex_error = str(exc)

    digest_dir = output_root / "digests"
    digest_json = digest_dir / f"{args.date.isoformat()}.json"
    if args.use_codex and codex_error:
        successful_digest = load_successful_digest(digest_json, args.date)
        if successful_digest is not None:
            digest = successful_digest
            mode = "codex-preserved"

    digest["metadata"] = {
        "mode": mode,
        "candidate_count": len(articles),
        "source_errors": source_errors,
        "codex_error": codex_error,
    }
    digest_md = digest_dir / f"{args.date.isoformat()}.md"
    atomic_write(digest_json, pretty_json(digest))
    atomic_write(digest_md, render_markdown(digest, mode, source_errors))
    shutil.copyfile(digest_json, digest_dir / "latest.json")
    shutil.copyfile(digest_md, digest_dir / "latest.md")

    status = {
        "date": args.date.isoformat(),
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "mode": mode,
        "candidate_count": len(articles),
        "topic_selected_count": sum(
            len(topic["items"]) for topic in digest.get("topics", [])
        ),
        "source_error_count": len(source_errors),
        "codex_error": codex_error,
    }
    atomic_write(output_root / "status/latest.json", pretty_json(status))
    print(digest_md)
    if not articles:
        return 2
    if args.require_codex and mode != "codex":
        return 3
    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"finance-news-digest: {exc}", file=sys.stderr)
        return 1
