"""Polite HTTP client: robots.txt, rate limiting, retries, timeouts, size limit."""
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger("eda.http")
UA_TOKEN = "ExamDarpanOrganicTrafficAgent"
RETRY_STATUSES = (429, 500, 502, 503, 504)


class FetchError(Exception):
    def __init__(self, message, status=None, retryable=False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


@dataclass
class Fetched:
    url: str
    final_url: str
    status: int
    content: bytes
    content_type: str


class PoliteClient:
    def __init__(self, crawl_cfg, session=None, sleep=time.sleep, monotonic=time.monotonic):
        self.cfg = crawl_cfg
        self.session = session or requests.Session()
        self.sleep = sleep
        self.monotonic = monotonic
        self._last = None
        self._robots = {}
        self._delay = float(crawl_cfg["request_delay_seconds"])

    def _headers(self):
        return {"User-Agent": self.cfg["user_agent"],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5"}

    def _wait(self):
        if self._last is not None:
            elapsed = self.monotonic() - self._last
            if elapsed < self._delay:
                self.sleep(self._delay - elapsed)
        self._last = self.monotonic()

    @staticmethod
    def _origin(url):
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}"

    def _load_robots(self, url):
        origin = self._origin(url)
        if origin in self._robots:
            return self._robots[origin]
        self._wait()
        try:
            resp = self.session.get(origin + "/robots.txt", headers=self._headers(),
                                    timeout=self.cfg["timeout_seconds"])
        except requests.RequestException as exc:
            raise FetchError(f"robots.txt could not be fetched ({type(exc).__name__})", retryable=True)
        rp = RobotFileParser()
        if resp.status_code == 200:
            rp.parse(resp.content.decode("utf-8", "replace").splitlines())
        elif 400 <= resp.status_code < 500:
            rp.parse([])  # no robots.txt = no restrictions
        else:
            raise FetchError(f"robots.txt returned HTTP {resp.status_code}", resp.status_code, True)
        rp.modified()  # required, otherwise can_fetch() always says no
        delay = rp.crawl_delay(UA_TOKEN)
        if delay:
            self._delay = max(self._delay, min(float(delay), 30.0))
        self._robots[origin] = rp
        return rp

    def can_fetch(self, url) -> bool:
        return self._load_robots(url).can_fetch(UA_TOKEN, url)

    def sitemaps_from_robots(self, base_url) -> list:
        try:
            return list(self._load_robots(base_url).site_maps() or [])
        except FetchError:
            return []

    def get(self, url, respect_robots=True) -> Fetched:
        if respect_robots and not self.can_fetch(url):
            raise FetchError("blocked by robots.txt", retryable=False)
        retries = int(self.cfg["max_retries"])
        last_err = None
        for attempt in range(retries + 1):
            self._wait()
            backoff = 2 ** (attempt + 1)
            try:
                resp = self.session.get(url, headers=self._headers(), timeout=self.cfg["timeout_seconds"],
                                        allow_redirects=True)
            except requests.RequestException as exc:
                last_err = FetchError(f"network error ({type(exc).__name__})", retryable=True)
            else:
                status = resp.status_code
                if status in RETRY_STATUSES:
                    last_err = FetchError(f"HTTP {status}", status, True)
                    ra = resp.headers.get("Retry-After", "")
                    if ra.isdigit():
                        backoff = int(ra)
                elif status != 200:
                    raise FetchError(f"HTTP {status}", status, False)
                else:
                    body = resp.content
                    if len(body) > int(self.cfg["max_page_bytes"]):
                        raise FetchError("page larger than max_page_bytes", 200, False)
                    return Fetched(url, str(getattr(resp, "url", url) or url), status, body,
                                   resp.headers.get("Content-Type", ""))
            if attempt < retries:
                log.warning("Fetch problem for %s (%s); retrying in %ss", url, last_err, min(backoff, 60))
                self.sleep(min(backoff, 60))
        raise last_err
