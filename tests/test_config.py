import tempfile
import unittest
from pathlib import Path

from eda.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent


class ConfigTests(unittest.TestCase):
    def test_shipped_config_is_valid_and_audit_only(self):
        cfg = load_config(ROOT / "config.yaml")
        self.assertEqual(cfg["publishing"]["mode"], "audit")
        self.assertEqual(cfg["site"]["base_url"], "https://examdarpan.in")

    def test_defaults_without_file(self):
        self.assertEqual(load_config()["crawl"]["batch_size"], 3)

    def test_overrides_merge(self):
        cfg = load_config(overrides={"crawl": {"batch_size": 5}})
        self.assertEqual(cfg["crawl"]["batch_size"], 5)
        self.assertEqual(cfg["crawl"]["timeout_seconds"], 20)

    def test_publishing_other_than_audit_rejected(self):
        with self.assertRaises(ConfigError):
            load_config(overrides={"publishing": {"mode": "auto"}})

    def test_bad_values_rejected(self):
        for bad in ({"site": {"base_url": "examdarpan.in"}}, {"crawl": {"batch_size": 500}},
                    {"crawl": {"request_delay_seconds": 0}}, {"ai": {"provider": "mystery"}}):
            with self.assertRaises(ConfigError):
                load_config(overrides=bad)

    def test_missing_and_broken_file(self):
        with self.assertRaises(ConfigError):
            load_config("/nonexistent/config.yaml")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.yaml"
            p.write_text("a: [unclosed", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(p)


if __name__ == "__main__":
    unittest.main()
