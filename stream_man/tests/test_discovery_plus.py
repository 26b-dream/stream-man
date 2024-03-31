from __future__ import annotations

import _activate_django  # pyright: ignore[reportUnusedImport]  # noqa: F401

from .scraper_test_base import ScraperTestBase


class TestDiscoveryPlus(ScraperTestBase):
    def test_multiple_season(self):
        # This TV show was just randomly chosen
        self.compare_all("https://www.discoveryplus.com/show/mythbusters")

    def test_single_season(self):
        # This TV show was just randomly chosen
        self.compare_all("https://www.discoveryplus.com/show/prisoner-of-the-prophet-us")

    def test_movie(self):
        # This movie was just randomly chosen because it was the first result when searching the word "movie" on the
        # webiste
        self.compare_all("https://www.discoveryplus.com/show/roar-the-most-dangerous-movie-ever-made")
