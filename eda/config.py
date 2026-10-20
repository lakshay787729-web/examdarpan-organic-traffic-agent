"""Configuration loading and validation."""
import copy
from pathlib import Path
from urllib.parse import urlsplit

import yaml


class ConfigError(ValueError):
    """Raised when config.yaml is missing or invalid."""


DEFAULTS = {
    "site": {
        "base_url": "https://examdarpan.in",
        "sitemap_urls": ["https://examdarpan.in/sitemap.xml"],
        "include_patterns": [],
        "exclude_patterns": [
            r"/(tag|tags|category|categories|author|page)/",
            r"/(admin|login|wp-admin|api)(/|$)",
            r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|xml)$",
        ],
        "exclude_homepage": True,
    },
    "crawl": {
        "user_agent": "ExamDarpanOrganicTrafficAgent/1.0 (+https://examdarpan.in; SEO audit of our own site)",
        "request_delay_seconds": 3, "timeout_seconds": 20, "max_retries": 2,
        "max_page_bytes": 2000000, "batch_size": 3, "recheck_after_days": 7,
        "sitemap_refresh_hours": 6, "max_consecutive_failures": 3,
        "failure_cooldown_hours": 24, "max_runtime_seconds": 240,
    },
    "analysis": {
        "title_min": 30, "title_max": 60, "description_min": 70, "description_max": 160,
        "thin_words": 300, "min_internal_links": 3, "stale_days": 365,
        "similar_title_jaccard": 0.6, "min_pages_for_orphan_check": 5,
    },
    "keywords": {"max_phrases": 12, "max_ideas": 10},
    "gsc": {
        "enabled": True, "days": 28, "refresh_hours": 24, "row_limit": 25000, "max_rows": 50000,
        "min_impressions": 50, "low_ctr_factor": 0.5, "striking_min_position": 8,
        "striking_max_position": 20, "few_clicks_max": 2, "decline_pct": 30,
        "min_query_impressions": 10,
    },
    "ai": {
        "provider": "none", "model": "gemini-2.5-flash", "base_url": "https://api.openai.com/v1",
        "max_calls_per_run": 1, "max_input_chars": 6000, "timeout_seconds": 60,
    },
    "reports": {"show_search_console_numbers": False, "max_priority_items": 15},
    "publishing": {"mode": "audit"},
    "logging": {"level": "INFO", "dir": "logs"},
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in (extra or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], val)
        else:
            out[key] = val
    return out


def _check_range(cfg, section, key, lo, hi):
    val = cfg[section][key]
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not (lo <= val <= hi):
        raise ConfigError(f"{section}.{key} must be a number between {lo} and {hi} (got {val!r})")


def validate_config(cfg: dict) -> dict:
    if cfg["publishing"].get("mode") != "audit":
        raise ConfigError("publishing.mode must be 'audit'. Automatic publishing is not supported.")
    base = urlsplit(str(cfg["site"].get("base_url", "")))
    if base.scheme not in ("http", "https") or not base.netloc:
        raise ConfigError("site.base_url must look like https://example.com")
    for u in cfg["site"].get("sitemap_urls", []):
        if urlsplit(str(u)).scheme not in ("http", "https"):
            raise ConfigError(f"site.sitemap_urls contains an invalid URL: {u!r}")
    for key in ("include_patterns", "exclude_patterns", "sitemap_urls"):
        if not isinstance(cfg["site"].get(key), list):
            raise ConfigError(f"site.{key} must be a list")
    _check_range(cfg, "crawl", "batch_size", 1, 20)
    _check_range(cfg, "crawl", "request_delay_seconds", 1, 60)
    _check_range(cfg, "crawl", "timeout_seconds", 5, 120)
    _check_range(cfg, "crawl", "max_retries", 0, 5)
    _check_range(cfg, "crawl", "recheck_after_days", 1, 365)
    _check_range(cfg, "crawl", "sitemap_refresh_hours", 1, 168)
    _check_range(cfg, "crawl", "max_runtime_seconds", 30, 3000)
    _check_range(cfg, "gsc", "days", 7, 90)
    _check_range(cfg, "gsc", "refresh_hours", 1, 168)
    _check_range(cfg, "ai", "max_calls_per_run", 0, 5)
    if cfg["ai"]["provider"] not in ("none", "gemini", "openai_compatible"):
        raise ConfigError("ai.provider must be none, gemini or openai_compatible")
    if str(cfg["logging"]["level"]).upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ConfigError("logging.level must be DEBUG, INFO, WARNING or ERROR")
    return cfg


def load_config(path=None, overrides=None) -> dict:
    """Load config.yaml (if a path is given), merge over defaults, validate."""
    data = {}
    if path is not None:
        p = Path(path)
        if not p.is_file():
            raise ConfigError(f"Config file not found: {p}")
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"config.yaml is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError("config.yaml must contain key: value settings")
    cfg = _merge(DEFAULTS, data)
    cfg = _merge(cfg, overrides or {})
    return validate_config(cfg)
