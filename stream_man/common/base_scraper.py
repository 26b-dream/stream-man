"""Contains ScraperShowShared."""
from __future__ import annotations

import functools
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import cached_property
from typing import TYPE_CHECKING

from django.db import transaction
from json_file import JSONFile
from media.models import Episode, Season, Show
from paved_path import PavedPath

import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR

if TYPE_CHECKING:
    from re import Pattern

    from common.scraper_functions import BeerShaker


# If you import AbstractScraperClass and ABC at the same time the class will still show up when using
# AbstractScraperClass.__subclasses__() so don't subclass AbstractScraperClass in this class
class BaseScraper(ABC):
    """Shared code for scraping show information."""

    URL_REGEX: Pattern[str]
    WEBSITE: str
    DOMAIN: str

    @classmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        # This docstring is just copied from AbstractScraperClass
        """Check if the given URL is a valid show URL for the scraper.

        Args:
            show_url: The URL to check.

        Returns:
            True if the URL is valid, False if the URL is not valid for the scraper.
        """
        return bool(re.search(cls._url_regex(), show_url))

    @classmethod
    def _url_regex(cls) -> Pattern[str]:
        """Regex used to determine if the URL is valid."""
        return cls.URL_REGEX

    def __init__(self, show_url: str) -> None:
        """Initializes a Scraper object for a specific show from a specific website."""
        self._show_id = str(re.strict_search(self._url_regex(), show_url).group("show_id"))
        self.show_object = Show.objects.get_or_new(show_id=self._show_id, website=self._website_name)[0]
        self._initialize_cache()

    def _initialize_cache(self) -> None:
        """Initialize the cache for the files so they are only loaded once."""
        self._season_json_file = functools.cache(self._season_json_file)
        self._image_file_from_url = functools.cache(self._image_file_from_url)
        self._episode_json_file = functools.cache(self._episode_json_file)

    @cached_property
    def _website_name(self) -> str:
        return self.WEBSITE

    @cached_property
    def _website_dir(self) -> PavedPath:
        return DOWNLOADED_FILES_DIR / self._website_name

    @cached_property
    def _show_dir(self) -> PavedPath:
        return self._website_dir / self._show_id

    @cached_property
    def _favicon_file(self) -> PavedPath:
        return PavedPath(self._website_dir, "favicon.png")

    @cached_property
    def _show_json_file(self) -> JSONFile:
        return JSONFile(self._show_dir, "show.json")

    @cached_property
    def _show_seasons_json_file(self) -> JSONFile:
        return JSONFile(self._show_dir, "show_seasons.json")

    @cached_property
    def _movie_json_file(self) -> JSONFile:
        return JSONFile(self._show_dir, "movie.json")

    def _episode_json_file(self, episode_id: str) -> JSONFile:
        return JSONFile(self._show_dir / f"episode/{episode_id}.json")

    def _season_json_file(
        self,
        season_id: int | str,
        page: int | None = None,
    ) -> JSONFile:
        # For simplciity, create the season_string as a string then voncert it to a JSONFile object
        season_string = f"season/{season_id}"

        # Page numbers aren't needed for all files, so only add them when needed
        if page is not None:
            season_string += f"/page/{page}"

        # This is the main reason a JSONFile is not created immediately, there is no easy way to append to a file path
        # without casting it to a string anyways so it makes more sense just to create the string as a string
        season_string += ".json"

        return JSONFile(self._show_dir, season_string)

    def _image_file_from_url(
        self,
        image_url: str,
        image_id: str | None = None,
        extension: str | None = None,
        subfolder: str | None = None,
    ) -> PavedPath:
        """Get the image file as a PavedPath object from its URL, or by using a specific ID and extension."""
        image_name = image_url.split("/")[-1]
        if image_id is None:
            image_id = image_name.split(".")[0]
        if extension is None:
            extension = image_name.split(".")[-1]

        if subfolder:
            return self._show_dir / "image" / subfolder / f"{image_id}.{extension}"

        return self._show_dir / "image" / f"{image_id}.{extension}"

    def _show_update_at_timestamp(self) -> datetime | None:
        return self.show_object.checked_update_at()

    def _season_update_at_timestamp(self, season_id: str) -> datetime | None:
        # Check if show_object is saved
        if self.show_object.pk:
            temp_season = Season.objects.get_or_new(season_id=season_id, show=self.show_object)[0]
            return temp_season.checked_update_at()
        return None

    def _episode_update_at_timestamp(self, season_id: str, episode_id: str) -> datetime | None:
        # Check if show_object is saved
        if self.show_object.pk:
            temp_season = Season.objects.get_or_new(season_id=season_id, show=self.show_object)[0]
            if temp_season.pk:
                temp_episode = Episode.objects.get_or_new(episode_id=episode_id, season=temp_season)[0]
                return temp_episode.checked_update_at()
        return None

    def _favicon_file_outdated(self) -> bool:
        """Check if the favicon is outdated."""
        # Favicons shouldn't really need updates so set it to never update
        return self._logged_file_outdated(self._favicon_file, "Favicon")

    def _logger(self, child: str | None = None) -> logging.Logger:
        """Logger instance that contains the website and show name."""
        name = self.show_object.name or self._show_id
        logger = logging.getLogger(__name__).getChild(self._website_name).getChild(name)
        return logger.getChild(child) if child else logger

    def _logged_file_outdated(self, file: PavedPath, name: str, timestamp: datetime | None = None) -> bool:
        """Check if a file exists and log if it is outdated."""
        if output := file.is_outdated(timestamp):
            if not file.exists():
                self._logger().info(f"{name} is missing")
            else:
                self._logger().info(f"{name} is outdated")

        return output

    def update(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        # This docstring is just copied from AbstractScraperClass
        """Download and update the information for an entire show.

        If data is older than the minimum_info_timestamp it will be updated.
        If the data in the database is older than the minimum_modified_timestamp, it will be updated.

        Args:
            minimum_info_timestamp: Download new information if the stored information is older than this.
            minimum_modified_timestamp: Import information if the stored information was last modified before this.
        """
        self._logger().info("Updating")
        self._download_all()
        self._import_all(minimum_modified_timestamp)

    def _download_image_if_outdated(
        self,
        page: BeerShaker,
        url: str,
        file: PavedPath,
        string: str | None,
        timestamp: datetime | None = None,
    ) -> None:
        """Download an image if it does not exist using BeerShaker."""
        if file.is_outdated(timestamp):
            self._logger(f"Downloading {string}").info(url)
            page.download_image(file, url)

    def _download_favicon_if_outdated(self, page: BeerShaker) -> None:
        """Download the favicon for the website."""
        if self._favicon_file_outdated():
            self._logger("Downloading").info("Favicon")
            page.download_favicon(self.DOMAIN, self._favicon_file)

    @transaction.atomic
    def _import_all(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        """Import the information for the show, will not update the information even if it is outdated."""
        self._logger().info("Importing")
        # Mark everything as deleted and let importing mark it as not deleted because this is the easiest way to
        # determine when an entry is deleted
        Show.objects.filter(id=self.show_object.id, website=self._website_name).update(deleted=True)
        if self.show_object.pk:
            Season.objects.filter(show=self.show_object).update(deleted=True)
            Episode.objects.filter(season__show=self.show_object).update(deleted=True)

        self._import_show(minimum_modified_timestamp)
        self._import_seasons(minimum_modified_timestamp)
        self._import_episodes(minimum_modified_timestamp)
        self._set_update_at()

    def _set_update_at(self) -> None:
        latest_episode = (
            Episode.objects.filter(season__show=self.show_object, deleted=False).order_by("-release_date").first()
        )
        """Set the update_at field for the show object automatically based on when the latest episode was released."""
        # ? Why is this being checked?
        if latest_episode:
            # If the episode aired within a month of the last download update the information weekly
            if latest_episode.release_date > self.show_object.info_timestamp - timedelta(days=365 / 12):
                weekly_airing = latest_episode.release_date + timedelta(days=7)

                # If the weekly update has not yet occured update the information a week after the last episode aired
                if weekly_airing > datetime.now().astimezone():
                    self.show_object.update_info_at = weekly_airing
                # If the weekly update has already occured update the information a week from the last update
                else:
                    self.show_object.update_info_at = self.show_object.info_timestamp + timedelta(days=7)
            # Any other situation update the information monthly
            else:
                self.show_object.update_info_at = self.show_object.info_timestamp + timedelta(days=365 / 12)
        self.show_object.save()

    @abstractmethod
    def _import_show(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        """Import the information for just the show."""

    @abstractmethod
    def _import_seasons(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        """Import the information for just the seasons."""

    @abstractmethod
    def _import_episodes(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        """Import the information for just the episodes."""

    @abstractmethod
    def _any_file_outdated(self) -> bool:
        """Check if any of the files are outdated."""

    @abstractmethod
    def _download_all(self) -> None:
        """Download all of the information if it is outdated or missing.

        Does not import the information.
        """
