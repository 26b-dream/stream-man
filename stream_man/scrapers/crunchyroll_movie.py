"""PLugin for crunchyroll show"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from json_file import JSONFile
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # pyright: ignore [reportMissingTypeStubs]
from scrapers.crunchyroll_shared import CrunchyRollShared

if TYPE_CHECKING:
    from typing import Optional

    from playwright.sync_api._generated import Page, Response


class CrunchyrollMovie(CrunchyRollShared, AbstractScraperClass):
    DOMAIN = "https://www.crunchyroll.com"
    # Example URL: https://www.crunchyroll.com/watch/G25FVD45Q/009-1-the-end-of-the-beginning
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}\/watch\/*(?P<show_id>.*?)(?:\/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/watch/{self.show_id}"
        self.movie_json_path = JSONFile(self.files_dir(), "movie.json")
        self.movie_2_json_path = JSONFile(self.files_dir(), "movie_extra.json")

    def any_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        output = self.movie_json_outdated(minimum_timestamp)
        output = self.movie_image_missing() or output
        output = self.episode_image_missing() or output
        return output

    def movie_json_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if the either of the movie JSON files are missing or outdated"""
        output = self.is_file_outdated(self.movie_json_path, "Movie JSON", minimum_timestamp)
        output = self.is_file_outdated(self.movie_2_json_path, "Movie 2 JSON", minimum_timestamp) or output
        return output

    def movie_image_missing(self) -> bool:
        """Check if the movie image file is missing"""
        if self.movie_2_json_path.exists():
            image_url = self.strict_image_url(self.movie_2_json_path, "poster_wide")
            image_path = self.image_path_from_url(image_url)
            return self.is_file_outdated(image_path, "Movie image")

        return False

    def episode_image_missing(self) -> bool:
        """Check if the episode image file is missing"""
        if self.movie_json_path.exists():
            image_url = self.strict_image_url(self.movie_json_path, "thumbnail")
            image_path = self.image_path_from_url(image_url)
            return self.is_file_outdated(image_path, "Episode image")

        return False

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_file_outdated(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Initializing Playwright")
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)

                page.on("response", self.save_playwright_files)
                self.download_movie(page, minimum_timestamp)

                page.on("response", self.playwright_response_save_images)
                self.download_movie_image(page)
                self.download_episode_image(page)

                page.close()

    def download_movie(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download both of the movie JSON files if at least one is missing or outdated"""
        if self.movie_json_outdated(minimum_timestamp):
            self.logged_goto(page, self.show_url, wait_until="networkidle")

            files = [self.movie_json_path, self.movie_2_json_path]
            self.playwright_wait_for_files(page, files, minimum_timestamp)

    def download_movie_image(self, page: Page) -> None:
        """Download the movie image if it is missing or outdated"""
        url = self.strict_image_url(self.movie_2_json_path, "poster_wide")
        self.playwright_download_image_if_needed(page, url, "Movie")

    def download_episode_image(self, page: Page) -> None:
        """Download the episode image if it is missing or outdated"""
        url = self.strict_image_url(self.movie_json_path, "thumbnail")
        self.playwright_download_image_if_needed(page, url, "Episode")

    def save_playwright_files(self, response: Response) -> None:
        """Save specific files from the response recieved by playwright"""
        # Example Good URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y?locale=en-US
        # Example Bad URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VXXP4Y/movies?locale=en-US
        # The IDs don't match up, and there is no good way to go from the ID in the URL to the ID returned in the JSON
        # URL. For simplicity just rename the files to match the ID in the URL
        if re.search(r"content\/v2\/cms\/movie_listings\/(?P<movie_video_id>[A-Za-z0-9]*).?locale", response.url):
            self.playwright_save_json_response(response, self.movie_2_json_path)

        # Example URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y/movies?locale=en-US
        elif f"cms/objects/{self.show_id}?" in response.url:
            self.playwright_save_json_response(response, self.movie_json_path)

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        self.import_show_shared(self.movie_2_json_path, "Movie", minimum_info_timestamp, minimum_modified_timestamp)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # For simplicity just use the show_id as the season_id and episode_id because although there is a second ID that
        # can be found it's not really specific for anything and there is no benefit of mixing it in when just using the
        # one single ID for everything works fine.
        season = Season().get_or_new(season_id=self.show_id, show=self.show)[0]
        if season.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            season.sort_order = 0
            season.number = 0
            season.name = "Movie"
            season.deleted = False
            season.add_timestamps_and_save(self.movie_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_movie = self.movie_json_path.parsed_cached()["data"][0]
        parsed_movie_extra = self.movie_2_json_path.parsed_cached()["data"][0]

        # For simplicity just use the show_id as the season_id and episode_id because although there is a second ID that
        # can be found it's not really specific for anything and there is no benefit of mixing it in when just using the
        # one single ID for everything works fine.
        season = Season().get_or_new(season_id=self.show_id, show=self.show)[0]
        episode = Episode().get_or_new(episode_id=self.show_id, season=season)[0]
        if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            episode.sort_order = 0
            episode.name = "Movie"
            episode.number = "0"
            episode.description = parsed_movie["description"]
            episode.duration = parsed_movie["movie_metadata"]["duration_ms"] / 1000
            episode.url = f"{self.DOMAIN}/watch/{self.show_id}"

            # Movie do not have an air_date value so just use the available date for both
            # This value is only present on the secondary file
            strp = "%Y-%m-%dT%H:%M:%S%z"
            episode.air_date = datetime.strptime(parsed_movie_extra["premium_available_date"], strp)
            episode.release_date = episode.air_date
            image_url = self.strict_image_url(self.movie_json_path, "thumbnail")
            image_path = self.image_path_from_url(image_url)
            self.set_image(episode, image_path)

            # No seperate file for episodes so just use the season file
            episode.deleted = False
            episode.add_timestamps_and_save(season.info_timestamp)
