"""Models for the playlists app."""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from great_django_family import ModelWithId, auto_unique
from media.models import Episode, Show
from sorl.thumbnail import ImageField  # type: ignore[reportMissingTypeStubs]

if TYPE_CHECKING:
    from django.db.models.query import QuerySet


class Playlist(ModelWithId):
    """Model for a playlist."""

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        ordering = ("name",)

    name = models.CharField(max_length=255, unique=True)
    shows: models.ManyToManyField[Show, Playlist] = models.ManyToManyField(Show, through="PlaylistShow")
    thumbnail = ImageField(upload_to="images", null=True, blank=True)
    default_filter = models.JSONField(default=None, blank=True, null=True)
    deleted = models.BooleanField(default=False)

    def __str__(self) -> str:
        """Return the name of the playlist as the string representation."""
        return self.name

    def episodes(self) -> QuerySet[Episode]:
        """Get a QuerySet for all of the episodes in this playlist."""
        # Get all of the shows in the playlist
        show_ids = self.shows.values_list("id", flat=True)

        # Get episodes that are in the playlist and not set to be skipped
        return Episode.objects.filter(season__show__id__in=show_ids).select_related("season__show", "season")

    # This needs to be return an an optional value because playlists start with no shows
    def random_episode(self) -> Episode | None:
        """Returns a random episode from the playlist or None if there are no episodes."""
        return self.episodes().order_by("?").first()

    def thumbnail_url(self) -> str:
        """Returns the thumbnail_url for a playlist automatically.

        If no specific thumbnail is defined just use a random image from en episode in the playlist.
        """
        if self.thumbnail:
            return self.thumbnail.url

        random_episode = self.random_episode()
        if random_episode:
            return random_episode.image.url

        return "/static/no_thumbnail.png"


class PlaylistShow(ModelWithId):
    """Model that will track what shows are in a playlist."""

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        constraints = (auto_unique("show", "playlist"),)

    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE)

    def __str__(self) -> str:
        """Return the playlist and show as the string representation."""
        return f"{self.playlist} - {self.show}"


# A simple que of URLs to import for a playlist
class PlaylistImportQueue(ModelWithId):
    """Model that will track URLs that need to be imported into a playlist."""

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        constraints = (auto_unique("playlist", "url"),)

    url = models.CharField(max_length=255)
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE)

    def __str__(self) -> str:
        """Return the playlist and url as the string representation."""
        return f"{self.playlist} - {self.url}"
