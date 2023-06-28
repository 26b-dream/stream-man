""""Scraper class that will return the correct concrete scraper for a URL

To do this scrapers must be imported, initializing a Scraper object will import all valid scrapers in the scrapers
folder`"""
import importlib

from common.abstract_scraper import AbstractScraperClass
from common.constants import BASE_DIR


def import_scrapers():
    """Import all plugins in the scrapers folder"""

    # Directory of all scrapers
    scrapers_dir = BASE_DIR / "scrapers"

    # Import each scraper
    for scraper in scrapers_dir.glob("*"):
        if scraper.is_dir():
            scraper_path = f"scrapers.{scraper.name}"
            importlib.import_module(scraper_path)
        elif scraper.suffix == ".py":
            scraper_path = f"scrapers.{scraper.stem}"
            importlib.import_module(scraper_path)


class InvalidURLError(Exception):
    """Exception raised when a URL is invalid"""


class Scraper:
    """Scraper class that will return the correct concrete scraper for a URL"""

    import_scrapers()

    def __new__(cls, url: str) -> AbstractScraperClass:
        for subclass in AbstractScraperClass.__subclasses__():
            # pyright note - This only returns concrete subclasses, so I do not need to worry about that the function is
            # not implemented
            if subclass.is_valid_show_url(url):  # pyright: ignore[reportGeneralTypeIssues]
                return subclass(url)  # pyright: ignore[reportGeneralTypeIssues]

        raise InvalidURLError(f"Invalid url {url}")

    @classmethod
    def credential_keys(cls) -> list[tuple[str, list[str]]]:
        # This would technically be faster if it used list comprehension, but it makes it much harder to read so the
        # speed penalty is acceptable
        output: list[tuple[str, list[str]]] = []
        for subclass in AbstractScraperClass.__subclasses__():
            if subclass.credential_keys():
                # pyright note - This only returns concrete subclasses, so I do not need to worry about that the
                # function is not implemented. In addition this is a seperate variable because having the comment on the
                # same line makes the comment too long and it gets wrapped and breaks
                website_name = subclass.website_name()  # pyright: ignore[reportGeneralTypeIssues]

                output.append((website_name, subclass.credential_keys()))

        return output
