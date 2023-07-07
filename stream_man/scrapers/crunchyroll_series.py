"""PLugin for crunchyroll show"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from common.constants import DOWNLOADED_FILES_DIR
from django.db import transaction
from extended_path import ExtendedPath
from json_file import JSONFile
from media.models import Episode, Season, Show
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

if TYPE_CHECKING:
    from typing import Optional

    from playwright.sync_api._generated import ElementHandle, Page, Response


class CrunchyrollSeries(ScraperShowShared, AbstractScraperClass):
    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
    FAVICON_URL = DOMAIN + "/favicons/favicon-32x32.png"

    # Example show URLs
    #   https://www.crunchyroll.com/series/G63VW2VWY
    #   https://www.crunchyroll.com/series/G63VW2VWY/non-non-biyori
    SHOW_URL_REGEX = re.compile(r"^(?:https:\/\/w?w?w?.?crunchyroll\.com)?\/series\/*(?P<show_id>.*?)(?:\/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/series/{self.show_id}"
        self.show_seasons_json_path = JSONFile(
            DOWNLOADED_FILES_DIR, self.WEBSITE, "show_seasons", f"{self.show_id}.json"
        )

    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> list[ExtendedPath]:
        """Check if any of the downloaded files are missing or outdated"""
        output = self.any_show_file_outdated(minimum_timestamp)

        if self.show_seasons_json_path.exists():
            show_seasons_json_parsed = self.show_seasons_json_path.parsed()
            for season in show_seasons_json_parsed["data"]:
                output += self.any_season_file_is_outdated(season["id"], minimum_timestamp)

        return output

    def any_show_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> list[ExtendedPath]:
        """Check if any of the downloaded show files are missing or outdated"""

        outdated_files: list[ExtendedPath] = []
        if self.show_json_path.outdated(minimum_timestamp):
            outdated_files.append(self.show_json_path)
        if self.show_seasons_json_path.outdated(minimum_timestamp):
            outdated_files.append(self.show_seasons_json_path)

        return outdated_files

    def any_season_file_is_outdated(
        self, season_id: str, minimum_timestamp: Optional[datetime] = None
    ) -> list[ExtendedPath]:
        """Check if any of the downloaded season files are missing or outdated"""

        season_json_path = self.season_json_path(season_id)
        return [season_json_path] if season_json_path.outdated(minimum_timestamp) else []

    def save_playwright_files(self, response: Response) -> None:
        """Function that is called on all of the reesponses that the playwright browser gets"""
        if f"series/{self.show_id}?" in response.url:
            # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP?locale=en-US
            raw_json = response.json()
            path = self.show_json_path
            path.write(json.dumps(raw_json))

        elif f"series/{self.show_id}/seasons?" in response.url:
            # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP/seasons?locale=en-US
            raw_json = response.json()
            path = self.show_seasons_json_path
            path.write(json.dumps(raw_json))

        elif "episodes?" in response.url:
            # Example URL: https://www.crunchyroll.com/content/v2/cms/seasons/GYQ4MQ496/episodes?locale=en-US
            season_id = re.strict_search(r"seasons/(.*)/episodes?", response.url).group(1)
            path = self.season_json_path(season_id)
            raw_json = response.json()
            path.write(json.dumps(raw_json))

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if outdated_files := self.any_file_is_outdated(minimum_timestamp):
            file_list = "\n".join([str(file) for file in outdated_files])
            logging.getLogger(self.logger_identifier()).info("Found outdated files %s", file_list)

            with sync_playwright() as playwright:
                # Create a new page that will autoamtically save JSON files when they are requested
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)
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
            logging.getLogger(self.logger_identifier()).info("Scraping %s", self.show_url)

            page.goto(self.show_url, wait_until="networkidle")

            self.playwright_wait_for_files(page, minimum_timestamp, self.show_json_path, self.show_seasons_json_path)

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the season files if they are outdated or do not exist"""
        show_seasons_json_parsed = self.show_seasons_json_path.parsed()
        for season in show_seasons_json_parsed["data"]:
            # If all of the season files are up to date nothing needs to be done
            if self.any_season_file_is_outdated(season["id"], minimum_timestamp):
                logging.getLogger(self.logger_identifier()).info("Scraping Season: %s", season["title"])
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this one time, all later pages can reuse existing page
                if self.show_url not in page.url:
                    page.goto(self.show_url, wait_until="networkidle")

                # Season selector only exists for shows with multiple seasons
                if page.query_selector("div[class='season-info']"):
                    # Open season selector
                    page.locator("div[class='season-info']").click()

                    # Sleep for 5 seconds to avoid being banned
                    page.wait_for_timeout(5000)

                    # Click season
                    self.season_button(page, season).click()

                # Wait for files to exist
                episodes_json_path = self.season_json_path(season["id"])
                self.playwright_wait_for_files(page, minimum_timestamp, episodes_json_path)

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
        logging.getLogger(self.logger_identifier()).info("Importing information")

        # Mark everything as deleted and let importing mark it as not deleted because this is the easiest way to
        # determine when an entry is deleted
        Show.objects.filter(id=self.show_info.id, website=self.WEBSITE).update(deleted=True)
        Season.objects.filter(show=self.show_info).update(deleted=True)
        Episode.objects.filter(season__show=self.show_info).update(deleted=True)

        self.import_show(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_seasons(minimum_info_timestamp, minimum_modified_timestamp)
        self.import_episodes(minimum_info_timestamp, minimum_modified_timestamp)
        self.update_update_at()

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.show_json_path.parsed_cached()["data"][0]

            self.show_info.name = parsed_show["title"]
            self.show_info.description = parsed_show["description"]
            self.show_info.url = self.show_url
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
            # I don't see anything on Cruncyhroll that shows the difference between a TV Series, ONA, or OVA, so just list
            # this as a series which is a generic catch all term
            self.show_info.media_type = "Series"
            self.show_info.add_timestamps_and_save(self.show_json_path)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_seasons_json_parsed = self.show_seasons_json_path.parsed_cached()

        for sort_order, season in enumerate(show_seasons_json_parsed["data"]):
            season_json_path = self.season_json_path(season["id"])
            season_json_parsed = season_json_path.parsed_cached()
            parsed_episode = season_json_parsed["data"][0]

            season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]

            if season_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.number = parsed_episode["season_number"]
                season_info.name = parsed_episode["season_title"]
                season_info.sort_order = sort_order
                season_info.deleted = False
                season_info.add_timestamps_and_save(season_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_seasons_json_parsed = self.show_seasons_json_path.parsed_cached()["data"]

        for season in show_seasons_json_parsed:
            season_json_parsed = self.season_json_path(season["id"]).parsed_cached()
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

                    episode_info.air_date = datetime.strptime(episode["episode_air_date"], "%Y-%m-%dT%H:%M:%S%z")
                    episode_info.release_date = datetime.strptime(
                        episode["premium_available_date"], "%Y-%m-%dT%H:%M:%S%z"
                    )
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
