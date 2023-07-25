from __future__ import annotations

import _activate_django  # pyright: ignore[reportUnusedImport] # pylint: disable=W0611

from .scraper_test_base import ScraperTestBase


class TestCrunchyrollSeries(ScraperTestBase):
    def test_multiple_season(self):
        # Code Geass was chosen because it is an old show that is unlikely to get new episodes, and the license is
        # likely to be reneweed if it expires.
        self.compare_all("https://www.crunchyroll.com/series/GY2P9ED0Y/code-geass")

    def test_single_season(self):
        # Cowboy bebop was chosen because it is an old show that is unlikely to get new episodes, and the license is
        # likely to be reneweed if it expires.
        self.compare_all("https://www.crunchyroll.com/series/GYVNXMVP6/cowboy-bebop")

    def test_movie(self):
        # This movie was just randomly chosen from the list of movies which are available at
        # https://www.crunchyroll.com/videos/alphabetical?media=movies
        self.compare_all("https://www.crunchyroll.com/watch/GJKF27X8M/fullmetal-alchemist-the-conqueror-of-shamballa")
