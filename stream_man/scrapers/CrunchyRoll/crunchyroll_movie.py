"""Plugin for crunchyroll movie."""
from __future__ import annotations

import logging
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.scraper_functions import BeerShaker, playwright_save_json_response
from json_file import JSONFile
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from typing_extensions import override

from scrapers.CrunchyRoll.crunchyroll_shared import CrunchyRollShared

if TYPE_CHECKING:
    from paved_path import PavedPath
    from playwright.sync_api._generated import Response
logger = logging.getLogger(__name__)


class CrunchyrollMovie(CrunchyRollShared, AbstractScraperClass):
    """Scraper for Crunchyroll movies."""

    # If a movie and series ever share an ID the website names can be changed to differentiate between the two
    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
    # Example URL: https://www.crunchyroll.com/watch/G25FVD45Q/009-1-the-end-of-the-beginning
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}\/watch\/*(?P<show_id>.*?)(?:\/|$)")

    @override
    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self._show_url = f"{self.DOMAIN}/watch/{self._show_id}"

    @cached_property
    def _movie_2_json_file(self) -> JSONFile:
        return JSONFile(self._show_dir, "Movie2.json")

    @cached_property
    def _episode_image_url(self) -> str:
        return self._strict_image_url(self._movie_json_file, "thumbnail")

    @cached_property
    def _movie_image_url(self) -> str:
        # Pass an empty string because the parent expects a string
        return self._strict_image_url(self._movie_2_json_file, "poster_wide")

    @cached_property
    def _episode_image_file(self) -> PavedPath:
        return self._image_file_from_url(self._episode_image_url, "episode")

    @cached_property
    def _movie_image_file(self) -> PavedPath:
        return self._image_file_from_url(self._movie_image_url, "movie")

    @override
    def _any_file_outdated(self) -> bool:
        output = self._movie_json_outdated()
        output = self._movie_image_missing() or output
        output = self._episode_image_missing() or output
        return self._favicon_file_outdated() or output

    def _movie_json_outdated(self) -> bool:
        timestamp = self.show_object.checked_update_at()
        output = self._logged_file_outdated(self._movie_json_file, "Movie JSON", timestamp)
        return self._logged_file_outdated(self._movie_2_json_file, "Movie 2 JSON", timestamp) or output

    def _movie_image_missing(self) -> bool:
        timestamp = self.show_object.checked_update_at()
        if not self._movie_2_json_file.exists():
            return False

        return self._logged_file_outdated(self._movie_image_file, "Movie Image", timestamp)

    def _episode_image_missing(self) -> bool:
        timestamp = self.show_object.checked_update_at()
        if not self._movie_json_file.exists():
            return False

        return self._logged_file_outdated(self._episode_image_file, "Episode Image", timestamp)

    @override
    def _download_all(self) -> None:
        if self._any_file_outdated():
            self._logger().info("Downloading")
            with sync_playwright() as playwright:
                page = BeerShaker(playwright)
                self._download_movie_jsons_if_outdated(page)
                self._download_image_if_outdated(page, self._movie_image_url, self._movie_image_file, "Movie Image")
                string = "Episode Image"
                self._download_image_if_outdated(page, self._episode_image_url, self._episode_image_file, string)
                self._download_favicon_if_outdated(page)
                page.close()

    def _download_movie_jsons_if_outdated(self, page: BeerShaker) -> None:
        if self._movie_json_outdated():
            page.on("response", self._save_playwright_files)
            self._logger("Downloading").getChild("Movie JSON Files").info(self._show_url)
            page.goto(self._show_url, wait_until="load")
            files = (self._movie_json_file, self._movie_2_json_file)
            page.wait_for_files(files, self.show_object.checked_update_at())
            page.remove_listener("response", self._save_playwright_files)

    def _save_playwright_files(self, response: Response) -> None:
        # Example Good URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y?locale=en-US
        # Example Bad URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VXXP4Y/movies?locale=en-US
        # The IDs don't match up, and there is no good way to go from the ID in the URL to the ID returned in the JSON
        # URL. For simplicity just rename the files to match the ID in the URL
        if re.search(r"content/v2/cms/movie_listings/(?P<movie_video_id>[A-Za-z0-9]*).?locale", response.url):
            playwright_save_json_response(response, self._movie_2_json_file)

        # Example URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y/movies?locale=en-US
        elif f"cms/objects/{self._show_id}?" in response.url:
            playwright_save_json_response(response, self._movie_json_file)

    @override
    def _import_show(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if self.show_object.is_outdated(minimum_modified_timestamp):
            self.show_object.media_type = "Movie"
            self.show_object.url = self._show_url
            parsed_json = self._movie_2_json_file.parsed_cached()["data"][0]
            self.show_object.name = parsed_json["title"]
            self.show_object.description = parsed_json["description"]
            self.show_object.set_image(self._movie_image_file)
            self.show_object.set_favicon(self._favicon_file)
            self.show_object.deleted = False
            self.show_object.add_timestamps_and_save(self._movie_image_file.aware_mtime())

    @override
    def _import_seasons(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        # For simplicity just use the show_id as the season_id and episode_id because although there is a second ID that
        # can be found it's not really specific for anything and there is no benefit of mixing it in when just using the
        # one single ID for everything works fine.
        season = Season.objects.get_or_new(season_id=self._show_id, show=self.show_object)[0]
        if season.is_outdated(minimum_modified_timestamp):
            season.sort_order = 0
            season.number = 0
            season.name = "Movie"
            season.deleted = False
            season.add_timestamps_and_save(self._movie_json_file.aware_mtime())

    @override
    def _import_episodes(
        self,
        minimum_modified_timestamp: None | datetime = None,
    ) -> None:
        parsed_movie = self._movie_json_file.parsed_cached()["data"][0]
        parsed_movie_extra = self._movie_2_json_file.parsed_cached()["data"][0]

        # For simplicity just use the show_id as the season_id and episode_id because although there is a second ID that
        # can be found it's not really specific for anything and there is no benefit of mixing it in when just using the
        # one single ID for everything works fine.
        season = Season.objects.get_or_new(season_id=self._show_id, show=self.show_object)[0]
        episode = Episode.objects.get_or_new(episode_id=self._show_id, season=season)[0]
        if episode.is_outdated(minimum_modified_timestamp):
            episode.sort_order = 0
            episode.name = "Movie"
            episode.number = "0"
            episode.description = parsed_movie["description"]
            episode.duration = parsed_movie["movie_metadata"]["duration_ms"] / 1000
            episode.url = f"{self.DOMAIN}/watch/{self._show_id}"

            # Movie do not have an air_date value so just use the available date for both
            # This value is only present on the secondary file
            strp = "%Y-%m-%dT%H:%M:%S%z"
            episode.air_date = datetime.strptime(parsed_movie_extra["premium_available_date"], strp).astimezone()
            episode.release_date = episode.air_date
            episode.set_image(self._episode_image_file)

            # No seperate file for episodes so just use the season file
            episode.deleted = False
            episode.add_timestamps_and_save(season.info_timestamp)
