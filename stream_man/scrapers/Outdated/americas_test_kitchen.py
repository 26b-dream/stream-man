"""Plugin for America's Test Kitchen."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Iterable

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import BaseScraper
from common.scraper_functions import BeerShaker, playwright_save_json_response
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from typing_extensions import override

if TYPE_CHECKING:
    from typing import Any

    from paved_path import PavedPath
    from playwright.sync_api._generated import Response


class AmericasTestKitchen(BaseScraper, AbstractScraperClass):
    """Scraper for America's Test Kitchen."""

    WEBSITE = "America's Test Kitchen"
    DOMAIN = "https://www.americastestkitchen.com"
    FAVICON_URL = "https://res.cloudinary.com/hksqkdlah/image/upload/atk-favicon.ico"
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}\/(?P<show_id>.*?)(?:/|$)")
    # Example show URLs
    #   https://www.americastestkitchen.com/cookscountry/episodes
    #   https://www.americastestkitchen.com/episodes

    @override
    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)

        # The main America's Test Kitchen show doesn't match the format used by their other shows. If this isn't the
        # main America's Test Kitchen show /episodes needs to be appended to the URL
        self._show_url = f"{self.DOMAIN}/{self._show_id}"
        if self._show_id != "episodes":
            self._show_url += "/episodes"

    def _episode_image_url(self, data: dict[str, Any]) -> str:
        if "c_fill,dpr_auto,f_auto,fl_lossy,q_auto,w_268,h_268" not in data["search_photo"]:
            msg = "Unexpected image URL format"
            raise ValueError(msg)
        # The format for the image is really hard to decide, I could actually pull in lossless images, but some of the
        # thumbnails end up being close to 10 MB and that's a waste of space, plus it will be really obvious in the
        # cloudinary logs. I think the best option is to just get an automatic quality image and be done with it. Also
        # by appending the file extension it forces the image to be that format.
        original_string = "c_fill,dpr_auto,f_auto,fl_lossy,q_auto,w_268,h_268"
        return data["search_photo"].replace(original_string, "q_auto") + ".webp"

    def _episode_image_file(self, data: dict[str, Any]) -> PavedPath:
        # File extension is not in the URL, it is hardcoded to a webp because the file type is locked to webp by the URL
        return self._image_file_from_url(self._episode_image_url(data), None, "webp")

    @override
    def _any_file_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        return (
            self._show_json_outdated(minimum_timestamp)
            or self._any_season_json_outdated(minimum_timestamp)
            or self._any_episode_image_missing()
        )

    def _show_json_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        return self._show_json_file().is_outdated(minimum_timestamp)

    def _any_season_json_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        """Check is any of the season JSON files are outdated."""
        if not self._show_json_file().exists():
            return True

        return any(self._season_json_outdated(i, minimum_timestamp) for i in self._season_numbers())

    def _season_json_outdated(self, season_number: int, minimum_timestamp: datetime | None = None) -> bool:
        """Check if any of the season JSON files are outdated for a specific season."""
        season_page_0 = self._season_json_file(season_number, page=0)

        # If the first page is outdated assume later pages are outdated
        if season_page_0.is_outdated():
            return True

        parsed_season_page_0 = season_page_0.parsed_cached()

        for page in range(parsed_season_page_0["results"][0]["nbPages"]):
            if self._season_json_file(season_number, page=page).is_outdated(minimum_timestamp):
                return True

        return False

    def _any_episode_image_missing(self) -> bool:
        if not self._show_json_file().exists():
            return True

        for season_number in self._season_numbers():
            season_page_0 = self._season_json_file(season_number, page=0)
            if not season_page_0.exists():
                return True

            parsed_season_page_0 = season_page_0.parsed_cached()
            for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                season_page = self._season_json_file(season_number, page=page_number)
                if not season_page.exists():
                    return True
                parsed_season_page = season_page.parsed_cached()
                for parsed_episode in parsed_season_page["results"][0]["hits"]:
                    if not self._episode_image_file(parsed_episode).exists():
                        return True

        return False

    @override
    def _download_all(self, minimum_timestamp: datetime | None = None) -> None:
        if self._any_file_outdated(minimum_timestamp):
            self._logger().info("Downloading")
            with sync_playwright() as playwright:
                page = BeerShaker(playwright)

                page.on("response", self._save_playwright_files)
                self._download_show(page, minimum_timestamp)
                self._download_seasons(page, minimum_timestamp)

                page.enable_image_download_mode()
                self._download_episode_images(page)

                page.close()

    def _download_show(self, page: BeerShaker, minimum_timestamp: datetime | None = None) -> None:
        if self._show_json_outdated(minimum_timestamp):
            self._logger("Downloading").info("Show Information")
            page.logged_goto(self._show_url, "Main page", wait_until="networkidle")
            page.wait_for_files(self._show_json_file(), minimum_timestamp)

    def _download_seasons(self, page: BeerShaker, minimum_timestamp: datetime | None = None) -> None:
        # This is made assuming all seasons will always be available
        for season_number in self._season_numbers():
            if self._season_json_outdated(season_number, minimum_timestamp):
                self._logger("Downloading").info(f"Season {season_number} Information")
                # Only open the website if it isn't already open
                if page.url != self._show_url:
                    page.logged_goto(self._show_url, "Main Page", wait_until="networkidle")

                # Click the button to show more seasons. This probably only needs to be done once but I put it in a
                # while loop just in case.
                if show_seasons := page.query_selector("button >> text=+ Show More"):
                    page.logged_click(show_seasons, "Show all seasons button")
                    page.wait_for_load_state("networkidle")

                # Click the button for the correct season then scroll to the bottom to load the first set of episodes
                season_button = page.get_by_role("link", name=f"Season {season_number}", exact=True)
                page.logged_click(season_button, "Show all seasons button")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_load_state("networkidle")

                # Click the button to show more episodes until all episodes are shown
                while remaining_episodes := page.query_selector("button >> text=SHOW MORE"):
                    # Need to scroll before the click for it to take
                    remaining_episodes.scroll_into_view_if_needed()
                    # Scrolling may causes things to load so wait for it to finish
                    page.wait_for_load_state("networkidle")
                    page.logged_click(remaining_episodes, "Show more episodes button")
                    page.wait_for_load_state("networkidle")

                # Make sure all season JSON files are downloaded for the current season
                while self._season_json_outdated(season_number, minimum_timestamp):
                    page.wait_for_timeout(1000)

    def _download_episode_images(self, page: BeerShaker) -> None:
        for season_number in self._season_numbers():
            season_page_0 = self._season_json_file(season_number, page=0)
            parsed_season_page_0 = season_page_0.parsed_cached()
            for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                season_page = self._season_json_file(season_number, page=page_number)
                parsed_season_page = season_page.parsed_cached()
                for parsed_episode in parsed_season_page["results"][0]["hits"]:
                    image_url = self._episode_image_url(parsed_episode)
                    image_file = self._episode_image_file(parsed_episode)
                    self._download_outdated_images(page, image_url, image_file)

    def _save_playwright_files(self, response: Response) -> None:
        # Example URLs:
        #   https://www.americastestkitchen.com/api/v6/shows/cco
        #   https://www.americastestkitchen.com/api/v6/shows/atk
        if re.search(r"api/v6/shows/[a-z]+$", response.url):
            playwright_save_json_response(response, self._show_json_file())

        # Example URL:
        #   https://y1fnzxui30-dsn.algolia.net/1/indexes/*/queries?x-algolia-agent=Algolia%20for%20JavaScript%20(3.35.1)%3B%20Browser%3B%20JS%20Helper%20(3.10.0)%3B%20react%20(17.0.2)%3B%20react-instantsearch%20(6.30.2)&x-algolia-application-id=Y1FNZXUI30&x-algolia-api-key=8d504d0099ed27c1b73708d22871d805
        if "algolia.net" in response.url:
            parsed_json = response.json()
            # Facets is probably more reliable than using the hits array
            season_number = next(iter(parsed_json["results"][0]["facets"]["search_season_list"].keys())).split(" ")[1]
            page_number = parsed_json["results"][0]["page"]
            season_path = self._season_json_file(season_number, page=page_number)
            playwright_save_json_response(response, season_path)

    @override
    def _import_show(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if self.show_object.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self._show_json_file().parsed_cached()
            self.show_object.name = parsed_show["title"]
            self.show_object.media_type = "TV Series"
            self.show_object.url = self._show_url
            self.show_object.set_favicon(self._favicon_file())
            self.show_object.deleted = False
            self.show_object.add_timestamps_and_save(self._show_json_file().aware_mtime())

    @override
    def _import_seasons(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        for season_number in self._season_numbers():
            season_page_0 = self._season_json_file(season_number, page=0)
            season = Season.objects.get_or_new(season_id=f"Season {season_number}", show=self.show_object)[0]
            if season.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                season.sort_order = season_number
                season.number = season_number
                season.name = f"Season {season_number}"
                season.deleted = False
                season.add_timestamps_and_save(season_page_0.aware_mtime())

    @override
    def _import_episodes(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        parsed_show = self._show_json_file().parsed_cached()
        slug = parsed_show["slug"]
        for season_number in self._season_numbers():
            parsed_season_page_0 = self._season_json_file(season_number, page=0).parsed_cached()
            season = Season.objects.get_or_new(season_id=f"Season {season_number}", show=self.show_object)[0]

            for page_number in range(parsed_season_page_0["results"][0]["nbPages"]):
                parsed_season_page = self._season_json_file(season_number, page=page_number).parsed_cached()
                for parsed_episode in parsed_season_page["results"][0]["hits"]:
                    episode = Episode.objects.get_or_new(episode_id=parsed_episode["objectID"], season=season)[0]

                    if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                        episode.sort_order = parsed_episode[f"search_{slug}_episode_number"]
                        episode.description = parsed_episode["search_description"]
                        episode.number = parsed_episode[f"search_{slug}_episode_number"]
                        episode.name = parsed_episode["title"]

                        minutes = int(parsed_episode["search_stickers"][0].split(":")[0]) * 60
                        seconds = int(parsed_episode["search_stickers"][0].split(":")[1])
                        episode.duration = minutes * 60 + seconds

                        date_string = str(parsed_episode["search_published_date"])
                        episode.air_date = datetime.strptime(date_string, "%Y%m%d").astimezone()

                        episode.url = f"{self.DOMAIN}{parsed_episode['search_url']}"
                        raw_date = parsed_episode["search_document_date"]
                        episode.release_date = datetime.strptime(raw_date, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone()
                        episode.set_image(self._episode_image_file(parsed_episode))
                        episode.deleted = False
                        episode.add_timestamps_and_save(season.info_timestamp)

    def _season_numbers(self) -> Iterable[int]:
        # This is made assuming all seasons will always be available because all content is owned internally
        return range(1, self._show_json_file().parsed_cached()["latestSeason"] + 1)
