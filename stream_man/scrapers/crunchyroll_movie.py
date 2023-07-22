"""PLugin for crunchyroll show"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from extended_path import ExtendedPath
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

if TYPE_CHECKING:
    from typing import Optional

    from playwright.sync_api._generated import Page, Response


class CrunchyrollSeries(ScraperShowShared, AbstractScraperClass):
    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
    FAVICON_URL = DOMAIN + "/favicons/favicon-32x32.png"

    # Example movie URL
    #   https://www.crunchyroll.com/watch/G25FVD45Q/009-1-the-end-of-the-beginning
    SHOW_URL_REGEX = re.compile(r"^(?:https:\/\/w?w?w?.?crunchyroll\.com)?\/watch\/*(?P<show_id>.*?)(?:\/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.movie_url = f"{self.DOMAIN}/series/{self.show_id}"

    def outdated_files(self, minimum_timestamp: Optional[datetime] = None) -> list[ExtendedPath]:
        """Check if any of the downloaded files are missing or outdated"""
        return self.outdated_movie_files(minimum_timestamp)

    def outdated_movie_files(self, minimum_timestamp: Optional[datetime] = None) -> list[ExtendedPath]:
        """Check if any of the downloaded movie files are missing or outdated"""

        outdated_files: list[ExtendedPath] = []
        if self.show_json_path.outdated(minimum_timestamp):
            outdated_files.append(self.show_json_path)
        if self.season_json_path(self.show_id).outdated(minimum_timestamp):
            outdated_files.append(self.season_json_path(self.show_id))

        return outdated_files

    def save_playwright_files(self, response: Response) -> None:
        """Function that is called on all of the reesponses that the playwright browser gets"""
        # The IDs don't match up, and there is no good way to go from the ID in the URL to the ID returned in the JSON
        # URL, just rename the files to match the ID in the URL

        # Example URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y?locale=en-US
        if re.compile(r"movie_listings/(?P<show_id>.*?)\?locale").search(response.url):
            raw_json = response.json()
            path = self.show_json_path
            path.write(json.dumps(raw_json))

        # Example URL: https://www.crunchyroll.com/content/v2/cms/movie_listings/GY8VX2G9Y/movies?locale=en-US
        elif re.compile(r"movie_listings/(?P<show_id>.*?)\/movies\?").search(response.url):
            raw_json = response.json()
            path = self.season_json_path(self.show_id)
            path.write(json.dumps(raw_json))

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if outdated_files := self.outdated_files(minimum_timestamp):
            file_list = "\n".join([str(file) for file in outdated_files])
            logging.getLogger(self.logger_identifier()).info("Found outdated files %s", file_list)

            with sync_playwright() as playwright:
                # Create a new page that will autoamtically save JSON files when they are requested
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)
                page.on("response", self.save_playwright_files)

                self.download_movie(page, minimum_timestamp)
                page.close()

    def download_movie(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the show files if they are outdated or do not exist"""
        if outdated_files := self.outdated_movie_files(minimum_timestamp):
            # Join all outdated files into line seperateed string
            file_list = "\n".join([str(file) for file in outdated_files])
            logging.getLogger(self.logger_identifier()).info("Found outdated movie files %s", file_list)
            logging.getLogger(self.logger_identifier()).info("Scraping %s", self.movie_url)

            page.goto(self.movie_url, wait_until="networkidle")

            self.playwright_wait_for_files(
                page, minimum_timestamp, self.show_json_path, self.season_json_path(self.show_id)
            )

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.show_json_path.parsed_cached()["data"][0]

            self.show_info.name = parsed_show["title"]
            self.show_info.description = parsed_show["description"]
            self.show_info.url = self.movie_url
            # poster_wide is an image with a 16x9 ratio (poster_tall is 6x9)
            # [0] is the first poster_wide design (as far as I can tell there is always just one)
            # [0][0] the first image listed is the lowest resolution
            # [0][1] the last image listed is the highest resolution
            # TODO: Get the favicon dynamically from the website
            # TODO: poster_long may be a better option depending on how the website lays out the information
            # TODO: Higher resolutions may be preferable depending on website layout
            self.show_info.thumbnail_url = parsed_show["images"]["poster_wide"][0][0]["source"]
            self.show_info.image_url = parsed_show["images"]["poster_wide"][0][-1]["source"]
            self.show_info.favicon_url = self.FAVICON_URL
            self.show_info.deleted = False
            self.show_info.media_type = "Movie"
            self.show_info.add_timestamps_and_save(self.show_json_path)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        season = self.show_json_path.parsed_cached()["data"][0]
        # season_id is the value that is returned on JSON which is not present on the website in any user facing way
        season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]
        if season_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            season_info.sort_order = 0
            season_info.number = 1
            season_info.name = season["title"]
            season_info.deleted = False
            season_info.add_timestamps_and_save(self.show_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        season = self.season_json_path(self.show_id).parsed_cached()["data"][0]
        # season_id is the value that is returned on JSON which is not present on the website in any user facing way
        season_info = Season().get_or_new(season_id=season["listing_id"], show=self.show_info)[0]
        # episode_id is just set to match the season_id because there is no unique identifier for episodes for movies
        episode_info = Episode().get_or_new(episode_id=season["listing_id"], season=season_info)[0]

        if episode_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            episode_info.sort_order = 0
            episode_info.name = season["title"]
            episode_info.number = "1"
            episode_info.description = season["description"]
            episode_info.duration = season["duration_ms"] / 1000
            episode_info.url = f"{self.DOMAIN}/watch/{self.show_id}"

            # Movie do not have an air_date value so just use the available date for both
            episode_info.air_date = datetime.strptime(season["premium_available_date"], "%Y-%m-%dT%H:%M:%S%z")
            episode_info.release_date = datetime.strptime(season["premium_available_date"], "%Y-%m-%dT%H:%M:%S%z")
            # Every now and then a show just won't have thumbnails
            # See: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri (May be updated later)
            if episode_images := season.get("images"):
                # [0] is the first thumbnail design (as far as I can tell there is always just one)
                # [0][0] the first image listed is the lowest resolution
                # [0][1] the last image listed is the highest resolution
                # TODO: Higher resolutions may be preferable depending on website layout
                episode_info.thumbnail_url = episode_images["thumbnail"][0][0]["source"]
                episode_info.image_url = episode_images["thumbnail"][0][-1]["source"]
            # No seperate file for episodes so just use the season file
            episode_info.deleted = False
            episode_info.add_timestamps_and_save(season_info.info_timestamp)
