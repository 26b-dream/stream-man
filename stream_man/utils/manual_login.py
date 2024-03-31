"""Manually login to a website when it cannot be easily automated due to captchas."""
import _activate_django  # pyright: ignore[reportUnusedImport]  # noqa: F401
from common.scraper_functions import BeerShaker
from playwright.sync_api import sync_playwright

if __name__ == "__main__":
    with sync_playwright() as playwright:
        page = BeerShaker(playwright)
        input("Press enter to quit the web browser.")
