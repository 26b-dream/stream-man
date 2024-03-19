"""AbstractScraperClass, which all scraper plugins must inherit and implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from media.models import Show


class AbstractScraperClass(ABC):
    """Abstract class that must be inherited and implemented by plugins for them to be loaded."""

    """The show object from the database."""
    show_object: Show

    @classmethod
    @abstractmethod
    def website_name(cls) -> str:
        """Get the name of the website.

        This could be a class constant in some situations, but having it as a function gives you the freedom to make a
        scraper that supports multiple websites at once.

        Returns:
        -------
        str: The name of the website.
        """

    @classmethod
    @abstractmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        """Check if the given URL is a valid show URL.

        Parameters:
        ----------
        show_url (str): The URL to check.

        Returns:
        -------
        bool: True if the URL is a valid show URL, False otherwise.
        """

    @classmethod
    def credential_keys(cls) -> list[str]:
        """List of credentials that are required for the scraper.

        Returns:
        -------
            A list of values where each value is the name of a credential for the scraper
        """
        # By default a blank value can be returned for scrapers that don't require credentials
        return []

    @abstractmethod
    def update(
        self,
        minimum_info_timestamp: datetime | None = None,
        minimum_modified_timestamp: datetime | None = None,
    ) -> None:
        """Download and update the information for the entire show.

        If files are older than the minimum_info_timestamp, they will be downloaded.
        If information in the database is older than the minimum_modified_timestamp, it will be updated.

        Parameters
        ----------
        minimum_info_timestamp (datetime | None): The minimum timestamp for files to be downloaded.
        minimum_modified_timestamp (datetime | None): The minimum timestamp for information to be updated.

        Returns:
        -------
        None
        """
