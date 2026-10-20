"""Beginner-friendly Markdown/CSV reports. Output is deterministic so unchanged data = unchanged files."""
import csv
import hashlib
import io
import re
from pathlib import Path
from urllib.parse import urlsplit

from .seo_analysis import WEIGHT, score
from .textutil import normalize_ws

GSC_FLAG_TEXT = {
    "LOW_CTR": "Shown in Google often, but few people click (improve title/description).",
    "FEW_CLICKS": "Gets impressions but almost no clicks.",
    "STRIKING_DISTANCE": "Ranks around positions 8-20: small improvements could move it onto page 1.",
    "DECLINING": "Clicks dropped a lot compared with the previous period.",
}
GSC_BOOST = {"LOW_CTR": 10, "FEW_CLICKS": 5, "STRIKING_DISTANCE": 8, "DECLINING": 12}
SEV_ICON = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def slug(url: str) -> str:
    path = urlsplit(url).path.strip("/") or "home"
    base = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-").lower()[:60] or "page"
    return f"{base}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:6]}"


def write_if_changed(path, content: str) -> bool:
    p = Path(path)
    if p.is_file() and p.read_text(encoding="utf-8") == content:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return True


def priority(issues, gsc_flags) -> int:
    return sum(WEIGHT[i["severity"]] for i in issues) + sum(GSC_BOOST.get(f, 0) for f in gsc_flags)


def _suggest_description(page) -> str:
    text = normalize_ws(page.get("excerpt", ""))
    if not text:
        return ""
    first = re.split(r"(?<=[\.\u0964!?])\s", text)[0]
    return first[:155].rsplit(" ", 1)[0] if len(first) > 155 else first


def render_article(url, rec, issues, ideas, related, gsc, queries, ai, show_numbers) -> str:
    page = rec.get("page") or {}
    L = [f"# {page.get('title') or url}", "", f"URL: {url}", ""]
    if not page:
        L += ["This page has not been read yet or could not be read.", ""]
    else:
        L += [f"**SEO health score: {score(issues)}/100** (this is this agent's own checklist score, not a Google score)",
              f"Words: {page.get('word_count')} | Last read: {rec.get('last_fetched')} | "
              f"Published: {page.get('published') or 'unknown'} | Updated: {page.get('modified') or 'unknown'}", ""]
    L += ["## Things to fix", ""]
    if issues:
        for i in issues:
            L.append(f"- **{SEV_ICON[i['severity']]}**: {i['message']}  \n  Fix: {i['fix']}")
    else:
        L.append("- Nothing found by the automatic checks.")
    if page:
        L += ["", "## Title and description ideas", ""]
        L.append(f"- Current title: {page.get('title') or '(none)'}")
        L.append(f"- Current description: {page.get('description') or '(none)'}")
        if not page.get("description"):
            d = _suggest_description(page)
            if d:
                L.append(f"- Draft description from your own text (edit before using): {d}")
        L += ["", "## Search ideas from this article's own content",
              "_These are ideas taken from the article text. They are NOT search-volume numbers. Check real queries in Search Console._", ""]
        for p in ideas["phrases"]:
            L.append(f"- {p['phrase']} ({p['source']}{', ' + p['note'] if p['note'] else ''})")
        if ideas["coverage_gaps"]:
            L += ["", "### Topics the article does not mention yet",
                  "_Add a section only if it is relevant AND you can confirm the facts from the official notice._", ""]
            L += [f"- {g}" for g in ideas["coverage_gaps"]]
            L += ["", "Possible search phrases for those sections (estimates):"]
            L += [f"- {q}" for q in ideas["query_ideas"]]
    if related:
        L += ["", "## Internal links you could add", ""]
        for r in related:
            L.append(f"- Link to [{r['title'] or r['url']}]({r['url']}) (shares: {', '.join(r['shared_terms'])})")
    if gsc:
        L += ["", "## Google Search Console (actual data)", ""]
        for f in gsc["flags"]:
            L.append(f"- {GSC_FLAG_TEXT[f]}")
        if show_numbers:
            L.append(f"- Clicks {gsc['clicks']}, impressions {gsc['impressions']}, CTR {gsc['ctr']:.1%}, average position {gsc['position']:.1f}")
            for q in queries[:5]:
                L.append(f"- Query \"{q['query']}\": {q['impressions']} impressions, {q['clicks']} clicks, position {q['position']:.1f}")
        elif not gsc["flags"]:
            L.append("- No Search Console warning flags for this page.")
    if ai:
        L += ["", "## AI suggestions (optional; REVIEW before using; may contain mistakes)", "", ai["text"]]
    return "\n".join(L).rstrip() + "\n"


