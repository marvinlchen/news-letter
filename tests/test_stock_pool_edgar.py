import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("stock_pool_edgar_test", ROOT / "scripts/stock_pool_news.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class EdgarTest(unittest.TestCase):
    def setUp(self):
        module._CIK_MAP = None

    def test_sec_row_index_is_not_ticker_and_integer_cik_is_normalized(self):
        payload = {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple"}}
        with mock.patch.object(module, "_http_get", return_value=json.dumps(payload)) as get:
            self.assertEqual(module._load_cik_map(), {"AAPL": "320193"})
            module._load_cik_map()
            get.assert_called_once()

    def test_fetch_filings_uses_padded_cik_and_filters_date(self):
        payload = {"filings": {"recent": {
            "filingDate": ["2026-09-18", "2026-09-17"],
            "form": ["8-K", "4"], "primaryDocument": ["filing.htm", "old.xml"],
            "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
        }}}
        with mock.patch.object(module, "_load_cik_map", return_value={"AAPL": 320193}), mock.patch.object(
            module, "_http_get", return_value=json.dumps(payload)
        ) as get:
            records = module.fetch_edgar("aapl", dt.date(2026, 9, 18))
        get.assert_called_once_with("https://data.sec.gov/submissions/CIK0000320193.json")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "SEC EDGAR")
        self.assertIn("/320193/000032019326000001/filing.htm", records[0].url)

    def test_http_error_is_cached_for_this_run(self):
        with mock.patch.object(module, "_http_get", side_effect=HTTPError("url", 403, "Forbidden", {}, None)) as get:
            self.assertEqual(module.fetch_edgar("AAPL", dt.date(2026, 9, 18)), [])
            self.assertEqual(module.fetch_edgar("MSFT", dt.date(2026, 9, 18)), [])
        get.assert_called_once()

    def test_contact_header_and_tls_verification(self):
        with mock.patch.dict(module.os.environ, {"SEC_EDGAR_USER_AGENT": "Digest contact@example.com"}), mock.patch.object(
            module._urllib_req, "urlopen"
        ) as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"
            self.assertEqual(module._http_get("https://data.sec.gov/test"), "{}")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "Digest contact@example.com")
        context = urlopen.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, module._ssl.CERT_REQUIRED)

    def test_private_contact_config_and_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(module.Path, "home", return_value=Path(tmp)), mock.patch.dict(
            module.os.environ, {}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "SEC_EDGAR_USER_AGENT"):
                module._edgar_user_agent()
            config = Path(tmp) / ".config/finance-news-digest/edgar.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"user_agent": "Digest file@example.com"}))
            self.assertEqual(module._edgar_user_agent(), "Digest file@example.com")
            with mock.patch.dict(module.os.environ, {"SEC_EDGAR_USER_AGENT": "Digest env@example.com"}):
                self.assertEqual(module._edgar_user_agent(), "Digest env@example.com")


class RepresentativeConfigTest(unittest.TestCase):
    def test_current_symbols_replace_retired_listings(self):
        data = json.loads((ROOT / "config/us_sector_hotspots.json").read_text())
        groups = {item["symbol"]: item["representatives"] for item in data["etfs"]}
        all_symbols = {symbol for group in groups.values() for symbol in group}
        self.assertFalse(all_symbols & {"EA", "FI", "ALTM", "PLL", "MAG", "SQ", "X"})
        self.assertIn("FISV", groups["FINX"])
        self.assertIn("ELVR", all_symbols)
        self.assertIn("XYZ", groups["BLOK"])
        for group in groups.values():
            self.assertGreaterEqual(len(group), 6)
            self.assertEqual(len(group), len(set(group)))


if __name__ == "__main__":
    unittest.main()
