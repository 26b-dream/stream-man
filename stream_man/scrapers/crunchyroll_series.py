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

    from playwright.sync_api._generated import ElementHandle, Page, Response


class CrunchyrollSeries(CrunchyRollShared, AbstractScraperClass):
    # Example show URLs
    #   https://www.crunchyroll.com/series/G63VW2VWY
    #   https://www.crunchyroll.com/series/G63VW2VWY/non-non-biyori
    URL_REGEX = re.compile(r"^(?:https:\/\/w?w?w?.?crunchyroll\.com)?\/series\/*(?P<show_id>.*?)(?:\/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/series/{self.show_id}"
        self.show_seasons_json_path = JSONFile(self.files_dir(), "show_seasons.json")

    def outdated_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        return (
            self.outdated_show_json(minimum_timestamp)
            or self.outdated_seasons_files(minimum_timestamp)
            or self.outdated_show_image()
            or self.outdated_episode_images()
        )

    def outdated_show_json(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the show JSON files are missing or outdated"""
        # Why does black have to make this so ugly?
        return self.check_if_outdated(self.show_json_path, "Show JSON", minimum_timestamp) or self.check_if_outdated(
            self.show_seasons_json_path, "Show Seasons JSON", minimum_timestamp
        )

    def outdated_show_image(self) -> bool:
        """Check if a specific show image file is missing or outdated"""
        if self.show_json_path.exists():
            image_url = self.strict_image_url(self.show_json_path, "poster_wide")
            image_path = self.image_path(image_url)
            return self.check_if_outdated(image_path, "Show image")

        return False

    def outdated_seasons_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the season files are missing or outdated"""
        # If files are missing but they are not the specific files that are being checked return False and assume
        # checking the parent files will cover the child files
        output = False
        if self.show_seasons_json_path.exists():
            # This seems like a silly way of checking multiple files, but it allows for every file to be checked even if a
            # file is found to be missing, this is useful for logging purposes.
            seasons = self.show_seasons_json_path.parsed_cached()["data"]
            for season in seasons:
                output = self.outdated_season_files(season["id"], minimum_timestamp) or output

        return output

    def outdated_season_files(self, season_id: str, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the season files for a specific season are missing or outdated, having this as a seperate
        function makes it easier to check what seasons need to be updated"""
        file_path = self.season_json_path(season_id)
        return self.check_if_outdated(file_path, "Season JSON", minimum_timestamp)

    def outdated_episode_images(self) -> bool:
        """Check if any of the downloaded episode image files are missing or outdated"""
        output = False

        # If files are missing and they are not the specific files that are being checked return False and assume
        # checking the parent files will cover the child files
        if self.show_seasons_json_path.exists():
            for season in self.show_seasons_json_path.parsed_cached()["data"]:
                season_json_path = self.season_json_path(season["id"])

                if season_json_path.exists():
                    season_json_parsed = self.season_json_path(season["id"]).parsed_cached()
                    for i, _episode in enumerate(season_json_parsed["data"]):
                        if image_url := self.image_url(season_json_path, "thumbnail", i):
                            image_path = self.image_path(image_url)
                            output = self.check_if_outdated(image_path, "Episode image") or output

        return output

    def save_playwright_files(self, response: Response) -> None:
        """Save specific files that are requested by playwright"""
        # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP?locale=en-US
        if f"series/{self.show_id}?" in response.url:
            self.playwright_save_json_response(response, self.show_json_path)

        # Example URL: https://www.crunchyroll.com/content/v2/cms/series/GEXH3W4JP/seasons?locale=en-US
        elif f"series/{self.show_id}/seasons?" in response.url:
            self.playwright_save_json_response(response, self.show_seasons_json_path)

        # Example URL: https://www.crunchyroll.com/content/v2/cms/seasons/GYQ4MQ496/episodes?locale=en-US
        elif "episodes?" in response.url:
            season_id = re.strict_search(r"seasons/(.*)/episodes?", response.url).group(1)
            self.playwright_save_json_response(response, self.season_json_path(season_id))

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the files that are outdated or do not exist"""
        if self.outdated_files(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Initializing Playwright")
            with sync_playwright() as playwright:
                # Create a new page that will autoamtically save JSON files when they are requested
                browser = self.playwright_browser(playwright)
                page = browser.new_page()
                stealth_sync(page)

                page.on("response", self.save_playwright_files)
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)

                page.on("response", self.save_playwright_images)
                self.download_show_image(page)
                self.download_episode_images(page)

                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the show files that are outdated or do not exist"""
        if self.outdated_show_json(minimum_timestamp):
            logging.getLogger(f"{self.logger_identifier()}.Scraping").info(self.show_url)

            page.goto(self.show_url, wait_until="networkidle")

            files = [self.show_json_path, self.show_seasons_json_path]
            self.playwright_wait_for_files(page, files, minimum_timestamp)

    def download_show_image(self, page: Page) -> None:
        """Download the show image if it is outdated or do not exist, this is a seperate function from downloading the
        show because it is easier to download all of the images after downloading all of the JSON files"""
        image_url = self.strict_image_url(self.show_json_path, "poster_wide")
        self.playwright_download_image(page, image_url, "show")

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the season files that are outdated or do not exist"""
        show_seasons_json_parsed = self.show_seasons_json_path.parsed_cached()
        logger = logging.getLogger(f"{self.logger_identifier()}.Scraping")
        for season in show_seasons_json_parsed["data"]:
            if self.outdated_season_files(season["id"], minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this one time, all later pages can reuse existing page
                if self.show_url not in page.url:
                    logger.info(self.show_url)
                    page.goto(self.show_url, wait_until="networkidle")

                # Season selector only exists for shows with multiple seasons
                if page.query_selector("div[class='season-info']"):
                    logger.info(season["title"])
                    # Sleep for 5 seconds to avoid being banned, do the timeout first so the initial visit doesn't
                    # immediately hit the next season button which would look suspicious
                    page.wait_for_timeout(5000)

                    # Open season selector
                    page.locator("div[class='season-info']").click()

                    # Click season
                    self.season_button(page, season).click()

                self.playwright_wait_for_files(page, self.season_json_path(season["id"]), minimum_timestamp)

    def download_episode_images(self, page: Page) -> None:
        """Download all of the episode files that are outdated or do not exist"""
        show_seasons_json_parsed = self.show_seasons_json_path.parsed_cached()["data"]

        for season in show_seasons_json_parsed:
            season_json_parsed = self.season_json_path(season["id"]).parsed_cached()

            for i, _episode in enumerate(season_json_parsed["data"]):
                if image_url := self.image_url(self.season_json_path(season["id"]), "thumbnail", i):
                    self.playwright_download_image(page, image_url, "episode")

    def season_button(self, page: Page, season: dict[str, str]) -> ElementHandle:
        """Find the button that changes the season shown on the show page"""
        season_string = f"S{season['season_number']}: {season['title']}"
        for maybe_season in page.query_selector_all("div[class='seasons-select'] div[role='button']"):
            # Use in because it also listed the number of episodes in inner_text
            if season_string in maybe_season.inner_text():
                return maybe_season

        raise RuntimeError(f"Could not find season button for {season_string}")

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # I don't see anything on Cruncyhroll that shows the difference between a TV Series, ONA, or OVA, so just list
        # this as a series which is a generic catch all term
        self.import_show_real(self.show_json_path, "Series", minimum_info_timestamp, minimum_modified_timestamp)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the season information into the database"""
        show_seasons_json_parsed = self.show_seasons_json_path.parsed_cached()

        for sort_order, parsed_season in enumerate(show_seasons_json_parsed["data"]):
            season_json_path = self.season_json_path(parsed_season["id"])
            season_json_parsed = season_json_path.parsed_cached()
            parsed_episode = season_json_parsed["data"][0]

            season = Season().get_or_new(season_id=parsed_season["id"], show=self.show)[0]

            if season.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                season.number = parsed_episode["season_number"]
                season.name = parsed_episode["season_title"]
                season.sort_order = sort_order
                season.deleted = False
                season.add_timestamps_and_save(season_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the episode information into the database"""
        show_seasons_json_parsed = self.show_seasons_json_path.parsed_cached()["data"]

        for season in show_seasons_json_parsed:
            season_json_parsed = self.season_json_path(season["id"]).parsed_cached()
            season_info = Season().get_or_new(season_id=season["id"], show=self.show)[0]

            for i, episode in enumerate(season_json_parsed["data"]):
                episode_info = Episode().get_or_new(episode_id=episode["id"], season=season_info)[0]

                if episode_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                    episode_info.sort_order = i
                    episode_info.name = episode["title"]
                    episode_info.number = episode["episode"]
                    episode_info.description = episode["description"]
                    episode_info.duration = episode["duration_ms"] / 1000
                    episode_info.url = f"{self.DOMAIN}/watch/{episode['id']}"

                    strp = "%Y-%m-%dT%H:%M:%S%z"
                    episode_info.air_date = datetime.strptime(episode["episode_air_date"], strp).astimezone()
                    episode_info.release_date = datetime.strptime(episode["premium_available_date"], strp).astimezone()
                    # Every now and then a show just won't have thumbnails and the thumbnail will be added a few weeks
                    # later, see: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri
                    if image_url := self.image_url(self.season_json_path(season["id"]), "thumbnail", i):
                        self.set_image(episode_info, image_url)

                    episode_info.deleted = False
                    # No seperate file for episodes so just use the season file because it has episode information
                    episode_info.add_timestamps_and_save(season_info.info_timestamp)