def render_summary(site_info, all_issues, rows, gsc_state, max_items, ai_state) -> str:
    counts = {"high": 0, "medium": 0, "low": 0}
    for issues in all_issues.values():
        for i in issues:
            counts[i["severity"]] += 1
    L = ["# Exam Darpan SEO Summary", "",
         "This agent only reads your site and suggests improvements. It never edits or publishes anything,",
         "and it does not create fake visits or clicks.", "",
         "## Progress", "",
         f"- Articles found in sitemap: {site_info['total']}",
         f"- Articles read so far: {site_info['fetched']} ({site_info['coverage']:.0%})",
         f"- Issues: {counts['high']} high, {counts['medium']} medium, {counts['low']} low", "",
         "## Search Console status", "", f"- {gsc_state}", "", "## AI status", "", f"- {ai_state}", "",
         f"## Fix these first (top {max_items})", ""]
    if not rows:
        L.append("- Nothing to show yet. Articles are read a few at a time on each run.")
    for n, r in enumerate(rows[:max_items], 1):
        L.append(f"{n}. {r['title'] or r['url']}  \n   {r['url']}  \n   Priority {r['priority']} | score {r['score']}/100"
                 + (f" | Search Console: {', '.join(r['flags'])}" if r["flags"] else ""))
        for i in r["top"]:
            L.append(f"   - {SEV_ICON[i['severity']]}: {i['message']}")
    L += ["", "## Words used here", "",
          "- **Impressions**: times your page appeared in Google results.",
          "- **CTR**: share of impressions that became clicks.",
          "- **Position**: average rank (1 = top).",
          "- **Cannibalization**: two of your pages competing for the same search.", "",
          "See `articles/` for one detailed report per article and `issues.csv` for a spreadsheet view."]
    return "\n".join(L) + "\n"


def render_issues_csv(all_issues) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["url", "severity", "code", "message", "fix"])
    for url in sorted(all_issues):
        for i in all_issues[url]:
            w.writerow([url, i["severity"], i["code"], i["message"], i["fix"]])
    return buf.getvalue()


def render_gsc_report(gsc_state, analysis, show_numbers) -> str:
    L = ["# Search Console findings", "", f"Status: {gsc_state}", ""]
    if not analysis:
        L += ["Search Console data is not available. Public website checks still run.",
              "See README.md > 'Connect Google Search Console' to enable this report.", ""]
        return "\n".join(L)
    period = analysis.get("period", {})
    L += [f"Source: Google Search Console API (actual data) for {period.get('start')} to {period.get('end')}.", ""]
    if not show_numbers:
        flagged = {u: m for u, m in analysis["by_page"].items() if m["flags"]}
        L += ["Numbers and queries are hidden because `reports.show_search_console_numbers` is false (safe for public repositories).",
              f"- Pages with warning flags: {len(flagged)}",
              f"- Queries where 2+ of your pages compete: {len(analysis['cannibalization'])}", "",
              "Open the individual article reports for the flags, or use a PRIVATE repository and set the option to true for details."]
        return "\n".join(L) + "\n"
    for flag, title in (("LOW_CTR", "Impressions but low CTR"), ("FEW_CLICKS", "Impressions but few clicks"),
                        ("STRIKING_DISTANCE", "Close to page 1 (positions 8-20)"), ("DECLINING", "Declining pages")):
        rows = sorted(((u, m) for u, m in analysis["by_page"].items() if flag in m["flags"]),
                      key=lambda kv: (-kv[1]["impressions"], kv[0]))[:15]
        L += [f"## {title}", ""]
        L += [f"- {u}: {m['impressions']} impressions, {m['clicks']} clicks, CTR {m['ctr']:.1%}, position {m['position']:.1f}"
              for u, m in rows] or ["- None"]
        L.append("")
    L += ["## Possible cannibalization (several pages shown for one query)", ""]
    for c in analysis["cannibalization"][:15]:
        L.append(f"- \"{c['query']}\" ({c['total_impressions']} impressions): " +
                 "; ".join(f"{p['url']} ({p['impressions']} imp, pos {p['position']:.1f})" for p in c["pages"]))
    if not analysis["cannibalization"]:
        L.append("- None found")
    return "\n".join(L) + "\n"
