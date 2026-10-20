"""Official Google Search Console API client (read-only).

Authentication: a Google service account whose e-mail has been added as a
(restricted / read-only) user on the Search Console property.
"""
import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger("eda.gsc")
API = "https://www.googleapis.com/webmasters/v3"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


class GSCUnavailable(Exception):
    """Credentials are missing/unusable. The agent keeps running without private data."""


class GSCError(Exception):
    """The API call failed."""


def build_authorized_session(env):
    raw = (env.get("GSC_SERVICE_ACCOUNT_JSON") or "").strip()
    site = (env.get("GSC_SITE_URL") or "").strip()
    if not raw:
        raise GSCUnavailable("GSC_SERVICE_ACCOUNT_JSON secret is not set")
    if not site:
        raise GSCUnavailable("GSC_SITE_URL secret is not set")
    try:
        info = json.loads(raw)
    except ValueError:
        raise GSCUnavailable("GSC_SERVICE_ACCOUNT_JSON is not valid JSON (paste the whole key file)")
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError:
        raise GSCUnavailable("the google-auth package is not installed")
    try:
        creds = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    except (ValueError, KeyError, TypeError):
        raise GSCUnavailable("the service-account JSON is incomplete or malformed")
    return AuthorizedSession(creds), site


class SearchConsoleClient:
    def __init__(self, session, site_url, timeout=30, max_retries=2, sleep=time.sleep):
        self.session, self.site_url = session, site_url
        self.timeout, self.max_retries, self.sleep = timeout, max_retries, sleep

    def _post(self, body):
        url = f"{API}/sites/{quote(self.site_url, safe='')}/searchAnalytics/query"
        err = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.post(url, json=body, timeout=self.timeout)
            except Exception as exc:  # network, auth refresh, etc. Never include details that could hold secrets.
                err = GSCError(f"request failed ({type(exc).__name__})")
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (401, 403):
                    raise GSCError(f"access denied (HTTP {resp.status_code}). Add the service-account e-mail as a user "
                                   "of this property in Search Console and enable the Search Console API.")
                if resp.status_code == 404:
                    raise GSCError("property not found (HTTP 404). Check GSC_SITE_URL matches the property exactly.")
                err = GSCError(f"HTTP {resp.status_code}")
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise err
            if attempt < self.max_retries:
                self.sleep(2 ** (attempt + 1))
        raise err

    def query(self, start: date, end: date, dimensions, row_limit=25000, max_rows=50000):
        rows, start_row = [], 0
        while len(rows) < max_rows:
            data = self._post({"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dimensions,
                               "rowLimit": row_limit, "startRow": start_row})
            batch = data.get("rows", [])
            rows.extend(batch)
            if len(batch) < row_limit:
                break
            start_row += row_limit
        return rows[:max_rows]


def fetch_all(client: SearchConsoleClient, today: date, gsc_cfg: dict) -> dict:
    days = int(gsc_cfg["days"])
    end = today - timedelta(days=3)  # recent days are incomplete
    start = end - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    lim, mx = int(gsc_cfg["row_limit"]), int(gsc_cfg["max_rows"])
    pages = client.query(start, end, ["page"], lim, mx)
    prev = client.query(prev_start, prev_end, ["page"], lim, mx)
    pq = client.query(start, end, ["query", "page"], lim, mx)
    pq.sort(key=lambda r: -r.get("impressions", 0))
    return {"period": {"start": start.isoformat(), "end": end.isoformat(),
                       "prev_start": prev_start.isoformat(), "prev_end": prev_end.isoformat()},
            "pages": pages, "prev_pages": prev, "page_queries": pq[:5000]}


def load_cache(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_cache(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data), encoding="utf-8")
