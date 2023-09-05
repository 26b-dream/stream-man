"""PLugin for Netflix show"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from json_file import JSONFile
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # pyright: ignore [reportMissingTypeStubs]

if TYPE_CHECKING:
    from typing import Optional

    from playwright.sync_api._generated import Page, Response


class AmericasTestKitchen(ScraperShowShared, AbstractScraperClass):
    WEBSITE = "America's Test Kitchen"
    DOMAIN = "https://www.americastestkitchen.com"

    # Example show URLs
    #   https://www.americastestkitchen.com/cookscountry/episodes
    #   https://www.americastestkitchen.com/episodes
    URL_REGEX = re.compile(rf"{re.escape(DOMAIN)}/(?P<show_id>.*?)(?:/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)

        # THe main America's Test Kitchen show doesn't match the format used by their other shows. If this isn't the
        # main America's Test Kitchen show /episodes needs to be appended to the URL
        self.show_url = f"{self.DOMAIN}/{self.show_id}"
        if self.show_id != "episodes":
            self.show_url += "/episodes"

        self.seasons_json_path = JSONFile(self.files_dir(), "seasons.json")

    def image_urls(self) -> list[str]:
        output: list[str] = []
        parsed_show = self.show_json_path.parsed_cached()
        # Just going to assume all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"]):
            season_page_0 = self.season_json_path(f"Season {season_number}_0")
            if season_page_0.exists():
                parsed_season_page_0 = season_page_0.parsed_cached()

                for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                    season_page = self.season_json_path(f"Season {season_number}_{page_number}")
                    if season_page.exists():
                        parsed_season_page = season_page.parsed_cached()
                        for episode in parsed_season_page["results"][0]["hits"]:
                            image_url = episode["search_photo"]
                            output.append(image_url)
        return output

    def any_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""
        output = self.show_json_outdated(minimum_timestamp)
        output = self.any_season_json_outdated(minimum_timestamp) or output
        output = self.any_episode_image_outdated() or output
        return output

    def show_json_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        return self.check_if_outdated(self.show_json_path, "Show JSON", minimum_timestamp)

    def any_season_json_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        output = False
        if self.show_json_path.exists():
            parsed_show = self.show_json_path.parsed_cached()
            # Just going to assume all seasons will always be available
            for i in range(1, parsed_show["latestSeason"]):
                if self.season_json_outdated(i, minimum_timestamp):
                    output = True
        return output

    def season_json_outdated(self, season_number: int, minimum_timestamp: Optional[datetime] = None) -> bool:
        output = False
        season_page_0 = self.season_json_path(f"Season {season_number}_0")

        # If the first page does not exist assume later pages are outdated
        if self.check_if_outdated(season_page_0, f"Season {season_number} Page 0"):
            return True

        parsed_season_page_0 = season_page_0.parsed_cached()

        for page in range(parsed_season_page_0["results"][0]["nbPages"]):
            season_path = self.season_json_path(f"Season {season_number}_{page}")
            season_string = f"Season {season_number} Page {page}"
            output = self.check_if_outdated(season_path, season_string, minimum_timestamp) or output

        return output

    def any_episode_image_outdated(self) -> bool:
        if not self.show_json_path.exists():
            return False
        output = False
        for image_url in self.image_urls():
            if self.check_if_outdated(self.image_path(image_url), "Episode Image"):
                output = True
        return output

    def save_playwright_files(self, response: Response) -> None:
        # https://www.americastestkitchen.com/api/v6/shows/cco
        # https://www.americastestkitchen.com/api/v6/shows/atk
        if re.search(r"api/v6/shows/[a-z]+$", response.url):
            self.playwright_save_json_response(response, self.show_json_path)

        # https://y1fnzxui30-dsn.algolia.net/1/indexes/*/queries?x-algolia-agent=Algolia%20for%20JavaScript%20(3.35.1)%3B%20Browser%3B%20JS%20Helper%20(3.10.0)%3B%20react%20(17.0.2)%3B%20react-instantsearch%20(6.30.2)&x-algolia-application-id=Y1FNZXUI30&x-algolia-api-key=8d504d0099ed27c1b73708d22871d805
        if "algolia.net" in response.url:
            parsed_json = response.json()
            season = list(parsed_json["results"][0]["facets"]["search_season_list"].keys())[0]
            page = parsed_json["results"][0]["page"]
            season_path = self.season_json_path(f"{season}_{page}")
            self.playwright_save_json_response(response, season_path)

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_file_outdated(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Initializing Playwright")
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)

                page.on("response", self.save_playwright_files)
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)
                page.on("response", self.save_playwright_images)
                self.download_episode_images(page)

                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.show_json_outdated(minimum_timestamp):
            logging.getLogger(f"{self.logger_identifier()}.Opening").info(self.show_url)
            page.goto(self.show_url, wait_until="networkidle")
            page.wait_for_timeout(1000)

            self.playwright_wait_for_files(page, self.show_json_path, minimum_timestamp)

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        parsed_show = self.show_json_path.parsed_cached()
        # Just going to assume all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"]):
            if self.season_json_outdated(season_number, minimum_timestamp):
                logging.getLogger(f"{self.logger_identifier()}.Scraping").info("Season %s", season_number)
                # Only go the the URL if it is not already on the page
                if page.url != self.show_url:
                    logging.getLogger(f"{self.logger_identifier()}.Opening").info(self.show_url)
                    page.goto(self.show_url, wait_until="networkidle")

                # Click the button to show all seasons. This probably only needs to be done once but I put it in a while
                # loop just in case.
                while show_seasons := page.query_selector("button >> text=+ Show More"):
                    self.logged_click(show_seasons, "Show all seasons button")
                    page.wait_for_load_state("networkidle")

                # Click the button for the correct season then scroll to the bottom to load the first set of episodes
                self.logged_click(page.get_by_text(f"Season {season_number}", exact=True), "Show all seasons button")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1000)  # networkidle is not always enough so wait 1 extra second

                # Click the button to show more episodes until all episodes are shown
                show_more_counter = 1
                while remaining_episodes := page.query_selector("button >> text=SHOW MORE"):
                    # Need to scroll before the click for it to take
                    remaining_episodes.scroll_into_view_if_needed()
                    # Scrolling causes things to load so wait for it to finish
                    page.wait_for_load_state("networkidle")
                    self.logged_click(remaining_episodes, f"Show more episodes {show_more_counter}")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1000)  # networkidle is not always enough so wait 1 extra second
                    show_more_counter += 1

                # Make sure all season json files are downloaded for the specified season
                while self.season_json_outdated(season_number, minimum_timestamp):
                    page.wait_for_timeout(1000)

    def download_episode_images(self, page: Page) -> None:
        """Download the show image if it is outdated or do not exist, this is a seperate function from downloading the
        show because it is easier to download all of the images after downloading all of the JSON files"""

        parsed_show = self.show_json_path.parsed_cached()
        # Just going to assume all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"]):
            season_page_0 = self.season_json_path(f"Season {season_number}_0")
            parsed_season_page_0 = season_page_0.parsed_cached()

            for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                parsed_season_page = self.season_json_path(f"Season {season_number}_{page_number}").parsed_cached()
                for episode in parsed_season_page["results"][0]["hits"]:
                    image_url = episode["search_photo"]
                    self.playwright_download_image(page, image_url, "Episode")

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.show_json_path.parsed()
            self.show.name = parsed_show["title"]
            self.show.media_type = "TV Series"
            self.show.url = self.show_url
            self.show.favicon_url = "https://res.cloudinary.com/hksqkdlah/image/upload/atk-favicon.ico"
            self.show.deleted = False
            self.show.add_timestamps_and_save(self.show_json_path)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_show = self.show_json_path.parsed_cached()
        # Just going to assume all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"]):
            season_page_0 = self.season_json_path(f"Season {season_number}_0")
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
        # Just going to assume all seasons will always be available
        for season_number in range(1, parsed_show["latestSeason"]):
            parsed_season_page_0 = self.season_json_path(f"Season {season_number}_0").parsed_cached()
            season = Season().get_or_new(season_id=f"Season {season_number}", show=self.show)[0]

            for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                parsed_season_page = self.season_json_path(f"Season {season_number}_{page_number}").parsed_cached()
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

                        episode.url = f"{self.DOMAIN}{parsed_episode['search_atk_episode_url']}"

                        # Convert  "2023-07-15T00:00:00.000-04:00" to timestamp
                        strp = "%Y-%m-%dT%H:%M:%S.%f%z"
                        date = datetime.strptime(parsed_episode["search_document_date"], strp).astimezone()
                        episode.release_date = date

                        # No air date so just duplicate release_date
                        episode.air_date = episode.release_date
                        self.set_image(episode, parsed_episode["search_photo"])
                        episode.deleted = False
                        episode.add_timestamps_and_save(season.info_timestamp)
