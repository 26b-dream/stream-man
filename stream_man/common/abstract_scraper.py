"""Includes AbstractScraperClass, which all scraper plugins must inherit and implement"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


class AbstractScraperClass(ABC):
    """Abstract class that must be inherited and implemented by plugins for them to be loaded"""

    @abstractmethod
    def website_name(self):
        """Name of the website that the scraper is for"""

    @classmethod
    @abstractmethod
    def is_valid_show_url(cls, show_url: str) -> bool:
        """Check if a url is a valid url for the scraper

        Args:
            show_url (str): The url to check

        Returns:
            bool: True if the url is valid, False otherwise
        """

    @abstractmethod
    def update(
        self, minimum_info_timestamp: Optional[datetime] = None, minimum_modified_timestamp: Optional[datetime] = None
    ) -> None:
        """Update the information for the show

        Args:
            minimum_info_timestamp (Optional[datetime], optional): A datetime that the information should be newer than.
            Defaults to None.
            minimum_modified_timestamp (Optional[datetime], optional): A datetime that the information in the database
            should be newer than. Defaults to None.
        """

    @abstractmethod
    def show_object(self) -> None:
        """The Show object from the database"""
