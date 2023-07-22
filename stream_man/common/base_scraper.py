"""Contains ScraperShared, ScraperUpdateShared, and ScraperShowShared, which are shared code for scraper plugins"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import lru_cache
from time import sleep
from typing import TYPE_CHECKING

import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from django.db import transaction
from extended_path import ExtendedPath
from html_file import HTMLFile
from json_file import JSONFile
from media.models import Episode, Season, Show

if TYPE_CHECKING:
    from re import Pattern
    from typing import Optional

    from playwright.sync_api._generated import BrowserContext, Page, Playwright


class ScraperShared:
    """Shared code for streaming scraper"""

    @classmethod
    def playwright_browser(
        cls,
        playwright: Playwright,
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/111.0",
    ) -> BrowserContext:
        """Create a playwright browser context that is preconfigured for scraping

        Args:
            playwright (Playwright): Playwright instance
            user_agent (_type_, optional): User agent for playwright. Defaults to "Mozilla/5.0 (Macintosh; Intel Mac OS
            X 10.15; rv:109.0) Gecko/20100101 Firefox/111.0" which is basically a generic and perfectly valid user
            agent.

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


class ScraperShowShared(ABC, ScraperShared):
    """Shared code for scraping show information"""

    SHOW_URL_REGEX: Pattern[str]
    WEBSITE: str

    @classmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        """Check if a URL is a valid show URL for a specific scraper"""
        return bool(re.search(cls.SHOW_URL_REGEX, show_url))

    def __init__(self, show_url: str) -> None:
        self.show_id = str(re.strict_search(self.SHOW_URL_REGEX, show_url).group("show_id"))
        self.show_info = Show().get_or_new(show_id=self.show_id, website=self.WEBSITE)[0]
        self.show_json_path = JSONFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "show", f"{self.show_id}.json")
        self.show_html_path = HTMLFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "show", f"{self.show_id}.html")

    @classmethod
    def website_name(cls) -> str:
        return cls.WEBSITE

    def show_object(self) -> Show:
        return self.show_info

    def logger_identifier(self) -> str:
        if self.show_info.name:
            return f"{self.WEBSITE}.{self.show_info.name}"

        return f"{self.WEBSITE}.{self.show_id}"

    def update(
        self, minimum_info_timestamp: Optional[datetime] = None, minimum_modified_timestamp: Optional[datetime] = None
    ) -> None:
        logging.getLogger(self.logger_identifier()).info("Updating %s", self.show_info)
        self.download_all(minimum_info_timestamp)
        self.import_all(minimum_info_timestamp, minimum_modified_timestamp)

    @abstractmethod
    def download_all(
        self,
        minimum_timestamp: Optional[datetime] = None,
    ) -> None:
        """Downloads all of the information for a show"""

    @transaction.atomic
    def import_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        logging.getLogger(self.logger_identifier()).info("Importing information")

        # Mark everything as deleted and let importing mark it as not deleted because this is the easiest way to
        # determine when an entry is deleted
        Show.objects.filter(id=self.show_info.id, website=self.WEBSITE).update(deleted=True)
        Season.objects.filter(show=self.show_info).update(deleted=True)
        Episode.objects.filter(season__show=self.show_info).update(deleted=True)

        self.import_show(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_seasons(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_episodes(minimum_info_timestamp, minimum_modified_timestamp)

        # Even though episodes won't be added, movies can still be deleted so still check it using the normal method
        self.update_update_at()

    @abstractmethod
    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Imports all of the information for a show without downloading any of the files"""

    @abstractmethod
    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Imports all of the information for a season without downloading any of the files"""

    @abstractmethod
    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Imports all of the information for an episode without downloading any of the files"""

    @lru_cache(maxsize=1024)  # Value will never change
    def season_json_path(self, season_id: str) -> JSONFile:
        """Path for the JSON file that lists all of the episodes for a specific season"""
        return JSONFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "season", self.show_id, f"{season_id}.json")

    def update_update_at(self) -> None:
        # Get last 5 aired episodes
        latest_episode = Episode.objects.filter(season__show=self.show_info).order_by("-release_date").first()

        if latest_episode:
            # If the episode aired within a month of the last download update the information weekly
            if latest_episode.release_date > self.show_info.info_timestamp - timedelta(days=365 / 12):
                self.show_info.update_at = latest_episode.release_date + timedelta(days=7)
            # Any other situation update the information monthly
            else:
                self.show_info.update_at = self.show_info.info_timestamp + timedelta(days=365 / 12)
