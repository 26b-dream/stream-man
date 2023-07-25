"""Models for the media app"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

from common.constants import BASE_DIR
from django.db import models
from django_model_helpers import GetOrNew, ModelWithIdAndTimestamp, auto_unique


class Show(ModelWithIdAndTimestamp, GetOrNew):
    """Model that stores information for a show"""

    season_set: models.QuerySet[Season]

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        ordering = ["name"]

        constraints = [auto_unique("website", "show_id")]

    website = models.CharField(max_length=255)
    show_id = models.CharField(max_length=255)
    """Unique show identifier from the website"""
    name = models.CharField(max_length=256)
    # Sometimes media types are not specified, or movies and TV shows will be mixed together
    #   Crunchyroll mixese movies and TV shows together
    media_type = models.CharField(max_length=256, blank=True)
    description = models.TextField()
    image = models.ImageField(upload_to="images", null=True, blank=True)
    url = models.CharField(max_length=255)
    favicon_url = models.CharField(max_length=255)
    # Null is allowed because you often need to import the Show before the episodes, but update_at is calculated based
    # on episode information
    update_at = models.DateTimeField(null=True, blank=True)
    deleted = models.BooleanField()

    def __str__(self) -> str:
        return self.name

    def last_watched_date(self) -> date:
        """Date that an episode was last watched"""
        episode_info = EpisodeWatch.objects.filter(episode=self).order_by("watch_date").last()
        if episode_info:
            return episode_info.watch_date
        else:
            return date.fromtimestamp(0)

    def newest_episode_date(self) -> date:
        """Release date of the newest episode"""
        if episode := Episode.objects.filter(season__show=self).order_by("release_date").last():
            return episode.release_date
        else:
            return date.fromtimestamp(0)

    def dump(self) -> dict[str, Any]:
        """Dump all of the information for a show as json"""
        variables = vars(self).copy()
        # State is just junk information when it comes to serialization
        variables.pop("_state")
        # Cast images to strings so they can be serialized
        variables["image"] = str(variables["image"])
        # Convert all of the datetimes to ISO format so they are able to be serialized
        variables["info_timestamp"] = self.info_timestamp.isoformat()
        variables["info_modified_timestamp"] = self.info_modified_timestamp.isoformat()
        variables["update_at"] = self.update_at.isoformat() if self.update_at else None

        variables["seasons"] = [season.dump() for season in self.season_set.all()]

        return variables


class Season(ModelWithIdAndTimestamp, GetOrNew):
    """Model that stores information for a season of a show"""

    episode_set: models.QuerySet[Episode]

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        constraints = [auto_unique("show", "season_id")]
        ordering = ["show", "sort_order"]

    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    season_id = models.CharField(max_length=64)
    """Unique season identifier from the website"""
    # Some websites say things like "P1" or "S1", so this value must be stored as a CharField and a seperate value needs
    # to be stored to track the order seasons appear on a website
    # TODO: I think this was Netflix, need to have an example of this
    name = models.CharField(max_length=64)
    sort_order = models.PositiveSmallIntegerField()
    number = models.PositiveSmallIntegerField()
    """The order that seasons are sorted on the original website"""
    image = models.ImageField(upload_to="images", null=True, blank=True)
    url = models.CharField(max_length=255)
    deleted = models.BooleanField()

    def __str__(self) -> str:
        return self.name

    def dump(self) -> dict[str, Any]:
        """Dump all of the information for a show as json"""
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


class Episode(ModelWithIdAndTimestamp, GetOrNew):
    """Model that stores information for an episode of a season of a show on"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        constraints = [auto_unique("season", "episode_id")]
        ordering = ["season", "sort_order"]

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
    image = models.ImageField(upload_to="images", null=True, blank=True)
    description = models.TextField()
    release_date = models.DateTimeField()
    """The date that the episode was made available for streaming, this value is useful for determining when to update a
    series"""
    air_date = models.DateTimeField()
    """THe date that the episode originally aired, this is the value that will be displayed to the user"""
    duration = models.PositiveSmallIntegerField()
    """Duration stored in number of seconds"""
    deleted = models.BooleanField()

    def __str__(self) -> str:
        return self.name

    def is_watched(self) -> bool:
        """Check if an episode has been watched"""
        return EpisodeWatch.objects.filter(episode=self).exists()

    def watch_count(self) -> int:
        """The number of times an episode has been watched"""
        return EpisodeWatch.objects.filter(episode=self).count()

    def last_watched(self) -> date:
        """Wehn an episode was last watched"""
        return EpisodeWatch.objects.filter(episode=self).last().watch_date

    def next_episode(self) -> Optional[Episode]:
        """The episode that is after this one chronologicaly"""
        episodes = Episode.objects.filter(
            season__show=self.season.show,
            season__sort_order__gte=self.season.sort_order,
            sort_order__gt=self.sort_order,
        ).order_by("season__sort_order", "sort_order")
        return episodes.first()

    def dump(self) -> dict[str, Any]:
        """Dump all of the information for a show as json"""
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


class EpisodeWatch(models.Model):
    """Model that tracks every time an episode is watched"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        # Technically you can watch an episode more than once in a single day
        # It's far more likely to accidently mark an episode as watched twice in the same day
        # Adding a unique constraint here will avoid the possibility of accidently double-watching an episode
        constraints = [auto_unique("episode", "watch_date")]

        ordering = ["watch_date"]

    id = models.AutoField(primary_key=True)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    watch_date = models.DateField()

    def __str__(self) -> str:
        return f"{self.watch_date} - {self.episode}"


class UpdateQue(models.Model):
    """Some websites have a calendar that can be used for updating show information

    This model will track when the calendar was last used to update information"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        constraints = [auto_unique("website")]

    id = models.AutoField(primary_key=True)
    website = models.CharField(max_length=256)
    next_update_at = models.DateTimeField(auto_now_add=True)
