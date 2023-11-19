"""PLugin for Netflix show"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from functools import cache
from subprocess import PIPE
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import ScraperShowShared
from common.constants import DOWNLOADED_FILES_DIR
from json_file import JSONFile
from media.models import Episode, Season
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # pyright: ignore [reportMissingTypeStubs]

if TYPE_CHECKING:
    from typing import Any, Optional

    from extended_path import ExtendedPath
    from playwright.sync_api._generated import Page


@cache
def episode_json_path_cached(website: str, episode_id: str) -> JSONFile:
    """Path for the JSON file that lists all of the episodes for a specific season"""
    return JSONFile(DOWNLOADED_FILES_DIR / website / f"episodes/{episode_id}.json")


# TODO: Special code to better determine when a playlist should be updated
class YouTubePlaylist(ScraperShowShared, AbstractScraperClass):
    """For now using this plugin requires yt-dlp uin the PATH"""

    WEBSITE = "YouTube"
    DOMAIN = "https://www.youtube.com"
    FAVICON_URL = DOMAIN + "/s/desktop/78ebd189/img/favicon_144x144.png"

    # Example show URLs
    #   https://www.youtube.com/playlist?list=PLSGAdUaWI73FQd0gWRj2GP9Ruln7HvEtq
    #   https://www.youtube.com/watch?v=nYfum3RdpuI&list=UULFL5_yRx9ujWPqH2lwD5d5_w
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}.*?list=(?P<show_id>.*?)(?:$)")

    def __init__(self, show_url: str) -> None:
        super().__init__(show_url)
        self.show_url = f"{self.DOMAIN}/playlist?list={self.show_id}"
        # self.show_html_path = HTMLFile(self.files_dir(), "show.html")
        # self.seasons_json_path = JSONFile(self.files_dir(), "seasons.json")

    def image_url_from_dict(self, data: dict[str, Any]) -> str:
        if data.get("thumbnail"):
            return data["thumbnail"]

        return data["thumbnails"][-1]["url"]

    def episode_json_path(self, episode_id: str) -> JSONFile:
        """Path for the JSON file that lists all of the episodes for a specific season"""
        return episode_json_path_cached(self.WEBSITE, episode_id)

    def any_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""
        output = self.show_files_outdated(minimum_timestamp)
        output = self.episode_files_outdated(minimum_timestamp) or output
        output = self.any_episode_image_missing() or output
        return output

    def show_files_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the show files are missing or outdated"""
        return self.show_json_path.outdated(minimum_timestamp)

    def episode_files_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the season files are missing or outdated"""
        output = False
        if self.show_json_path.exists():
            for episode_entry in self.show_json_path.parsed_cached()["entries"]:
                episode_json_path = self.episode_json_path(episode_entry["id"])
                if self.is_file_outdated(episode_json_path, "Episode JSON", minimum_timestamp):
                    output = True
        return output

    def any_episode_image_missing(self) -> bool:
        """Check if any of the episode images are missing"""
        output = False
        if self.show_json_path.exists():
            for episode_entry in self.show_json_path.parsed_cached()["entries"]:
                episode_json_path = self.episode_json_path(episode_entry["id"])
                if episode_json_path.exists():
                    image_path = self.image_path_from_dict(episode_json_path.parsed_cached())
                    output = self.is_file_outdated(image_path, "Episode image") or output

        return output

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_file_outdated(minimum_timestamp):
            self.download_show(minimum_timestamp)
            self.download_episodes(minimum_timestamp)

            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                stealth_sync(page)

                page.on("response", self.playwright_response_save_images)
                self.download_episode_images(page)

                page.close()

    def download_show(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.show_files_outdated(minimum_timestamp):
            logging.getLogger(self.logger_identifier()).info("Downloading show information")
            # Run external yt-dl and capture stdout and stderr
            command = [
                "yt-dlp",
                "--dump-single-json",  # Dump all output as a single json file
                "--flat-playlist",  # Only download playlist information
                self.show_url,
            ]

            raw_json = subprocess.run(command, stdout=PIPE, stderr=PIPE, check=True).stdout.decode("utf-8")
            self.show_json_path.write(raw_json)
            self.show_json_path.parsed_cached_value = json.loads(raw_json)

    def download_episodes(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.episode_files_outdated(minimum_timestamp):
            # Go through each video in the playlist
            for x in self.show_json_path.parsed_cached()["entries"]:
                episode_json_path = self.episode_json_path(x["id"])

                if not episode_json_path.exists():
                    logging.getLogger(self.logger_identifier() + "Downloading Episode Information").info(x["title"])
                    command = [
                        "yt-dlp",
                        "--ignore-errors",  # Ignore errors because private/deleted videos will cause errors
                        "--dump-single-json",  # Dump all output as a single json file
                        "--skip-download",  # Do not download the videos, just get the information
                        x["url"],
                    ]
                    # TODO: An error occurs if a scheduled video has not yet premiered
                    # TODO: Use this information to predict when the next udpate should be
                    raw_json = subprocess.run(command, stdout=PIPE, stderr=PIPE, check=True).stdout.decode("utf-8")
                    episode_json_path.write(raw_json)
                    episode_json_path.parsed_cached_value = json.loads(raw_json)

    def download_episode_images(self, page: Page) -> None:
        """Download a specific image using playwright if it does not exist"""
        for partial_episode in self.show_json_path.parsed_cached()["entries"]:
            episode_json_parsed = self.episode_json_path(partial_episode["id"]).parsed_cached()
            image_url = self.image_url_from_dict(episode_json_parsed)
            image_path = self.image_path_from_dict(episode_json_parsed)
            self.playwright_download_image_if_needed(page, image_url, "Episode", image_path)

    def episode_image_urls(self) -> list[str]:
        """Returns a list of all of the episode image urls"""
        output: list[str] = []
        if self.show_json_path.exists():
            for x in self.show_json_path.parsed_cached()["entries"]:
                episode_json_path = self.episode_json_path(x["id"])
                if episode_json_path.exists():
                    output.append(episode_json_path.parsed_cached()["thumbnail"])

        return output

    def image_path_from_dict(self, data: dict[str, Any]) -> ExtendedPath:
        # Image file names are not unique so the name needs to be based on the episode ID or show ID
        video_id = data["id"]
        if data.get("thumbnail"):
            img_suffix = data["thumbnail"].split(".")[-1]
        else:
            img_suffix = data["thumbnails"][-1]["url"].split(".")[-1].split("?")[0]
        return (DOWNLOADED_FILES_DIR / self.WEBSITE / "images" / video_id).with_suffix(f".{img_suffix}")

    def import_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.show_json_path.parsed_cached()

            self.show.name = f"{parsed_show['channel']} - {parsed_show['title']}"
            self.show.media_type = "Playlist"
            self.show.show_id = self.show_id
            self.show.description = parsed_show["description"]
            self.show.favicon_url = self.FAVICON_URL
            self.show.deleted = False
            self.show.add_timestamps_and_save(self.show_json_path)

    def import_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        season_info = Season().get_or_new(season_id=self.show_id, show=self.show)[0]

        if season_info.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            season_json_parsed = self.show_json_path.parsed_cached()
            season_info.number = 0
            season_info.sort_order = 0
            season_info.name = season_json_parsed["title"]
            season_info.sort_order = 0
            season_info.deleted = False
            season_info.add_timestamps_and_save(self.show_json_path)

    def import_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        season_info = Season().get_or_new(season_id=self.show_id, show=self.show)[0]
        season_json_parsed = self.show_json_path.parsed_cached()

        for i, partial_episode in enumerate(season_json_parsed["entries"]):
            episode = Episode().get_or_new(episode_id=partial_episode["id"], season=season_info)[0]

            if episode.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
                episode_json_path = self.episode_json_path(partial_episode["id"])
                if episode_json_path.exists():
                    episode_json_parsed = episode_json_path.parsed_cached()
                    episode.sort_order = i
                    episode.name = episode_json_parsed["title"]
                    episode.number = str(i)
                    episode.description = episode_json_parsed["description"]
                    episode.duration = episode_json_parsed["duration"]
                    episode.url = f"https://youtu.be/{episode.id}"

                    date = datetime.strptime(episode_json_parsed["upload_date"], "%Y%m%d").astimezone()
                    episode.air_date = date

                    if release_timestamp := episode_json_parsed.get("release_timestamp"):
                        episode.release_date = datetime.fromtimestamp(release_timestamp).astimezone()
                    else:
                        episode.release_date = episode.air_date

                    image_path = self.image_path_from_dict(episode_json_parsed)
                    self.set_image(episode, image_path)
                    episode.deleted = False
                    episode.add_timestamps_and_save(episode_json_path)
