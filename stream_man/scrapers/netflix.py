"""PLugin for Netflix show"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from common.credential_mangement import Credentials
from html_file import HTMLFile
from json_file import JSONFile
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # pyright: ignore [reportMissingTypeStubs]

if TYPE_CHECKING:
    from typing import Any, Optional

    from playwright.sync_api._generated import Page, Response


class NetflixShow(ScraperShowShared, AbstractScraperClass):
    WEBSITE = "Netflix"
    DOMAIN = "https://www.netflix.com"

    # Example show URLs
    #   https://www.netflix.com/browse?jbv=81511776
    #   https://www.netflix.com/tilte/81511776
    URL_REGEX = re.compile(r"https?://www\.netflix\.com/(?:browse\?jbv=|title/)(?P<show_id>\d+)")

    @classmethod
    def credential_keys(cls) -> list[str]:
        return ["email", "password", "pin", "name"]

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/title/{self.show_id}"
        self.show_html_path = HTMLFile(self.files_dir(), "show.html")
        self.seasons_json_path = JSONFile(self.files_dir(), "seasons.json")

        credentials = Credentials.load_credentials()
        self.emaiil = credentials["Netflix"]["email"]
        self.password = credentials["Netflix"]["password"]
        self.pin = credentials["Netflix"]["pin"]
        self.name = credentials["Netflix"]["name"]

    def outdated_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""
        output = self.outdated_show_files(minimum_timestamp)
        output = self.outdated_season_files(minimum_timestamp) or output
        output = self.outdated_show_image() or output
        output = self.outdated_episode_images() or output
        return output

    def outdated_show_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the show files are missing or outdated"""
        output = self.outdated_show_json(minimum_timestamp)
        output = self.outdated_show_html(minimum_timestamp)
        output = self.outdated_seasons_json(minimum_timestamp)
        return output

    def outdated_show_json(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if the show json file is missing or outdated"""
        return self.check_if_outdated(self.show_json_path, "Show JSON", minimum_timestamp)

    def outdated_show_html(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if the show json file is missing or outdated"""
        return self.check_if_outdated(self.show_html_path, "Show HTML", minimum_timestamp)

    def outdated_seasons_json(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if the show json file is missing or outdated"""
        return self.check_if_outdated(self.seasons_json_path, "Show JSON", minimum_timestamp)

    def outdated_season_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the season files are missing or outdated"""
        if self.check_if_outdated(self.seasons_json_path, "Seasons JSON", minimum_timestamp):
            return True

        output = False
        if self.show_json_path.exists():
            for season_id in self.seasons_json_path.parsed()["jsonGraph"]["seasons"]:
                season_file = self.season_json_path(season_id)
                if self.check_if_outdated(season_file, f"Seasons {season_id} JSON", minimum_timestamp):
                    output = True

        return output

    def outdated_show_image(self) -> bool:
        """Check if any of the show image are missing or outdated"""
        if self.show_html_path.exists():
            image_path = self.image_path(self.show_img_url())
            return self.check_if_outdated(image_path, "Show image")

        return False

    def outdated_episode_images(self) -> bool:
        """Check if any of the show image are missing or outdated"""
        output = False
        if self.seasons_json_path.exists():
            for image_url in self.episode_image_urls():
                image_path = self.image_path(image_url)
                output = self.check_if_outdated(image_path, "Show image") or output

        return output

    def go_to_page_logged_in(
        self,
        page: Page,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> None:
        page.goto(url, wait_until=wait_until)
        self.login_if_needed(page, url)
        self.select_user_if_needed(page)

    def login_if_needed(self, page: Page, url: str) -> None:
        # Check for the button to login to determine if user is logged in
        if page.query_selector("a[class='authLinks']"):
            page.goto(f"{self.DOMAIN}/login", wait_until="networkidle")
            page.type("input[id='id_userLoginId']", self.emaiil)
            page.type("input[id='id_password']", self.password)
            page.keyboard.press("Enter")
            # Login was acting up so just in case...
            page.wait_for_timeout(1000)
            page.wait_for_load_state("networkidle")

            # After logging in attempt to go the the original page because it will not redirect automatically
            page.goto(url, wait_until="networkidle")

    def select_user_if_needed(self, page: Page) -> bool:
        # Check if it this is the user selection page
        if page.query_selector(f"span[class='profile-name'] >> text={self.name}"):
            page.click(f"span[class='profile-name'] >> text={self.name}")
            page.wait_for_load_state("networkidle")
            # Entry is more reliable one character at a time for some reason so loop through each character in the PIN
            for number in str(self.pin):
                # Netflix is screwing with me try slowing down pin entry
                page.wait_for_timeout(1000)
                page.type("div[class='pin-input-container']", number)

            # Because Netflix is weird the sleep is required to retain the user selection
            page.wait_for_timeout(5000)
            return True
        return False

    def save_playwright_files(self, response: Response) -> None:
        # All information from Netflix is under this url
        if "pathEvaluator?" in response.url:
            parsed_json = response.json()
            dumped_json = json.dumps(parsed_json)
            self.show_json_path.write(dumped_json)

            # Check for information for a show
            if parsed_json["jsonGraph"].get("videos", {}).get(self.show_id):
                # If there is a summary for every season this has to be the show json
                if all("summary" in value.keys() for value in parsed_json["jsonGraph"].get("seasons", {}).values()):
                    self.show_json_path.write(dumped_json)

            # Everything has a seasons response basically, but only the actual season file has the prePlayExperiences
            if parsed_json["jsonGraph"].get("seasons") and parsed_json["jsonGraph"].get("prePlayExperiences"):
                self.seasons_json_path.write(dumped_json)
                # Return here because I don't want to accidently overwrite a real season file with the season file

            # I have no idea what this is but it messes up season downloading
            if list(parsed_json["jsonGraph"].keys()) == ["seasons"]:
                return

            if season_id := self.season_id_from_json(parsed_json):
                self.season_json_path(season_id).write(dumped_json)

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the files that are outdated or do not exist"""
        if self.outdated_files(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Initializing Playwright")
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)

                # Download main information
                page.on("response", self.save_playwright_files)
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)

                # Download images after main information is downloaded because it makes things a little easier
                page.on("response", self.save_playwright_images)
                self.download_show_image(page)
                self.download_episode_images(page)

                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.outdated_show_files(minimum_timestamp):
            logging.getLogger(f"{self.logger_identifier()}.Scraping").info(self.show_url)
            self.go_to_page_logged_in(page, self.show_url)
            page.wait_for_load_state("networkidle")

            self.show_html_path.write(page.content())

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.outdated_season_files(minimum_timestamp):
            logging.getLogger(f"{self.logger_identifier()}.Scraping").info("All Seasons")
            # Only go the the URL if it is not already on the page
            if page.url != self.show_url:
                self.go_to_page_logged_in(page, self.show_url)
                page.wait_for_load_state("networkidle")

            # If there is a list of seasons open up the season selector
            season_selector = page.query_selector("button[data-uia='dropdown-toggle']")
            if season_selector:
                season_selector.click()

                # Click the button to show all of the seasons at once on the page
                li_elements = page.query_selector_all('li[data-uia="dropdown-menu-item"]')
                if li_elements:
                    li_elements[-1].click()

                for season_id in self.seasons_json_path.parsed()["jsonGraph"]["seasons"]:
                    while self.season_json_path(season_id).outdated(minimum_timestamp):
                        page.wait_for_timeout(1000)

    def show_img_url(self):
        selector = self.show_html_path.parsed().strict_select_one("div[class^='storyArt'] img:first-of-type")
        full_url = selector.attrs["src"]
        return full_url.split("?")[0]

    def season_id_from_json(self, body: dict[str, Any]) -> Optional[str]:
        for season_id, season in body["jsonGraph"].get("seasons", {}).items():
            if season.get("episodes"):
                return season_id

    # TODO: Move this into the parent function and require a show_img_url function
    def download_show_image(self, page: Page) -> None:
        """Download the show image if it is outdated or do not exist, this is a seperate function from downloading the
        show because it is easier to download all of the images after downloading all of the JSON files"""
        self.playwright_download_image(page, self.show_img_url(), "show")

    def download_episode_images(self, page: Page) -> None:
        for image_url in self.episode_image_urls():
            self.playwright_download_image(page, image_url, "show")

    def episode_image_urls(self) -> list[str]:
        """Returns a list of all of the episode image urls"""
        output: list[str] = []
        if self.seasons_json_path.exists():
            for season_id in self.seasons_json_path.parsed()["jsonGraph"]["seasons"]:
                parsed_season_path = self.season_json_path(season_id).parsed()
                for _episode_id, parsed_episode in parsed_season_path["jsonGraph"]["videos"].items():
                    if parsed_episode.get("interestingMoment"):
                        output.append(self.episode_image_url(parsed_episode))

        return output

    def episode_image_url(self, parsed_episode: dict[str, Any]) -> str:
        last_key = list(parsed_episode["interestingMoment"].keys())[-1]
        last_key_2 = list(parsed_episode["interestingMoment"][last_key].keys())[-1]
        full_image_url = parsed_episode["interestingMoment"][last_key][last_key_2]["value"]["url"]
        return full_image_url.split("?")[0]

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show_html = self.show_html_path.parsed()

            # A ton of information is not present on ANY JSON file and it needs to be scraped from the html file
            # There is just a single strong that has just the title it looks like
            self.show.name = parsed_show_html.strict_select_one("strong").text
            self.show.description = parsed_show_html.strict_select_one("p[class^='preview-modal-synopsis']").text
            self.set_image(self.show, self.show_img_url())
            self.show.favicon_url = parsed_show_html.strict_select_one("link[rel='shortcut icon']").attrs["href"]
            # TODO: Movie support
            self.show.media_type = "TV Show"
            self.show.url = self.show_url
            self.show.deleted = False
            self.show.add_timestamps_and_save(self.show_json_path)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the season information, does not attempt to download or update the information"""
        for i, (season_id, season_info) in enumerate(self.seasons_json_path.parsed()["jsonGraph"]["seasons"].items()):
            season = Season().get_or_new(season_id=season_id, show=self.show)[0]

            if not season.is_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season.sort_order = i
                season.name = season_info["summary"]["value"]["name"]
                if season.name.split(" ")[-1].isnumeric():
                    season.number = season.name.split(" ")[-1]
                else:
                    season.number = i
                season.deleted = False
                season.add_timestamps_and_save(self.show_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the episode information, does not attempt to download or update the information"""

        for season_id in self.seasons_json_path.parsed()["jsonGraph"]["seasons"]:
            season = Season().get_or_new(season_id=season_id, show=self.show)[0]
            parsed_season_path = self.season_json_path(season_id).parsed()
            for i, (episode_id, parsed_episode) in enumerate(parsed_season_path["jsonGraph"]["videos"].items()):
                # Some junk entries
                if not parsed_episode.get("title"):
                    continue
                episode = Episode().get_or_new(episode_id=episode_id, season=season)[0]

                if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                    episode.sort_order = i
                    episode.description = parsed_episode["title"]["value"]
                    episode.number = parsed_episode["summary"]["value"]["episode"]
                    episode.name = parsed_episode["title"]["value"]
                    episode.description = parsed_episode["contextualSynopsis"]["value"]["text"]
                    episode.duration = parsed_episode["runtime"]["value"]
                    episode.url = f"https://www.netflix.com/watch/{episode_id}"

                    unix_timestamp = parsed_episode["availability"]["value"]["availabilityStartTime"] / 1000
                    episode.release_date = datetime.fromtimestamp(unix_timestamp).astimezone()
                    # No air date so just duplicate release_date
                    episode.air_date = episode.release_date
                    episode.deleted = False
                    self.set_image(episode, self.episode_image_url(parsed_episode))
                    episode.add_timestamps_and_save(season.info_timestamp)
