"""One agent run: discover -> read a small batch -> analyze -> (optional GSC/AI) -> write reports."""
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from . import report
from .ai_provider import AIError, build_prompt, build_provider
from .extractor import extract_article
from .gsc_analysis import analyze_gsc
from .http_client import FetchError, PoliteClient
from .inventory import Inventory, iso, parse_iso
from .keywords import build_ideas
from .search_console import (GSCError, GSCUnavailable, SearchConsoleClient, build_authorized_session,
                             fetch_all, load_cache, save_cache)
from .seo_analysis import analyze_site, score
from .sitemap import SitemapError, discover_article_urls
from .urlutil import normalize_url

log = logging.getLogger("eda.run")


def _refresh_gsc(cfg, env, root, now, force, gsc_client):
    """Return (analysis_or_None, status_text, error_flag)."""
    g = cfg["gsc"]
    if not g["enabled"]:
        return None, "Search Console is switched off in config.yaml.", False
    cache_path = Path(root) / ".cache" / "gsc_cache.json"
    cache = load_cache(cache_path)
    fresh = bool(cache) and not force and cache.get("fetched_at") and \
        (now - parse_iso(cache["fetched_at"])).total_seconds() < g["refresh_hours"] * 3600
    status = None
    if not fresh:
        try:
            client = gsc_client
            if client is None:
                session, site = build_authorized_session(env)
                client = SearchConsoleClient(session, site, timeout=cfg["crawl"]["timeout_seconds"] + 10)
            data = fetch_all(client, now.date(), g)
            data["fetched_at"] = iso(now)
            save_cache(cache_path, data)
            cache = data
            status = "Search Console data refreshed (actual API data)."
        except GSCUnavailable as exc:
            log.info("Search Console unavailable: %s", exc)
            if not cache:
                return None, f"UNAVAILABLE: {exc}. Public website checks still ran; private Search Console analytics were skipped.", False
            status = f"Using older cached Search Console data ({exc})."
        except GSCError as exc:
            log.warning("Search Console error: %s", exc)
            if not cache:
                return None, f"ERROR: {exc}. Public website checks still ran.", True
            status = f"Using older cached Search Console data (refresh failed: {exc})."
    else:
        status = "Search Console data loaded from cache (refreshed at most once per day)."
    return analyze_gsc(cache, g), status, False


