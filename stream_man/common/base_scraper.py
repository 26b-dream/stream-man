"""Contains ScraperShared, ScraperUpdateShared, and ScraperShowShared, which are shared code for scraper plugins"""

from __future__ import annotations

import json
import logging
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import cache
from time import sleep
from typing import TYPE_CHECKING, Literal

import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from django.db import transaction
from extended_path import ExtendedPath
from html_file import HTMLFile
from json_file import JSONFile
from media.models import Episode, Season, Show

from stream_man.settings import MEDIA_ROOT

if TYPE_CHECKING:
    from re import Pattern
    from typing import Optional, TypeVar

    from playwright._impl._api_structures import Position
    from playwright.sync_api._generated import BrowserContext, ElementHandle, Locator, Page, Playwright, Response

    T = TypeVar("T", bound="ExtendedPath")


@cache
def season_json_path_cached(files_dir: ExtendedPath, season_id: str | int, page: Optional[int]) -> JSONFile:
    """Path for the JSON file that lists all of the episodes for a specific season"""
    if page:
        return JSONFile(files_dir, "Season", f"{season_id}", f"{page}.json")
    else:
        return JSONFile(files_dir, "Season", f"{season_id}.json")


class ScraperShared:
    """Shared code for streaming scraper"""

    @classmethod
    def playwright_browser(
        cls,
        playwright: Playwright,
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/111.0",
    ) -> BrowserContext:
        """Create a playwright browser context that is preconfigured for scraping"""

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

    def playwright_wait_for_files(
        self,
        page: Page,
        files: list[T] | T,
        timestamp: Optional[datetime] = None,
        seconds: int = 10,
    ) -> None:
        """Downloads will sometimes randomly not be detected by playwright if nothing is being executed. This function
        will simply execute a query selector until the file exists and is up to date. This is also useful to detect
        changes in the website causing files to no longer download or be detected"""
        if not isinstance(files, list):
            files = [files]

        for _ in range(seconds):
            if all(
                file.exists() and (not timestamp or file.stat().st_mtime >= timestamp.timestamp()) for file in files
            ):
                return

            # Executing a query_selector will keep the download form randomly hanging while waiting for the file to
            # be downloaded
            page.query_selector("html")
            sleep(1)

        missing_files = [str(file) for file in files if not file.exists()]

        raise FileNotFoundError(f"Files {', '.join(missing_files)} were not found")

    def playwright_save_json_response(self, response: Response, file_path: JSONFile) -> None:
        """Save a JSON response from playwright"""
        raw_json = response.json()
        file_path.write(json.dumps(raw_json))
        file_path.parsed_cached_value = raw_json

    def playwright_save_html_response(self, page: Page, file_path: HTMLFile) -> None:
        """Save a JSON response from playwright"""
        file_path.write(page.content())
        file_path.parsed_cached_value = None


class ScraperUpdateShared(ScraperShared):
    """Shared code for scraping update information"""


