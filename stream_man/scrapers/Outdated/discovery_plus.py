"""Plugin for crunchyroll show."""
from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

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


class DiscoveryPlusShow(BaseScraper, AbstractScraperClass):
    """Scraper for Discovery+ shows."""

    WEBSITE = "Discovery+"
    DOMAIN = "https://www.discoveryplus.com"
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}\/show\/(?P<show_id>.*)(?:\/|$)")
    FAVICON_URL = "https://www.discoveryplus.com/favicon.png"
    # Example show URL
    #   https://www.discoveryplus.com/show/mythbusters

    @override
    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/show/{self._show_id}"

    def _show_image_url(self) -> str:
        # Find all of the images related to this show
        for image_to_find in self._show_entry()["relationships"]["images"]["data"]:
            image_id = image_to_find["id"]

            # Go through every entry because some entries are iamges
            for img in self._show_json_file.parsed_cached()["included"]:
                # There are a ton of images for each show
                #   poster: https://us1-prod-images.disco-api.com/2020/11/09/0511b4d2-5134-3e14-ae3d-f750ac529108.jpeg
                #   default: https://us1-prod-images.disco-api.com/2020/11/09/24a61f35-22a5-36a9-b5d2-23f8107aa0cc.jpeg
                #   poster_with_logo:
                #   https://us1-prod-images.disco-api.com/2020/11/09/6dfea9f8-2033-3f86-b8dc-3b7ef8fade85.jpeg
                #   cover_artwork_horizontal: https://us1-prod-images.disco-api.com/2023/05/11/4ed57781-5d70-3b61-86c1-3b6dad08abfe.png
                #   cover_artwork_horizontal: https://us1-prod-images.disco-api.com/2023/05/11/4ed57781-5d70-3b61-86c1-3b6dad08abfe.png
                #   cover_artwork: https://us1-prod-images.disco-api.com/2020/11/09/6154e275-77f2-3abd-97bf-f4fdc3ddf03a.jpeg
                #   logo: https://us1-prod-images.disco-api.com/2020/07/20/788e55c5-9855-3af2-9634-11eb0678be6b.png
                # Use cover_artwork_horizontal for the image because it is the closest to 16:9
                if img["id"] == image_id and img["attributes"]["kind"] == "cover_artwork_horizontal":
                    return img["attributes"]["src"]

        msg = "Unable to get show_image_url from"
        raise ValueError(msg)

    def _episode_image_url(self, parsed_episode: dict[str, Any]) -> str:
        image_id = parsed_episode["relationships"]["images"]["data"][0]["id"]
        season_number = parsed_episode["attributes"]["seasonNumber"]

        # Go through all the included images and find the image that matches
        file_path = self._season_json_file(season_number)
        for entry in file_path.parsed_cached()["included"]:
            # Find matching value
            if entry["id"] == image_id:
                return entry["attributes"]["src"]

        msg = "Unable to get episode_image_url"
        raise ValueError(msg)

    def _episode_image_file(self, parsed_episode: dict[str, Any]) -> PavedPath:
        episode_number = parsed_episode["attributes"]["episodeNumber"]
        season_number = parsed_episode["attributes"]["seasonNumber"]
        image_url = self._episode_image_url(parsed_episode)
        return self._image_file_from_url(image_url, f"Season {season_number}/Episode {episode_number}")

    def _show_image_file(self) -> PavedPath:
        return self._image_file_from_url(self._show_image_url(), "Show")

    @override
    def _any_file_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        return (
            self._show_json_outdated(minimum_timestamp)
            or self._any_season_json_outdated(minimum_timestamp)
            or self._any_episode_image_missing()
            or self._show_image_missing()
        )

    def _show_json_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        return self._show_json_file.is_outdated(minimum_timestamp)

    def _show_image_missing(self) -> bool:
        if not self._show_json_file.exists():
            return True

        return self._show_image_file().is_outdated()

    def _any_season_json_outdated(self, minimum_timestamp: datetime | None = None) -> bool:
        if not self._show_json_file.exists():
            return True

        for season_number in self._season_numbers():
            if self._season_json_outdated(season_number, minimum_timestamp):
                return True

        return False

    def _season_json_outdated(self, season_number: str, minimum_timestamp: datetime | None = None) -> bool:
        return self._season_json_file(season_number).is_outdated(minimum_timestamp)

    def _any_episode_image_missing(self) -> bool:
        if not self._show_json_file.exists():
            return True

        if season_numbers := self._season_numbers():
            for season_number in season_numbers:
                if not self._season_json_file(season_number).exists():
                    return True
                for parsed_episode in self._season_episodes(season_number):
                    image_path = self._episode_image_file(parsed_episode)
                    if image_path.is_outdated():
                        return True

        return False

    def _save_playwright_files(self, response: Response) -> None:
        # This is the JSON file that is recieved when loading up the show page
        # Don't use self.DOMAIN here because the URL is on a subdomain
        if "discoveryplus.com/cms/routes/show/{self.show_id}?" in response.url:
            parsed_json = response.json()
            dumped_json = json.dumps(parsed_json)
            self._show_json_file.write(dumped_json)

            # The show files also include information for the first season shown on screen. Need to determine what the
            # first season shown on screen is then double save this file as the file with season infomration
            for entry in parsed_json["included"]:
                # Find the entry that is a list of episodes
                if entry.get("attributes", {}).get("title") == "Episodes":
                    season_info = entry["attributes"]["component"]["filters"][0]
                    # Determine what season is embedded in the show JSON, if no value is found assume this is a movie
                    season_id = season_info.get("initiallySelectedOptionIds", ["movie"])[0]
                    playwright_save_json_response(response, self._season_json_file(season_id))

        # These are the JSON files that are recieved when changing seasons on the show page. The initially displayed
        # season on the show page does not send a season specific JSON file and instead adds that information to the
        # show JSON file, so some of the season files will be the same as the show page JSON file and some of them will
        # be a unique file
        elif "pf[seasonNumber]" in response.url:
            parsed_url = urlparse(response.url)
            query_params = parse_qs(parsed_url.query)
            season_number = query_params["pf[seasonNumber]"][0]
            playwright_save_json_response(response, self._season_json_file(season_number))

    @override
    def _download_all(self, minimum_timestamp: datetime | None = None) -> None:
        if self._any_file_outdated(minimum_timestamp):
            self._logger().info("Downloading")
            with sync_playwright() as playwright:
                page = BeerShaker(playwright)

                page.on("response", self._save_playwright_files)
                self._download_show_json(page, minimum_timestamp)
                self._download_seasons(page, minimum_timestamp)

                page.enable_image_download_mode()
                self._download_show_image(page)
                self._download_episode_images(page)

                page.close()

    def _download_show_json(self, page: BeerShaker, minimum_timestamp: datetime | None = None) -> None:
        if self._show_json_outdated(minimum_timestamp):
            page.logged_goto(self.show_url, "Main Page", wait_until="networkidle")
            page.wait_for_files(self._show_json_file, minimum_timestamp)

    def _download_seasons(self, page: BeerShaker, minimum_timestamp: datetime | None = None) -> None:
        for season in self._season_numbers():
            if self._season_json_outdated(season, minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this one time, all later pages can reuse existing page
                if self.show_url not in page.url:
                    page.logged_goto(self.show_url, "Main Page", wait_until="networkidle")

                if page.query_selector("div[data-testid='season-dropdown']"):
                    # Open season selector
                    page.logged_click(page.locator("div[data-testid='season-dropdown']"), "Season selector")

                    # Click season
                    season_button = page.locator(f"span[data-testid='season-{season}']")
                    page.logged_click(season_button, "Season button")

                    page.wait_for_files(self._season_json_file(season), minimum_timestamp)

    def _download_show_image(self, page: BeerShaker) -> None:
        self._download_outdated_images(page, self._show_image_url(), self._show_image_file())

    def _download_episode_images(self, page: BeerShaker) -> None:
        for season_number in self._season_numbers():
            for parsed_episode in self._season_episodes(season_number):
                image_path = self._episode_image_file(parsed_episode)
                image_url = self._episode_image_url(parsed_episode)
                self._download_outdated_images(page, image_url, image_path)

    @override
    def _import_show(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if self.show_object.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self._show_entry()
            self.show_object.name = parsed_show["attributes"]["name"]

            # Sometimes longDescription is not available so just use description instead
            self.show_object.description = (
                parsed_show["attributes"].get("longDescription") or parsed_show["attributes"]["description"]
            )

            self.show_object.set_image(self._show_image_file())
            self.show_object.favicon_url = self.FAVICON_URL
            # parsed_show["type"] is not reliable for media type because movies are listed as "shows" see:
            # https://www.discoveryplus.com/show/roar-the-most-dangerous-movie-ever-made
            if self._season_numbers() == ["movie"]:
                self.show_object.media_type = "Movie"
            else:
                self.show_object.media_type = "TV Show"
            self.show_object.url = self.show_url
            self.show_object.deleted = False
            self.show_object.add_timestamps_and_save(self._show_json_file.aware_mtime())

    @override
    def _import_seasons(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        # There really isn't much for season specific information
        for i, season_number in enumerate(self._season_numbers()):
            # parsed_season["id"] is not actually a season id because it is the same for every season for a show
            # Just use the season number as the id and hope it never changes
            season = Season.objects.get_or_new(season_id=season_number, show=self.show_object)[0]

            if not season.is_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season.sort_order = i
                if season_number == "movie":
                    season.number = 1
                    season.name = "Movie"
                else:
                    season.number = int(season_number)
                    season.name = f"Season {season_number}"
                season.deleted = False
                season.add_timestamps_and_save(self._season_json_file(season_number).aware_mtime())

    @override
    def _import_episodes(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if season_numbers := self._season_numbers():
            for season_number in season_numbers:
                season = Season.objects.get_or_new(season_id=season_number, show=self.show_object)[0]
                for i, parsed_episode in enumerate(self._season_episodes(season_number)):
                    episode = Episode.objects.get_or_new(episode_id=parsed_episode["id"], season=season)[0]

                    if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                        episode.sort_order = i
                        episode.name = parsed_episode["attributes"]["name"]
                        # Assume if no episode number is given this is a movie
                        episode.number = parsed_episode["attributes"].get("episodeNumber", "movie")
                        episode.description = parsed_episode["attributes"]["longDescription"]
                        episode.duration = parsed_episode["attributes"]["videoDuration"] / 1000
                        episode.url = f"{self.DOMAIN}/video/{parsed_episode['attributes']['path']}"

                        # Movie do not have an air_date value so just use the available date for both
                        strp = "%Y-%m-%dT%H:%M:%S%z"
                        episode.air_date = datetime.strptime(parsed_episode["attributes"]["airDate"], strp).astimezone()

                        # release_date is not really accurate, earliestPlayableStart, publishStart, and
                        # firstAvailableDate all are changed when licensing changes, see:
                        # https://www.discoveryplus.com/show/mythbusters
                        episode.release_date = datetime.strptime(
                            parsed_episode["attributes"]["earliestPlayableStart"],
                            strp,
                        ).astimezone()
                        # Every now and then a show just won't have thumbnails
                        # See: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri (May be updated later)
                        episode.set_image(self._episode_image_file(parsed_episode))

                        # No seperate file for episodes so just use the season file
                        episode.deleted = False
                        episode.add_timestamps_and_save(season.info_timestamp)

    def _season_numbers(self) -> list[str]:
        """Get a list of all of the season numbers for the show."""
        # Return a list instead of a generator because it's easier to check if the contents of a list matches a
        # predetermined value which is used when checking if a show is a movie
        output: list[str] = []
        show_json = self._show_json_file.parsed_cached()
        # Go through every entry in the JSON file
        for entry in show_json["included"]:
            # Find the entry that has all of the show information
            if entry.get("attributes", {}).get("title") == "Episodes":
                # Go through each season for the show
                seasons_numbers = entry["attributes"]["component"]["filters"][0]["options"]
                if seasons_numbers:
                    for season in seasons_numbers:
                        output.append(season["id"])
                # seasons_numbers will be an empty array for movies, for simplicty, save an extra file named movie in
                # the season folder so code can be easily re-used
                else:
                    output.append("movie")
        return output

    def _season_entry(self, season_id: str) -> dict[str, Any]:
        """Get the information for a specific season from the season_json_file."""
        season_json_path = self._season_json_file(season_id)
        season_json_parsed = season_json_path.parsed_cached()

        # This works for all seasons but the first one
        # Check if the main data entry in the JSON file is the season information
        if season_json_parsed.get("data", {}).get("attributes", {}).get("title") == "Episodes":
            return season_json_parsed["data"]

        # This only works for the first season and is required for shows that only have one season
        for entry in season_json_parsed["included"]:
            # Find the entry that has season information
            if entry.get("attributes", {}).get("title") == "Episodes":
                return entry

        msg = "Found no matches for the season"
        raise ValueError(msg)

    def _season_episodes(self, season_id: str) -> list[dict[str, Any]]:
        """Get all of the episode information for a season from the season_json_files."""
        parsed_seasons = self._season_json_file(season_id).parsed_cached()
        # This list comprehennsion goes through every entry in season_json_file and checks if the entry is a video, and
        # it is a video if it will be returned
        return [entry for entry in parsed_seasons["included"] if entry.get("relationships", {}).get("video")]

    def _show_entry(self) -> dict[str, Any]:
        """Get the information for the show from the show_json_file."""
        show_json_parsed = self._show_json_file.parsed_cached()
        for entry in show_json_parsed["included"]:
            if entry.get("attributes", {}).get("alternateId") == self._show_id:
                return entry

        msg = "Unable to find show information in show_json file"
        raise ValueError(msg)
