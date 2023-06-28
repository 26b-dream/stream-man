from __future__ import annotations

import logging
from datetime import datetime

import _activate_django  # pyright: ignore[reportUnusedImport] # pylint: disable=W0611
from common.scrapers import InvalidURLError, Scraper
from playlists.models import Playlist, PlaylistImportQueue, PlaylistShow

logging.basicConfig(level=logging.INFO)

for show in PlaylistImportQueue.objects.all():
    playlist = Playlist.objects.get(id=show.playlist.id)

    try:
        show_scraper = Scraper(show.url)
    except InvalidURLError:
        logging.getLogger("Error").info("Invalid URL %s", show.url)
        continue
    logging.getLogger("Importing").info("Importing %s", show.url)

    show_scraper.update(minimum_modified_timestamp=datetime.now().astimezone())

    # Link show to playlist
    # get_or_create in case the show is already in the playlist for some reason
    PlaylistShow.objects.get_or_create(playlist=playlist, show=show_scraper.show_object())

    # Delete show from que as it has been imported
    show.delete()
