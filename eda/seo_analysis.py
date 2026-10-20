"""Deterministic SEO checks. No network, no AI: plain rules a beginner can follow."""
from datetime import date

from .textutil import STOPWORDS, normalize_ws, tokenize
from .urlutil import normalize_url

WEIGHT = {"high": 15, "medium": 7, "low": 3}
ORDER = {"high": 0, "medium": 1, "low": 2}


def issue(url, code, severity, message, fix):
    return {"url": url, "code": code, "severity": severity, "message": message, "fix": fix}


def score(issues) -> int:
    return max(0, 100 - sum(WEIGHT[i["severity"]] for i in issues))


def _trim_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-|")


def analyze_page(url, page, th, today: date) -> list:
    out = []
    title, desc = page.get("title", ""), page.get("description", "")
    if not title:
        out.append(issue(url, "TITLE_MISSING", "high", "The page has no <title>.", "Add a clear title that includes the main topic."))
    elif len(title) < th["title_min"]:
        out.append(issue(url, "TITLE_SHORT", "low", f"Title is short ({len(title)} characters).",
                         f"Expand it toward {th['title_min']}-{th['title_max']} characters with the main topic."))
    elif len(title) > th["title_max"]:
        out.append(issue(url, "TITLE_LONG", "low", f"Title is long ({len(title)} characters) and may be cut off in Google.",
                         f"Shorten to about {th['title_max']} characters. Idea: \"{_trim_words(title, th['title_max'])}\""))
    if not desc:
        out.append(issue(url, "DESC_MISSING", "medium", "No meta description.",
                         "Write a 1-2 sentence summary (about 120-155 characters) that makes people want to click."))
    elif len(desc) < th["description_min"]:
        out.append(issue(url, "DESC_SHORT", "low", f"Meta description is short ({len(desc)} characters).",
                         "Add a little more useful detail (dates, who it is for)."))
    elif len(desc) > th["description_max"]:
        out.append(issue(url, "DESC_LONG", "low", f"Meta description is long ({len(desc)} characters).",
                         f"Shorten to about {th['description_max']} characters."))
    h1s = page.get("h1s", [])
    if not h1s:
        out.append(issue(url, "H1_MISSING", "medium", "No H1 heading.", "Add exactly one H1 with the main topic."))
    elif len(h1s) > 1:
        out.append(issue(url, "H1_MULTIPLE", "low", f"{len(h1s)} H1 headings found.", "Keep one H1; make the others H2."))
    if not page.get("h2s"):
        out.append(issue(url, "H2_NONE", "low", "No H2 sub-headings.", "Split the article into sections with H2 headings (e.g. Eligibility, Last Date, How to Apply)."))
    words, scripts = page.get("word_count", 0), page.get("script_count", 0)
    if words < 80 and scripts >= 3:
        out.append(issue(url, "JS_RENDER_SUSPECTED", "high",
                         f"Only {words} words were visible in the raw HTML but the page loads {scripts} scripts. "
                         "The content may be added by JavaScript, which this agent cannot see.",
                         "Check the page with URL Inspection in Search Console. Prefer server-rendered or pre-rendered article text."))
    elif words < th["thin_words"]:
        out.append(issue(url, "THIN_CONTENT", "medium", f"Only {words} words of article text.",
                         "Add genuinely useful detail: eligibility, important dates, steps to apply, official links, FAQs."))
    if not page.get("canonical"):
        out.append(issue(url, "CANONICAL_MISSING", "low", "No canonical link.", "Add <link rel=\"canonical\"> pointing to this page's preferred URL."))
    elif normalize_url(page["canonical"]) != normalize_url(url):
        out.append(issue(url, "CANONICAL_DIFFERENT", "medium", f"Canonical points to a different URL: {page['canonical']}",
                         "If this is not intentional, fix it, otherwise Google may ignore this page."))
    if page.get("noindex"):
        out.append(issue(url, "NOINDEX", "high", "The page has a noindex robots tag, so Google will not show it.", "Remove noindex if this article should appear in search."))
    if len(page.get("internal_links", [])) < th["min_internal_links"]:
        out.append(issue(url, "FEW_INTERNAL_LINKS", "medium", f"Only {len(page.get('internal_links', []))} links to other Exam Darpan pages.",
                         "Link to related articles where it helps readers (see suggestions below)."))
    if page.get("images_missing_alt", 0):
        out.append(issue(url, "IMG_ALT_MISSING", "low", f"{page['images_missing_alt']} image(s) without alt text.", "Add short descriptive alt text."))
    if page.get("final_url") and normalize_url(page["final_url"]) != normalize_url(url):
        out.append(issue(url, "REDIRECTED", "medium", f"The sitemap URL redirects to {page['final_url']}.", "List the final URL in the sitemap instead."))

    latest = page.get("modified") or page.get("published")
    if not latest:
        out.append(issue(url, "NO_DATE", "low", "No publish or update date found.", "Show and mark up a published/updated date so readers and Google can judge freshness."))
    else:
        try:
            age = (today - date.fromisoformat(latest)).days
        except ValueError:
            age = 0
        if age > th["stale_days"]:
            out.append(issue(url, "OLD_CONTENT", "medium", f"Last updated about {age // 30} months ago ({latest}).",
                             "Re-check the facts against the official source and refresh the article if anything changed."))
    years = page.get("years", [])
    if years and max(years) < today.year and page.get("exam_related"):
        out.append(issue(url, "OLD_YEAR_ONLY", "medium", f"The newest year mentioned is {max(years)}, but it is {today.year}.",
                         "Verify whether newer notices/results exist and update the year only if the facts are confirmed."))
    past = [d for d in page.get("deadline_dates", []) if d < today.isoformat()]
    if past:
        out.append(issue(url, "DEADLINE_PASSED", "medium", f"Mentions deadline date(s) already passed: {', '.join(past[:3])}.",
                         "Make clear whether applications are closed, or update after checking the official notice."))
    return out


