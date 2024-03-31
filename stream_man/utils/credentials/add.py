"""Add secret values to the keyring."""
from __future__ import annotations

from getpass import getpass

import _activate_django  # pyright: ignore[reportUnusedImport]  # noqa: F401
import keyring
from common.abstract_scraper import AbstractScraperClass
from common.get_scraper import import_scrapers

if __name__ == "__main__":
    import_scrapers()
    all_credential_keys: list[tuple[str, list[str]]] = []

    for subclass in AbstractScraperClass.__subclasses__():
        if subclass.credential_keys():
            website_name = subclass.__name__
            all_credential_keys.append((website_name, subclass.credential_keys()))

    # Show a list of scrapers for the user to choose from
    for i, scraper_credential_keys in enumerate(all_credential_keys):
        print(f"{i}. {scraper_credential_keys[0]}")  # noqa: T201 - Print is not used for logging
    scraper_index = int(input("Choose scraper number to configure: "))

    # Show each secret for the sccraper and get user input
    scraper_name, scraper_keys = all_credential_keys[scraper_index]
    for key in scraper_keys:
        user_input = getpass(f"Enter {key}: ")
        keyring.set_password(f"stream-man-{scraper_name}", key, user_input)
