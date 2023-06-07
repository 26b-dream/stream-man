""""Scraper class that will return the correct concrete scraper for a URL

To do this scrapers must be imported, initializing a Scraper object will import all scrapers in the scrapers folder"""
import importlib

from common.abstract_scraper import AbstractScraperClass
from extended_path import ExtendedPath


def import_scrapers():
    """Import all plugins in the scrapers folder"""

    # Directory of all scrapers
    scrapers_dir = ExtendedPath(__file__).parent.parent / "scrapers"

    # Import each scraper
    for scraper in scrapers_dir.glob("*"):
        if scraper.is_dir():
            scraper_path = f"scrapers.{scraper.name}"
            importlib.import_module(scraper_path)


class InvalidURLError(Exception):
    """Exception raised when a URL is invalid"""


class Scraper:
    """Scraper class that will return the correct concrete scraper for a URL"""

    import_scrapers()

    def __new__(cls, url: str):
        for subclass in AbstractScraperClass.__subclasses__():
            if subclass.is_valid_show_url(url):
                return subclass(url)

        raise InvalidURLError(f"Invalid url {url}")
