"""Guards for the project's safety promises."""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = ["selenium", "playwright", "pyppeteer", "webdriver", "proxies=", "proxy", "fake_useragent",
             "google.com/search", "randomize", "rotate_ip", "xdotool", "pyautogui", ".click("]


def cron_minutes(expr):
    return expr.split()[0]


class SafetyTests(unittest.TestCase):
    def test_no_traffic_manipulation_code(self):
        files = [ROOT / "agent.py"] + sorted((ROOT / "eda").glob("*.py"))
        for f in files:
            text = f.read_text(encoding="utf-8").lower()
            for bad in FORBIDDEN:
                self.assertNotIn(bad, text, f"{bad!r} found in {f.name}")

    def test_only_own_site_and_official_apis_are_contacted(self):
        urls = set()
        for f in (ROOT / "eda").glob("*.py"):
            urls |= set(re.findall(r"https?://[A-Za-z0-9\.\-]+", f.read_text(encoding="utf-8")))
        allowed = {"https://examdarpan.in", "https://www.googleapis.com", "https://generativelanguage.googleapis.com",
                   "https://api.openai.com", "https://example.com", "http://www.sitemaps.org"}
        self.assertTrue(urls <= allowed | {u for u in urls if "w3.org" in u}, urls - allowed)

    def test_workflow_is_valid_and_uses_valid_five_minute_schedule(self):
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / "agent.yml").read_text(encoding="utf-8"))
        triggers = doc.get("on", doc.get(True))
        crons = [s["cron"] for s in triggers["schedule"]]
        self.assertEqual(crons, ["*/5 * * * *"])
        self.assertIn("workflow_dispatch", triggers)
        step = int(cron_minutes(crons[0]).split("/")[1])
        self.assertGreaterEqual(step, 5)  # GitHub's minimum
        self.assertEqual(doc["concurrency"]["cancel-in-progress"], False)
        job = doc["jobs"]["run-agent"]
        self.assertLessEqual(job["timeout-minutes"], 15)
        self.assertEqual(doc["permissions"], {"contents": "write"})

    def test_workflow_only_references_expected_secrets(self):
        text = (ROOT / ".github" / "workflows" / "agent.yml").read_text(encoding="utf-8")
        names = set(re.findall(r"secrets\.([A-Z_]+)", text))
        self.assertEqual(names, {"GSC_SERVICE_ACCOUNT_JSON", "GSC_SITE_URL", "AI_API_KEY"})
        self.assertNotIn("set -x", text)

    def test_gitignore_blocks_credentials(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for needle in (".env", "service-account*.json", "logs/", ".cache/"):
            self.assertIn(needle, text)

    def test_no_hardcoded_keys_in_repo(self):
        pats = [re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*[A-Za-z0-9+/]{20,}")]
        for f in ROOT.rglob("*"):
            if f.is_file() and f.suffix in (".py", ".yml", ".yaml", ".md", ".example", ".txt") and "tests" not in f.parts:
                text = f.read_text(encoding="utf-8", errors="ignore")
                for p in pats:
                    self.assertIsNone(p.search(text), f.name)


if __name__ == "__main__":
    unittest.main()
