"""PLugin for crunchyroll show"""
from __future__ import annotations

from common.base_scraper import ScraperShowShared


class CrunchyRollShared(ScraperShowShared):
    WEBSITE = "Crunchyroll"
    DOMAIN = "https://www.crunchyroll.com"
