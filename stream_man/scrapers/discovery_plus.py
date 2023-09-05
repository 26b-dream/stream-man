"""PLugin for crunchyroll show"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # pyright: ignore [reportMissingTypeStubs]

if TYPE_CHECKING:
    from typing import Any, Optional

    from playwright.sync_api._generated import Page, Response


class DiscoveryPlusShow(ScraperShowShared, AbstractScraperClass):
    WEBSITE = "Discovery+"
    DOMAIN = "https://www.discoveryplus.com"

    # Example show URL
    #   https://www.discoveryplus.com/show/mythbusters
    URL_REGEX = re.compile(r"^(?:https:\/\/www\.discoveryplus\.com)?\/show\/(?P<show_id>.*)(?:\/|$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/show/{self.show_id}"
        # These values are hosted under a subdomain so don't use DOMAIN here
        self.partial_show_json_url = f"discoveryplus.com/cms/routes/show/{self.show_id}?"

    def show_image_url(self) -> str:
        """Get the show image url from the show json"""
        # Find all of the images related to this show
        for image_to_find in self.show_entry()["relationships"]["images"]["data"]:
            image_id = image_to_find["id"]

            # Go through every entry because some entries are iamges
            for img in self.show_json_path.parsed_cached()["included"]:
                # There are a ton of images for each show
                #   poster: https://us1-prod-images.disco-api.com/2020/11/09/0511b4d2-5134-3e14-ae3d-f750ac529108.jpeg
                #   default: https://us1-prod-images.disco-api.com/2020/11/09/24a61f35-22a5-36a9-b5d2-23f8107aa0cc.jpeg
                #   poster_with_logo:
                #   https://us1-prod-images.disco-api.com/2020/11/09/6dfea9f8-2033-3f86-b8dc-3b7ef8fade85.jpeg
                #   cover_artwork_horizontal: https://us1-prod-images.disco-api.com/2023/05/11/4ed57781-5d70-3b61-86c1-3b6dad08abfe.png
                #   cover_artwork_horizontal: https://us1-prod-images.disco-api.com/2023/05/11/4ed57781-5d70-3b61-86c1-3b6dad08abfe.png
                #   cover_artwork: https://us1-prod-images.disco-api.com/2020/11/09/6154e275-77f2-3abd-97bf-f4fdc3ddf03a.jpeg
                #   logo: https://us1-prod-images.disco-api.com/2020/07/20/788e55c5-9855-3af2-9634-11eb0678be6b.png
                # Use cover_artwork_horizontal for the image because it is the closes to 16:9
                if img["id"] == image_id and img["attributes"]["kind"] == "cover_artwork_horizontal":
                    return img["attributes"]["src"]
        raise ValueError("Unable to get show_image_url from")

    def episode_image_url(self, image_id: str, season_id: str) -> str:
        # Go through all the included images and find the image that matches
        file_path = self.season_json_path(season_id)
        for entry in file_path.parsed_cached()["included"]:
            # Find matching value
            if entry["id"] == image_id:
                return entry["attributes"]["src"]

        raise ValueError("Unable to get episode_image_url")

    def outdated_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""
        return (
            self.outdated_show_files(minimum_timestamp)
            or self.outdated_seasons_files(minimum_timestamp)
            or self.outdated_episodes_files()
        )

    def outdated_show_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the show files are missing or outdated"""
        return self.outdated_show_json(minimum_timestamp) or self.outdated_show_image()

    def outdated_show_json(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if the show json file is missing or outdated"""
        return self.check_if_outdated(self.show_json_path, "Show JSON", minimum_timestamp)

    def outdated_show_image(self) -> bool:
        """Check if any of the show image are missing or outdated"""
        if self.show_json_path.exists():
            show_image_path = self.image_path(self.show_image_url())
            return self.check_if_outdated(show_image_path, "Show Image")
        return False

    def outdated_seasons_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the season files are missing or outdated"""
        output = False
        if self.show_json_path.exists():
            for season_number in self.season_numbers():
                output = self.outdated_season_files(season_number, minimum_timestamp) or output

        return output

    def outdated_season_files(self, season_number: str, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the season files for a specific season are missing or outdated, having this as a seperate
        function makes it easier to check what seasons need to be updated"""
        return self.check_if_outdated(self.season_json_path(season_number), "Season JSON", minimum_timestamp)

    def outdated_episodes_files(self) -> bool:
        """Check if any of the image files are missing or outdated"""
        output = False
        if self.show_json_path.exists():
            if season_numbers := self.season_numbers():
                for season_number in season_numbers:
                    if self.season_json_path(season_number).exists():
                        for parsed_episode in self.season_episodes(season_number):
                            image_id = parsed_episode["relationships"]["images"]["data"][0]["id"]
                            image_url = self.episode_image_url(image_id, season_number)
                            image_path = self.image_path(image_url)
                            output = self.check_if_outdated(image_path, "Episode Image") or output
        return output

    def save_playwright_files(self, response: Response) -> None:
        # This is the JSON file that is recieved when loading up the show page
        if self.partial_show_json_url in response.url:
            parsed_json = response.json()
            dumped_json = json.dumps(parsed_json)
            self.show_json_path.write(dumped_json)

            # The show files also include information for the first season shown on screen. Need to determine what the
            # first season shown on screen is then double save this file as the file with season infomration
            # Go through all vlaues in the JSON
            for entry in parsed_json["included"]:
                # Find the entry that is a list of episodes
                if entry.get("attributes", {}).get("title") == "Episodes":
                    season_info = entry["attributes"]["component"]["filters"][0]
                    # Determine what season is embedded in the show JSON, if no value is found assume this is a movie
                    season_id = season_info.get("initiallySelectedOptionIds", ["movie"])[0]
                    self.season_json_path(season_id).write(dumped_json)

        # These are the JSON files that are recieved when changing seasons on the show page. The initially displayed
        # season on the show page does not send a season specific JSON file and instead adds that information to the
        # show JSON file, so some of the season files will be the same as the show page JSON file and some of them will
        # be a unique file
        elif "pf[seasonNumber]" in response.url:
            parsed_url = urlparse(response.url)
            query_params = parse_qs(parsed_url.query)
            season_number = query_params["pf[seasonNumber]"][0]
            self.season_json_path(season_number).write(json.dumps(response.json()))

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the files that are outdated or do not exist"""
        if self.outdated_files(minimum_timestamp):
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)
                page.on("response", self.save_playwright_files)
                self.download_show_json(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)
                page.on("response", self.save_playwright_images)
                self.download_show_image(page)
                self.download_episodes(page)
                page.close()

    def download_show_json(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the show files that are outdated or do not exist"""
        if self.outdated_show_json(minimum_timestamp):
            logging.getLogger(f"{self.logger_identifier()}.Scraping").info(self.show_url)
            page.goto(self.show_url, wait_until="networkidle")
            self.playwright_wait_for_files(page, self.show_json_path, minimum_timestamp)

    def download_show_image(self, page: Page) -> None:
        """Download the show image if it is outdated or do not exist, this is a seperate function from downloading the
        show because it is easier to download all of the images after downloading all of the JSON files"""
        self.playwright_download_image(page, self.show_image_url(), "show")

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        """Download all of the season files that are outdated or do not exist"""
        logger = logging.getLogger(f"{self.logger_identifier()}.Scraping")
        for season in self.season_numbers():
            # If all of the season files are up to date nothing needs to be done
            if self.outdated_season_files(season, minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this one time, all later pages can reuse existing page
                if self.show_url not in page.url:
                    logger.info(self.show_url)
                    page.goto(self.show_url, wait_until="networkidle")

                if page.query_selector("div[data-testid='season-dropdown']"):
                    logger.info("Season %s", season)
                    # Open season selector
                    page.locator("div[data-testid='season-dropdown']").click()

                    # Sleep for 5 seconds to avoid being banned
                    page.wait_for_timeout(5000)

                    # Click season
                    page.locator(f"span[data-testid='season-{season}']").click()

                    self.playwright_wait_for_files(page, self.season_json_path(season), minimum_timestamp)

    def download_episodes(self, page: Page) -> None:
        for season_number in self.season_numbers():
            for episode_parsed in self.season_episodes(season_number):
                image_id = episode_parsed["relationships"]["images"]["data"][0]["id"]
                image_url = self.episode_image_url(image_id, season_number)
                self.playwright_download_image(page, image_url, "episode")

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.show_entry()
            self.show.name = parsed_show["attributes"]["name"]

            # Sometimes longDescription is not available so just use description instead
            self.show.description = (
                parsed_show["attributes"].get("longDescription") or parsed_show["attributes"]["description"]
            )
            self.set_image(self.show, self.show_image_url())
            self.show.favicon_url = "https://www.discoveryplus.com/favicon.png"
            # parsed_show["type"] is not reliable for media type because movies are listed as "shows" see:
            # https://www.discoveryplus.com/show/roar-the-most-dangerous-movie-ever-made
            if self.season_numbers() == ["movie"]:
                self.show.media_type = "Movie"
            else:
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

        # There really isn't much for season specific information
        for i, season_number in enumerate(self.season_numbers()):
            # parsed_season["id"] is not actually a season id because it is the same for every season for a show
            # Just use the season number as the id and hope it never changes
            season = Season().get_or_new(season_id=season_number, show=self.show)[0]

            if not season.is_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season.sort_order = i
                if season_number == "movie":
                    season.number = 1
                    season.name = "Movie"
                else:
                    season.number = int(season_number)
                    season.name = f"Season {season_number}"
                season.deleted = False
                season.add_timestamps_and_save(self.season_json_path(season_number))

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the episode information, does not attempt to download or update the information"""
        if season_numbers := self.season_numbers():
            for season_number in season_numbers:
                season = Season().get_or_new(season_id=season_number, show=self.show)[0]
                for i, parsed_episode in enumerate(self.season_episodes(season_number)):
                    episode = Episode().get_or_new(episode_id=parsed_episode["id"], season=season)[0]

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
                        episode.air_date = datetime.strptime(parsed_episode["attributes"]["airDate"], strp)

                        # release_date is not really accurate, earliestPlayableStart, publishStart, and firstAvailableDate
                        # all are changed when licensing changes, see: https://www.discoveryplus.com/show/mythbusters
                        episode.release_date = datetime.strptime(
                            parsed_episode["attributes"]["earliestPlayableStart"], strp
                        )
                        # Every now and then a show just won't have thumbnails
                        # See: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri (May be updated later)

                        image_id = parsed_episode["relationships"]["images"]["data"][0]["id"]
                        image_url = self.episode_image_url(image_id, season_number)
                        self.set_image(episode, str(self.image_path(image_url)))

                        # No seperate file for episodes so just use the season file
                        episode.deleted = False
                        episode.add_timestamps_and_save(season.info_timestamp)

    def season_numbers(self) -> list[str]:
        """Get a list of all of the season numbers for the show"""
        show_json = self.show_json_path.parsed_cached()
        output: list[str] = []
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

    def season_entry(self, season_id: str) -> dict[str, Any]:
        """Get the information for a specific season"""
        season_json_path = self.season_json_path(season_id)
        season_json_parsed = season_json_path.parsed_cached()

        # This works for all seasons but the first one
        # Check if the main data entry in the JSON file is the season information
        if season_json_parsed.get("data", {}).get("attributes", {}).get("title") == "Episodes":
            return season_json_parsed["data"]

        # This only works for the first season
        # Go through each value in the JSON file
        for entry in season_json_parsed["included"]:
            # Find the entry that has season information
            if entry.get("attributes", {}).get("title") == "Episodes":
                return entry
        raise ValueError("Found no matches for the season")

    def season_episodes(self, season_id: str) -> list[dict[str, Any]]:
        """Get all of the episodes for a specific season"""
        parsed_seasons = self.season_json_path(season_id).parsed_cached()
        # This can be done with a map but it becomes harder to read
        episode_ids: list[str] = []
        # Go through each entry on the JSON file
        for entry in parsed_seasons["included"]:
            # Find the entry that has a list of episodes
            if entry.get("relationships", {}).get("video"):
                # Compile the ids of the episodes
                episode_ids.append(entry["relationships"]["video"]["data"]["id"])

        # Convert episode ids to episode entries
        return [entry for entry in parsed_seasons["included"] if entry.get("id") in episode_ids]

    def show_entry(self) -> dict[str, Any]:
        """Parse the show JSON file and just return the dictionary that includes information about the show"""
        show_json_parsed = self.show_json_path.parsed_cached()
        for entry in show_json_parsed["included"]:
            if entry.get("attributes", {}).get("alternateId") == self.show_id:
                return entry

        raise ValueError("Unable to find show information in show_json file")
