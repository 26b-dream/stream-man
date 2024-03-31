"""Views for the playlist app."""
from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from common.get_scraper import GetScraper, InvalidURLError
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from media.models import Episode

from .forms import (
    AddShowForm,
    Builder,
    EditPlaylistForm,
    NewPlaylistForm,
    PlaylistFilterForm,
    PlaylistShow,
    RemoveShowForm,
    VisualConfigForm,
)
from .models import Playlist, PlaylistImportQueue

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


def columns_from_cookies(request: HttpRequest, playlist_id: int) -> int:
    """Get the number of columns from the cookies. If the cookie is not a valid number, return 4."""
    try:
        columns = int(request.COOKIES.get(f"playlist-{playlist_id}-columns", 4))
    except ValueError:
        columns = 4
    return columns


def image_width_from_cookies(request: HttpRequest, playlist_id: int) -> int:
    """Get the image width from the cookies. If the cookie is not a valid number, return 1920."""
    try:
        image_width = int(request.COOKIES.get(f"playlist-{playlist_id}-image-width", 1920))
    except ValueError:
        image_width = 1920
    return image_width


class Pages:
    """Views for the pages for the playlist app."""

    @staticmethod
    def playlists(request: HttpRequest) -> HttpResponse:
        """Main page for playlists, shows a list of all playlists."""
        playlists = Playlist.objects.filter(deleted=False)
        context = {"playlists": playlists}
        return render(request, "playlists/playlists.html", context)

    @staticmethod
    def playlist(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Main page for a specific playlist, shows all episodes in the playlist."""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        columns = columns_from_cookies(request, playlist_id)
        image_width = image_width_from_cookies(request, playlist_id)
        context = {"playlist": playlist, "request": request, "columns": columns, "image_width": image_width}
        return render(request, "playlists/playlist.html", context)


class Cards:
    """Views for the cards for the playlist app."""

    @staticmethod
    def episodes(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Episode cards that are displayed on the specific playlist page."""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        filter_string = request.COOKIES.get(f"episode-filter-{playlist_id}", "{}")
        filter_dict = json.loads(filter_string)
        filter_dict["playlist"] = playlist
        form = PlaylistFilterForm(filter_dict)
        episodes = playlist.episodes() if not form.is_valid() else Builder(playlist.episodes(), form).sorted_episodes()
        columns = columns_from_cookies(request, playlist_id)
        image_width = image_width_from_cookies(request, playlist_id)
        context = {"playlist": playlist, "episodes": episodes, "columns": columns, "image_width": image_width}

        return render(request, "playlists/cards/episodes.html", context)

    @staticmethod
    def playlists(request: HttpRequest) -> HttpResponse:
        """Playlist cards that will be displayed on the playlists page."""
        playlists = Playlist.objects.filter(deleted=False)
        context = {"playlists": playlists}
        response = render(request, "playlists/cards/playlists.html", context)
        response["HX-Trigger"] = "playlistsRefreshed"
        return response


class Forms:
    """Views for the forms for the playlist app."""

    @staticmethod
    def playlist_filter(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Form to filter the episodes of the playlist that are shwon."""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        filter_string = request.COOKIES.get(f"episode-filter-{playlist_id}", "{}")
        filter_dict = json.loads(filter_string)
        filter_dict["playlist"] = playlist

        form = PlaylistFilterForm(filter_dict)
        if not form.is_valid():
            form = PlaylistFilterForm()
        context = {"playlist": playlist, "form": form}
        return render(request, "playlists/forms/filter_episodes.html", context)

    @staticmethod
    def new_playlist_form(request: HttpRequest) -> HttpResponse:
        """Form for creating a new playlist."""
        existing_playlists = None
        form = NewPlaylistForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            existing_playlists = Playlist.objects.filter(name=form.cleaned_data["name"]).first()
            if not existing_playlists:
                # Add a note on the form error that says it is added
                form.save()
                form.add_error(None, "Playlist added")

        context = {"form": form}
        response = render(request, "playlists/forms/new_playlist.html", context)
        response["HX-Trigger"] = "refreshPlaylists"
        return response

    @staticmethod
    def edit_playlist_form(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Form to edit a playlist."""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        form = EditPlaylistForm(request.POST or None, instance=playlist)
        context = {"playlist": playlist, "form": form}

        if form.is_valid():
            if form.cleaned_data.get("deleted"):
                # When soft deleting a playlist also appent the current timestamp. This makes it so a new placelist
                # of the same name can be made, but keeps the old one in a soft deleted state that is easy to
                # restore
                form.cleaned_data["name"] += str(datetime.now().astimezone().timestamp())
            form.save()
            form.add_error(None, "Playlist updated")

        # When the form is valid the playlists should be refresh so the changes are immediately visible
        response = render(request, "playlists/forms/edit_playlist.html", context)
        response["HX-Trigger"] = "refreshPlaylists"
        return response

    @staticmethod
    def visual_config_form(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Form to change the visuals of a playlist."""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        form = VisualConfigForm(request.POST)
        columns = columns_from_cookies(request, playlist_id)
        image_width = image_width_from_cookies(request, playlist_id)
        context = {"playlist": playlist, "form": form, "columns": columns, "image_width": image_width}
        return render(request, "playlists/forms/visual_config.html", context)

    @staticmethod
    @transaction.atomic
    def add_show_form(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Form to add a show to a playlist."""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        urls_in_queue = PlaylistImportQueue.objects.filter(playlist=playlist_id)
        initial_urls = "\n".join([url.url for url in urls_in_queue])
        form = AddShowForm(request.POST or None, initial={"urls": initial_urls})
        context = {"form": form, "playlist": playlist}

        if request.POST and form.is_valid():
            # Delete all of the old entries because they are going to be replaced with the new ones
            PlaylistImportQueue.objects.filter(playlist=playlist).delete()

            urls = form.cleaned_data["urls"].split("\n")  # Treat each line as a separate URL
            urls = [url for url in urls if url]  # Remove blank URLs
            urls = list(set(urls))  # Remove duplicate urls

            for url in urls:
                PlaylistImportQueue.objects.create(url=url, playlist=playlist)
                try:
                    scraper = GetScraper(url)
                    form.add_error(None, f"{scraper.__class__}: {url}")
                except InvalidURLError:
                    form.add_error(None, mark_safe(f"<b>Error</b>: {escape(url)}"))  # noqa: S308 - It's fine

        return render(request, "playlists/forms/add_show.html", context)

    @staticmethod
    def remove_show_form(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Form to remove a show from a playlist."""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        form = RemoveShowForm(request.POST or {"playlist_id": playlist_id})
        context = {"playlist": playlist, "form": form}

        if form.is_valid():
            # Delete all of these shows from PlaylistShow
            for show in form.cleaned_data["remove_show"]:
                PlaylistShow.objects.filter(playlist=playlist, show=show).delete()
                form.add_error(None, f"Removed {show.pretty_html_name()}")

            # Response must be rendered after shows are removed
            response = render(request, "playlists/forms/remove_show.html", context)
            response["HX-Trigger"] = "refreshEpisodes"
            return response

        return render(request, "playlists/forms/remove_show.html", context)


def episode_info_footer(request: HttpRequest, episode_id: int) -> HttpResponse:
    """Show the episode info in a footer."""
    episode = get_object_or_404(Episode, id=episode_id)
    content = {"episode": episode}
    return render(request, "playlists/episode_info_footer.html", content)
