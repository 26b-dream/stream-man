"""Reimport all shows."""
from __future__ import annotations

import logging
from datetime import datetime

import _activate_django  # pyright: ignore[reportUnusedImport]  # noqa: F401
from common.get_scraper import GetScraper
from media.models import Show

logging.basicConfig(level=logging.INFO)

for show in Show.objects.all():
    logging.getLogger("Reimporting").info(show.url)
    show_scraper = GetScraper(show.url)
    show_scraper.update(minimum_modified_timestamp=datetime.now().astimezone())
