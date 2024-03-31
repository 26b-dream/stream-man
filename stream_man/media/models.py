"""Django models for the media app."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from common.constants import DOWNLOADED_FILES_DIR
from django.db import models
from django.utils.html import escape
from django.utils.safestring import mark_safe
from great_django_family import ModelWithId, ModelWithIdTimestampAndGetOrNew, auto_unique
from sorl.thumbnail import ImageField  # type: ignore[reportMissingTypeStubs]

from stream_man.settings import MEDIA_ROOT

if TYPE_CHECKING:
    from paved_path import PavedPath


class UpdateAtMixin(ModelWithIdTimestampAndGetOrNew):
    """Mixin that adds an update_at field to a model."""

    update_info_at = models.DateTimeField(null=True, blank=True)

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        abstract = True

    def checked_update_at(self) -> datetime | None:
        """Get the update_at value if it has already passed, if it has not passed return None."""
        if self.update_info_at and self.update_info_at < datetime.now().astimezone():
            return self.update_info_at

        return None

    def is_up_to_date(
        self,
        minimum_modified_timestamp: datetime | None = None,
    ) -> bool:
        """Check if the information in the database is up to date."""
        # If no timestamp is present the information has to be outdated
        if not self.info_timestamp or not self.info_modified_timestamp:
            return False

        # Check that minimum_modified_timestamp is up to date
        if minimum_modified_timestamp and minimum_modified_timestamp > self.info_modified_timestamp:
            return False

        # Check using up_to_date
        checked_update_at = self.checked_update_at()
        if checked_update_at and checked_update_at > self.info_timestamp:
            return False

        # If other tests passed information is up to date
        return True

    def is_outdated(self, minimum_modified_timestamp: datetime | None = None) -> bool:
        """Check if the information in the database is outdated."""
        return not self.is_up_to_date(minimum_modified_timestamp)

    def add_timestamps_and_save(self, info_timestamp: datetime) -> None:
        """Add timestamps to the model and save it."""
        self.add_timestamps(info_timestamp)
        self.save()

    def add_timestamps(self, info_timestamp: datetime) -> None:
        """Add timestamps to the model."""
        self.info_timestamp = info_timestamp
        self.info_modified_timestamp = datetime.now().astimezone()


class ModelImageSaver(models.Model):
    """Model that has an image and an easy way to save it."""

    image = ImageField(upload_to="images", null=True, blank=True)

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        abstract = True

    def set_image(self, image_path: PavedPath) -> None:
        """Set the image for a model object and hardlink the image so it can be easily accessed through Django."""
        pretty_name = image_path.relative_to(DOWNLOADED_FILES_DIR)

        self.image.name = str(pretty_name)

        # Hardlink the file so it can be served through the server easier
        media_path = MEDIA_ROOT / pretty_name
        if not media_path.exists():
            media_path.parent.mkdir(parents=True, exist_ok=True)
            media_path.hardlink_to(image_path)


class Show(ModelImageSaver, UpdateAtMixin):
    """Model for a show."""

    season_set: models.QuerySet[Season]

    website = models.CharField(max_length=255)
    show_id = models.CharField(max_length=255)
    """Unique show identifier imported from the website"""
    name = models.CharField(max_length=255)
    media_type = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    url = models.CharField(max_length=255, null=False)
    favicon = ImageField(max_length=255)
    # Null is allowed because you often need to import the Show before the episodes, but update_at is calculated based
    # on episode information
    deleted = models.BooleanField()

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        constraints = (auto_unique("website", "show_id"),)
        ordering = ("name",)

    def __str__(self) -> str:
        """Show represented as a string."""
        return self.name

    def last_watched_date(self) -> date:
        """Date that an episode was last watched."""
        episode_info = EpisodeWatch.objects.filter(episode__season__show=self).order_by("watch_date").last()
        if episode_info:
            return episode_info.watch_date

        # If not episode info is found return the earliest possible date
        return datetime.fromtimestamp(0).astimezone()

    def newest_episode_date(self) -> date:
        """Release date of the newest episode."""
        if episode := Episode.objects.filter(season__show=self).order_by("release_date").last():
            return episode.release_date

        # If not episode info is found return the earliest possible date
        return datetime.fromtimestamp(0).astimezone().date()

    def dump(self) -> dict[str, Any]:
        """Dump all of the information for a show as json."""
        variables = vars(self).copy()
        # State is just junk information when it comes to serialization
        variables.pop("_state")
        # Cast images to strings so they can be serialized
        variables["image"] = str(variables["image"])
        # Convert all of the datetimes to ISO format so they are able to be serialized
        variables["info_timestamp"] = self.info_timestamp.isoformat()
        variables["info_modified_timestamp"] = self.info_modified_timestamp.isoformat()
        variables["update_at"] = self.update_info_at.isoformat() if self.update_info_at else None

        variables["seasons"] = [season.dump() for season in self.season_set.all()]

        return variables

    def pretty_html_name(self, favicon_size: int = 16) -> str:
        """Return a pretty HTML name for the show."""
        img = f"<img width='{favicon_size}' height='{favicon_size}' src='{escape(self.favicon.url)}'></img>"
        return mark_safe(f"{img} {escape(self.name)}")  # noqa: S308 - This is safe as long as the plugin is safe

    def set_favicon(self, image_path: PavedPath) -> None:
        """Set the image for a model object and hardlink the image so it can be easily accessed through Django."""
        pretty_name = image_path.relative_to(DOWNLOADED_FILES_DIR)

        self.favicon.name = str(pretty_name)

        # Hardlink the file so it can be served through the server easier
        media_path = MEDIA_ROOT / pretty_name
        if not media_path.exists():
            media_path.parent.mkdir(parents=True, exist_ok=True)
            media_path.hardlink_to(image_path)


class Season(ModelImageSaver, UpdateAtMixin):
    """Model for a Season."""

    episode_set: models.QuerySet[Episode]

    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    season_id = models.CharField(max_length=64)
    """Unique season identifier from the website"""
    # Some websites say things like "P1" or "S1", so this value must be stored as a CharField and a seperate value needs
    # to be stored to track the order seasons appear on a website
    # I think this was Netflix, need to have an example of this, will have to double check later
    name = models.CharField(max_length=64)
    sort_order = models.PositiveSmallIntegerField()
    number = models.PositiveSmallIntegerField()
    """The order that seasons are sorted on the original website"""
    url = models.CharField(max_length=255)
    deleted = models.BooleanField()

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        constraints = (auto_unique("show", "season_id"),)
        ordering = ("show", "sort_order")

    def __str__(self) -> str:
        """Season represented as a string."""
        return self.name

    def dump(self) -> dict[str, Any]:
        """Dump all of the information for a season as json."""
        variables = vars(self).copy()
        # State is just junk information when it comes to serialization
        variables.pop("_state")
        # Cast images to strings so they can be serialized
        variables["image"] = str(variables["image"])
        # Convert all of the datetimes to ISO format so they are able to be serialized
        variables["info_timestamp"] = self.info_timestamp.isoformat()
        variables["info_modified_timestamp"] = self.info_modified_timestamp.isoformat()

        variables["episodes"] = [episode.dump() for episode in self.episode_set.all()]

        return variables


class Episode(ModelImageSaver, UpdateAtMixin):
    """Model for an episode."""

    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    episode_id = models.CharField(max_length=64)
    name = models.CharField(max_length=500)
    url = models.CharField(max_length=255)
    # CrunchyRoll has episode numbers that sometimes include strings
    #   See Gintama Season 3: https://beta.crunchyroll.com/series/GYQ4MKDZ6/gintama
    #       Episode 136C is after episode 256
    #   Store episode number as a CharField to support these weird episode numbers
    number = models.CharField(max_length=64)
    """Episide "number" as defined on the website, is usually a number, but sometimes includes other
    characters"""
    sort_order = models.PositiveSmallIntegerField(null=True)
    """The order that episodes are sorted on the website"""
    description = models.TextField()
    release_date = models.DateTimeField()
    """The date that the episode was made available for streaming, this value is useful for determining when to update a
    series"""
    air_date = models.DateTimeField()
    """The date that the episode originally aired, this is the value that will be displayed to the user"""
    duration = models.PositiveSmallIntegerField()
    """Duration stored in number of seconds"""
    deleted = models.BooleanField()

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        constraints = (auto_unique("season", "episode_id"),)
        ordering = ("season", "sort_order")

    def __str__(self) -> str:
        """Episode represented as a string."""
        return self.name

    def is_watched(self) -> bool:
        """Check if an episode has been watched."""
        return EpisodeWatch.objects.filter(episode=self).exists()

    def watch_count(self) -> int:
        """Return the number of times an episode has been watched."""
        return EpisodeWatch.objects.filter(episode=self).count()

    def last_watched(self) -> date:
        """Get when an episode was last watched.

        Raises:
            ValueError: If the episode was never watched
        """
        if episode := EpisodeWatch.objects.filter(episode=self).last():
            return episode.watch_date

        msg = "The episode was never watched"
        raise ValueError(msg)

    def next_episode(self) -> Episode | None:
        """Get the next episode in the series or None if the current episode is the last one."""
        episodes = Episode.objects.filter(
            season__show=self.season.show,
            season__sort_order__gte=self.season.sort_order,
            sort_order__gt=self.sort_order,
        ).order_by("season__sort_order", "sort_order")
        return episodes.first()

    def dump(self) -> dict[str, Any]:
        """Dump all of the information for an episode as json."""
        variables = vars(self).copy()
        # State is just junk information when it comes to serialization
        variables.pop("_state")
        # Cast images to strings so they can be serialized
        variables["image"] = str(variables["image"])
        # Convert all of the datetimes to ISO format so they are able to be serialized
        variables["info_timestamp"] = self.info_timestamp.isoformat()
        variables["info_modified_timestamp"] = self.info_modified_timestamp.isoformat()
        variables["air_date"] = self.air_date.isoformat()
        variables["release_date"] = self.release_date.isoformat()
        return variables


class EpisodeWatch(ModelWithId):
    """Model for logging when an episode is watched."""

    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    watch_date = models.DateTimeField()

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        ordering = ("watch_date",)

    def __str__(self) -> str:
        """EpisodeWatch represented as a string."""
        return f"{self.watch_date} - {self.episode}"


class UpdateQue(ModelWithId):
    """Track when the information for an entire website was last updated.

    This is useful on website that have a calendar or a clear list of new content that can easily be scraped to
    determine when a show needs to be updated.
    """

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        constraints = (auto_unique("website"),)

    website = models.CharField(max_length=255)
    next_update_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """UpdateQue represented as a string."""
        return f"{self.website} - {self.next_update_at}"
