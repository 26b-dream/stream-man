"""Base scraper class for scraping streaming websites"""

from __future__ import annotations

from datetime import datetime
from time import sleep
from typing import TYPE_CHECKING

from common.constants import DOWNLOADED_FILES_DIR
from extended_path import ExtendedPath

if TYPE_CHECKING:
    from typing import Optional

    from playwright.sync_api._generated import BrowserContext, Page, Playwright


class ScraperShared:
    """Shared code for streaming scraper"""

    def playwright_browser(
        self,
        playwright: Playwright,
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/111.0",
    ) -> BrowserContext:
        """Create a playwright browser context that is preconfigured for scraping

        Args:
            playwright (Playwright): Playwright instance
            user_agent (_type_, optional): User agent for playwright. Defaults to "Mozilla/5.0 (Macintosh; Intel Mac OS
            X 10.15; rv:109.0) Gecko/20100101 Firefox/111.0".

        Returns:
            BrowserContext: Playwright browser context"""

        # Browser seem to suck when headless=False
        #   Firefox will just show a white screen if using cookies that already exist
        #   Chrome constantly has crashes when not running in headless mode
        return playwright.chromium.launch_persistent_context(
            user_data_dir=DOWNLOADED_FILES_DIR / "cookies/chrome",
            headless=False,
            channel="chrome",
            slow_mo=100,
            user_agent=user_agent,
        )

    def playwright_wait_for_files(self, page: Page, timestamp: Optional[datetime], *files: ExtendedPath) -> None:
        """Downloads will sometimes randomly not be detected by playwright if nothing is being executed

        This function will simply execute a query selector until the file exists and is up to date

        This is also useful to detect changes in the website causing files to no longer download or be detected

        Args:
            page (Page): Playwright page that is being used to download the files
            timestamp (Optional[datetime]): Timestamp that the files must be newer than"""
        for file in files:
            # Wait until file exists and is up to date
            while not file.exists() or (timestamp and file.stat().st_mtime < timestamp.timestamp()):
                # Executing a query_selector will keep the download form randomly hanging while waiting for the file to
                # be downloaded
                page.query_selector("html")
                sleep(1)


class ScraperUpdateShared(ScraperShared):
    """Shared code for scraping update information"""


class ScraperShowShared(ScraperShared):
    """Shared code for scraping show information"""
