import copy
import io
import json
import logging
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from eda.ai_provider import AIError, build_provider
from eda.config import load_config
from eda.logging_utils import collect_secrets, redact, setup_logging
from eda.runner import run
from tests.helpers import FakeResp, make_client, site_routes

NOW = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)
GOOD = "https://examdarpan.in/rajasthan-patwari-recruitment-2026"


def cfg():
    return load_config(overrides={"crawl": {"batch_size": 5}})


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_run_without_gsc_credentials(self):
        stats = run(cfg(), {}, self.root, client=make_client(), now=NOW, ai_provider=None)
        self.assertEqual(stats["fetched"], 2)
        self.assertTrue(stats["sitemap"].startswith("ok"))
        summary = (self.root / "reports" / "summary.md").read_text(encoding="utf-8")
        self.assertIn("UNAVAILABLE", summary)
        self.assertIn("GSC_SERVICE_ACCOUNT_JSON secret is not set", summary)
        self.assertTrue((self.root / "reports" / "issues.csv").is_file())
        self.assertEqual(len(list((self.root / "reports" / "articles").glob("*.md"))), 2)
        self.assertIn("unavailable".lower(), (self.root / "reports" / "search_console.md").read_text().lower() + "unavailable")

    def test_second_run_is_idle_and_changes_nothing(self):
        run(cfg(), {}, self.root, client=make_client(), now=NOW, ai_provider=None)
        c2 = make_client()
        stats = run(cfg(), {}, self.root, client=c2, now=NOW + timedelta(minutes=5), ai_provider=None)
        self.assertEqual(stats["fetched"], 0)
        self.assertEqual(stats["sitemap"], "skipped")
        self.assertEqual(c2.session.calls, [])  # no network at all
        self.assertEqual(stats["report_files_changed"], 0)
        self.assertFalse(stats["inventory_changed"])

    def test_changed_lastmod_triggers_refetch_but_not_everything(self):
        run(cfg(), {}, self.root, client=make_client(), now=NOW, ai_provider=None)
        routes = site_routes()
        later = NOW + timedelta(hours=7)
        sm = routes["https://examdarpan.in/sitemap-posts.xml"].content.replace(b"2026-10-02", b"2026-10-19")
        routes["https://examdarpan.in/sitemap-posts.xml"] = FakeResp(200, sm)
        c = make_client(routes)
        stats = run(cfg(), {}, self.root, client=c, now=later, ai_provider=None)
        self.assertEqual(stats["fetched"], 1)
        self.assertEqual(c.session.calls.count(GOOD), 1)

    def test_network_failure_is_recorded_not_fatal_and_cools_down(self):
        routes = site_routes()
        routes[GOOD] = requests.ConnectionError("down")
        stats = run(cfg(), {}, self.root, client=make_client(routes), now=NOW, ai_provider=None)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["fetched"], 1)
        inv = json.loads((self.root / "data" / "inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(inv["articles"][GOOD]["failures"], 1)
        csv_text = (self.root / "reports" / "issues.csv").read_text(encoding="utf-8")
        self.assertIn("FETCH_FAILED", csv_text)

    def test_sitemap_outage_does_not_crash_and_backs_off(self):
        routes = {"https://examdarpan.in/robots.txt": FakeResp(200, b"")}
        stats = run(cfg(), {}, self.root, client=make_client(routes), now=NOW, ai_provider=None)
        self.assertTrue(stats["sitemap"].startswith("failed"))
        c = make_client(routes)
        stats2 = run(cfg(), {}, self.root, client=c, now=NOW + timedelta(minutes=5), ai_provider=None)
        self.assertEqual(stats2["sitemap"], "skipped")  # waits 30 min before retrying
        self.assertEqual(c.session.calls, [])

    def test_gsc_with_fake_client_and_number_hiding(self):
        class FakeGSC:
            def query(self, start, end, dims, row_limit=0, max_rows=0):
                if dims == ["page"]:
                    return [{"keys": [GOOD], "clicks": 0, "impressions": 900, "ctr": 0.0, "position": 4.0}]
                return [{"keys": ["patwari 2026", GOOD], "clicks": 0, "impressions": 900, "ctr": 0.0, "position": 4.0}]

        run(cfg(), {}, self.root, client=make_client(), gsc_client=FakeGSC(), now=NOW, ai_provider=None)
        text = "\n".join(p.read_text(encoding="utf-8") for p in (self.root / "reports").rglob("*.md"))
        self.assertIn("LOW_CTR".lower() and "Shown in Google often", text)
        self.assertNotIn("900", text)            # numbers hidden by default
        self.assertNotIn("patwari 2026", text)   # queries hidden by default
        cfg2 = load_config(overrides={"crawl": {"batch_size": 5}, "reports": {"show_search_console_numbers": True}})
        run(cfg2, {}, self.root, client=make_client(), gsc_client=FakeGSC(), now=NOW, ai_provider=None)
        text = (self.root / "reports" / "search_console.md").read_text(encoding="utf-8")
        self.assertIn("900 impressions", text)

    def test_ai_optional_and_bounded(self):
        class FakeAI:
            n = 0

            def generate(self, prompt):
                FakeAI.n += 1
                return "AI TITLE IDEA"

        c = load_config(overrides={"crawl": {"batch_size": 5}, "ai": {"max_calls_per_run": 1}})
        run(c, {}, self.root, client=make_client(), now=NOW, ai_provider=FakeAI())
        self.assertEqual(FakeAI.n, 1)

        class BrokenAI:
            def generate(self, prompt):
                raise AIError("AI provider returned HTTP 500")

        stats = run(c, {}, self.root, client=make_client(), now=NOW + timedelta(minutes=5), ai_provider=BrokenAI())
        self.assertEqual(stats["fetched"], 0)  # AI failure does not break anything
        self.assertIn("AI provider returned HTTP 500", stats["errors"])

    def test_no_ai_without_key(self):
        c = load_config(overrides={"ai": {"provider": "gemini"}})
        self.assertIsNone(build_provider(c["ai"], {}))
        self.assertIsNotNone(build_provider(c["ai"], {"AI_API_KEY": "abcdef123456"}))


class SecretLoggingTests(unittest.TestCase):
    def test_secrets_never_reach_log_output(self):
        key = "AIzaSyFAKEKEYFAKEKEYFAKEKEY123456"
        sa = json.dumps({"private_key": "-----BEGIN PRIVATE KEY-----\nMIIFAKE\n-----END PRIVATE KEY-----\n",
                         "private_key_id": "abcdef1234567890", "client_email": "x@y.iam.gserviceaccount.com"})
        env = {"AI_API_KEY": key, "GSC_SERVICE_ACCOUNT_JSON": sa}
        with tempfile.TemporaryDirectory() as d:
            log = setup_logging(d, "DEBUG", env, console=False)
            log.info("key is %s", key)
            log.info("sa is %s", sa)
            log.info("pk %s", json.loads(sa)["private_key"])
            log.info("Authorization: Bearer abcdefghijklmnop123")
            try:
                raise RuntimeError("failed with " + key)
            except RuntimeError:
                log.exception("boom")
            for h in log.handlers:
                h.flush()
            content = (Path(d) / "agent.log").read_text(encoding="utf-8")
            for h in list(log.handlers):
                h.close()
                log.removeHandler(h)
        for secret in (key, "MIIFAKE", "abcdef1234567890", "abcdefghijklmnop123"):
            self.assertNotIn(secret, content)
        self.assertIn("***", content)

    def test_redact_function(self):
        self.assertEqual(redact("a SECRET123 b", ["SECRET123"]), "a *** b")
        self.assertEqual(collect_secrets({}), [])


if __name__ == "__main__":
    unittest.main()
