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

    @abstractmethod
    def outdated_files(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        """Check if any of the files are missing or outdated"""

    def image_url(self, file: JSONFile, image_type: str, index: int = 0) -> Optional[str]:
        """Return the URL of an image"""
        # Every now and then an episode just won't have thumbnails, but it is added later
        # Example: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri
        if images := file.parsed_cached()["data"][index].get("images"):
            return images[image_type][0][-1]["source"]

        return None

    def strict_image_url(self, file: JSONFile, image_type: str, index: int = 0) -> str:
        """Return the URL of an image, if the image is not found an erorr will be raised"""
        return file.parsed_cached()["data"][index]["images"][image_type][0][-1]["source"]

    def import_show_real(
        self,
        json_path: JSONFile,
        media_type: str,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        """Import the show information into the database for real"""
        if self.show.is_outdated(minimum_info_timestamp, minimum_modified_timestamp):
            # I don't see anything on Cruncyhroll that shows the difference between a TV Series, ONA, or OVA, so just list
            # this as a series which is a generic catch all term
            self.show.media_type = media_type
            self.show.url = self.show_url
            parsed_json = json_path.parsed_cached()["data"][0]
            self.show.name = parsed_json["title"]
            self.show.description = parsed_json["description"]
            image_url = self.strict_image_url(json_path, "poster_wide")
            self.set_image(self.show, image_url)
            self.show.favicon_url = self.DOMAIN + "/favicons/favicon-32x32.png"
            self.show.deleted = False
            self.show.add_timestamps_and_save(json_path)
