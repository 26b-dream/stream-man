"""Import a URL then dump the information to a JSON file.

Makes it easier to create test data.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

import _activate_django  # pyright: ignore[reportUnusedImport]  # noqa: F401
from common.get_scraper import GetScraper
from json_file import JSONFile

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else input("Enter URL: ")
    show_scraper = GetScraper(url)
    show_scraper.update(minimum_modified_timestamp=datetime.now().astimezone())
    show_object = show_scraper.show_object
    file_name = JSONFile(__file__).parent / f"{show_object.website}_{show_object.show_id}.json"
    JSONFile(file_name).write(json.dumps(show_scraper.show_object.dump()))
