"""PLugin for Netflix show"""
from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import common.extended_re as re
import keyring
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import BaseScraper
from common.scraper_functions import (
    playwright_save_json_response,  # pyright: ignore [reportMissingTypeStubs]
)
from html_file import HTMLFile
from json_file import JSONFile
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

if TYPE_CHECKING:
    from typing import Any, Optional

    from playwright.sync_api._generated import Page, Response


class NetflixShow(BaseScraper, AbstractScraperClass):
    WEBSITE = "Netflix"
    DOMAIN = "https://www.netflix.com"

    # Example show URLs
    #   https://www.netflix.com/browse?jbv=81511776
    #   https://www.netflix.com/title/81511776
    #   https://www.netflix.com/browse/genre/34399?jbv=1181461
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}/(?:browse.*?\?jbv=|title\/)(?P<show_id>\d+)")

    @classmethod
    def credential_keys(cls) -> list[str]:
        return ["email", "password", "pin", "name"]

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/title/{self._show_id}"
        self.show_html_path = HTMLFile(self._show_dir, "show.html")
        self.seasons_json_path = JSONFile(self._show_dir, "seasons.json")
        self.falcor_cache_cached_value = None

        credentials = Credentials.load_credentials()
        self.emaiil = credentials["Netflix"]["email"]
        self.password = credentials["Netflix"]["password"]
        self.pin = credentials["Netflix"]["pin"]
        self.name = credentials["Netflix"]["name"]

    def show_img_url(self):
        return self.falcor_cache()["videos"][self._show_id]["jawSummary"]["value"]["backgroundImage"]["url"]

    def episode_image_urls(self) -> list[str]:
        """Returns a list of all of the episode image urls"""
        output: list[str] = []
        if self.seasons_json_path.exists():
            for season_id in self.seasons_json_path.parsed_cached()["jsonGraph"]["seasons"]:
                parsed_season_path = self._season_json_file(season_id).parsed_cached()
                for _episode_id, parsed_episode in parsed_season_path["jsonGraph"]["videos"].items():
                    if parsed_episode.get("interestingMoment"):
                        output.append(self.episode_image_url(parsed_episode))

        return output

    def episode_image_url(self, parsed_episode: dict[str, Any]) -> str:
        last_key = list(parsed_episode["interestingMoment"].keys())[-1]
        last_key_2 = list(parsed_episode["interestingMoment"][last_key].keys())[-1]
        full_image_url = parsed_episode["interestingMoment"][last_key][last_key_2]["value"]["url"]
        return full_image_url.split("?")[0]

    def _any_file_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        output = self.show_files_outdated(minimum_timestamp)
        output = self.season_files_outdated(minimum_timestamp) or output
        output = self.show_image_missing() or output
        output = self.episode_images_missing() or output
        return output

    def show_files_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        """Check if any of the show files are missing or outdated"""
        output = self._show_json_file.is_outdated(minimum_timestamp)
        output = self.show_html_path.is_outdated(minimum_timestamp) or output
        return self.seasons_json_path.is_outdated(minimum_timestamp) or output

    def season_files_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        """Check if any of the season files are missing or outdated"""
        if self.show_html_path.exists() and self.is_movie():
            return False

        output = False

        if self.is_file_outdated(self.seasons_json_path, "Seasons JSON", minimum_timestamp):
            output = True

        if self._show_json_file.exists():
            for season_id in self.seasons_json_path.parsed_cached()["jsonGraph"]["seasons"]:
                season_file = self._season_json_file(season_id)
                if self.is_file_outdated(season_file, f"Seasons {season_id} JSON", minimum_timestamp):
                    output = True

        return output

    def show_image_missing(self) -> bool:
        """Check if the show image is missing"""
        if self.show_html_path.exists():
            image_path = self._image_file_from_url(self.show_img_url())
            return self.is_file_outdated(image_path, "Show image")

        return False

    def episode_images_missing(self) -> bool:
        """Check if any of the episode images are missing"""
        output = False
        if self.seasons_json_path.exists():
            for image_url in self.episode_image_urls():
                image_path = self._image_file_from_url(image_url)
                output = self.is_file_outdated(image_path, "Show image") or output

        return output

    def save_playwright_files(self, response: Response) -> None:
        """Save specific files from the response recieved by playwright"""
        # All information from Netflix is under this url
        if "pathEvaluator?" in response.url:
            parsed_json = response.json()
            dumped_json = json.dumps(parsed_json)
            self._show_json_file.write(dumped_json)

            # Check for information for a show
            if parsed_json["jsonGraph"].get("videos", {}).get(self._show_id):
                # If there is a summary for every season this has to be the show json
                if all("summary" in value.keys() for value in parsed_json["jsonGraph"].get("seasons", {}).values()):
                    playwright_save_json_response(response, self._show_json_file)

            # Everything has a seasons response basically, but only the actual season file has the prePlayExperiences
            if parsed_json["jsonGraph"].get("seasons") and parsed_json["jsonGraph"].get("prePlayExperiences"):
                playwright_save_json_response(response, self.seasons_json_path)

            # I have no idea what this is but it messes up season downloading
            if list(parsed_json["jsonGraph"].keys()) == ["seasons"]:
                return

            if season_id := self.season_id_from_json(parsed_json):
                playwright_save_json_response(response, self._season_json_file(season_id))

    def _download_all(self, minimum_timestamp: datetime | None = None) -> None:
        if self._any_file_outdated(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Initializing Playwright")
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)

                page.on("response", self.save_playwright_files)
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)

                page.on("response", self.response_save_images)
                self.download_show_image(page)
                self.download_episode_images(page)

                page.close()

    def download_show(self, page: BeerShaker, minimum_timestamp: datetime | None = None) -> None:
        if self.show_files_outdated(minimum_timestamp):
            self.go_to_page_logged_in(page, self.show_url)
            page.wait_for_load_state("networkidle")

            playwright_save_html_response(page, self.show_html_path)
            self.falcor_cache_cached_value = None

    def download_seasons(self, page: BeerShaker, minimum_timestamp: datetime | None = None) -> None:
        if self.season_files_outdated(minimum_timestamp):
            logging.getLogger(f"{self.logger_identifier()}.Scraping").info("All Seasons")
            if page.url != self.show_url:
                self.go_to_page_logged_in(page, self.show_url)
                page.wait_for_load_state("networkidle")

            # If there is a list of seasons open up the season selector
            if season_selector := page.query_selector("button[data-uia='dropdown-toggle']"):
                self.logged_click(season_selector, "Season selector")

                # Click the button to show all of the seasons at once on the page
                if li_elements := page.query_selector_all('li[data-uia="dropdown-menu-item"]'):
                    self.logged_click(li_elements[-1], "Show all seasons")

                # Wait for all files to exist
                files: list[JSONFile] = []
                for season_id in self.seasons_json_path.parsed_cached()["jsonGraph"]["seasons"]:
                    files.append(self._season_json_file(season_id))
                self.playwright_wait_for_files(page, files, minimum_timestamp)

    def download_show_image(self, page: BeerShaker) -> None:
        """Download the show image if it does not exist"""
        self._download_outdated_images(page, self.show_img_url(), "show")

    def download_episode_images(self, page: BeerShaker) -> None:
        for image_url in self.episode_image_urls():
            self._download_outdated_images(page, image_url, "Show")

    def go_to_page_logged_in(
        self,
        page: BeerShaker,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> None:
        page.goto(url, wait_until=wait_until)
        self.login_if_needed(page, url)
        self.select_user_if_needed(page)

    def login_if_needed(self, page: BeerShaker, url: str) -> None:
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

    def select_user_if_needed(self, page: BeerShaker) -> bool:
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

    def season_id_from_json(self, body: dict[str, Any]) -> str | None:
        for season_id, season in body["jsonGraph"].get("seasons", {}).items():
            if season.get("episodes"):
                return season_id

    def is_movie(self) -> bool:
        """Check if the media is a movie or not"""
        return "movie" in self.falcor_cache()["videos"][self._show_id]["jawSummary"]["value"]["type"]

    # TODO: Cahce this so JSOn doesn't have to be parsed so many times
    def falcor_cache(self, reload: bool = False) -> dict[str, Any]:
        if not self.falcor_cache_cached_value or reload:
            string = self.show_html_path.read_text("utf-8")
            string = string.split("netflix.falcorCache =")[-1]
            string = string.split(";</script>")[0]
            string = string.replace("\\x", "%")
            string = urllib.parse.unquote(string)
            self.falcor_cache_cached_value = json.loads(string.encode())
        return self.falcor_cache_cached_value

    def _import_show(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if self.show_object.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show_html = self.show_html_path.parsed_cached()
            falcor_cache = self.falcor_cache()
            show_thing = falcor_cache["videos"][self._show_id]
            self.show_object.name = show_thing["jawSummary"]["value"]["title"]
            self.show_object.description = show_thing["jawSummary"]["value"]["synopsis"]
            self.show_object.media_type = show_thing["jawSummary"]["value"]["type"].title()

            self.set_image(self.show_object, self._image_file_from_url(self.show_img_url()))
            self.show_object.url = self.show_url
            self.show_object.favicon_url = parsed_show_html.strict_select_one("link[rel='shortcut icon']").attrs["href"]
            self.show_object.deleted = False
            self.show_object.add_timestamps_and_save(self._show_json_file)

    def _import_seasons(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if self.is_movie():
            season = Season().get_or_new(season_id="Movie", show=self.show_object)[0]
            if season.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                season.sort_order = 0
                season.name = "Movie"
                season.number = 0
                season.deleted = False
                season.add_timestamps_and_save(self._show_json_file)
        else:
            season_items = self.seasons_json_path.parsed_cached()["jsonGraph"]["seasons"].items()
            for i, (season_id, season_info) in enumerate(season_items):
                season = Season().get_or_new(season_id=season_id, show=self.show_object)[0]

                if season.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                    season.sort_order = i
                    season.name = season_info["summary"]["value"]["name"]
                    if season.name.split(" ")[-1].isnumeric():
                        season.number = season.name.split(" ")[-1]
                    else:
                        season.number = i
                    season.deleted = False
                    season.add_timestamps_and_save(self._show_json_file)

    def _import_episodes(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if self.is_movie():
            season = Season().get_or_new(season_id="Movie", show=self.show_object)[0]
            episode = Episode().get_or_new(episode_id="Movie", season=season)[0]
            if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                falcor_cache = self.falcor_cache()
                show_thing = falcor_cache["videos"][self._show_id]

                # Deal with deleted content
                if not "availability" in show_thing["bobSummary"]["value"].keys():
                    return

                episode.sort_order = 0
                episode.description = self.show_object.description
                episode.number = "0"
                episode.name = "Movie"
                episode.duration = show_thing["runtime"]["value"]
                episode.url = f"https://www.netflix.com/watch/{self._show_id}"

                unix_timestamp = show_thing["bobSummary"]["value"]["availability"]["availabilityStartTime"] / 1000
                episode.release_date = datetime.fromtimestamp(unix_timestamp).astimezone()
                # No air date so just duplicate release_date
                episode.air_date = episode.release_date
                episode.deleted = False
                image_path = self._image_file_from_url(self.show_img_url())
                self.set_image(episode, image_path)
                episode.add_timestamps_and_save(season.info_timestamp)
        else:
            for season_id in self.seasons_json_path.parsed_cached()["jsonGraph"]["seasons"]:
                season = Season().get_or_new(season_id=season_id, show=self.show_object)[0]
                parsed_season_path = self._season_json_file(season_id).parsed_cached()
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
                        image_url = self.episode_image_url(parsed_episode)
                        image_path = self._image_file_from_url(image_url)
                        self.set_image(episode, image_path)
                        episode.deleted = False
                        episode.add_timestamps_and_save(season.info_timestamp)
