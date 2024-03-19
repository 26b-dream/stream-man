""""Scraper class that will return the correct concrete scraper for a URL.

To do this scrapers must be imported, initializing a Scraper object will import all valid scrapers in the scrapers
folder.
"""
from __future__ import annotations

import importlib

from common.abstract_scraper import AbstractScraperClass
from common.constants import BASE_DIR


def import_scrapers() -> None:
    """Import all plugins in the scrapers folder."""
    # Directory of all scrapers
    scrapers_dir = BASE_DIR / "scrapers"

    # Import each scraper
    for scraper in scrapers_dir.glob("*"):
        # Not used in any official scrapers, but allow third party scrapers to be in a subfolder if the author wants to
        # write it that way
        if scraper.is_dir():
            scraper_path = f"scrapers.{scraper.name}"
            importlib.import_module(scraper_path)
        elif scraper.suffix == ".py":
            scraper_path = f"scrapers.{scraper.stem}"
            importlib.import_module(scraper_path)


class InvalidURLError(Exception):
    """Exception raised when a URL is invalid."""


class Scraper:
    """Scraper class that will return the correct concrete scraper for a URL."""

    import_scrapers()

    def __new__(cls, url: str) -> AbstractScraperClass:
        """Return the correct concrete scraper for a URL.

        Parameters:
        ----------
        url (str): The URL to get the scraper for

        Returns:
        -------
        AbstractScraperClass: The concrete scraper for the URL which has to be a subclass of AbstractScraperClass
        """
        for subclass in AbstractScraperClass.__subclasses__():
            if subclass.is_valid_show_url(url):
                return subclass(url)
        error_message = f"No scraper found for {url}"
        raise InvalidURLError(error_message)

    @classmethod
    def credential_keys(cls) -> list[tuple[str, list[str]]]:
        """Return a list of tuples with the website name and the credential keys for each scraper.

        Returns:
        -------
        list[tuple[str, list[str]]]: A list of tuples with the website name and the credential keys for each scraper.
        """
        # This would technically be faster if it used list comprehension, but it makes it much harder to read so the
        # speed penalty is acceptable for a small thing like credential keys
        output: list[tuple[str, list[str]]] = []
        for subclass in AbstractScraperClass.__subclasses__():
            if subclass.credential_keys():
                website_name = subclass.website_name()

                output.append((website_name, subclass.credential_keys()))

        return output
