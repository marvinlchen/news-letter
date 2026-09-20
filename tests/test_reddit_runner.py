from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RedditRunnerTest(unittest.TestCase):
    def test_runner_fails_fast_without_oauth(self) -> None:
        runner = (ROOT / "scripts" / "run-reddit-digest.sh").read_text(encoding="utf-8")
        self.assertIn('REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required', runner)
        self.assertIn('exit 4', runner)

    def test_cron_is_conditional_on_oauth(self) -> None:
        installer = (ROOT / "scripts" / "install-cron.sh").read_text(encoding="utf-8")
        self.assertIn('reddit_oauth_configured=0', installer)
        self.assertIn('if [[ "$reddit_oauth_configured" == "1" ]]', installer)


if __name__ == "__main__":
    unittest.main()
