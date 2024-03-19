"""Shared code for scrapers."""

from __future__ import annotations

import functools
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from json_file import JSONFile
from media.models import Episode, Season, Show

import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR

if TYPE_CHECKING:
    from re import Pattern

    from paved_path import PavedPath

    from common.scraper_functions import BeerShaker


class ScraperShowShared(ABC):
    """Shared code for scraping show information."""

    URL_REGEX: Pattern[str]
    """Regex pattern used to match the show URL."""
    WEBSITE: str
    """The name of the website."""

    @classmethod
    def website_name(cls) -> str:
        """Name of the website.

        This may seem redundant, but it is useful for when a scraper supports multiple websites.

        Returns:
        -------
        str: The name of the website.
        """
        return cls.WEBSITE

    @classmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        """Check if a URL is a valid show URL for a specific scraper.

        Parameters:
        ----------
        show_url (str): The URL to check.

        Returns:
        -------
        bool: True if the URL is a valid show URL, False otherwise.
        """
        return bool(re.search(cls.URL_REGEX, show_url))

    @abstractmethod
    def _download_all(
        self,
        minimum_timestamp: datetime | None = None,
    ) -> None:
        """Download all of the information if it is outdated or missing.

        Parameters:
        -----------
        minimum_timestamp (datetime | None): The minimum timestamp for files to be downloaded.

        Returns:
        --------
        None
        """

    def __init__(self, show_url: str) -> None:
        """Initializes a Scraper.

        Args:
            show_url (str): The URL of the show.

        Returns:
            None
        """
        self._show_id = str(re.strict_search(self.URL_REGEX, show_url).group("show_id"))
        self._show = Show.objects.get_or_new(show_id=self._show_id, website=self.WEBSITE)[0]
        self._files_dir = DOWNLOADED_FILES_DIR / self.WEBSITE / self._show_id
        self._show_json_file = JSONFile(self._files_dir, "Data", f"Show ({self._show_id}).json")
        self._show_seasons_json_file = JSONFile(self._files_dir, "Data", f"Show Seasons ({self._show_id}).json")
        self._movie_json_file = JSONFile(self._files_dir, "Data", f"Movie ({self._show_id}).json")

        # ? Is this workaround still needed?
        if not TYPE_CHECKING:
            self._season_json_file = functools.cache(self._season_json_file)
            self._image_file_from_url = functools.cache(self._image_file_from_url)

    def _season_json_file(
        self,
        season_name: int | str,
        season_id: str | int | None = None,
        page: int | None = None,
    ) -> JSONFile:
        """Get the JSON file for a season.

        You can have a season without a unique identfier, but you will always have a season name because there must be
        some way to refer to the season.

        Parameters:
        -----------
        season_name (int | str): The name of the season.
        season_id (str | int | None): The ID of the season.
        page (int | None): The page number of the season.

        Returns:
        --------
        JSONFile: The JSON file for the season.
        """
        # If the season name changes that should be fine because show and seasons are updated in batches at the same
        # time
        season_string = f"Season {season_name} ({season_id})" if season_id else f"Season {season_name}"

        # Page numbers aren't needed for all files, so only add them when needed
        if page is not None:
            season_string += f"/Page {page}"

        # Append extension manually just in case the id contains a period in it
        season_string += ".json"

        return JSONFile(self._files_dir, "Data", season_string)

    def logger(self, child: str | None = None) -> logging.Logger:
        """Logger instance that contains the website and show name.

        Parameters:
        -----------
        child (str | None): The name of the child logger to create. If None, the logger will be for the show itself.

        Returns:
        --------
        logging.Logger: The logger instance for the show or a child of the show logger
        """
        name = self._show.name or self._show_id
        logger = logging.getLogger(__name__).getChild(self.WEBSITE).getChild(name)

        return logger.getChild(child) if child else logger

    def update(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        """Download and update the information for the entire show.

        If files are older than the minimum_info_timestamp, they will be downloaded.
        If information in the database is older than the minimum_modified_timestamp, it will be updated.

        Parameters
        ----------
        minimum_info_timestamp (datetime | None): The minimum timestamp for files to be downloaded.
        minimum_modified_timestamp (datetime | None): The minimum timestamp for information to be updated.

        Returns:
        -------
        None
        """
        self.logger().info("Updating")
        self._download_all(minimum_info_timestamp)
        self._import_all(minimum_info_timestamp, minimum_modified_timestamp)

    @transaction.atomic
    def _import_all(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        self.logger().info("Importing")
        # Mark everything as deleted and let importing mark it as not deleted because this is the easiest way to
        # determine when an entry is deleted
        Show.objects.filter(id=self._show.id, website=self.WEBSITE).update(deleted=True)
        if self._show.id:
            Season.objects.filter(show=self._show).update(deleted=True)
            Episode.objects.filter(season__show=self._show).update(deleted=True)

        # Clear all caches just in case

        self._import_show(minimum_info_timestamp, minimum_modified_timestamp)
        self._import_seasons(minimum_info_timestamp, minimum_modified_timestamp)
        self._import_episodes(minimum_info_timestamp, minimum_modified_timestamp)
        self._set_update_at()

    @abstractmethod
    def _import_show(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        pass

    @abstractmethod
    def _import_seasons(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        pass

    @abstractmethod
    def _import_episodes(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        pass

    def _set_update_at(self) -> None:
        latest_episode = (
            Episode.objects.filter(season__show=self._show, deleted=False).order_by("-release_date").first()
        )
        # ? Why is this being checked?
        if latest_episode:
            # If the episode aired within a month of the last download update the information weekly
            if latest_episode.release_date > self._show.info_timestamp - timedelta(days=365 / 12):
                weekly_airing = latest_episode.release_date + timedelta(days=7)

                # If the weekly update has not yet occured update the information a week after the last episode aired
                if weekly_airing > datetime.now().astimezone():
                    self._show.update_at = weekly_airing
                # If the weekly update has already occured update the information a week from the last update
                else:
                    self._show.update_at = self._show.info_timestamp + timedelta(days=7)
            # Any other situation update the information monthly
            else:
                self._show.update_at = self._show.info_timestamp + timedelta(days=365 / 12)
        self._show.save()

    def _image_file_from_url(self, image_url: str, name: str, extension: str | None = None) -> PavedPath:
        image_name = image_url.split("/")[-1]
        image_id = image_name.split(".")[0]
        if extension is None:
            extension = image_name.split(".")[-1]
        file = self._files_dir / "Images" / f"{name} ({image_id}).{extension}"
        file.title = f"{name} ({image_id}).{extension}"
        return file

    def _download_image(self, page: BeerShaker, url: str, file: PavedPath) -> None:
        if file.is_outdated():
            self.logger("Downloading").info(file.title)
            page.download_image(file, url)

    @abstractmethod
    def _any_file_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        pass
