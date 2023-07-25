"""PLugin for crunchyroll show"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from common.base_scraper import ScraperShowShared
from common.constants import DOWNLOADED_FILES_DIR

from stream_man.settings import MEDIA_ROOT

if TYPE_CHECKING:
    from extended_path import ExtendedPath
    from media.models import Episode, Show
    from playwright.sync_api._generated import Page, Response


class CrunchyRollShared(ScraperShowShared):
    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
    FILES_DIR = DOWNLOADED_FILES_DIR / WEBSITE

    def image_path(self, image_url: str) -> ExtendedPath:
        image_name = image_url.split("/")[-1]
        return DOWNLOADED_FILES_DIR / self.WEBSITE / "images" / image_name

    def outdated_image(self, image_url: str, image_type: str) -> bool:
        """Check if a specific image is missing or outdated"""
        image_path = self.image_path(image_url)
        if image_path.outdated():
            logger = logging.getLogger(f"{self.logger_identifier()}.Outdated {image_type} file")
            logger.info(self.pretty_file_path(image_path))
            return True

        return False

    def pretty_file_path(self, file_path: ExtendedPath) -> str:
        """Returns the file path relative to the downloaded files directory which is easier to read when logging"""
        return str(file_path.relative_to(DOWNLOADED_FILES_DIR))

    def download_image(self, page: Page, image_url: str, image_source: str) -> None:
        """Download a specific image using playwright"""
        image_path = self.image_path(image_url)

        if not image_path.exists():
            logger = logging.getLogger(f"{self.logger_identifier()}.Outdated {image_source} image")
            logger.info(self.pretty_file_path(image_path))
            logging.getLogger(f"{self.logger_identifier()}.Downloading").info(image_url)
            page.goto(image_url, wait_until="networkidle")
            page.wait_for_timeout(1000)

            self.playwright_wait_for_files(page, 10, None, image_path)

    def save_playwright_images(self, response: Response) -> None:
        """Save every image file that is requested by playwright"""
        self.image_path(response.url).write(response.body())

    def set_image(self, model_object: Episode | Show, image_url: str):
        """Set the image for a model object and hardlink the image so it can be accessed through Django"""
        image_path = self.image_path(image_url)
        pretty_name = self.pretty_file_path(image_path)
        model_object.image.name = pretty_name

        # Hardlink the file so it can be served through the server easier
        media_path = MEDIA_ROOT / pretty_name
        if not media_path.exists():
            media_path.parent.mkdir(parents=True, exist_ok=True)
            media_path.hardlink_to(image_path)
