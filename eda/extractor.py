"""Extract SEO facts from one article page (HTML in, plain dict out)."""
import copy
import json
import re

from bs4 import BeautifulSoup

from . import keywords
from .textutil import (content_hash, find_deadline_dates, normalize_ws, parse_iso_date, top_phrases,
                       top_terms, tokenize)
from .urlutil import host_key, normalize_url

from urllib.parse import urljoin

_STRIP_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"]


def _meta(soup, name):
    tag = soup.find("meta", attrs={"name": re.compile(rf"^{re.escape(name)}$", re.I)})
    return normalize_ws(tag.get("content", "")) if tag else ""


def _meta_prop(soup, prop):
    tag = soup.find("meta", attrs={"property": re.compile(rf"^{re.escape(prop)}$", re.I)})
    return normalize_ws(tag.get("content", "")) if tag else ""


def _jsonld_values(soup, key):
    out = []

    def walk(node):
        if isinstance(node, dict):
            if key in node and isinstance(node[key], str):
                out.append(node[key])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for s in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            walk(json.loads(s.string or s.get_text() or ""))
        except ValueError:
            continue
    return out


def _dates(soup):
    pub = (_meta_prop(soup, "article:published_time") or _meta(soup, "date") or _meta(soup, "publish-date"))
    mod = _meta_prop(soup, "article:modified_time") or _meta_prop(soup, "og:updated_time")
    if not pub:
        tag = soup.find(attrs={"itemprop": "datePublished"})
        pub = (tag.get("content") or tag.get("datetime") or tag.get_text()) if tag else ""
    if not pub:
        vals = _jsonld_values(soup, "datePublished")
        pub = vals[0] if vals else ""
    if not mod:
        tag = soup.find(attrs={"itemprop": "dateModified"})
        mod = (tag.get("content") or tag.get("datetime") or tag.get_text()) if tag else ""
    if not mod:
        vals = _jsonld_values(soup, "dateModified")
        mod = vals[0] if vals else ""
    if not pub:
        t = soup.find("time", attrs={"datetime": True})
        pub = t["datetime"] if t else ""
    p, m = parse_iso_date(pub), parse_iso_date(mod)
    return (p.isoformat() if p else None), (m.isoformat() if m else None)


def extract_article(html, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = normalize_ws(soup.title.get_text()) if soup.title else ""
    robots_meta = _meta(soup, "robots").lower()
    canon_tag = soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, list) else [v]))
    canonical = normalize_url(urljoin(url, canon_tag["href"])) if canon_tag and canon_tag.get("href") else ""
    h1s = [t for t in (normalize_ws(h.get_text()) for h in soup.find_all("h1")) if t]
    h2s = [t for t in (normalize_ws(h.get_text()) for h in soup.find_all("h2")) if t]
    published, modified = _dates(soup)
    script_count = len(soup.find_all("script"))

    container = soup.find("article") or soup.find("main") or soup.body or soup
    work = copy.copy(container)
    for tag in work.find_all(_STRIP_TAGS):
        tag.decompose()
    text = normalize_ws(work.get_text(" "))

    me = host_key(url)
    internal, external = [], 0
    for a in work.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        target = normalize_url(urljoin(url, href))
        if not target.startswith(("http://", "https://")):
            continue
        if host_key(target) == me:
            if target != normalize_url(url) and target not in internal:
                internal.append(target)
        else:
            external += 1

    low = text.lower()
    years = sorted({int(y) for y in re.findall(r"\b(20[0-3]\d)\b", text)})
    html_tag = soup.find("html")
    return {
        "title": title,
        "description": _meta(soup, "description"),
        "canonical": canonical,
        "noindex": "noindex" in robots_meta,
        "h1s": h1s,
        "h2s": h2s,
        "published": published,
        "modified": modified,
        "word_count": len(tokenize(text)),
        "internal_links": internal,
        "external_link_count": external,
        "images_missing_alt": sum(1 for i in work.find_all("img") if not (i.get("alt") or "").strip()),
        "script_count": script_count,
        "lang": (html_tag.get("lang") if html_tag else "") or "",
        "years": years,
        "deadline_dates": find_deadline_dates(text),
        "top_terms": top_terms(text, 15),
        "phrases": top_phrases(text, 12),
        "intents_present": keywords.intents_present(low + " " + title.lower()),
        "exam_related": keywords.looks_exam_related(low[:3000] + " " + title.lower()),
        "excerpt": text[:1200],
        "content_hash": content_hash("|".join([title, _meta(soup, "description"), text])),
    }
