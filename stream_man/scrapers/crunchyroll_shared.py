"""PLugin for crunchyroll show"""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Optional

from common.base_scraper import ScraperShowShared
from json_file import JSONFile


class CrunchyRollShared(ScraperShowShared):
    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
    show_url: str
    FAVICON_URL = DOMAIN + "/favicons/favicon-32x32.png"

    @abstractmethod
    def any_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""

    def image_url(self, file: JSONFile, image_type: str, index: int = 0) -> Optional[str]:
        """Return the URL of an image or None if no image is found"""
        # Every now and then an episode just won't have thumbnails, but it is added later
        # Example: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri
        if images := file.parsed_cached()["data"][index].get("images"):
            return images[image_type][0][-1]["source"]

        return None

    def strict_image_url(self, file: JSONFile, image_type: str, index: int = 0) -> str:
        """Return the URL of an image, if the image is not found an erorr will be raised"""
        # Every now and then an episode just won't have thumbnails, but it is added later
        # Example: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri
        return file.parsed_cached()["data"][index]["images"][image_type][0][-1]["source"]

    def import_show_shared(
        self,
        json_path: JSONFile,
        media_type: str,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """An extra function that is called by import_show that makes it wasier to share code between a movie and a
        series on Crunchyroll"""
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            # I don't see anything on Cruncyhroll that shows the difference between a TV Series, ONA, or OVA, so just list
            # this as a series which is a generic catch all term
            self.show.media_type = media_type
            self.show.url = self.show_url
            parsed_json = json_path.parsed_cached()["data"][0]
            self.show.name = parsed_json["title"]
            self.show.description = parsed_json["description"]
            image_url = self.strict_image_url(json_path, "poster_wide")
            image_path = self.image_path_from_url(image_url)
            self.set_image(self.show, image_path)
            self.show.favicon_url = self.FAVICON_URL
            self.show.deleted = False
            self.show.add_timestamps_and_save(json_path)
