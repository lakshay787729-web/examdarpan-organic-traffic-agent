#!/usr/bin/env python3
"""Exam Darpan Organic Traffic Agent - entry point.

Audit-and-suggest only. Reads your own public site, reports SEO problems and ideas.
It never publishes, edits content, or generates visits/clicks.
"""
import argparse
import os
import sys
from pathlib import Path

from eda.config import ConfigError, load_config
from eda.logging_utils import setup_logging
from eda.runner import run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--batch-size", type=int, default=None, help="override crawl.batch_size")
    ap.add_argument("--force-sitemap", action="store_true", help="re-read the sitemap now")
    ap.add_argument("--force-gsc", action="store_true", help="refresh Search Console data now")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent
    try:
        cfg = load_config(root / args.config if not Path(args.config).is_absolute() else args.config)
    except ConfigError as exc:
        print(f"Configuration problem: {exc}", file=sys.stderr)
        return 2
    logger = setup_logging(root / cfg["logging"]["dir"], cfg["logging"]["level"], os.environ)
    try:
        stats = run(cfg, os.environ, root=root, force_sitemap=args.force_sitemap,
                    force_gsc=args.force_gsc, batch_size=args.batch_size)
    except Exception:
        logger.exception("The agent stopped because of an unexpected error")
        return 1
    print(f"Done. read={stats['fetched']} failed={stats['failed']} sitemap={stats['sitemap']} "
          f"reports_changed={stats['report_files_changed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
