import unittest
from datetime import date

from eda.extractor import extract_article
from eda.textutil import find_dates, find_deadline_dates, tokenize, top_phrases
from tests.helpers import fixture

URL = "https://examdarpan.in/rajasthan-patwari-recruitment-2026"


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.p = extract_article(fixture("article_good.html"), URL)

    def test_basic_fields(self):
        p = self.p
        self.assertTrue(p["title"].startswith("Rajasthan Patwari Recruitment 2026"))
        self.assertIn("eligibility", p["description"])
        self.assertEqual(p["canonical"], URL)
        self.assertEqual(p["h1s"], ["Rajasthan Patwari Recruitment 2026"])
        self.assertEqual(p["h2s"], ["Eligibility", "How to apply online"])
        self.assertEqual(p["published"], "2026-09-28")
        self.assertEqual(p["modified"], "2026-10-10")
        self.assertFalse(p["noindex"])
        self.assertEqual(p["lang"], "en")

    def test_internal_links_only_from_article_body(self):
        links = self.p["internal_links"]
        self.assertIn("https://examdarpan.in/bstc-refund-guide", links)
        self.assertIn("https://examdarpan.in/ssc-gd-result-2026", links)
        self.assertNotIn("https://examdarpan.in/menu", links)       # nav is ignored
        self.assertNotIn("https://examdarpan.in/privacy", links)    # footer is ignored
        self.assertNotIn("https://rajasthan.gov.in/", links)
        self.assertEqual(self.p["external_link_count"], 1)

    def test_deadline_and_intents(self):
        self.assertEqual(self.p["deadline_dates"], ["2026-12-25"])
        self.assertIn("eligibility", self.p["intents_present"])
        self.assertNotIn("admit card", self.p["intents_present"])
        self.assertTrue(self.p["exam_related"])

    def test_bad_page(self):
        p = extract_article(fixture("article_bad.html"), "https://examdarpan.in/bstc-refund-guide")
        self.assertTrue(p["noindex"])
        self.assertEqual(len(p["h1s"]), 2)
        self.assertEqual(p["script_count"], 3)
        self.assertEqual(p["images_missing_alt"], 1)
        self.assertEqual(p["deadline_dates"], ["2024-01-15", "2024-02-10"])
        self.assertEqual(p["years"], [2024])

    def test_hindi_tokenizing_keeps_words_whole(self):
        self.assertEqual(tokenize("राजस्थान भर्ती-परीक्षा, पात्रता।"), ["राजस्थान", "भर्ती", "परीक्षा", "पात्रता"])

    def test_dates(self):
        self.assertEqual(find_dates("25/12/2026 and 3rd March 2026 and 5 मार्च 2026 and 31/02/2026"),
                         [date(2026, 12, 25), date(2026, 3, 3), date(2026, 3, 5)])
        self.assertEqual(find_deadline_dates("Posted 01/01/2026. Last date: 10/10/2026."), ["2026-10-10"])

    def test_phrases(self):
        ph = dict(top_phrases("Patwari recruitment form. Patwari recruitment date. Other text here.", 5))
        self.assertIn("patwari recruitment", ph)


if __name__ == "__main__":
    unittest.main()
