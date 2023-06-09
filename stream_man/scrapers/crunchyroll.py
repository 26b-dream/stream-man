"""PLugin for crunchyroll show"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from common.constants import DOWNLOADED_FILES_DIR
from django.db import transaction
from extended_path import ExtendedPath
from html_file import HTMLFile
from json_file import JSONFile
from media.models import Episode, Season, Show
from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from typing import Optional

    from playwright.sync_api._generated import ElementHandle, Page, Response


class CrunchyrollShow(ScraperShowShared, AbstractScraperClass):
    """PLugin for crunchyroll show"""

    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
    FAVICON_URL = DOMAIN + "/favicons/favicon-32x32.png"

    # Example show URLs
    #   https://www.crunchyroll.com/series/G63VW2VWY
    #   https://www.crunchyroll.com/series/G63VW2VWY/non-non-biyori
    SHOW_URL_REGEX = re.compile(r"^(?:https:\/\/w?w?w?.?crunchyroll\.com)?\/series\/*(?P<show_id>.*?)(?:\/|$)")

    @classmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        """Check if a URL is a valid show URL for a specific scraper"""
        return bool(re.search(cls.SHOW_URL_REGEX, show_url))

    def __init__(self, show_url: str) -> None:
        self.show_id = str(re.strict_search(self.SHOW_URL_REGEX, show_url).group("show_id"))
        self.show_info = Show().get_or_new(show_id=self.show_id, website=self.WEBSITE)[0]

    def show_object(self) -> Show:
        """The Show object from the database"""
        return self.show_info

    def logger_identifier(self) -> str:
        """The best possibel string for identifying a show given the known information"""
        if self.show_info.name:
            return f"{self.WEBSITE}.{self.show_info.name}"

        return f"{self.WEBSITE}.{self.show_id}"

    @lru_cache(maxsize=1024)  # Value will never change
    def show_url(self) -> str:
        """URL for the show"""
        return f"{self.DOMAIN}/series/{self.show_id}"

    @lru_cache(maxsize=1024)  # Value will never change
    def episode_url(self, episode: Episode) -> str:
        """URL for a specific episode"""
        return f"{self.DOMAIN}/watch/{episode.episode_id}"

    @lru_cache(maxsize=1024)  # Value will never change
    def show_html_path(self) -> HTMLFile:
        """Path for the HTML file for the show"""
        return HTMLFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "show", f"{self.show_id}.html")

    @lru_cache(maxsize=1024)  # Value will never change
    def season_html_path(self, season_id: str) -> HTMLFile:
        """Path for HTML file for a specific season"""
        return HTMLFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "show_season", f"{season_id}.html")

    @lru_cache(maxsize=1024)  # Value will never change
    def show_json_path(self) -> JSONFile:
        """Path for the JSON file for the show"""
        return JSONFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "show", f"{self.show_id}.json")

    @lru_cache(maxsize=1024)  # Value will never change
    def show_seasons_json_path(self) -> JSONFile:
        """Path for the JSON file that lists all of the seasons for the show"""
        return JSONFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "show_seasons", f"{self.show_id}.json")

    @lru_cache(maxsize=1024)  # Value will never change
    def season_episodes_json_path(self, season_id: str) -> JSONFile:
        """Path for the JSON file that lists all of the episodes for a specific season"""
        return JSONFile(DOWNLOADED_FILES_DIR, self.WEBSITE, "season_episodes", f"{season_id}.json")

    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> list[ExtendedPath]:
        """Check if any of the downloaded files are missing or outdated

        Args:
            minimum_timestamp (Optional[datetime], optional): The minimum timestamp the files must have. Defaults to
            None.

        Returns:
            list[ExtendedPath]: List of outdated files, empty if all files are up to date"""
        output = self.any_show_file_outdated(minimum_timestamp)

        if self.show_seasons_json_path().exists():
            show_seasons_json_parsed = self.show_seasons_json_path().parsed()
            for season in show_seasons_json_parsed["data"]:
                output += self.any_season_file_is_outdated(season["id"], minimum_timestamp)

        return output

    def any_show_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> list[ExtendedPath]:
        """Check if any of the downloaded show files are missing or outdated

        Args:
            minimum_timestamp (Optional[datetime], optional): The minimum timestamp the files must have. Defaults to
            None.

        Returns:
            list[ExtendedPath]: List of outdated show files, empty if all files are up to date"""
        outdated_files: list[ExtendedPath] = []
        if self.show_html_path().outdated(minimum_timestamp):
            outdated_files.append(self.show_html_path())
        if self.show_json_path().outdated(minimum_timestamp):
            outdated_files.append(self.show_json_path())
        if self.show_seasons_json_path().outdated(minimum_timestamp):
            outdated_files.append(self.show_seasons_json_path())

        return outdated_files

    def any_season_file_is_outdated(
        self, season_id: str, minimum_timestamp: Optional[datetime] = None
    ) -> list[ExtendedPath]:
        """Check if any of the downloaded season files are missing or outdated

        Args:
            minimum_timestamp (Optional[datetime], optional): The minimum timestamp the files must have. Defaults to
            None.

        Returns:
            list[ExtendedPath]: List of outdated season files, empty if all files are up to date"""
        season_html_path = self.season_html_path(season_id)
        season_json_path = self.season_episodes_json_path(season_id)

        output: list[ExtendedPath] = []

        # If the files are up to date nothing needs to be done
        if season_html_path.outdated(minimum_timestamp):
            output.append(season_html_path)
        elif season_json_path.outdated(minimum_timestamp):
            output.append(season_json_path)

        return output

    def update(
        self, minimum_info_timestamp: Optional[datetime] = None, minimum_modified_timestamp: Optional[datetime] = None
    ) -> None:
        """Update the information for the show"""
        logging.getLogger(self.logger_identifier()).info("Updating %s", self.show_info)
        self.download_all(minimum_info_timestamp)
        self.import_all(minimum_info_timestamp, minimum_modified_timestamp)

    def save_playwright_files(self, response: Response) -> None:
        """Sorts the files that playwright recieves based on the URL of the file"""
        if f"series/{self.show_id}?" in response.url:
            # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP?locale=en-US
            raw_json = response.json()
            path = self.show_json_path()
            path.write(json.dumps(raw_json))

        elif f"series/{self.show_id}/seasons?" in response.url:
            # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP/seasons?locale=en-US
            raw_json = response.json()
            path = self.show_seasons_json_path()
            path.write(json.dumps(raw_json))

        elif "episodes?" in response.url:
            # Example URL: https://www.crunchyroll.com/content/v2/cms/seasons/GYQ4MQ496/episodes?locale=en-US
            season_id = re.strict_search("seasons/(.*)/episodes?", response.url).group(1)
            path = self.season_episodes_json_path(season_id)
            raw_json = response.json()
            path.write(json.dumps(raw_json))

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the files if they are outdated or do not exist"""
        if outdated_files := self.any_file_is_outdated(minimum_timestamp):
            file_list = "\n".join([str(file) for file in outdated_files])
            logging.getLogger(self.logger_identifier()).info("Found outdated files %s", file_list)

            with sync_playwright() as playwright:
                # Create a new page that will autoamtically save JSON files when they are requested
                page = self.playwright_browser(playwright).new_page()
                page.on("response", self.save_playwright_files)

                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)
                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the show files if they are outdated or do not exist"""
        if outdated_files := self.any_show_file_outdated(minimum_timestamp):
            # Join all outdated files into line seperateed string
            file_list = "\n".join([str(file) for file in outdated_files])
            logging.getLogger(self.logger_identifier()).info("Found outdated show files %s", file_list)
            logging.getLogger(self.logger_identifier()).info("Scraping %s", self.show_url())

            page.goto(self.show_url(), wait_until="networkidle")

            # Make sure the page is for the first season
            # TODO: Can this be done without clicking something?
            if page.query_selector("div[class='season-info']"):
                # Open season selector
                page.locator("div[class='season-info']").click()
                page.wait_for_load_state("networkidle")

                # Click first season
                page.locator("div.seasons-select div[role='button']").first.click()

            self.show_html_path().write(page.content())

            self.playwright_wait_for_files(
                page, minimum_timestamp, self.show_json_path(), self.show_seasons_json_path()
            )

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the season files if they are outdated or do not exist"""
        show_seasons_json_parsed = self.show_seasons_json_path().parsed()
        for season in show_seasons_json_parsed["data"]:
            # If all of the season files are up to date nothing needs to be done
            if self.any_season_file_is_outdated(season["id"], minimum_timestamp):
                logging.getLogger(self.logger_identifier()).info("Scraping Season: %s", season["title"])
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this one time, all later pages can reuse existing page
                if not self.show_url() in page.url:
                    page.goto(self.show_url(), wait_until="networkidle")

                # Season selector only exists for shows with multiple seasons
                if page.query_selector("div[class='season-info']"):
                    # Open season selector
                    page.locator("div[class='season-info']").click()
                    page.wait_for_load_state("networkidle")

                    # Click season
                    self.season_button(page, season).click()

                # Wait for files to exist
                episodes_json_path = self.season_episodes_json_path(season["id"])
                self.playwright_wait_for_files(page, minimum_timestamp, episodes_json_path)

                self.season_html_path(season["id"]).write(page.content())

    def season_button(self, page: Page, season: dict[str, str]) -> ElementHandle:
        """Finds the button that will go to the season page"""
        season_string = f"S{season['season_number']}: {season['title']}"
        for maybe_season in page.query_selector_all("div[class='seasons-select'] div[role='button']"):
            # Use in because it also listed the number of episodes in inner_text
            if season_string in maybe_season.inner_text():
                return maybe_season

        raise ValueError(f"Could not find season: {season_string}")

    @transaction.atomic
    def import_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import all of the information for the show, seasons, and episodes"""
        logging.getLogger(self.logger_identifier()).info("Importing information")

        # Mark everything as deleted and let importing mark it as not deleted because this is the easiest way to
        # determine when an entry is deleted
        Show.objects.filter(id=self.show_info.id, website=self.WEBSITE).update(deleted=True)
        Season.objects.filter(show=self.show_info).update(deleted=True)
        Episode.objects.filter(season__show=self.show_info).update(deleted=True)

        self.import_show(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_seasons(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_episodes(minimum_info_timestamp, minimum_modified_timestamp)

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the show information if it is outdated or does not exist"""
        if self.show_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.show_json_path().parsed_cached()["data"][0]

            self.show_info.name = parsed_show["title"]
            self.show_info.description = parsed_show["description"]
            self.show_info.url = self.show_url()
            # poster_wide is an image with a 16x9 ratio (poster_tall is 6x9)
            # [0] is the first poster_wide design (as far as I can tell there is always just one)
            # [0][0] the first image listed is the lowest resolution
            # [0][1] the last image listed is the highest resolution
            # TODO: poster_long may be a better option depending on how the website lays out the information
            # TODO: Higher resolutions may be preferable depending on website layout
            self.show_info.thumbnail_url = parsed_show["images"]["poster_wide"][0][0]["source"]
            self.show_info.image_url = parsed_show["images"]["poster_wide"][0][-1]["source"]
            self.show_info.favicon_url = self.FAVICON_URL
            self.show_info.deleted = False
            self.show_info.add_timestamps_and_save(self.show_html_path())

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the season information if it is outdated or does not exist"""
        show_seasons_json_parsed = self.show_seasons_json_path().parsed_cached()

        for sort_order, season in enumerate(show_seasons_json_parsed["data"]):
            season_json_path = self.season_episodes_json_path(season["id"])
            season_json_parsed = season_json_path.parsed_cached()
            parsed_episode = season_json_parsed["data"][0]

            season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]

            if season_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.sort_order = parsed_episode["season_number"]
                season_info.name = parsed_episode["season_title"]
                season_info.sort_order = sort_order
                season_info.deleted = False
                season_info.add_timestamps_and_save(season_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the episode information if it is outdated or does not exist"""
        show_seasons_json_parsed = self.show_seasons_json_path().parsed_cached()["data"]

        for season in show_seasons_json_parsed:
            season_json_parsed = self.season_episodes_json_path(season["id"]).parsed_cached()
            season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]

            for i, episode in enumerate(season_json_parsed["data"]):
                episode_info = Episode().get_or_new(episode_id=episode["id"], season=season_info)[0]

                if episode_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                    episode_info.sort_order = i
                    episode_info.name = episode["title"]
                    episode_info.number = episode["episode"]
                    episode_info.description = episode["description"]
                    episode_info.duration = episode["duration_ms"] / 1000
                    episode_info.url = f"{self.DOMAIN}/watch/{episode['id']}"

                    episode_info.release_date = datetime.strptime(episode["episode_air_date"], "%Y-%m-%dT%H:%M:%S%z")
                    # Every now and then a show just won't have thumbnails
                    # See: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri (May be updated later)
                    if episode_images := episode.get("images"):
                        # [0] is the first thumbnail design (as far as I can tell there is always just one)
                        # [0][0] the first image listed is the lowest resolution
                        # [0][1] the last image listed is the highest resolution
                        # TODO: Higher resolutions may be preferable depending on website layout
                        episode_info.thumbnail_url = episode_images["thumbnail"][0][0]["source"]
                        episode_info.image_url = episode_images["thumbnail"][0][-1]["source"]
                    # No seperate file for episodes so just use the season file
                    episode_info.deleted = False
                    episode_info.add_timestamps_and_save(season_info.info_timestamp)
