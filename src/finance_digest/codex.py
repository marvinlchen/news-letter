from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .models import Article


def validate_digest(
    digest: dict[str, Any], target_date: date, articles: list[Article]
) -> dict[str, Any]:
    if digest.get("date") != target_date.isoformat():
        raise ValueError("Codex returned the wrong digest date")
    raw_items = digest.get("items")
    if not isinstance(raw_items, list) or not raw_items or len(raw_items) > 10:
        raise ValueError("Codex returned an invalid item count")

    articles_by_url = {article.url: article for article in articles}
    seen_urls: set[str] = set()
    items: list[dict[str, Any]] = []
    for rank, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError("Codex returned a non-object item")
        url = raw_item.get("url")
        if url not in articles_by_url:
            raise ValueError(f"Codex returned an unknown candidate URL: {url}")
        if url in seen_urls:
            raise ValueError(f"Codex returned a duplicate candidate URL: {url}")
        seen_urls.add(url)
        article = articles_by_url[url]
        item = dict(raw_item)
        item.update(
            {
                "rank": rank,
                "title_original": article.title,
                "category": article.category,
                "source": article.source,
                "published_at": article.published_at.isoformat(),
                "url": article.url,
            }
        )
        items.append(item)
    return {"date": target_date.isoformat(), "items": items}


def run_codex(
    project_root: Path,
    target_date: date,
    articles: list[Article],
    codex_bin: str = "codex",
) -> dict[str, Any]:
    prompt = (project_root / "prompts/select_top10.md").read_text(encoding="utf-8")
    candidates = {
        "date": target_date.isoformat(),
        "candidates": [article.to_dict() for article in articles[:50]],
    }
    full_prompt = f"{prompt}\n{json.dumps(candidates, ensure_ascii=False, indent=2)}\n"
    schema = project_root / "schemas/digest.schema.json"
    with tempfile.TemporaryDirectory(prefix="finance-digest-codex-") as temp_dir:
        output_path = Path(temp_dir) / "digest.json"
        command = [
            codex_bin,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(output_path),
            "-",
        ]
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=os.environ.copy(),
            input=full_prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"codex exited {completed.returncode}: {completed.stderr[-2000:]}"
            )
        digest = json.loads(output_path.read_text(encoding="utf-8"))
        return validate_digest(digest, target_date, articles[:50])
