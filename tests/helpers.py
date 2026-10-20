"""Shared test helpers: fake HTTP session serving saved fixtures."""
import copy
from pathlib import Path

import requests

from eda.config import DEFAULTS

FIX = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


class FakeResp:
    def __init__(self, status=200, content=b"", headers=None, url=""):
        self.status_code, self.content, self.headers, self.url = status, content, headers or {}, url

    def json(self):
        import json
        return json.loads(self.content)


class FakeSession:
    """routes: {url: FakeResp | Exception | list-of-those (consumed in order)}"""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, **kw):
        self.calls.append(url)
        r = self.routes.get(url)
        if r is None:
            return FakeResp(404, b"", {}, url)
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, Exception):
            raise r
        r.url = r.url or url
        return r

    post = get


def fast_crawl_cfg():
    cfg = copy.deepcopy(DEFAULTS["crawl"])
    cfg["request_delay_seconds"] = 1
    cfg["max_retries"] = 2
    return cfg


def site_routes():
    ok = {"Content-Type": "application/xml"}
    html = {"Content-Type": "text/html; charset=utf-8"}
    return {
        "https://examdarpan.in/robots.txt": FakeResp(200, b"User-agent: *\nDisallow: /private/\nSitemap: https://examdarpan.in/sitemap.xml\n"),
        "https://examdarpan.in/sitemap.xml": FakeResp(200, fixture("sitemap_index.xml"), ok),
        "https://examdarpan.in/sitemap-posts.xml": FakeResp(200, fixture("sitemap_posts.xml"), ok),
        "https://examdarpan.in/sitemap-broken.xml": FakeResp(500, b""),
        "https://examdarpan.in/rajasthan-patwari-recruitment-2026": FakeResp(200, fixture("article_good.html"), html),
        "https://examdarpan.in/bstc-refund-guide": FakeResp(200, fixture("article_bad.html"), html),
    }


def make_client(routes=None):
    from eda.http_client import PoliteClient
    sleeps = []
    c = PoliteClient(fast_crawl_cfg(), session=FakeSession(routes if routes is not None else site_routes()),
                     sleep=sleeps.append)
    c.sleeps = sleeps
    return c