def _title_tokens(title):
    return {t for t in tokenize(title) if t not in STOPWORDS and len(t) > 1}


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def analyze_site(records: dict, th: dict, today: date):
    """records: {url: record}. Returns (issues_by_url, site_info)."""
    pages = {u: dict(r["page"], url=u) for u, r in records.items() if r.get("page")}
    issues = {u: analyze_page(u, p, th, today) for u, p in pages.items()}
    total = len(records)
    coverage = len(pages) / total if total else 0.0

    for u, r in records.items():
        if not r.get("page") and r.get("failures", 0) > 0:
            issues[u] = [issue(u, "FETCH_FAILED", "high", f"Could not read this page: {r.get('last_error')}",
                               "Open the URL in a browser. If it is broken or removed, fix it or remove it from the sitemap.")]

    for field, code, label in (("title", "DUP_TITLE", "title"), ("description", "DUP_DESC", "meta description")):
        groups = {}
        for u, p in pages.items():
            key = normalize_ws(p.get(field, "")).lower()
            if key:
                groups.setdefault(key, []).append(u)
        for urls in groups.values():
            if len(urls) > 1:
                for u in urls:
                    others = [x for x in urls if x != u][:3]
                    issues[u].append(issue(u, code, "medium", f"Same {label} as: {', '.join(others)}",
                                           f"Give every article a unique {label} that describes that article."))

    inbound = {u: 0 for u in pages}
    for u, p in pages.items():
        for target in set(p.get("internal_links", [])):
            if target in inbound and target != u:
                inbound[target] += 1
    if len(pages) >= th["min_pages_for_orphan_check"] and coverage >= 0.9:
        for u, n in inbound.items():
            if n == 0:
                issues[u].append(issue(u, "ORPHAN", "medium", "No other article links to this page.",
                                       "Add a link to it from a related article or a category/hub page."))

    urls = sorted(pages)[:1500]
    toks = {u: _title_tokens(pages[u].get("title", "")) for u in urls}
    similar = []
    for i, a in enumerate(urls):
        for b in urls[i + 1:]:
            if _jaccard(toks[a], toks[b]) >= th["similar_title_jaccard"]:
                similar.append((a, b))
    for a, b in similar:
        for u, other in ((a, b), (b, a)):
            issues[u].append(issue(u, "SIMILAR_TITLE", "medium",
                                   f"Title is very similar to {other}. They may compete for the same searches (a guess based on titles only).",
                                   "Decide which page should rank for this topic. Merge, differentiate, or link them clearly."))

    related = {}
    for u in urls:
        mine = {t for t, _ in pages[u].get("top_terms", [])[:12]}
        linked = set(pages[u].get("internal_links", []))
        cands = []
        for v in urls:
            if v == u or v in linked:
                continue
            theirs = {t for t, _ in pages[v].get("top_terms", [])[:12]}
            shared = sorted(mine & theirs)
            if len(shared) >= 2 and _jaccard(mine, theirs) >= 0.15:
                cands.append((_jaccard(mine, theirs), v, shared))
        cands.sort(key=lambda c: (-c[0], c[1]))
        related[u] = [{"url": v, "title": pages[v].get("title", ""), "shared_terms": s[:5]} for _, v, s in cands[:3]]

    for u in issues:
        issues[u].sort(key=lambda i: (ORDER[i["severity"]], i["code"]))
    return issues, {"coverage": coverage, "fetched": len(pages), "total": total, "related": related, "inbound": inbound}
