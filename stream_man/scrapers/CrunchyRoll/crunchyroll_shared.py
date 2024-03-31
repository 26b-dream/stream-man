"""Generic plugin for different media types on Crunchyroll."""
from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from common.base_scraper import BaseScraper

if TYPE_CHECKING:
    from json_file import JSONFile


class CrunchyRollShared(BaseScraper, ABC):
    """Abstract class for Crunchyroll movies and series."""

    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"

    def _image_url(self, file: JSONFile, image_type: str, index: int = 0) -> str | None:
        """Return the URL of an image, if the image is not found return None."""
        # Every now and then an episode just won't have thumbnails, but it is added later
        # Example: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri
        if images := file.parsed_cached()["data"][index].get("images"):
            return images[image_type][0][-1]["source"]

        return None

    def _strict_image_url(self, file: JSONFile, image_type: str, index: int = 0) -> str:
        """Return the URL of an image, if the image is not found an erorr will be raised."""
        # Every now and then an episode just won't have thumbnails, but it is added later
        # Example: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri
        return file.parsed_cached()["data"][index]["images"][image_type][0][-1]["source"]
