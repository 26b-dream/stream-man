from __future__ import annotations

import datetime
from typing import Any, Optional

from common.get_scraper import GetScraper
from django.test import TestCase
from json_file import JSONFile
from media.models import Show


class ScraperTestBase(TestCase):
    """Base class for testing scrapers."""

    CURRENT_TIME = datetime.datetime.now().astimezone()
    DATE_A_WEEK_AGO = CURRENT_TIME - datetime.timedelta(weeks=1)

    def compare_all(self, url: str) -> None:
        """Compares all of the information."""
        scraper = GetScraper(url)
        scraper.update(self.DATE_A_WEEK_AGO, self.CURRENT_TIME)
        self.compare_show(scraper.show_object)

    def compare_show(self, show_object: Show) -> None:
        """Compare all of the show information."""
        correct_show = (JSONFile(__file__).parent / f"{show_object.website}_{show_object.show_id}.json").parsed_cached()
        show = show_object.dump()

        # Loop through dumped_show and parsed_json
        for (correct_key, correct_value), (key, value) in zip(correct_show.items(), show.items()):
            self.check_key(correct_key, key, correct_show, show)

            # This key is automatically generated so any value is acceptabled
            if key == "id":
                pass
            elif key == "info_modified_timestamp":
                self.assertGreaterEqual(datetime.datetime.fromisoformat(value), self.CURRENT_TIME)
            elif key == "info_timestamp":
                self.assertGreaterEqual(datetime.datetime.fromisoformat(value), self.DATE_A_WEEK_AGO)
            elif key == "update_at":
                self.assertGreaterEqual(datetime.datetime.fromisoformat(value), self.DATE_A_WEEK_AGO)
            elif key == "seasons":
                self.compare_seasons(correct_show, show, correct_value, value)
            else:
                self.check_value(key, correct_value, value, correct_show, show)

    def compare_seasons(
        self,
        correct_show: dict[str, Any],
        show: dict[str, Any],
        correct_seasons: list[dict[str, Any]],
        seasons: list[dict[str, Any]],
    ):
        """Compare all of the season information"""
        for correct_season, season in zip(correct_seasons, seasons):
            for (correct_key, correct_value), (key, value) in zip(correct_season.items(), season.items()):
                self.check_key(correct_key, key, correct_show, show, correct_season, season)

                # This key is automatically generated so any value is acceptabled
                if key == "id":
                    pass
                elif key == "info_modified_timestamp":
                    self.assertGreaterEqual(datetime.datetime.fromisoformat(value), self.CURRENT_TIME)
                elif key == "info_timestamp":
                    self.assertGreaterEqual(datetime.datetime.fromisoformat(value), self.DATE_A_WEEK_AGO)
                elif key == "episodes":
                    self.compare_episodes(correct_show, show, correct_season, season, correct_value, value)
                else:
                    self.check_value(key, correct_value, value, correct_show, show, correct_season, season)

    def compare_episodes(
        self,
        correct_show: dict[str, Any],
        show: dict[str, Any],
        correct_season: dict[str, Any],
        season: dict[str, Any],
        correct_episodes: list[dict[str, Any]],
        episodes: list[dict[str, Any]],
    ):
        """Compare all of the episode information"""
        for correct_episode, episode in zip(correct_episodes, episodes):
            for (correct_key, correct_value), (key, value) in zip(correct_episode.items(), episode.items()):
                self.check_key(correct_key, key, correct_show, show, correct_season, season, correct_episode, episode)

                # This key is automatically generated so any value is acceptabled
                if key == "id":
                    pass
                elif key == "info_modified_timestamp":
                    self.assertGreaterEqual(datetime.datetime.fromisoformat(value), self.CURRENT_TIME)
                elif key == "info_timestamp":
                    self.assertGreaterEqual(datetime.datetime.fromisoformat(value), self.DATE_A_WEEK_AGO)
                else:
                    self.check_value(
                        key, correct_value, value, correct_show, show, correct_season, season, correct_episode, episode
                    )

    def check_key(
        self,
        correct_key: str,
        key: str,
        correct_show: dict[str, Any],
        show: dict[str, Any],
        correct_season: Optional[dict[str, Any]] = None,
        season: Optional[dict[str, Any]] = None,
        correct_episode: Optional[dict[str, Any]] = None,
        episode: Optional[dict[str, Any]] = None,
    ):
        """Check that all of the keys match up"""
        error_string = "Key Mismatch"
        error_string += f"\n\tCorrect Show:{correct_show['name']}\n\tShow: {show['name']}"

        if correct_season and season:
            error_string += f"\n\tCorrect Season:{correct_season['number']}. {correct_season['name']}\n\tSeason:{season['number']}. {season['name']}"

        if correct_episode and episode:
            error_string += f"\n\tCorrect Episodes:{correct_episode['number']}. {correct_episode['name']}\n\tSeason:{episode['number']}. {episode['name']}"
        error_string += f"\n\tCorrect Key: = {correct_key}\n\tKey: {key}"

        self.assertEqual(correct_key, key, error_string)

    def check_value(
        self,
        key: str,
        correct_value: str,
        value: str,
        correct_show: dict[str, Any],
        show: dict[str, Any],
        correct_season: Optional[dict[str, Any]] = None,
        season: Optional[dict[str, Any]] = None,
        correct_episode: Optional[dict[str, Any]] = None,
        episode: Optional[dict[str, Any]] = None,
    ):
        """Check that all of the values match up"""
        if correct_value != value:
            error_string = "Value Mismatch"
            error_string += f"\n\tCorrect Show: {correct_show['name']}\n\tShow: {show['name']}"

            if correct_season and season:
                error_string += f"\n\tCorrect Season: {correct_season['number']}. {correct_season['name']}\n\tSeason: {season['number']}. {season['name']}"

            if correct_episode and episode:
                error_string += f"\n\tCorrect Episodes:{correct_episode['number']}. {correct_episode['name']}\n\tEpisode: {episode['number']}. {episode['name']}"
            error_string += f"\n\tKey: {key}"
            error_string += f"\n\tCorrect Value: {correct_value}\n\tValue: {value}"

            self.assertEqual(correct_value, value, error_string)
