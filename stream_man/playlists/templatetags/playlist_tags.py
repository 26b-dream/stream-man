import json
from datetime import date

from django import template
from django.http import HttpRequest
from django.urls import reverse
from media.forms import MarkEpisodeWatchedForm
from media.models import Episode  # For some reason putting this under TYPE_CHECKING causes an error
from playlists.forms import PlaylistSortForm
from playlists.models import Playlist

register = template.Library()


@register.filter
def mark_episode_watched(episode: Episode) -> MarkEpisodeWatchedForm:
    """Make a form that can be used to mark an episode as watched"""
    return MarkEpisodeWatchedForm(initial={"episode": episode, "watch_date": date.today().strftime("%Y-%m-%d")})


@register.simple_tag()
def divide(numerator: float | str, denominator: float | str) -> float:
    """Divide x by y and return the result"""
    return float(numerator) / float(denominator)


@register.simple_tag()
def playlist_filter_json(playlist: Playlist) -> str:
    """Converts the default playlist filter into a JSON string if it is valid, otherwise it returns the initial
    values"""

    # Invalid JSON can be saved to the database so extra checks need to be done to make sure the default filter in the
    # database is valid
    try:
        filter_json = json.loads(playlist.default_filter)
    # If you go into the admin screen and manually clear the value as a way to reset the default filter a TypeError will
    # occur
    except TypeError:
        filter_json = {}
    form = PlaylistSortForm(filter_json)

    # If the default filter saved in the database is invalid use the initial values instead
    if not form.is_valid():
        filter_json = PlaylistSortForm.initial_values()
        filter_json["playlist"] = playlist.id

    return json.dumps(filter_json)


@register.simple_tag()
def playlist_card_url_1_params(request: HttpRequest, playlist: Playlist) -> str:
    """Function that returns the parameters for the URL that will be opened on the first click on a playlist card"""
    return json.dumps(
        [
            "GET",
            reverse("playlists:forms/edit_playlist/form", kwargs={"playlist_id": playlist.id}),
            {
                "values": {"playlist": playlist.id},
                "target": "#htmx-footer",
                "swap": "innerHTML",
            },
        ]
    )


@register.simple_tag()
def playlist_card_url_2_params(request: HttpRequest, playlist: Playlist) -> str:
    """Function that returns the parameters for the URL that will be opened on the second click on a playlist card"""
    return json.dumps([reverse("playlists:playlist", kwargs={"playlist_id": playlist.id}), "_self"])


@register.simple_tag()
def episode_card_url_1_params(request: HttpRequest, episode: Episode) -> str:
    """Function that returns the parameters for the URL that will be opened on the first click on a episode card"""
    return json.dumps(
        [
            "POST",
            reverse("playlists:episode_info_footer", kwargs={"episode_id": episode.id}),
            {
                "values": {"csrfmiddlewaretoken": request.META.get("CSRF_COOKIE"), "playlist": episode.id},
                "target": "#htmx-footer",
                "swap": "innerHTML",
            },
        ]
    )


@register.simple_tag()
def episode_card_url_2_params(request: HttpRequest, episode: Episode) -> str:
    """Function that returns the parameters for the URL that will be opened on the second click on a episode card"""
    return json.dumps([episode.url, "_self"])


@register.filter()
def seconds_to_time(seconds: int) -> str:
    """Take a time as an integer and return it as a string in the format HH:MM:SS"""
    return (
        str(int(seconds / 3600)).zfill(2)
        + ":"
        + str(int(seconds / 60) % 60).zfill(2)
        + ":"
        + str(seconds % 60).zfill(2)
    )
