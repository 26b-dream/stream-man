"""Reimports all shows using the matching scraper, useful when plugins are updated to include additional information"""
from __future__ import annotations

import logging
from datetime import datetime

import _activate_django  # pyright: ignore[reportUnusedImport] # pylint: disable=W0611
from common.scrapers import Scraper
from media.models import Show

logging.basicConfig(level=logging.INFO)

for show in Show.objects.all():
    show_scraper = Scraper(show.url)
    logging.getLogger("Reimport").info("Reimporting %s", show.url)
    show_scraper.update(minimum_modified_timestamp=datetime.now().astimezone())
