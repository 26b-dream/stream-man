"""PLugin for Netflix show"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from extended_path import ExtendedPath
from json_file import JSONFile
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # pyright: ignore [reportMissingTypeStubs]

if TYPE_CHECKING:
    from typing import Any, Optional

    from playwright.sync_api._generated import Page, Response


class AmericasTestKitchen(ScraperShowShared, AbstractScraperClass):
    WEBSITE = "America's Test Kitchen"
    DOMAIN = "https://www.americastestkitchen.com"
    FAVICON_URL = "https://res.cloudinary.com/hksqkdlah/image/upload/atk-favicon.ico"

    # Example show URLs
    #   https://www.americastestkitchen.com/cookscountry/episodes
    #   https://www.americastestkitchen.com/episodes
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}/(?P<show_id>.*?)(?:/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)

        # The main America's Test Kitchen show doesn't match the format used by their other shows. If this isn't the
        # main America's Test Kitchen show /episodes needs to be appended to the URL
        self.show_url = f"{self.DOMAIN}/{self.show_id}"
        if self.show_id != "episodes":
            self.show_url += "/episodes"

        self.seasons_json_path = JSONFile(self.files_dir(), "seasons.json")

    def episode_image_urls(self) -> list[str]:
        output: list[str] = []
        parsed_show = self.show_json_path.parsed_cached()
        # This is made assuming all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"] + 1):
            season_page_0 = self.season_json_path(season_number, 0)
            # Need to make sure pages exist before trying to parse them
            if season_page_0.exists():
                parsed_season_page_0 = season_page_0.parsed_cached()
                for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                    season_page = self.season_json_path(season_number, page_number)
                    # Need to make sure pages exist before trying to parse them
                    if season_page.exists():
                        parsed_season_page = season_page.parsed_cached()
                        for episode in parsed_season_page["results"][0]["hits"]:
                            image_url = episode["search_photo"].replace(",w_268,h_268", "")
                            output.append(image_url)
        return output

    def image_path_from_url(self, image_url: str) -> ExtendedPath:
        # Special modification because
        image_name = image_url.split("/")[-1]
        return (self.files_dir() / "Images" / image_name).with_suffix(".webp")

    def episode_image_path(self, data: dict[str, Any]) -> ExtendedPath:
        file_name = ExtendedPath(data["search_photo"]).stem
        return (self.files_dir() / "images" / file_name).with_suffix(".webp")

    def any_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""
        output = self.show_json_outdated(minimum_timestamp)
        output = self.any_season_json_outdated(minimum_timestamp) or output
        output = self.any_episode_file_missing() or output
        return output

    def show_json_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if the show JSON file is missing or outdated"""
        return self.is_file_outdated(self.show_json_path, "Show JSON", minimum_timestamp)

    def any_season_json_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the season JSON files are missing or outdated"""
        output = False
        if self.show_json_path.exists():
            parsed_show = self.show_json_path.parsed_cached()
            # This is made assuming all seasons will always be available
            for i in range(1, parsed_show["latestSeason"] + 1):
                if self.season_json_outdated(i, minimum_timestamp):
                    output = True
        return output

    def season_json_outdated(self, season_number: int, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if a single season JSON file is missing or outdated"""
        output = False
        season_page_0 = self.season_json_path(season_number, 0)

        # If the first page is outdated assume later pages are outdated
        if self.is_file_outdated(season_page_0, f"Season {season_number} Page 0"):
            return True

        parsed_season_page_0 = season_page_0.parsed_cached()

        for page in range(parsed_season_page_0["results"][0]["nbPages"]):
            season_path = self.season_json_path(season_number, page)
            season_string = f"Season {season_number} Page {page}"
            output = self.is_file_outdated(season_path, season_string, minimum_timestamp) or output

        return output

    def any_episode_file_missing(self) -> bool:
        """Check if any of the episode image files are missing"""
        if not self.show_json_path.exists():
            return False
        output = False
        for url in self.episode_image_urls():
            path = self.image_path_from_url(url)
            if self.is_file_outdated(path, "Episode Image"):
                output = True
        return output

    def playwright_response_save_json(self, response: Response) -> None:
        """Save specific files from the response recieved by playwright"""
        # Example URLs:
        #   https://www.americastestkitchen.com/api/v6/shows/cco
        #   https://www.americastestkitchen.com/api/v6/shows/atk
        if re.search(r"api/v6/shows/[a-z]+$", response.url):
            self.playwright_save_json_response(response, self.show_json_path)

        # Example URL:
        #   https://y1fnzxui30-dsn.algolia.net/1/indexes/*/queries?x-algolia-agent=Algolia%20for%20JavaScript%20(3.35.1)
        #   %3B%20Browser%3B%20JS%20Helper%20(3.10.0)%3B%20react%20(17.0.2)%3B%20react-instantsearch%20(6.30.2)&x-algoli
        #   a-application-id=Y1FNZXUI30&x-algolia-api-key=8d504d0099ed27c1b73708d22871d805
        if "algolia.net" in response.url:
            parsed_json = response.json()
            season_number = int(list(parsed_json["results"][0]["facets"]["search_season_list"].keys())[0].split(" ")[1])
            page_number = parsed_json["results"][0]["page"]
            season_path = self.season_json_path(season_number, page_number)
            self.playwright_save_json_response(response, season_path)

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_file_outdated(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Initializing Playwright")
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)

                page.on("response", self.playwright_response_save_json)
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)

                page.on("response", self.playwright_response_save_images)
                self.download_episode_images(page)

                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download show JSON file if it is missing or outdated"""
        if self.show_json_outdated(minimum_timestamp):
            self.logged_goto(page, self.show_url, wait_until="networkidle")

            self.playwright_wait_for_files(page, self.show_json_path, minimum_timestamp)

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all season JSON files if they are missing or outdated"""
        parsed_show = self.show_json_path.parsed_cached()
        # This is made assuming all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"] + 1):
            # ! Kinda sketch speed up, once a season is downloaded never touch it again. May cause issues in the future.
            if self.season_json_path(season_number + 1):
                continue

            if self.season_json_outdated(season_number, minimum_timestamp):
                logging.getLogger(f"{self.logger_identifier()}.Scraping").info("Season %s", season_number)
                # Only open the website if it isn't already open
                if page.url != self.show_url:
                    logging.getLogger(f"{self.logger_identifier()}.Opening").info(self.show_url)
                    page.goto(self.show_url, wait_until="networkidle")

                # Click the button to show all seasons. This probably only needs to be done once but I put it in a while
                # loop just in case.
                while show_seasons := page.query_selector("button >> text=+ Show More"):
                    self.logged_click(show_seasons, "Show all seasons button")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1000)  # networkidle is not always enough so wait 1 extra second

                # Click the button for the correct season then scroll to the bottom to load the first set of episodes
                season_button = page.get_by_role("link", name=f"Season {season_number}", exact=True)
                self.logged_click(season_button, "Show all seasons button")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(5000)  # Extra wait to avoid bans

                # Click the button to show more episodes until all episodes are shown
                show_more_counter = 1  # Improves logging to easily see if button is clicked too many times
                while remaining_episodes := page.query_selector("button >> text=SHOW MORE"):
                    # Need to scroll before the click for it to take
                    remaining_episodes.scroll_into_view_if_needed()
                    # Scrolling causes things to load so wait for it to finish
                    page.wait_for_load_state("networkidle")
                    self.logged_click(remaining_episodes, f"Show more episodes {show_more_counter}")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(5000)  # Extra wait to avoid bans
                    show_more_counter += 1

                # Make sure all season JSON files are downloaded for the specified season
                while self.season_json_outdated(season_number, minimum_timestamp):
                    page.wait_for_timeout(1000)

    def download_episode_images(self, page: Page) -> None:
        """Download all episode images if they do not exist"""
        for url in self.episode_image_urls():
            self.playwright_download_image_if_needed(page, url, "Episode Image")

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.show_json_path.parsed_cached()
            self.show.name = parsed_show["title"]
            self.show.media_type = "TV Series"
            self.show.url = self.show_url
            self.show.favicon_url = self.FAVICON_URL
            self.show.deleted = False
            self.show.add_timestamps_and_save(self.show_json_path)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_show = self.show_json_path.parsed_cached()
        # This is made assuming all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"] + 1):
            season_page_0 = self.season_json_path(season_number, 0)
            season = Season().get_or_new(season_id=f"Season {season_number}", show=self.show)[0]
            if season.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                season.sort_order = season_number
                season.number = season_number
                season.name = f"Season {season_number}"
                season.deleted = False
                season.add_timestamps_and_save(season_page_0)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_show = self.show_json_path.parsed_cached()
        # This is made assuming all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"] + 1):
            parsed_season_page_0 = self.season_json_path(season_number, 0).parsed_cached()
            season = Season().get_or_new(season_id=f"Season {season_number}", show=self.show)[0]

            for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                parsed_season_page = self.season_json_path(season_number, page_number).parsed_cached()
                for parsed_episode in parsed_season_page["results"][0]["hits"]:
                    episode = Episode().get_or_new(episode_id=parsed_episode["objectID"], season=season)[0]

                    if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                        episode.sort_order = parsed_episode["search_atk_episode_number"]
                        episode.description = parsed_episode["search_description"]
                        episode.number = parsed_episode["search_atk_episode_number"]
                        episode.name = parsed_episode["title"]

                        minutes = int(parsed_episode["search_stickers"][0].split(":")[0]) * 60
                        seconds = int(parsed_episode["search_stickers"][0].split(":")[1])
                        episode.duration = minutes * 60 + seconds

                        episode.url = f"{self.DOMAIN}{parsed_episode['search_url']}"
                        raw_date = parsed_episode["search_document_date"]
                        episode.release_date = datetime.strptime(raw_date, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone()

                        # No air date so just duplicate release_date
                        episode.air_date = episode.release_date
                        image_path = self.episode_image_path(parsed_episode)

                        self.set_image(episode, image_path)
                        episode.deleted = False
                        episode.add_timestamps_and_save(season.info_timestamp)
