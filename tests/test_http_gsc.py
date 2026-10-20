import json
import unittest

import requests

from eda.config import DEFAULTS
from eda.gsc_analysis import analyze_gsc
from eda.http_client import FetchError, PoliteClient
from eda.search_console import (GSCError, GSCUnavailable, SearchConsoleClient, build_authorized_session)
from tests.helpers import FakeResp, FakeSession, fast_crawl_cfg, make_client, site_routes


class HttpTests(unittest.TestCase):
    def test_robots_disallow_blocks_fetch_without_requesting_page(self):
        c = make_client()
        with self.assertRaises(FetchError) as cm:
            c.get("https://examdarpan.in/private/page")
        self.assertIn("robots", str(cm.exception))
        self.assertNotIn("https://examdarpan.in/private/page", c.session.calls)

    def test_retry_then_success_and_rate_limit(self):
        routes = site_routes()
        url = "https://examdarpan.in/rajasthan-patwari-recruitment-2026"
        ok = routes[url]
        routes[url] = [FakeResp(503, b"", {"Retry-After": "7"}), ok]
        c = make_client(routes)
        self.assertEqual(c.get(url).status, 200)
        self.assertIn(7, c.sleeps)  # Retry-After honoured

    def test_gives_up_after_retries(self):
        routes = site_routes()
        url = "https://examdarpan.in/x"
        routes[url] = FakeResp(503)
        c = make_client(routes)
        with self.assertRaises(FetchError) as cm:
            c.get(url)
        self.assertTrue(cm.exception.retryable)
        self.assertEqual(c.session.calls.count(url), 3)  # 1 try + 2 retries

    def test_network_exception_becomes_fetch_error(self):
        routes = site_routes()
        routes["https://examdarpan.in/x"] = requests.ConnectionError("boom secret-token")
        c = make_client(routes)
        with self.assertRaises(FetchError) as cm:
            c.get("https://examdarpan.in/x")
        self.assertNotIn("secret-token", str(cm.exception))

    def test_404_not_retried(self):
        c = make_client()
        with self.assertRaises(FetchError) as cm:
            c.get("https://examdarpan.in/missing")
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(c.session.calls.count("https://examdarpan.in/missing"), 1)

    def test_robots_unreachable_means_skip(self):
        c = make_client({"https://examdarpan.in/robots.txt": FakeResp(500)})
        with self.assertRaises(FetchError):
            c.get("https://examdarpan.in/a")

    def test_too_large_page(self):
        routes = site_routes()
        routes["https://examdarpan.in/big"] = FakeResp(200, b"x" * 100)
        cfg = dict(fast_crawl_cfg(), max_page_bytes=50)
        c = PoliteClient(cfg, session=FakeSession(routes), sleep=lambda s: None)
        with self.assertRaises(FetchError):
            c.get("https://examdarpan.in/big")


class GscTests(unittest.TestCase):
    def test_missing_credentials(self):
        for env in ({}, {"GSC_SERVICE_ACCOUNT_JSON": "{}"}, {"GSC_SERVICE_ACCOUNT_JSON": "not json", "GSC_SITE_URL": "sc-domain:x.in"},
                    {"GSC_SERVICE_ACCOUNT_JSON": "{}", "GSC_SITE_URL": "sc-domain:x.in"}):
            with self.assertRaises(GSCUnavailable):
                build_authorized_session(env)

    def test_paging_and_url_encoding(self):
        calls = []

        class S:
            def post(self, url, json=None, timeout=None):
                calls.append((url, json["startRow"]))
                n = 2 if json["startRow"] == 0 else 1
                return FakeResp(200, __import__("json").dumps({"rows": [{"keys": ["a"]}] * n}).encode())

        from datetime import date
        rows = SearchConsoleClient(S(), "sc-domain:x.in").query(date(2026, 1, 1), date(2026, 1, 2), ["page"], row_limit=2)
        self.assertEqual(len(rows), 3)
        self.assertEqual([c[1] for c in calls], [0, 2])
        self.assertIn("sites/", calls[0][0])

    def test_access_denied_and_retry_failure(self):
        from datetime import date
        denied = type("S", (), {"post": lambda s, *a, **k: FakeResp(403)})()
        with self.assertRaises(GSCError) as cm:
            SearchConsoleClient(denied, "sc-domain:x.in").query(date(2026, 1, 1), date(2026, 1, 2), ["page"])
        self.assertIn("service-account", str(cm.exception))
        flaky = type("S", (), {"post": lambda s, *a, **k: FakeResp(503)})()
        slept = []
        with self.assertRaises(GSCError):
            SearchConsoleClient(flaky, "x", sleep=slept.append).query(date(2026, 1, 1), date(2026, 1, 2), ["page"])
        self.assertEqual(len(slept), 2)

    def test_network_failure_message_has_no_details(self):
        from datetime import date

        class S:
            def post(self, *a, **k):
                raise ConnectionError("token=SUPERSECRET")

        with self.assertRaises(GSCError) as cm:
            SearchConsoleClient(S(), "x", sleep=lambda s: None).query(date(2026, 1, 1), date(2026, 1, 2), ["page"])
        self.assertNotIn("SUPERSECRET", str(cm.exception))

    def test_analysis_flags(self):
        def row(keys, clicks, imp, pos):
            return {"keys": keys, "clicks": clicks, "impressions": imp, "ctr": clicks / imp if imp else 0, "position": pos}
        data = {"pages": [row(["https://examdarpan.in/a/"], 0, 500, 3.0),
                          row(["https://examdarpan.in/b"], 5, 200, 12.0),
                          row(["https://examdarpan.in/c"], 2, 10, 4.0),
                          row(["https://examdarpan.in/d"], 5, 300, 2.0)],
                "prev_pages": [row(["https://examdarpan.in/d"], 50, 900, 2.0)],
                "page_queries": [row(["patwari", "https://examdarpan.in/a"], 0, 100, 3.0),
                                 row(["patwari", "https://examdarpan.in/b"], 1, 40, 12.0),
                                 row(["solo", "https://examdarpan.in/a"], 0, 90, 3.0)]}
        res = analyze_gsc(data, DEFAULTS["gsc"])
        a = res["by_page"]["https://examdarpan.in/a"]["flags"]
        self.assertTrue({"LOW_CTR", "FEW_CLICKS"} <= set(a))
        self.assertIn("STRIKING_DISTANCE", res["by_page"]["https://examdarpan.in/b"]["flags"])
        self.assertEqual(res["by_page"]["https://examdarpan.in/c"]["flags"], [])  # too few impressions
        self.assertIn("DECLINING", res["by_page"]["https://examdarpan.in/d"]["flags"])
        self.assertEqual([c["query"] for c in res["cannibalization"]], ["patwari"])


if __name__ == "__main__":
    unittest.main()
