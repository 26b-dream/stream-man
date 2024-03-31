"""Plugin for Crunchyroll series."""
from __future__ import annotations

from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.scraper_functions import BeerShaker, playwright_save_json_response
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from typing_extensions import override

from scrapers.CrunchyRoll.crunchyroll_shared import CrunchyRollShared

if TYPE_CHECKING:
    from json_file import JSONFile
    from paved_path import PavedPath
    from playwright.sync_api._generated import ElementHandle, Response


class CrunchyrollSeries(CrunchyRollShared, AbstractScraperClass):
    """Scraper for Crunchyroll series."""

    # If a movie and series ever share an ID the website names can be changed to differentiate between the two
    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}\/series\/*(?P<show_id>.*?)(?:\/|$)")
    # Example show URLs
    #   https://www.crunchyroll.com/series/G63VW2VWY
    #   https://www.crunchyroll.com/series/G63VW2VWY/non-non-biyori

    @override
    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self._show_url = f"{self.DOMAIN}/series/{self._show_id}"

    @cached_property
    def _show_image_url(self) -> str:
        """Show image URL."""
        return self._strict_image_url(self._show_json_file, "poster_wide")

    @cached_property
    def _show_image_file(self) -> PavedPath:
        """Show image file."""
        return self._image_file_from_url(self._show_image_url, "show")

    def _episode_image_file(self, season_file: JSONFile, episode_index: int) -> PavedPath | None:
        url = self._episode_image_url(season_file, episode_index)
        return self._image_file_from_url(url, "episode") if url else None

    def _episode_image_url(self, season_file: JSONFile, episode_index: int) -> str | None:
        return self._image_url(season_file, "thumbnail", episode_index)

    @override
    def _any_file_outdated(self) -> bool:
        return (
            self._show_json_or_show_seasons_json_outdated()
            or self._any_season_json_outdated()
            or self._show_image_missing()
            or self._any_episode_image_missing()
        )

    def _show_json_or_show_seasons_json_outdated(self) -> bool:
        timestamp = self.show_object.checked_update_at()
        return self._logged_file_outdated(self._show_json_file, timestamp) or self._logged_file_outdated(
            self._show_seasons_json_file,
            timestamp,
        )

    def _any_season_json_outdated(self) -> bool:
        if not self._show_seasons_json_file.exists():
            return False

        for season in self._show_seasons_json_file.parsed_cached()["data"]:
            file = self._season_json_file(season["id"])
            timestamp = self._season_update_at(season["id"])
            if self._logged_file_outdated(file, timestamp):
                return True

        return False

    def _show_image_missing(self) -> bool:
        if not self._show_json_file.exists():
            return True

        # By default images should never need to be updated
        return self._logged_file_outdated(self._show_image_file)

    def _any_episode_image_missing(self) -> bool:
        if not self._show_seasons_json_file.exists():
            return True

        for show_season in self._show_seasons_json_file.parsed_cached()["data"]:
            if not self._season_json_file(show_season["id"]).exists():
                return True
            season_json_file = self._season_json_file(show_season["id"])
            season_json_parsed = season_json_file.parsed_cached()
            for i, _episode_parsed in enumerate(season_json_parsed["data"]):
                if image_file := self._episode_image_file(season_json_file, i):  # noqa: SIM102 - Ugly
                    if self._logged_file_outdated(image_file):
                        return True

        return False

    @override
    def _download_all(self) -> None:
        with sync_playwright() as playwright:
            # Create a new page that will autoamtically save JSON files when they are requested
            page = BeerShaker(playwright)
            page.on("response", self._save_playwright_files)

            self._download_show_if_outdated(page)
            self._download_seasons_if_outdated(page)

            self._download_show_image_if_missing(page)
            self._download_episode_images_if_missing(page)
            self._download_favicon_if_oudated(page)

            page.close()

    def _download_show_if_outdated(self, page: BeerShaker) -> None:
        if self._show_json_or_show_seasons_json_outdated():
            self._logger("Opening").info(self._show_url)
            # networkidle hangs forever, use
            page.goto(self._show_url, wait_until="load")
            files = (self._show_json_file, self._show_seasons_json_file)
            page.wait_for_files(files, self._show_update_at())

    def _download_seasons_if_outdated(self, page: BeerShaker) -> None:
        show_seasons_json_parsed = self._show_seasons_json_file.parsed_cached()
        for show_season in show_seasons_json_parsed["data"]:
            season_json_file = self._season_json_file(show_season["id"])
            season_id = show_season["id"]

            if season_json_file.is_outdated(self._season_update_at(season_id)):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this one time, all later pages can reuse existing page
                if self._show_url not in page.url:
                    self._logger("Opening").info(self._show_url)
                    page.goto(self._show_url, wait_until="networkidle")

                # Season selector only exists for shows with multiple seasons
                if page.query_selector("div[class='season-info']"):
                    # Open season selector
                    self._logger("Opening Season Selector").info(season_id)
                    page.locator("div[class='season-info']").click()

                    # Click season
                    self._logger("Clicking Season").info(season_id)
                    self._season_button(page, show_season).click()

                page.wait_for_files(season_json_file, self._season_update_at(season_id))

    def _download_show_image_if_missing(self, page: BeerShaker) -> None:
        self._download_image_if_outdated(page, self._show_image_url, self._show_image_file)

    def _download_episode_images_if_missing(self, page: BeerShaker) -> None:
        for show_season in self._show_seasons_json_file.parsed_cached()["data"]:
            season_json_file = self._season_json_file(show_season["id"])
            season_json_parsed = season_json_file.parsed_cached()

            for i, _episode_parsed in enumerate(season_json_parsed["data"]):
                if image_url := self._episode_image_url(season_json_file, i):
                    image_path = self._episode_image_file(season_json_file, i)
                    self._download_image_if_outdated(page, image_url, image_path)

    def _save_playwright_files(self, response: Response) -> None:
        """Save specific files from the response recieved by playwright."""
        # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP?locale=en-US
        re_domain = re.escape(self.DOMAIN)  # Stops lines from being too long
        show_regex = re.compile(rf"^{re_domain}\/content\/v2\/cms\/series\/(?P<show_id>.*?)\?")

        # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP/seasons?locale=en-US
        show_seasons_regex = re.compile(rf"^{re_domain}\/content\/v2\/cms\/series\/(?P<show_id>.*?)\/seasons")

        # Example URL: https://www.crunchyroll.com/content/v2/cms/seasons/GYQ4MQ496/episodes?locale=en-US
        season_regex = re.compile(rf"^{re_domain}\/content\/v2\/cms\/seasons\/(?P<season_id>.*?)\/episodes")

        if show_seasons_regex.match(response.url):
            playwright_save_json_response(response, self._show_seasons_json_file)

        # Alwyays check after show_seasons due to regex
        elif show_regex.match(response.url):
            playwright_save_json_response(response, self._show_json_file)

        elif season_regex.match(response.url):
            season_id = re.strict_search(season_regex, response.url)["season_id"]
            playwright_save_json_response(response, self._season_json_file(season_id))

    def _season_button(self, page: BeerShaker, season: dict[str, str]) -> ElementHandle:
        """Find and return the button that changes the season shown on the show page."""
        season_string = f"S{season['season_number']}: {season['title']}"
        for maybe_season in page.query_selector_all("div[class='seasons-select'] div[role='button']"):
            # Use in because it also listed the number of episodes in inner_text
            if season_string in maybe_season.inner_text():
                return maybe_season

        msg = f"Could not find season button for {season_string}"
        raise RuntimeError(msg)

    @override
    def _import_show(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        # I don't see anything on Cruncyhroll that shows the difference between a TV Series, ONA, or OVA, so just list
        # this as a series which is a generic catch all term
        if self.show_object.is_outdated(minimum_modified_timestamp):
            parsed_json = self._show_json_file.parsed_cached()["data"][0]
            # I don't see anything on Cruncyhroll that shows the difference between a TV Series, ONA, or OVA, so just
            # list this as a series which is a generic catch all term
            self.show_object.media_type = "Series"
            self.show_object.name = parsed_json["title"]
            self.show_object.description = parsed_json["description"]
            self.show_object.set_image(self._show_image_file)
            self.show_object.set_favicon(self._favicon_file)
            self.show_object.deleted = False
            self.show_object.add_timestamps_and_save(self._show_json_file.aware_mtime())

    @override
    def _import_seasons(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        show_seasons_json_parsed = self._show_seasons_json_file.parsed_cached()

        for sort_order, show_season in enumerate(show_seasons_json_parsed["data"]):
            season_json_path = self._season_json_file(show_season["id"])
            season_json_parsed = season_json_path.parsed_cached()
            parsed_episode = season_json_parsed["data"][0]

            season = Season.objects.get_or_new(season_id=show_season["id"], show=self.show_object)[0]

            if season.is_outdated(minimum_modified_timestamp):
                season.number = parsed_episode["season_number"]
                season.name = parsed_episode["season_title"]
                season.sort_order = sort_order
                season.deleted = False
                season.add_timestamps_and_save(season_json_path.aware_mtime())

    @override
    def _import_episodes(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        show_seasons_json_parsed = self._show_seasons_json_file.parsed_cached()["data"]

        for show_season in show_seasons_json_parsed:
            season_json_file = self._season_json_file(show_season["id"])
            season_json_parsed = season_json_file.parsed_cached()
            season_info = Season.objects.get_or_new(season_id=show_season["id"], show=self.show_object)[0]

            for i, episode_parsed in enumerate(season_json_parsed["data"]):
                episode_info = Episode.objects.get_or_new(episode_id=episode_parsed["id"], season=season_info)[0]

                if episode_info.is_outdated(minimum_modified_timestamp):
                    episode_info.sort_order = i
                    episode_info.name = episode_parsed["title"]
                    episode_info.number = episode_parsed["episode"]
                    episode_info.description = episode_parsed["description"]
                    episode_info.duration = episode_parsed["duration_ms"] / 1000
                    episode_info.url = f"{self.DOMAIN}/watch/{episode_parsed['id']}"

                    strp = "%Y-%m-%dT%H:%M:%S%z"
                    available_date = episode_parsed["premium_available_date"]
                    episode_info.air_date = datetime.strptime(episode_parsed["episode_air_date"], strp).astimezone()
                    episode_info.release_date = datetime.strptime(available_date, strp).astimezone()
                    # Every now and then a show just won't have thumbnails and the thumbnail will be added a few weeks
                    # later, see: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri
                    if image_path := self._episode_image_file(season_json_file, i):
                        episode_info.set_image(image_path)

                    episode_info.deleted = False
                    # No seperate file for episodes so just use the season file because it has episode information
                    episode_info.add_timestamps_and_save(season_info.info_timestamp)
