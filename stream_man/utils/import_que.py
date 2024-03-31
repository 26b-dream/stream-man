"""Imports all shows in the import queue and updates all shows that are outdated."""
from __future__ import annotations

import logging
from datetime import datetime

import _activate_django  # pyright: ignore[reportUnusedImport]  # noqa: F401
from common.get_scraper import GetScraper, InvalidURLError
from django.db import transaction
from media.models import Show
from playlists.models import Playlist, PlaylistImportQueue, PlaylistShow

logging.basicConfig(level=logging.INFO)


@transaction.atomic
def import_new_url(show: PlaylistImportQueue) -> None:
    """Import a new URL from the import queue."""
    playlist = Playlist.objects.get(id=show.playlist.id)

    try:
        show_scraper = GetScraper(show.url)
        logging.getLogger("Importing").getChild("Importing").info(show.url)
    except InvalidURLError:
        logging.getLogger("Error").getChild("Invalid URL").info(show.url)
        return
    try:
        show_scraper.update(minimum_modified_timestamp=datetime.now().astimezone())
    # Need to be able to catch all exceptions so the next URL can be imported even if the current one fails
    except Exception as e:  # noqa: BLE001
        logging.getLogger("Error").getChild("Import Failure").info(e)
        return

    # Add show to playlist and delete it from the queue
    PlaylistShow.objects.create(playlist=playlist, show=show_scraper.show_object)
    show.delete()


def update_show(show: Show) -> None:
    """Update a show."""
    try:
        show_scraper = GetScraper(show.url)
        logging.getLogger("Importing").getChild("Importing").info(show.url)
    except InvalidURLError:
        logging.getLogger("Error").getChild("Invalid URL").info(show.url)
        return
    try:
        show_scraper.update()
    # Need to be able to catch all exceptions so the next URL can be updated even if the current one fails
    except Exception as e:  # noqa: BLE001
        logging.getLogger("Error").getChild("Import Failure").info(e)


if __name__ == "__main__":
    # Import shows that are in the import queue
    for show in PlaylistImportQueue.objects.all():
        import_new_url(show)

    # Update shows that have already been imported but the imported data is outdated
    for show in Show.objects.filter(update_at__lt=datetime.now().astimezone()):
        update_show(show)
