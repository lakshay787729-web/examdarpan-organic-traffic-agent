"""Sitemap index / urlset parsing and article URL discovery."""
import gzip
import logging
import re
from urllib.parse import urlsplit

from lxml import etree

from .http_client import FetchError
from .urlutil import host_key, normalize_url

log = logging.getLogger("eda.sitemap")
MAX_SITEMAP_BYTES = 20_000_000


class SitemapError(Exception):
    pass


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_sitemap(data: bytes):
    """Return ('index'|'urlset', [{'loc':..., 'lastmod':...}, ...])."""
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)[:MAX_SITEMAP_BYTES]
        except (OSError, EOFError) as exc:
            raise SitemapError("could not decompress sitemap") from exc
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise SitemapError(f"sitemap is not valid XML: {exc}") from exc
    kind = _local(root.tag)
    if kind not in ("sitemapindex", "urlset"):
        raise SitemapError(f"unexpected sitemap root element: {kind!r}")
    entries = []
    for child in root:
        loc = lastmod = None
        for el in child:
            name = _local(el.tag)
            if name == "loc":
                loc = (el.text or "").strip()
            elif name == "lastmod":
                lastmod = (el.text or "").strip() or None
        if loc:
            entries.append({"loc": loc, "lastmod": lastmod})
    return ("index" if kind == "sitemapindex" else "urlset"), entries


def is_article_url(url: str, site_cfg: dict, base_url: str) -> bool:
    if host_key(url) != host_key(base_url):
        return False
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    path = parts.path or "/"
    if site_cfg.get("exclude_homepage", True) and path == "/":
        return False
    target = path + (("?" + parts.query) if parts.query else "")
    if any(re.search(p, target) for p in site_cfg.get("exclude_patterns", [])):
        return False
    include = site_cfg.get("include_patterns", [])
    return not include or any(re.search(p, target) for p in include)


def discover_article_urls(client, site_cfg, max_sitemaps=50, max_depth=3):
    """Walk sitemap index + child sitemaps. Returns {normalized_url: lastmod}."""
    base = site_cfg["base_url"]
    queue = [(u, 0) for u in site_cfg.get("sitemap_urls", [])]
    for u in client.sitemaps_from_robots(base):
        queue.append((u, 0))
    seen, found, ok_count, fetched = set(), {}, 0, 0
    while queue and fetched < max_sitemaps:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        fetched += 1
        try:
            resp = client.get(url)
            kind, entries = parse_sitemap(resp.content)
        except (FetchError, SitemapError) as exc:
            log.warning("Could not read sitemap %s: %s", url, exc)
            continue
        ok_count += 1
        if kind == "index":
            if depth < max_depth:
                queue.extend((e["loc"], depth + 1) for e in entries)
            continue
        for e in entries:
            if is_article_url(e["loc"], site_cfg, base):
                found[normalize_url(e["loc"])] = e["lastmod"]
    if ok_count == 0:
        raise SitemapError("none of the sitemaps could be read")
    log.info("Sitemap discovery: %d article URLs from %d sitemap file(s)", len(found), ok_count)
    return found
