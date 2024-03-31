"""PLugin for a YouTube playlist."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from functools import cached_property
from typing import TYPE_CHECKING

import common.extended_re as re
from common.abstract_scraper import AbstractScraperClass
from common.base_scraper import BaseScraper
from common.scraper_functions import BeerShaker
from json_file import JSONFile
from media.models import Episode, Season, Show
from playwright.sync_api import sync_playwright
from typing_extensions import override

if TYPE_CHECKING:
    from typing import Any

    from paved_path import PavedPath


# TODO: Special code to better determine when a playlist should be updated
class YouTube(BaseScraper, AbstractScraperClass):
    """Plugin to support YouTube playlists.

    For now using this plugin requires yt-dlp in the PATH.
    """

    WEBSITE = "YouTube"
    DOMAIN = "https://www.youtube.com"

    # Example channel URL
    #   https://www.youtube.com/@DiscoveryWalkingToursTV
    CHANNEL_URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}\/@(?P<show_id>.*?)(?:$)")

    # Example playlist URLs
    #   https://www.youtube.com/playlist?list=PLSGAdUaWI73FQd0gWRj2GP9Ruln7HvEtq
    #   https://www.youtube.com/watch?v=nYfum3RdpuI&list=UULFL5_yRx9ujWPqH2lwD5d5_w
    PLAYLIST_URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}.*?list=(?P<show_id>.*?)(?:$|&)")

    # Combined regex for both channel and playlist URLs
    URL_REGEX = re.compile(rf"^{re.escape(DOMAIN)}(?:.*?list=|\/@)(?P<show_id>.*?)(?:$|&)")

    @override
    def __init__(self, show_url: str) -> None:
        """Initializes a Scraper object for a specific show from a specific website."""
        super().__init__(show_url)
        if re.search(self.CHANNEL_URL_REGEX, show_url):
            self.type = "Channel"
            self._show_url = f"{self.DOMAIN}/@{self._show_id}"
        elif re.search(self.PLAYLIST_URL_REGEX, show_url):
            self.type = "Playlist"
            self._show_url = f"{self.DOMAIN}/playlist?list={self._show_id}"
        else:
            error_message = f"Invalid URL: {show_url}"
            raise ValueError(error_message)

        # Replace existing show_object to include if this is a plylist or a channel. This is done just in case a
        # playlist and a channel can share an ID.
        website_name = f"{self._website_name} {self.type}"
        self.show_object = Show.objects.get_or_new(show_id=self._show_id, website=website_name)[0]

    @cached_property
    @override
    def _show_json_file(self) -> JSONFile:
        # Add in the type of the show to the file name.
        # This is done just in case playlists and channels can share an ID.
        return JSONFile(self._website_dir, self.type, f"{self._show_id}.json")

    @cached_property
    @override
    def _show_dir(self) -> PavedPath:
        # Force all shows to share a folder so episodes can all be grouped together
        return self._website_dir

    def _episode_image_file(self, data: dict[str, Any]) -> PavedPath:
        # Can't cache this in any meaningful way because the parameter is a dictionary
        # Image file names are not unique so the name needs to be based on the episode ID or show ID
        # ? Can't remember why this is formatted like this
        episode_id = data["id"]
        if data.get("thumbnail"):
            img_suffix = data["thumbnail"].split(".")[-1]
        else:
            img_suffix = data["thumbnails"][-1]["url"].split(".")[-1].split("?")[0]
        return (self._website_dir / "Image" / "Episode" / episode_id).with_suffix(f".{img_suffix}")

    def _get_episode_image_url(self, data: dict[str, Any]) -> str:
        # Can't cache this in any meaningful way because the parameter is a dictionary
        """Get the URL for the image.

        Args:
            data: The dictionary that contains the information for the episode.
        """
        # ? Can't remember why this is formatted like this
        if data.get("thumbnail"):
            return data["thumbnail"]

        return data["thumbnails"][-1]["url"]

    @override
    def _any_file_outdated(self) -> bool:
        self._logger().info("Checking for outdated files")
        output = self._favicon_file_outdated()
        output = self._show_files_outdated() or output
        output = self._episode_files_outdated() or output
        return self._any_episode_image_missing() or output

    def _show_files_outdated(self) -> bool:
        return self._logged_file_outdated(self._show_json_file, "Show JSON", self._show_update_at_timestamp())

    def _episode_files_outdated(self) -> bool:
        output = False
        if self._show_json_file.exists():
            for episode_entry in self._episode_list():
                episode_json_file = self._episode_json_file(episode_entry["id"])
                file_name = f"Episode JSON {episode_entry['id']}"
                # There is no reason to update this file so set the timestamp to None
                output = self._logged_file_outdated(episode_json_file, file_name) or output
        return output

    def _any_episode_image_missing(self) -> bool:
        output = False
        if self._show_json_file.exists():
            for episode_entry in self._episode_list():
                episode_json_file = self._episode_json_file(episode_entry["id"])
                if episode_json_file.exists():
                    image_path = self._episode_image_file(episode_json_file.parsed_cached())
                    file_name = f"Episode Image {episode_entry['id']}"
                    # There is no reason to update this file so set the timestamp to none
                    output = self._logged_file_outdated(image_path, file_name) or output

        return output

    @override
    def _download_all(self) -> None:
        if self._any_file_outdated():
            self._download_show_if_outdated()
            self._download_episode_if_outdated()

            # I don't actually need to use Playwrite since this just downloads images, but the code is already there and
            # easy to re-use
            with sync_playwright() as playwright:
                page = BeerShaker(playwright)
                self._download_episode_images(page)
                self._download_favicon_if_outdated(page)
                page.close()

    def _download_show_if_outdated(self) -> None:
        if self._show_files_outdated():
            self._logger("Downloading Show Information").info(self._show_url)
            # Run external yt-dl and capture stdout and stderr
            command = [
                "yt-dlp",
                "--dump-single-json",  # Dump all output as a single json file
                "--flat-playlist",  # Only download playlist information
                self._show_url,
            ]

            # This error is just inconsistent, the URL is already verified to be a YouTube URL so it should be safe to
            # run the process
            raw_json = subprocess.run(command, capture_output=True, check=True).stdout.decode("utf-8")  # noqa: S603
            self._show_json_file.write(raw_json)

    def _download_episode_if_outdated(self) -> None:
        if self._episode_files_outdated():
            # Go through each video in the playlist
            for episode in self._episode_list():
                episode_json_path = self._episode_json_file(episode["id"])

                # No information to gain by downloading it so just ignore it
                if self._episode_deleted(episode):
                    continue

                timestamp = self._episode_update_at_timestamp(self._show_id, episode["id"])
                if episode_json_path.is_outdated(timestamp):
                    self._logger("Downloading Episode Information").info(episode["url"])
                    command = [
                        "yt-dlp",
                        "--ignore-errors",  # Ignore errors because private/deleted videos will cause errors
                        "--dump-single-json",  # Dump all output as a single json file
                        "--skip-download",  # Do not download the videos, just get the information
                        episode["url"],
                    ]
                    # TODO: An error occurs if a scheduled video has not yet premiered
                    # TODO: Use this information to predict when the next udpate should be
                    # Subprocess is secure as possible because the URL comes directly from yt-dlp
                    raw_json = subprocess.run(command, capture_output=True, check=True).stdout.decode("utf-8")  # noqa: S603
                    episode_json_path.write(raw_json)

    def _download_episode_images(self, page: BeerShaker) -> None:
        for partial_episode in self._episode_list():
            # No information to gain by downloading it so just ignore it
            if self._episode_deleted(partial_episode):
                continue

            episode_json_parsed = self._episode_json_file(partial_episode["id"]).parsed_cached()
            image_url = self._get_episode_image_url(episode_json_parsed)
            image_path = self._episode_image_file(episode_json_parsed)
            self._download_image_if_outdated(page, image_url, image_path, "Episode Image")

    def _episode_deleted(self, episode_entry: dict[str, Any]) -> bool:
        # Video title can be "[Deleted video]" or "[Private video]", but it looks like view_count will always be None
        # and will only ever be None for deleted videos, I don't know what this will do with videos that actually have 0
        # views, I am assuming that they will have the number 0 instead of None.
        return episode_entry["view_count"] is None

    def _episode_list(self) -> list[dict[str, Any]]:
        """Get the list of videos."""
        if self.type == "Channel":
            return self._show_json_file.parsed_cached()["entries"][0]["entries"]

        # Plylists can just return this simplified version
        return self._show_json_file.parsed_cached()["entries"]

    @override
    def _import_show(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        if self.show_object.is_outdated(minimum_modified_timestamp):
            parsed_show = self._show_json_file.parsed_cached()

            self.show_object.name = f"{parsed_show['channel']} - {parsed_show['title']}"
            self.show_object.media_type = "Playlist"
            self.show_object.show_id = self._show_id
            self.show_object.url = f"{self.DOMAIN}/playlist?list={self._show_id}"
            self.show_object.description = parsed_show["description"]
            self.show_object.set_favicon(self._favicon_file)
            self.show_object.deleted = False
            self.show_object.add_timestamps_and_save(self._show_json_file.aware_mtime())

    @override
    def _import_seasons(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        season_info = Season.objects.get_or_new(season_id=self._show_id, show=self.show_object)[0]

        if season_info.is_outdated(minimum_modified_timestamp):
            season_json_parsed = self._show_json_file.parsed_cached()
            season_info.number = 0
            season_info.sort_order = 0
            season_info.name = season_json_parsed["title"]
            season_info.sort_order = 0
            season_info.deleted = False
            season_info.add_timestamps_and_save(self._show_json_file.aware_mtime())

    @override
    def _import_episodes(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        season_info = Season.objects.get_or_new(season_id=self._show_id, show=self.show_object)[0]
        for i, partial_episode in enumerate(self._episode_list()):
            episode = Episode.objects.get_or_new(episode_id=partial_episode["id"], season=season_info)[0]

            if episode.is_outdated(minimum_modified_timestamp):
                episode_json_path = self._episode_json_file(partial_episode["id"])
                if episode_json_path.exists():
                    episode_json_parsed = episode_json_path.parsed_cached()
                    episode.sort_order = i
                    episode.name = episode_json_parsed["title"]
                    episode.number = str(i)
                    episode.description = episode_json_parsed["description"]
                    episode.duration = episode_json_parsed["duration"]
                    episode.url = f"https://youtu.be/{episode.episode_id}"

                    date = datetime.strptime(episode_json_parsed["upload_date"], "%Y%m%d").astimezone()
                    episode.air_date = date

                    if release_timestamp := episode_json_parsed.get("release_timestamp"):
                        episode.release_date = datetime.fromtimestamp(release_timestamp).astimezone()
                    else:
                        episode.release_date = episode.air_date

                    episode.set_image(self._episode_image_file(episode_json_parsed))
                    episode.deleted = False
                    episode.add_timestamps_and_save(episode_json_path.aware_mtime())

    def _set_update_at(self) -> None:
        # YouTube's is pretty relaxed about scraping considering yt-dlp exists, update everything every 24 hours
        self.show_object.update_info_at = self.show_object.info_timestamp + timedelta(days=1)
        self.show_object.save()
