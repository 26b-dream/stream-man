"""Builder class used to filter and sort episodes in a playlist"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import TYPE_CHECKING

from media.models import Show

if TYPE_CHECKING:
    from typing import Any, Callable

    from django.db.models.query import QuerySet
    from media.models import Episode

    from .forms import PlaylistSortForm


class Builder:
    """Class used to filter and sort episodes in a playlist"""

    def show_order_function(self) -> Callable[[list[tuple[Show, list[Episode]]]], None]:
        """Get the function from the form or the initial value"""
        return getattr(Builder.ShowOrder, self.form.cleaned_data["show_order"])

    def episode_order_function(self) -> Callable[[QuerySet[Episode]], QuerySet[Episode]]:
        """Get the function from the form or the initial value"""
        return getattr(Builder.EpisodeOrder, self.form.cleaned_data["episode_order"])

    def change_show_function(self) -> Callable[[list[tuple[Show, list[Episode]]]], bool]:
        """Get the function from the form or the initial value"""
        return getattr(Builder.ChangeShowIf, self.form.cleaned_data["change_show"])

    def rotate_function(self) -> Callable[[list[tuple[Show, list[Episode]]]], None]:
        """Get the function from the form or the initial value"""
        return getattr(Builder.Rotate, self.form.cleaned_data["rotate_type"])

    def __init__(self, episodes: QuerySet[Episode], form: PlaylistSortForm):
        self.episodes = episodes
        self.form = form

    def _filter_and_sort_episodes(self) -> None:
        """Filter out the episodes and get only the ones that will be returned for the playlist"""

        # Loop through all the episode filters that are active and apply them
        for function_name in self.form.cleaned_data["filter"]:
            self.episodes = getattr(Builder.Filter, function_name)(self.episodes)

        # TODO: Test this and make sure it still works this is old code and the code around it has been changed quite a
        # bit
        if self.form.cleaned_data.get("websites"):
            websites = list(self.form.cleaned_data["websites"])
            self.episodes = self.episodes.filter(season__show__website__in=websites)

        self.episodes = self.episode_order_function()(self.episodes)
        if "episodes" in self.form.cleaned_data.get("reverse", []):
            self.episodes = self.episodes.reverse()

    def _group_episodes_by_show(self) -> list[tuple[Show, list[Episode]]]:
        """Sort episodes by show to make it easier to perform sorting based on the show"""

        grouped_episodes_dict: defaultdict[Show, list[Episode]] = defaultdict(list)

        # When the show order is set to none dump all the episodes into a random show object, if all episodes belong to
        # one show it should be functionally the same as having no show filters.
        if self.show_order_function().__name__ == "none":
            show = Show.objects.first()
            for episode in self.episodes:
                grouped_episodes_dict[show].append(episode)
        else:
            for episode in self.episodes:
                show = episode.season.show
                grouped_episodes_dict[show].append(episode)

        return list(grouped_episodes_dict.items())

    def _sort_by_show(self, grouped_episodes: list[tuple[Show, list[Episode]]]) -> list[tuple[Show, list[Episode]]]:
        # Sort the shows
        self.form.show_order_function()(grouped_episodes)

        # Reverse shows if needed
        if "shows" in self.form.cleaned_data.get("reverse", []):
            grouped_episodes.reverse()

        return grouped_episodes

    def _compile_episodes(self, sorted_grouped_episodes: list[tuple[Show, list[Episode]]]) -> list[Episode]:
        # Determine the number of episodes to add to the playlist, should be whicehver value is smaller between the
        # number of episodes that where filtered and the number in the form
        number_of_episodes_to_add_to_playlist = min(len(self.episodes), self.form.cleaned_data["number_of_episodes"])

        # THis could be done using list comprehension but it becomes impossible to read
        episode_output: list[Episode] = []
        for _ in range(number_of_episodes_to_add_to_playlist):
            # Get all of the episodes for the first show
            show_episodes = sorted_grouped_episodes[0][1]
            # Add the first episode to the sorted_episodes list
            episode_output.append(show_episodes.pop(0))
            # If all the episodes are used up from a show, remove the show from the list
            if not show_episodes:
                sorted_grouped_episodes.pop(0)
            # Check when the next show should be used instead of the current one
            elif self.change_show_function()(sorted_grouped_episodes):
                self.rotate_function()(sorted_grouped_episodes)

        return episode_output

    def sorted_episodes(self) -> list[Episode] | QuerySet[Episode]:
        """Get the sorted episodes for the playlist"""

        # Find all of the episodes that will be used
        self._filter_and_sort_episodes()

        # Sort the episodes and group them by show
        grouped_episodes = self._group_episodes_by_show()
        sorted_grouped_episodes = self._sort_by_show(grouped_episodes)

        return self._compile_episodes(sorted_grouped_episodes)

    class Filter:
        """Functions used to filter episodes"""

        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def only_new_episodes(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            """Filter out episodes that have already been watched"""
            return episodes.filter(episodewatch__isnull=True)

        @classmethod
        def only_started_shows(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            """Filter out episodes that belong to shows"""
            shows = Show.objects.filter(season__episode__episodewatch__isnull=False).distinct()
            return episodes.filter(season__show__in=shows)

        @classmethod
        def only_new_shows(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            """Filter out shows that have at least one episode watched"""
            shows = Show.objects.filter(season__episode__episodewatch__isnull=False).distinct()
            return episodes.exclude(season__show__in=shows)

    class ShowOrder:
        """Functions used to sort shows"""

        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def shuffle(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Randomly sort the shows"""
            random.shuffle(grouped_episodes)

        # TODO: This is is probably slow, can be easily sped up,
        # TODO: Need to create a large playlist for benchmarking this function to improve it
        @classmethod
        def weighted_shuffle(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Shuffle the shows, but weight the shuffle based on the number of episodes for each show in the playlist"""

            # Stick all episodes in one list
            all_episodes: list[Episode] = [episode for _, episodes in grouped_episodes for episode in episodes]

            while all_episodes:
                random_episode = random.choice(all_episodes)

                # Remove all episodes from all_episodes that are from the same show
                all_episodes = [
                    episode for episode in all_episodes if episode.season.show != random_episode.season.show
                ]

                for show, episodes in grouped_episodes:
                    if random_episode.season.show == show:
                        grouped_episodes.insert(0, grouped_episodes.pop(grouped_episodes.index((show, episodes))))
            grouped_episodes.reverse()

        @classmethod
        def none(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Function that does nothing, but exists so it can be chosen on the form"""

        @classmethod
        def least_recently_watched(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Sort the shows by the date of the last episode watched"""
            grouped_episodes.sort(key=lambda episode: episode[0].last_watched_date())

        @classmethod
        def newest_episodes_first(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Sort the shows by the date of the newest episode"""
            grouped_episodes.sort(key=lambda episode: episode[0].newest_episode_date(), reverse=True)

        @classmethod
        def finish_up_duration(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Sort the shows by the duration of the episodes that have not been watched"""
            grouped_episodes.sort(key=lambda show: sum(episode.duration for episode in show[1]))

        @classmethod
        def finish_up_episodes(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Sort the shows by the number of episodes that have not been watched"""
            grouped_episodes.sort(key=lambda show: len(show[1]))

    class EpisodeOrder:
        """Functions used to set the episode order"""

        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def random(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            """Randomly sort the episodes"""
            return episodes.order_by("?")

        @classmethod
        def chronological(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            """Sort the episodes chronilogically"""
            return episodes.order_by("season__sort_order", "sort_order")

        @classmethod
        def newest_first(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            """Sort the episodes by the airing date"""
            return episodes.order_by("release_date").reverse()

    class ChangeShowIf:
        """Functions used to determine when to change the show"""

        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def after_every_episode(cls, **kwargs: Any) -> bool:
            """Change the show after every episode"""
            return True

        @classmethod
        def when_show_is_complete(cls, **kwargs: Any) -> bool:
            """Change the show when all of the episodes have been added to the playlist"""
            return False

    class Rotate:
        """Functions used to rotate the shows"""

        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def rotate(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Rotate the shows"""
            grouped_episodes.append(grouped_episodes.pop(0))

        @classmethod
        def shuffle(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Shuffle the shows"""
            random.shuffle(grouped_episodes)

        # TODO: This is is probably slow, can be easily sped up,
        # TODO: Need to create a large playlist for benchmarking this function to improve it
        @classmethod
        def weighted_shuffle(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            """Shuffle the shows, but weight the shuffle based on the number of episodes for each show in the playlist"""

            # Stick all episodes in one list
            all_episodes: list[Episode] = [episode for _, episodes in grouped_episodes for episode in episodes]

            random_episode = random.choice(all_episodes)

            for show, episodes in grouped_episodes:
                if random_episode.season.show == show:
                    grouped_episodes.insert(0, grouped_episodes.pop(grouped_episodes.index((show, episodes))))


# Compile all of the builder options into the class variables
for x in [Builder.ShowOrder, Builder.Rotate, Builder.ChangeShowIf, Builder.EpisodeOrder, Builder.Filter]:
    for method in [method for method in dir(x) if method.startswith("_") is False]:
        if method != "acceptable_functions":
            x.acceptable_functions.append((method, method.replace("_", " ").title()))
