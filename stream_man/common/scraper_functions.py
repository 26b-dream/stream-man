"""Functions to make scraping easier."""

from __future__ import annotations

import logging
import urllib.request
from time import sleep
from typing import TYPE_CHECKING, Literal

from playwright.sync_api._generated import Page, Playwright
from playwright_stealth import stealth_sync  # type: ignore  # noqa: PGH003 - Stubs won't generate for some reason
from typing_extensions import override

from common.constants import DOWNLOADED_FILES_DIR

if TYPE_CHECKING:
    from datetime import datetime

    from html_file import HTMLFile
    from json_file import JSONFile
    from paved_path import PavedPath
    from playwright._impl._api_structures import Position
    from playwright.sync_api._generated import BrowserContext, ElementHandle, Locator, Response

logger = logging.getLogger(__name__)


def persistent_browser(
    playwright: Playwright,
) -> BrowserContext:
    """Preconfigured Playwright browser used for scraping.

    Args:
    ----
        playwright: Playwright object
        user_agent: User agent to use

    Returns:
    -------
        Playwright browser context
    """
    return playwright.chromium.launch_persistent_context(
        # For some reason using Firefox as the user agent seems to bypass Cloudflare more frequently than Chrome even
        # though the actual browser is Chrome
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        user_data_dir=DOWNLOADED_FILES_DIR / "cookies/chrome",  # Persist cookies for simplicity
        headless=False,  # Use a full browser instantiation to reduce likelihood of being detected as a bot
        channel="chrome",  # firefox has issues with persistent cookies so use Chrome
        slow_mo=1000,  # Probably helps reduce likelihood of being detected as a bot
    )


def playwright_save_json_response(response: Response, file_path: JSONFile) -> None:
    """Save a JSON response from playwright.

    Args:
    ----
        response: Response from playwright
        file_path: Path to save the JSON file to

    Returns:
    -------
        None
    """
    raw_json = response.json()
    # Add some extra information to json files to help with debugging
    if isinstance(raw_json, dict):  # This is just for type safety
        raw_json["stream_man"] = {"url": response.url, "status": response.status, "headers": response.headers}

    file_path.write(raw_json)


class BeerShaker(Page):
    """Page object with additional functionality.

    The name BeerShaker is just a goofy thought process of Playwright -> Shakespeare -> BeerShaker.
    """

    @override
    def __init__(self, playwright: Playwright | BrowserContext) -> None:
        browser_context = persistent_browser(playwright) if isinstance(playwright, Playwright) else playwright
        page = browser_context.new_page()
        self.__dict__.update(vars(page))
        stealth_sync(self)

    def wait_for_files(
        self,
        files: PavedPath | tuple[PavedPath, ...],
        timestamp: datetime | None = None,
        seconds: int = 10,
    ) -> None:
        """Wait for files to exist.

        Downloads will sometimes randomly not be detected by playwright if nothing is being executed. This function
        will simply execute a query selector until the file exists and is up to date. This is also useful to detect
        changes in the website causing files to no longer download or be detected.

        Args:
        ----
            page: BeerShaker to execute the query selector on, required to keep downloads from randomly hanging
            files: List of files to wait for
            timestamp: Minimum timestamp for the file to be considered up to date
            seconds: Number of seconds to wait for the file to be downloaded

        Returns:
        -------
            None
        """
        if not isinstance(files, tuple):
            files = (files,)

        for _ in range(seconds):
            if all(file.is_up_to_date(timestamp) for file in files):
                return

            # Executing a query_selector will keep the download form randomly hanging while waiting for the file to
            # be downloaded.
            self.query_selector("html")
            sleep(1)

        missing_files = [str(file) for file in files if not file.exists()]
        error_message = f"Files {', '.join(missing_files)} were not found"
        raise FileNotFoundError(error_message)

    def save_html_response(self, file_path: HTMLFile) -> None:
        """Save a HTML response from playwright.

        Parameters:
        ----------
        file_path (HTMLFile): Path to save the HTML file to

        Returns:
        -------
        None
        """
        file_path.write(self.content())

    def download_image(self, path: PavedPath, url: str) -> None:
        """Download a specific image.

        Will initially attempt to download the file using Playwright, if that fails it will then try to download the
        file using urlib because Playwright is unable to download images larger than 10 MB.

        Parameters:
        ----------
        path (PavedPath): The path to save the image to
        url (str): The URL of the image to download

        Returns:
        -------
        None
        """
        # ? Do I really want pictures bigger than like 1 MB? I should probably make something that limits file sizes
        # Set the image path so that the response_save_images function knows where to save the image
        self.image_path = path

        self.logged_goto(url, "Downloading image", wait_until="networkidle")
        self.wait_for_timeout(1000)

        # Sometimes images are over 10 MB, when that happens Playwright will have an error because it is unable to
        # download files larger than 10 MB see: https://github.com/microsoft/playwright/issues/13449
        # When this happens download the file using urllib instead
        try:
            self.wait_for_files(path)
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, path)  # noqa: S310 - This check is bugged

    def enable_image_download_mode(self) -> None:
        """Enable image download mode."""
        self.on("response", self._response_save_images)

    def logged_goto(  # noqa: PLR0913 - This wraps a function with a lot of parameters, there is no way to avoid this
        self,
        url: str,
        msg: str = "",
        *,
        timeout: float | None = None,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None = None,
        referer: str | None = None,
    ) -> None:
        """Goto with logging, see goto for more information."""
        msg = f"{msg} ({url})" if msg else url
        logger.getChild("Opening URL").info(msg)
        self.goto(url, timeout=timeout, wait_until=wait_until, referer=referer)

    def logged_click(  # noqa: PLR0913 - This wraps a function with a lot of parameters, there is no way to avoid this
        self,
        element: ElementHandle | Locator,
        msg: str,
        modifiers: list[Literal["Alt", "Control", "Meta", "Shift"]] | None = None,
        position: Position | None = None,
        delay: float | None = None,
        button: Literal["left", "middle", "right"] | None = None,
        click_count: int | None = None,
        timeout: float | None = None,
        force: bool | None = None,
        no_wait_after: bool | None = None,
        trial: bool | None = None,
    ) -> None:
        """Click with logging, see click for more information."""
        logger.getChild("Clicking").info(f"Clicking: {msg}")
        element.click(
            modifiers=modifiers,
            position=position,
            delay=delay,
            button=button,
            click_count=click_count,
            timeout=timeout,
            force=force,
            no_wait_after=no_wait_after,
            trial=trial,
        )

    def _response_save_images(self, response: Response) -> None:
        """Save every image file that is requested by playwright.

        Parameters:
        ----------
        response (Response): The response object from playwright

        Returns:
        -------
        None
        """
        if self.image_path:
            self.image_path.write(response.body())
        else:
            msg = "No image path was set"
            raise ValueError(msg)
