"""Contains AbstractScraperClass."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from media.models import Show


class AbstractScraperClass(ABC):
    """Abstract class that must be inherited and implemented by plugins for them to function."""

    show_object: Show
    """The show object from the database. It should be initialized when the scraper instance is created."""

    @classmethod
    @abstractmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        """Check if the given URL is a valid show URL for the scraper.

        Args:
            show_url: The URL to check.

        Returns:
            True if the URL is valid, False if the URL is not valid for the scraper.
        """

    @abstractmethod
    def update(self, minimum_modified_timestamp: datetime | None = None) -> None:
        """Download and update the information for an entire show.

        If the data in the database is older than the minimum_modified_timestamp, it will be updated but not downloaded

        Args:
            minimum_modified_timestamp: Import information if the stored information was last modified before this.
        """

    @classmethod
    def credential_keys(cls) -> list[str]:
        """List of credentials that are required for the scraper to function.

        Returns:
            A list of values where each value is the name of a credential for the scraper
        """
        # By default a blank value is returned, so if a scraper requires no credentials, this function can be omitted.
        return []
