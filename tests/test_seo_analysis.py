import unittest
from datetime import date

from eda.config import DEFAULTS
from eda.extractor import extract_article
from eda.keywords import build_ideas
from eda.seo_analysis import analyze_page, analyze_site, score
from tests.helpers import fixture

TH = DEFAULTS["analysis"]
TODAY = date(2026, 10, 20)
GOOD = "https://examdarpan.in/rajasthan-patwari-recruitment-2026"
BAD = "https://examdarpan.in/bstc-refund-guide"


def codes(issues):
    return {i["code"] for i in issues}


class SeoTests(unittest.TestCase):
    def setUp(self):
        self.good = dict(extract_article(fixture("article_good.html"), GOOD), final_url=GOOD, status=200)
        self.bad = dict(extract_article(fixture("article_bad.html"), BAD), final_url=BAD, status=200)

    def test_bad_page_issues(self):
        c = codes(analyze_page(BAD, self.bad, TH, TODAY))
        for expected in ("TITLE_SHORT", "DESC_MISSING", "H1_MULTIPLE", "H2_NONE", "JS_RENDER_SUSPECTED",
                         "CANONICAL_DIFFERENT", "NOINDEX", "FEW_INTERNAL_LINKS", "IMG_ALT_MISSING",
                         "NO_DATE", "OLD_YEAR_ONLY", "DEADLINE_PASSED"):
            self.assertIn(expected, c)
        self.assertNotIn("THIN_CONTENT", c)  # reported as JS_RENDER_SUSPECTED instead

    def test_good_page_has_no_serious_issues(self):
        issues = analyze_page(GOOD, self.good, TH, TODAY)
        self.assertFalse([i for i in issues if i["severity"] == "high"])
        self.assertNotIn("DESC_MISSING", codes(issues))
        self.assertNotIn("DEADLINE_PASSED", codes(issues))
        self.assertIn("THIN_CONTENT", codes(issues))  # fixture is short on purpose

    def test_old_content(self):
        old = dict(self.good, modified="2024-01-01")
        self.assertIn("OLD_CONTENT", codes(analyze_page(GOOD, old, TH, TODAY)))

    def test_score_bounds(self):
        self.assertEqual(score([]), 100)
        self.assertEqual(score(analyze_page(BAD, self.bad, TH, TODAY) * 5), 0)

    def test_site_level_duplicates_orphans_similar_and_failures(self):
        recs = {}
        for n in range(6):
            u = f"https://examdarpan.in/p{n}"
            recs[u] = {"page": dict(self.good, title="Same Title For Every Page Here Okay", internal_links=[]), "failures": 0}
        issues, info = analyze_site(recs, dict(TH, min_pages_for_orphan_check=3), TODAY)
        c = codes(issues["https://examdarpan.in/p0"])
        self.assertTrue({"DUP_TITLE", "SIMILAR_TITLE", "ORPHAN"} <= c)
        self.assertAlmostEqual(info["coverage"], 1.0)
        recs["https://examdarpan.in/dead"] = {"page": None, "failures": 2, "last_error": "HTTP 404"}
        issues, info = analyze_site(recs, dict(TH, min_pages_for_orphan_check=3), TODAY)
        self.assertEqual(codes(issues["https://examdarpan.in/dead"]), {"FETCH_FAILED"})
        self.assertAlmostEqual(info["coverage"], 6 / 7)

    def test_orphan_check_waits_for_coverage(self):
        recs = {f"https://examdarpan.in/p{n}": {"page": None, "failures": 0} for n in range(10)}
        recs["https://examdarpan.in/p0"]["page"] = dict(self.good, internal_links=[])
        issues, _ = analyze_site(recs, TH, TODAY)
        self.assertNotIn("ORPHAN", codes(issues["https://examdarpan.in/p0"]))

    def test_related_link_suggestions(self):
        a = dict(self.good, internal_links=[], top_terms=[["patwari", 5], ["recruitment", 4], ["rajasthan", 3]])
        b = dict(self.good, title="Other", internal_links=[], top_terms=[["patwari", 5], ["recruitment", 2], ["rajasthan", 2]])
        c = dict(self.good, title="Unrelated", internal_links=[], top_terms=[["cricket", 5], ["score", 4]])
        recs = {f"https://examdarpan.in/{k}": {"page": v, "failures": 0} for k, v in (("a", a), ("b", b), ("c", c))}
        _, info = analyze_site(recs, TH, TODAY)
        rel = [r["url"] for r in info["related"]["https://examdarpan.in/a"]]
        self.assertEqual(rel, ["https://examdarpan.in/b"])

    def test_keyword_ideas_from_content(self):
        ideas = build_ideas(self.good, DEFAULTS["keywords"])
        self.assertIn("admit card", ideas["coverage_gaps"])
        self.assertNotIn("eligibility", ideas["coverage_gaps"])
        self.assertTrue(all(q.startswith("Rajasthan Patwari Recruitment 2026") for q in ideas["query_ideas"]))


if __name__ == "__main__":
    unittest.main()
