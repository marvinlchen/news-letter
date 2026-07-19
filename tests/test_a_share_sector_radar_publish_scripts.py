from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "scripts" / "publish-a-share-sector-radar-weekly.sh"
RUNNER = ROOT / "scripts" / "run-a-share-sector-radar-weekly.sh"
REPORT_DATE = "2026-07-17"


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=merged_env,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise AssertionError(
            f"command failed ({result.returncode}): {command!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def git(project: Path, *args: str) -> str:
    return run(["git", *args], project).stdout.strip()


def write_artifacts_and_status(project: Path) -> list[str]:
    report_dir = project / "published" / "a-share-sector-radar-weekly"
    snapshot_dir = report_dir / "snapshots"
    status_dir = project / "var" / "a-share-sector-radar-weekly-status"
    snapshot_dir.mkdir(parents=True)
    status_dir.mkdir(parents=True)

    report = report_dir / f"{REPORT_DATE}.md"
    latest = report_dir / "latest.md"
    ledger = report_dir / "ledger.json"
    snapshot = snapshot_dir / f"{REPORT_DATE}.json"
    report.write_text("# repaired weekly report\n", encoding="utf-8")
    latest.write_bytes(report.read_bytes())
    ledger.write_text('{"schema_version": 1}\n', encoding="utf-8")
    snapshot.write_text('{"date": "2026-07-17"}\n', encoding="utf-8")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    artifact_status = {
        "date": REPORT_DATE,
        "mode": "codebuddy",
        "publishable": True,
        "fallback_used": False,
        "codex_error": "",
        "error": "",
        "output_path": str(report.resolve()),
        "report_sha256": digest(report),
        "ledger_sha256": digest(ledger),
        "snapshot_sha256": digest(snapshot),
        "publish_status": "pending",
        "publish_commit": "",
        "publish_error": "",
    }
    run_status = {
        "date": REPORT_DATE,
        "artifact_date": REPORT_DATE,
        "outcome": "generated",
        "publishable": True,
        "publish_required": True,
    }
    payload = json.dumps(artifact_status, ensure_ascii=False, indent=2) + "\n"
    (status_dir / f"{REPORT_DATE}.json").write_text(payload, encoding="utf-8")
    (status_dir / "latest-artifact.json").write_text(payload, encoding="utf-8")
    (status_dir / "latest-run.json").write_text(
        json.dumps(run_status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return [
        f"published/a-share-sector-radar-weekly/{REPORT_DATE}.md",
        "published/a-share-sector-radar-weekly/latest.md",
        "published/a-share-sector-radar-weekly/ledger.json",
        f"published/a-share-sector-radar-weekly/snapshots/{REPORT_DATE}.json",
    ]


class PublisherIntegrationTest(unittest.TestCase):
    def init_project(self, project: Path) -> None:
        run(["git", "init", "--initial-branch=main"], project)
        git(project, "config", "user.name", "Test User")
        git(project, "config", "user.email", "test@example.invalid")
        (project / "unrelated.txt").write_text("base\n", encoding="utf-8")
        git(project, "add", "unrelated.txt")
        git(project, "commit", "-m", "base")

    def publisher_env(self, project: Path) -> dict[str, str]:
        return {
            "PROJECT_ROOT": str(project),
            "PUBLISH_BRANCH": "main",
            "A_SHARE_RADAR_GIT_LOCK_HELD": "1",
        }

    def test_no_diff_reuses_report_commit_instead_of_current_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.init_project(project)
            artifact_paths = write_artifacts_and_status(project)
            git(project, "add", *artifact_paths)
            git(project, "commit", "-m", "initial report")
            report_commit = git(project, "rev-parse", "HEAD")

            (project / "unrelated.txt").write_text("later\n", encoding="utf-8")
            git(project, "add", "unrelated.txt")
            git(project, "commit", "-m", "later unrelated change")
            unrelated_head = git(project, "rev-parse", "HEAD")
            commit_count = git(project, "rev-list", "--count", "HEAD")

            result = run([str(PUBLISHER)], project, self.publisher_env(project))

            self.assertIn("is unchanged; existing commit", result.stdout)
            self.assertEqual(git(project, "rev-list", "--count", "HEAD"), commit_count)
            self.assertNotEqual(report_commit, unrelated_head)
            status_dir = project / "var" / "a-share-sector-radar-weekly-status"
            artifact_status = json.loads((status_dir / "latest-artifact.json").read_text(encoding="utf-8"))
            run_status = json.loads((status_dir / "latest-run.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact_status["publish_commit"], report_commit)
            self.assertEqual(run_status["publish_commit"], report_commit)
            self.assertTrue(run_status["publish_required"])

    def test_diff_commit_contains_only_artifacts_and_trailer_then_pushes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "project"
            remote = base / "remote.git"
            project.mkdir()
            self.init_project(project)
            run(["git", "init", "--bare", "--initial-branch=main", str(remote)], base)
            git(project, "remote", "add", "origin", str(remote))
            git(project, "push", "-u", "origin", "main")

            artifact_paths = write_artifacts_and_status(project)
            (project / "unrelated.txt").write_text("staged but unrelated\n", encoding="utf-8")
            git(project, "add", "unrelated.txt")

            run([str(PUBLISHER)], project, self.publisher_env(project))

            report_commit = git(
                project,
                "log",
                "-1",
                "--format=%H",
                "--",
                f"published/a-share-sector-radar-weekly/{REPORT_DATE}.md",
            )
            message = git(project, "show", "-s", "--format=%B", report_commit)
            committed_paths = set(git(project, "show", "--pretty=", "--name-only", report_commit).splitlines())
            self.assertEqual(committed_paths, set(artifact_paths))
            self.assertIn("Co-authored-by: Codex <noreply@openai.com>", message)
            self.assertEqual(git(project, "diff", "--cached", "--name-only"), "unrelated.txt")
            self.assertEqual(
                run(["git", "--git-dir", str(remote), "rev-parse", "main"], base).stdout.strip(),
                report_commit,
            )


class RunnerPublishGateTest(unittest.TestCase):
    def make_fake_project(self, project: Path, publish_required: bool) -> Path:
        scripts = project / "scripts"
        scripts.mkdir(parents=True)
        generator = scripts / "a_share_sector_radar_weekly.py"
        generator.write_text(
            """\
import json
import sys
from pathlib import Path

status_dir = Path(sys.argv[sys.argv.index('--status-dir') + 1])
status_dir.mkdir(parents=True, exist_ok=True)
(status_dir / 'latest-run.json').write_text(
    json.dumps({'publish_required': PUBLISH_REQUIRED}) + '\\n', encoding='utf-8'
)
""".replace("PUBLISH_REQUIRED", "True" if publish_required else "False"),
            encoding="utf-8",
        )
        publisher = scripts / "publish-a-share-sector-radar-weekly.sh"
        publisher.write_text(
            '#!/usr/bin/env bash\nset -euo pipefail\ntouch "$PROJECT_ROOT/publisher-called"\n',
            encoding="utf-8",
        )
        publisher.chmod(0o755)
        (project / "config").mkdir()
        (project / "config" / "a_share_sector_radar.json").write_text("{}\n", encoding="utf-8")
        return project / "publisher-called"

    def test_false_publish_required_skips_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            marker = self.make_fake_project(project, False)
            result = run([str(RUNNER)], project, {"PROJECT_ROOT": str(project)})
            self.assertFalse(marker.exists())
            self.assertIn("publish_required=false", result.stdout)

    def test_true_publish_required_calls_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            marker = self.make_fake_project(project, True)
            run([str(RUNNER)], project, {"PROJECT_ROOT": str(project)})
            self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
