import gzip
import unittest

from eda.config import DEFAULTS
from eda.http_client import FetchError
from eda.sitemap import SitemapError, discover_article_urls, is_article_url, parse_sitemap
from tests.helpers import FakeResp, fixture, make_client, site_routes


class SitemapTests(unittest.TestCase):
    def test_parse_index(self):
        kind, entries = parse_sitemap(fixture("sitemap_index.xml"))
        self.assertEqual(kind, "index")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["lastmod"], "2026-10-01")

    def test_parse_urlset_and_gzip(self):
        kind, entries = parse_sitemap(gzip.compress(fixture("sitemap_posts.xml")))
        self.assertEqual(kind, "urlset")
        self.assertEqual(len(entries), 6)

    def test_invalid_xml_and_wrong_root(self):
        with self.assertRaises(SitemapError):
            parse_sitemap(b"<urlset><url>")
        with self.assertRaises(SitemapError):
            parse_sitemap(b"<html></html>")

    def test_article_filter(self):
        site = DEFAULTS["site"]
        base = "https://examdarpan.in"
        self.assertTrue(is_article_url("https://examdarpan.in/some-post", site, base))
        self.assertTrue(is_article_url("https://www.examdarpan.in/some-post", site, base))
        for bad in ("https://examdarpan.in/", "https://examdarpan.in/tag/x/", "https://examdarpan.in/a.png",
                    "https://evil.com/some-post"):
            self.assertFalse(is_article_url(bad, site, base), bad)

    def test_discovery_skips_broken_child_and_filters(self):
        found = discover_article_urls(make_client(), DEFAULTS["site"])
        self.assertEqual(sorted(found), ["https://examdarpan.in/bstc-refund-guide",
                                         "https://examdarpan.in/rajasthan-patwari-recruitment-2026"])
        self.assertEqual(found["https://examdarpan.in/rajasthan-patwari-recruitment-2026"], "2026-10-02")

    def test_discovery_fails_cleanly_when_all_sitemaps_down(self):
        routes = site_routes()
        routes["https://examdarpan.in/sitemap.xml"] = FakeResp(503)
        with self.assertRaises(SitemapError):
            discover_article_urls(make_client(routes), DEFAULTS["site"])


if __name__ == "__main__":
    unittest.main()
