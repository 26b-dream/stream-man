"""Import/Update a single show from a given URL."""
from __future__ import annotations

import logging
import sys
from datetime import datetime

import _activate_django  # pyright: ignore[reportUnusedImport] # noqa: F401
from common.get_scraper import GetScraper

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    # If a URL is given as an argument use that URL, if not get the URL from the user.
    url = sys.argv[1] if len(sys.argv) > 1 else input("Enter URL: ")

    show_scraper = GetScraper(url)
    show_scraper.update(minimum_modified_timestamp=datetime.now().astimezone())
