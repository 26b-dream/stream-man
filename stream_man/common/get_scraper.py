""""Scraper class that will return the correct concrete scraper for a URL.

To do this scrapers must be imported, initializing a Scraper object will import all valid scrapers in the scrapers
folder.
"""
from __future__ import annotations

import importlib

from common.abstract_scraper import AbstractScraperClass
from common.constants import BASE_DIR


def import_scrapers() -> None:
    """Import all plugins in the scrapers folder so they are available to be used."""
    # Directory of all scrapers
    scrapers_dir = BASE_DIR / "scrapers"

    # Import each scraper
    for scraper in scrapers_dir.glob("*"):
        # Not used in any official scrapers, but allow third party scrapers to be in a subfolder if the plugin author
        # wants to write it that way
        if scraper.is_dir():
            scraper_path = f"scrapers.{scraper.name}"
            importlib.import_module(scraper_path)
        elif scraper.suffix == ".py":
            scraper_path = f"scrapers.{scraper.stem}"
            importlib.import_module(scraper_path)


class InvalidURLError(Exception):
    """Exception raised when a URL is invalid."""


class GetScraper:
    """Class for manager all of the scrapers.

    GetScraper(url) will return a scraper that matches the given url
    credential_keys will return a list of tuples with the website name and the credential keys for each scraper
    """

    import_scrapers()

    def __new__(cls, url: str) -> AbstractScraperClass:
        """Return the correct concrete scraper for a URL.

        Parameters:
            url (str): The URL to get the scraper for

        Returns:
            AbstractScraperClass: The concrete scraper for the URL which has to be a subclass of AbstractScraperClass
        """
        for subclass in AbstractScraperClass.__subclasses__():
            print(subclass)
            if subclass.is_valid_show_url(url):
                return subclass(url)
        error_message = f"No scraper found for {url}"
        raise InvalidURLError(error_message)
