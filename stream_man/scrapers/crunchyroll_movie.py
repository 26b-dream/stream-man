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
    # Example movie URL
    #   https://www.crunchyroll.com/watch/G25FVD45Q/009-1-the-end-of-the-beginning
    URL_REGEX = re.compile(r"^(?:https:\/\/w?w?w?.?crunchyroll\.com)?\/watch\/*(?P<show_id>.*?)(?:\/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.movie_url = f"{self.DOMAIN}/watch/{self.show_id}"
        self.movie_json_path = JSONFile(self.files_dir(), "movie.json")
        self.movie_extra_json_path = JSONFile(self.files_dir(), "movie_extra.json")

    def outdated_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""
        # This seems like a silly way of checking multiple files, but it allows for every file to be checked even if a
        # file is found to be missing, this is useful for logging purposes. A single pipe could be used instead, but
        # this is easier to read and understand.
        output = self.outdated_movie_json(minimum_timestamp)
        output = self.outdated_movie_images() or output
        output = self.outdated_episode_images() or output
        return output

    def outdated_movie_json(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the movie files are missing or outdated"""
        output = self.check_if_outdated(self.movie_json_path, "Movie JSON", minimum_timestamp)
        output = self.check_if_outdated(self.movie_extra_json_path, "Movie JSON", minimum_timestamp) or output

        return output

    def outdated_movie_images(self) -> Optional[bool]:
        """Check if any of the downloaded episode image files are missing or outdated"""
        # If files are missing but they are not the specific files that are being checked return False and assume
        # checking the parent files will cover the child files
        if self.movie_extra_json_path.exists():
            if episode_images := self.movie_extra_json_path.parsed()["data"][0].get("images"):
                image_url = episode_images["poster_wide"][0][-1]["source"]
                image_path = self.image_path(image_url)
                return self.check_if_outdated(image_path, "Movie image")

    def outdated_episode_images(self) -> Optional[bool]:
        # Check if the main movie image file exists
        if self.movie_json_path.exists():
            if episode_images := self.movie_json_path.parsed()["data"][0].get("images"):
                image_url = episode_images["thumbnail"][0][-1]["source"]
                image_path = self.image_path(image_url)
                return self.check_if_outdated(image_path, "Episode image")

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.outdated_files(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Initializing Playwright")
            with sync_playwright() as playwright:
                # Create a new page that will autoamtically save JSON files when they are requested
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)
                page.on("response", self.save_playwright_files)

                self.download_movie_json(page, minimum_timestamp)
                page.on("response", self.save_playwright_images)
                self.download_movie_image(page)
                self.download_episodes(page)
                page.close()

    def download_movie_json(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the movie files that are outdated or do not exist"""
        if self.outdated_movie_json(minimum_timestamp):
            logging.getLogger(f"{self.logger_identifier()}.Scraping").info(self.movie_url)
            page.goto(self.movie_url, wait_until="networkidle")

            files = [self.movie_json_path, self.movie_extra_json_path]
            self.playwright_wait_for_files(page, files, minimum_timestamp)

    def download_movie_image(self, page: Page) -> None:
        """Download the movie image if it is outdated or do not exist, this is a seperate function from downloading the
        movie because it is easier to download all of the images after downloading all of the JSON files"""
        parsed_show = self.movie_extra_json_path.parsed_cached()["data"][0]
        image_url = parsed_show["images"]["poster_wide"][0][-1]["source"]
        self.playwright_download_image(page, image_url, "movie")

    def download_episodes(self, page: Page) -> None:
        """Download all of the episode files that are outdated or do not exist"""
        parsed_movie_extra = self.movie_json_path.parsed_cached()["data"][0]
        image_url = parsed_movie_extra["images"]["thumbnail"][0][-1]["source"]
        self.playwright_download_image(page, image_url, "episode")

    def save_playwright_files(self, response: Response) -> None:
        """Save specific files that are requested by playwright"""
        # The IDs don't match up, and there is no good way to go from the ID in the URL to the ID returned in the JSON
        # URL, just rename the files to match the ID in the URL

        # Example URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y?locale=en-US
        # Bad URL that needs to be ignored:
        # https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VXXP4Y/movies?locale=en-US
        if re.search(r"content\/v2\/cms\/movie_listings\/(?P<movie_video_id>[A-Za-z0-9]*).?locale", response.url):
            self.playwright_save_json_response(response, self.movie_extra_json_path)

        # Example URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y/movies?locale=en-US
        elif f"cms/objects/{self.show_id}?" in response.url:
            self.playwright_save_json_response(response, self.movie_json_path)

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parrsed_movie = self.movie_json_path.parsed_cached()["data"][0]
            parsed_movie_posters = self.movie_extra_json_path.parsed_cached()["data"][0]

            self.show.name = parrsed_movie["title"]
            self.show.description = parrsed_movie["description"]
            self.show.url = self.movie_url
            # poster_wide is an image with a 16x9 ratio (poster_tall is 6x9)
            # [0][-1] the last image listed is the highest resolution
            image_url = parsed_movie_posters["images"]["poster_wide"][0][-1]["source"]
            self.set_image(self.show, image_url)
            self.show.favicon_url = self.DOMAIN + "/favicons/favicon-32x32.png"
            self.show.deleted = False
            self.show.media_type = "Movie"
            self.show.add_timestamps_and_save(self.movie_json_path)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_movie = self.movie_json_path.parsed_cached()["data"][0]
        # For simplicity just use the show_id as the season_id and episode_id because although there is a second ID that
        # can be found it's not really specific for anything and there is no benefit of mixing it in when just using the
        # one single ID for everything works fine.
        season = Season().get_or_new(season_id=self.show_id, show=self.show)[0]
        if season.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            season.sort_order = 0
            season.number = 1
            season.name = parsed_movie["title"]
            season.deleted = False
            season.add_timestamps_and_save(self.movie_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_movie = self.movie_json_path.parsed_cached()["data"][0]
        parsed_movie_posters = self.movie_extra_json_path.parsed_cached()["data"][0]

        # For simplicity just use the show_id as the season_id and episode_id because although there is a second ID that
        # can be found it's not really specific for anything and there is no benefit of mixing it in when just using the
        # one single ID for everything works fine.
        season = Season().get_or_new(season_id=self.show_id, show=self.show)[0]
        episode = Episode().get_or_new(episode_id=self.show_id, season=season)[0]
        if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            episode.sort_order = 0
            episode.name = parsed_movie["title"]
            episode.number = "1"
            episode.description = parsed_movie["description"]
            episode.duration = parsed_movie["movie_metadata"]["duration_ms"] / 1000
            episode.url = f"{self.DOMAIN}/watch/{self.show_id}"

            # Movie do not have an air_date value so just use the available date for both
            # This value is only present on the secondary file
            strp = "%Y-%m-%dT%H:%M:%S%z"
            episode.air_date = datetime.strptime(parsed_movie_posters["premium_available_date"], strp)
            episode.release_date = datetime.strptime(parsed_movie_posters["premium_available_date"], strp)
            # Every now and then a show just won't have thumbnails
            # See: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri (May be updated later)

            if episode_images := parsed_movie.get("images"):
                # [0] is the first thumbnail design (as far as I can tell there is always just one)
                # [0][-1] the last image listed is the highest resolution
                image_url = episode_images["thumbnail"][0][-1]["source"]
                self.set_image(episode, image_url)

            # No seperate file for episodes so just use the season file
            episode.deleted = False
            episode.add_timestamps_and_save(season.info_timestamp)