def run(cfg, env, root=".", client=None, gsc_client=None, ai_provider="auto", now=None,
        force_sitemap=False, force_gsc=False, batch_size=None) -> dict:
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    today = now.date()
    started = time.monotonic()
    crawl = cfg["crawl"]
    inv = Inventory(root / "data" / "inventory.json").load()
    client = client or PoliteClient(crawl)
    stats = {"fetched": 0, "failed": 0, "changed": 0, "ai_calls": 0, "sitemap": "skipped", "errors": []}

    # 1. sitemap discovery (at most every sitemap_refresh_hours)
    slot = int(now.timestamp() // (3600 * crawl["sitemap_refresh_hours"]))
    retry_after = parse_iso(inv.meta.get("sitemap_retry_after"))
    if force_sitemap or (inv.meta.get("sitemap_slot") != slot and not (retry_after and now < retry_after)):
        try:
            found = discover_article_urls(client, cfg["site"])
            inv.merge_discovered(found, now)
            inv.meta["sitemap_slot"] = slot
            inv.meta.pop("sitemap_retry_after", None)
            stats["sitemap"] = f"ok ({len(found)} urls)"
        except (SitemapError, FetchError) as exc:
            log.warning("Sitemap discovery failed: %s", exc)
            stats["sitemap"] = f"failed: {exc}"
            stats["errors"].append(str(exc))
            inv.meta["sitemap_retry_after"] = iso(datetime.fromtimestamp(now.timestamp() + 1800, timezone.utc))

    # 2. read a small batch of articles
    batch = inv.pick_batch(batch_size or crawl["batch_size"], now, crawl)
    processed = []
    for url in batch:
        if time.monotonic() - started > crawl["max_runtime_seconds"]:
            log.warning("Runtime budget reached; stopping early")
            break
        try:
            fetched = client.get(url)
            if "html" not in fetched.content_type.lower() and fetched.content_type:
                raise FetchError(f"not an HTML page ({fetched.content_type.split(';')[0]})")
            page = extract_article(fetched.content, url)
            page["status"] = fetched.status
            page["final_url"] = normalize_url(fetched.final_url)
            if inv.record_success(url, page, now):
                stats["changed"] += 1
            stats["fetched"] += 1
            processed.append(url)
        except FetchError as exc:
            inv.record_failure(url, str(exc), now)
            stats["failed"] += 1
            log.warning("Could not read %s: %s", url, exc)
        except Exception as exc:  # a parsing bug on one page must not stop the run
            inv.record_failure(url, f"parse error ({type(exc).__name__})", now)
            stats["failed"] += 1
            log.exception("Unexpected error while reading %s", url)

    # 3. Search Console (optional)
    gsc_analysis, gsc_status, gsc_err = _refresh_gsc(cfg, env, root, now, force_gsc, gsc_client)
    if gsc_err:
        stats["errors"].append(gsc_status)

    # 4. deterministic analysis
    records = inv.active()
    issues_by_url, site_info = analyze_site(records, cfg["analysis"], today)
    ideas = {u: build_ideas(r["page"], cfg["keywords"]) for u, r in records.items() if r.get("page")}

    # 5. optional AI (small, bounded, never required)
    provider = build_provider(cfg["ai"], env) if ai_provider == "auto" else ai_provider
    if provider is None:
        ai_state = "Off (no provider/key configured). Only deterministic checks are used."
    else:
        ai_state = f"On ({cfg['ai']['provider']}, max {cfg['ai']['max_calls_per_run']} call(s) per run). Suggestions need human review."
        cands = [u for u in processed if records[u].get("page")]
        rest = sorted((u for u, r in records.items() if r.get("page") and u not in cands),
                      key=lambda u: (score(issues_by_url[u]), u))
        for url in cands + rest:
            rec = records[url]
            if stats["ai_calls"] >= cfg["ai"]["max_calls_per_run"]:
                break
            if rec.get("ai", {}).get("hash") == rec["page"]["content_hash"] or rec.get("ai_failures", 0) >= 3:
                continue
            try:
                text = provider.generate(build_prompt(rec["page"], issues_by_url[url], ideas[url], cfg["ai"]["max_input_chars"]))
                rec["ai"] = {"hash": rec["page"]["content_hash"], "text": text}
                stats["ai_calls"] += 1
            except AIError as exc:
                rec["ai_failures"] = rec.get("ai_failures", 0) + 1
                log.warning("AI suggestion failed for %s: %s", url, exc)
                stats["errors"].append(str(exc))
                break

    # 6. reports (only rewritten when content changes)
    show = cfg["reports"]["show_search_console_numbers"]
    rdir = root / "reports"
    changed_files = 0
    rows = []
    by_gsc = (gsc_analysis or {}).get("by_page", {})
    tq = (gsc_analysis or {}).get("top_queries", {})
    for url, rec in records.items():
        issues = issues_by_url.get(url, [])
        g = by_gsc.get(url)
        flags = g["flags"] if g else []
        if rec.get("page"):
            md = report.render_article(url, rec, issues, ideas[url], site_info["related"].get(url, []), g,
                                       tq.get(url, []), rec.get("ai"), show)
            changed_files += report.write_if_changed(rdir / "articles" / f"{report.slug(url)}.md", md)
        rows.append({"url": url, "title": (rec.get("page") or {}).get("title", ""), "score": score(issues),
                     "priority": report.priority(issues, flags), "flags": flags, "top": issues[:3]})
    rows.sort(key=lambda r: (-r["priority"], r["url"]))
    rows = [r for r in rows if r["priority"] > 0]
    changed_files += report.write_if_changed(rdir / "summary.md", report.render_summary(
        site_info, issues_by_url, rows, gsc_status, cfg["reports"]["max_priority_items"], ai_state))
    changed_files += report.write_if_changed(rdir / "issues.csv", report.render_issues_csv(issues_by_url))
    changed_files += report.write_if_changed(rdir / "search_console.md", report.render_gsc_report(gsc_status, gsc_analysis, show))
    inv_changed = inv.save()
    stats.update({"report_files_changed": changed_files, "inventory_changed": inv_changed,
                  "articles_total": site_info["total"], "articles_read": site_info["fetched"],
                  "gsc": gsc_status, "ai": ai_state})
    log.info("Run complete: %s", {k: v for k, v in stats.items() if k not in ("gsc", "ai")})
    return stats