class ScraperShowShared(ABC, ScraperShared):
    """Shared code for scraping show information"""

    URL_REGEX: Pattern[str]
    WEBSITE: str

    @classmethod
    def website_name(cls) -> str:
        return cls.WEBSITE

    @classmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        """Check if a URL is a valid show URL for a specific scraper"""
        return bool(re.search(cls.URL_REGEX, show_url))

    def __init__(self, show_url: str) -> None:
        self.show_id = str(re.strict_search(self.URL_REGEX, show_url).group("show_id"))
        self.show = Show().get_or_new(show_id=self.show_id, website=self.WEBSITE)[0]
        self.show_json_path = JSONFile(self.files_dir(), "show.json")
        self.playwright_image_path = None

    def show_object(self) -> Show:
        """Due to subclassing AbstractScraperClass this is the easiest type safe way to access self.show"""
        return self.show

    def files_dir(self) -> ExtendedPath:
        return DOWNLOADED_FILES_DIR / self.WEBSITE / self.show_id

    def pretty_file_path(self, file_path: ExtendedPath) -> str:
        """Returns the file path relative to the downloaded files directory which is easier to read when logging"""
        return str(file_path.relative_to(DOWNLOADED_FILES_DIR))

    def is_file_outdated(
        self, file_path: ExtendedPath, file_type: str, minimum_timestamp: Optional[datetime] = None
    ) -> bool:
        """Check if a specific image is missing or outdated"""
        # This is basically a re-implementation of ExtendedPath.outdated() but with added logging
        if not file_path.exists():
            logger = logging.getLogger(f"{self.logger_identifier()}:Missing:{file_type}")
            logger.info(self.pretty_file_path(file_path))
            return True

        if minimum_timestamp and file_path.aware_mtime() < minimum_timestamp.astimezone():
            logger = logging.getLogger(f"{self.logger_identifier()}:Outdated:{file_type}")
            logger.info(self.pretty_file_path(file_path))
            return True

        return False

    def logged_goto(
        self,
        page: Page,
        url: str,
        msg: Optional[str] = None,
        timeout: Optional[float] = None,
        wait_until: Optional[Literal["commit", "domcontentloaded", "load", "networkidle"]] = None,
        referer: Optional[str] = None,
    ) -> None:
        """Go to a URL and log it to the logger"""
        if not msg:
            msg = url
        logging.getLogger(f"{self.logger_identifier()}.Opening").info(msg)
        page.goto(url, timeout=timeout, wait_until=wait_until, referer=referer)

    def logged_click(
        self,
        element: ElementHandle | Locator,
        msg: str,
        modifiers: Optional[list[Literal["Alt", "Control", "Meta", "Shift"]]] = None,
        position: Optional[Position] = None,
        delay: Optional[float] = None,
        button: Optional[Literal["left", "middle", "right"]] = None,
        click_count: Optional[int] = None,
        timeout: Optional[float] = None,
        force: Optional[bool] = None,
        no_wait_after: Optional[bool] = None,
        trial: Optional[bool] = None,
    ) -> None:
        logging.getLogger(f"{self.logger_identifier()}.Clicking").info(msg)
        element.click(
            modifiers=modifiers,
            position=position,
            delay=delay,
            button=button,
            click_count=click_count,
            timeout=timeout,
            force=force,
            no_wait_after=no_wait_after,
            trial=trial,
        )

    def logger_identifier(self) -> str:
        if self.show.name:
            return f"{self.WEBSITE}:{self.show.name}"

        return f"{self.WEBSITE}:{self.show_id}"

    def update(
        self, minimum_info_timestamp: Optional[datetime] = None, minimum_modified_timestamp: Optional[datetime] = None
    ) -> None:
        """Downloads and imports all of the information"""
        self.download_all(minimum_info_timestamp)
        self.import_all(minimum_info_timestamp, minimum_modified_timestamp)

    @abstractmethod
    def download_all(
        self,
        minimum_timestamp: Optional[datetime] = None,
    ) -> None:
        """Download all of the files that are missing or outdated"""

    @transaction.atomic
    def import_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Imports all of the information without downloading any files"""
        logging.getLogger(self.logger_identifier()).info("Importing information")

        # Mark everything as deleted and let importing mark it as not deleted because this is the easiest way to
        # determine when an entry is deleted
        Show.objects.filter(id=self.show.id, website=self.WEBSITE).update(deleted=True)
        Season.objects.filter(show=self.show).update(deleted=True)
        Episode.objects.filter(season__show=self.show).update(deleted=True)

        # Clear all caches just in case

        self.import_show(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_seasons(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_episodes(minimum_info_timestamp, minimum_modified_timestamp)

        self.set_update_at()

    @abstractmethod
    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import all of the information for a show without downloading any of the files"""

    @abstractmethod
    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import all of the information for a season without downloading any of the files"""

    @abstractmethod
    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import all of the information for an episode without downloading any of the files"""

    def season_json_path(self, season_id: str | int, page: Optional[int] = None) -> JSONFile:
        """Path for the JSON file that lists all of the episodes for a specific season"""
        return season_json_path_cached(self.files_dir(), season_id, page)

    def set_update_at(self) -> None:
        """Set the update_at value of show based on when the last episode aired."""
        latest_episode = Episode.objects.filter(season__show=self.show, deleted=False).order_by("-release_date").first()

        if latest_episode:
            # If the episode aired within a week of the last download update the information weekly
            if latest_episode.release_date > self.show.info_timestamp - timedelta(days=365 / 12):
                self.show.update_at = latest_episode.release_date + timedelta(days=7)
            # Any other situation update the information monthly
            else:
                self.show.update_at = self.show.info_timestamp + timedelta(days=365 / 12)
        self.show.save()

    # TODO: Move this to each sub-class to make the file names more descriptive
    def image_path_from_url(self, image_url: str) -> ExtendedPath:
        """Automatically generated image path based on the image URL"""
        image_name = image_url.split("/")[-1]
        return self.files_dir() / "Images" / image_name

    def playwright_download_image_if_needed(
        self, page: Page, url: str, image_source: str, path: Optional[ExtendedPath] = None
    ) -> None:
        """Download a specific image using playwright if it does not exist"""
        if not path:
            path = self.image_path_from_url(url)

        self.playwright_image_path = path

        if self.is_file_outdated(path, f"{image_source} image"):
            self.logged_goto(page, url, url, wait_until="networkidle")
            page.wait_for_timeout(1000)

            # Sometimes images are over 10 MB, when that happens Playwright will have an error because it is unable to
            # download files larger than 10 MB see: https://github.com/microsoft/playwright/issues/13449
            # When this happens download the file using urllib instead
            try:
                self.playwright_wait_for_files(page, path)
            except FileNotFoundError:
                self.urllib_download_if_needed(url, path, image_source)

    def urllib_download_if_needed(self, url: str, path: ExtendedPath, image_source: str) -> None:
        """Download a specific image using playwright"""
        logging.getLogger(f"{self.logger_identifier()}.Downloading").info(image_source)

        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, path)

    def playwright_response_save_images(self, response: Response) -> None:
        """Save every image file that is requested by playwright"""
        if self.playwright_image_path:
            self.playwright_image_path.write(response.body())
        else:
            raise Exception("No image path was set")

    def set_image(self, model_object: Episode | Show, image_path: ExtendedPath) -> None:
        """Set the image for a model object and hardlink the image so it can be easily accessed through Django"""
        pretty_name = self.pretty_file_path(image_path)
        model_object.image.name = pretty_name

        # Hardlink the file so it can be served through the server easier
        media_path = MEDIA_ROOT / pretty_name
        if not media_path.exists():
            media_path.parent.mkdir(parents=True, exist_ok=True)
            media_path.hardlink_to(image_path)
