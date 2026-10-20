"""Article inventory stored in data/inventory.json (so runs can work in small batches)."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = 1


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if value else None


class Inventory:
    def __init__(self, path):
        self.path = Path(path)
        self.meta = {"schema": SCHEMA}
        self.records = {}
        self._loaded_text = None

    def load(self):
        if self.path.is_file():
            text = self.path.read_text(encoding="utf-8")
            self._loaded_text = text
            try:
                data = json.loads(text)
                self.meta = data.get("meta", self.meta)
                self.records = data.get("articles", {})
            except ValueError:
                # Corrupt file: start clean rather than crash; the next save repairs it.
                self.meta, self.records = {"schema": SCHEMA}, {}
        return self

    def save(self) -> bool:
        text = json.dumps({"meta": self.meta, "articles": self.records}, indent=1, sort_keys=True,
                          ensure_ascii=False) + "\n"
        if text == self._loaded_text:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)
        self._loaded_text = text
        return True

    def merge_discovered(self, found: dict, now: datetime):
        """found = {url: lastmod}. Marks URLs missing from the sitemap as not in_sitemap."""
        for url, lastmod in found.items():
            rec = self.records.get(url)
            if rec is None:
                self.records[url] = {"first_seen": iso(now), "lastmod": lastmod, "last_fetched": None,
                                     "needs_refresh": False, "failures": 0, "last_failure_at": None,
                                     "last_error": None, "in_sitemap": True, "page": None}
                continue
            rec["in_sitemap"] = True
            if lastmod and lastmod != rec.get("lastmod"):
                rec["lastmod"] = lastmod
                if rec.get("last_fetched"):
                    rec["needs_refresh"] = True
        for url, rec in self.records.items():
            if url not in found:
                rec["in_sitemap"] = False

    def active(self) -> dict:
        return {u: r for u, r in self.records.items() if r.get("in_sitemap", True)}

    def pick_batch(self, size: int, now: datetime, crawl_cfg: dict) -> list:
        cooldown = timedelta(hours=float(crawl_cfg["failure_cooldown_hours"]))
        max_fail = int(crawl_cfg["max_consecutive_failures"])
        recheck = timedelta(days=float(crawl_cfg["recheck_after_days"]))
        new, changed, stale = [], [], []
        for url, rec in self.active().items():
            if rec.get("failures", 0) >= max_fail:
                last = parse_iso(rec.get("last_failure_at"))
                if last and now - last < cooldown:
                    continue
            fetched = parse_iso(rec.get("last_fetched"))
            if fetched is None:
                new.append((rec.get("first_seen") or "", url))
            elif rec.get("needs_refresh"):
                changed.append((rec.get("last_fetched") or "", url))
            elif now - fetched >= recheck:
                stale.append((rec.get("last_fetched") or "", url))
        ordered = [u for _, u in sorted(new)] + [u for _, u in sorted(changed)] + [u for _, u in sorted(stale)]
        return ordered[:size]

    def record_success(self, url: str, page: dict, now: datetime) -> bool:
        """Store extracted page. Returns True when the content differs from last time."""
        rec = self.records[url]
        old = (rec.get("page") or {}).get("content_hash")
        changed = old != page.get("content_hash")
        rec.update({"page": page, "last_fetched": iso(now), "needs_refresh": False,
                    "failures": 0, "last_error": None})
        if changed:
            rec.pop("ai", None)
            rec.pop("ai_failures", None)
        return changed

    def record_failure(self, url: str, message: str, now: datetime):
        rec = self.records[url]
        rec["failures"] = rec.get("failures", 0) + 1
        rec["last_failure_at"] = iso(now)
        rec["last_error"] = message[:200]
