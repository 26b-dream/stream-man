import json
from datetime import datetime

from common.scrapers import InvalidURLError, Scraper
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from media.models import Episode

from .forms import (
    AddShowForm,
    Builder,
    EditPlaylistForm,
    NewPlaylistForm,
    PlaylistShow,
    PlaylistSortForm,
    RemoveShowForm,
    VisualConfigForm,
)
from .models import Playlist, PlaylistImportQueue


class Pages:
    """Views for the pages for the playlist app."""

    @staticmethod
    def playlists(request: HttpRequest) -> HttpResponse:
        """Main page for playlists, shows a list of all playlists"""
        playlists = Playlist.objects.filter(deleted=False)
        context = {"playlists": playlists}
        return render(request, "playlists/playlists.html", context)

    @staticmethod
    def playlist(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Main page for a specific playlist, shows all episodes in the playlist"""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        context = {"playlist": playlist, "request": request}
        return render(request, "playlists/playlist.html", context)


class Cards:
    """Views for the cards for the playlist app."""

    @staticmethod
    def episodes(request: HttpRequest, playlist_id: int) -> HttpResponse:
        """Episode cards that are displayed on the specific playlist page"""
        playlist = get_object_or_404(Playlist, id=playlist_id)
        form = PlaylistSortForm(request.GET)

        if form.is_valid():
            episodes = Builder(playlist.episodes(), form).sorted_episodes()

            # Because the cookie can be set to any arbitrary value it needs to be forced to be an integer
            columns = int(request.COOKIES.get(f"playlist_{playlist_id}_columns", 4))
            image_width = int(request.COOKIES.get(f"playlist_{playlist_id}_image_width", 1920))
            context = {"playlist": playlist, "episodes": episodes, "columns": columns, "image_width": image_width}

            return render(request, "playlists/cards/episodes.html", context)

        return HttpResponse("Error: Unable to get list of episodes for playlist because the form was invalid")

    @staticmethod
    def playlists(request: HttpRequest) -> HttpResponse:
        """Playlist cards that will be displayed on the playlists page"""
        playlists = Playlist.objects.filter(deleted=False)
        context = {"playlists": playlists}
        return render(request, "playlists/cards/playlists.html", context)


class Forms:
    class PlaylistFilter:
        @staticmethod
        def form(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = PlaylistSortForm(request.GET)
            context = {"playlist": playlist, "form": form}
            return render(request, "playlists/forms/filter_episodes.html", context)

        @staticmethod
        def set_defaults(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = PlaylistSortForm(request.POST)
            context = {"playlist": playlist, "form": form}

            if form.is_valid():
                # Convert the playlist object to an integer so it can be serialized to json
                default_filter = form.cleaned_data
                default_filter["playlist"] = form.cleaned_data["playlist"].id

                # Don't allow blank values for websites because it can cause errors when trying to load the default
                # values
                if not default_filter["websites"]:
                    default_filter.pop("websites")

                playlist.default_filter = json.dumps(default_filter)
                playlist.save()
                messages.success(request, "Default playlist filters saved")
                return render(request, "playlists/forms/filter_episodes.html", context)

            # Manage invalid form
            messages.error(request, "Invalid Form: Unable to save default playlist filters")
            return render(request, "playlists/forms/filter_episodes.html", context)

        @staticmethod
        def submit(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = PlaylistSortForm(request.POST)
            context = {"playlist": playlist, "form": form}

            if form.is_valid():
                messages.success(request, "Episodes filtered")
                response = render(request, "playlists/forms/filter_episodes.html", context)
                response["HX-Trigger"] = "refreshEpisodes"
                return response

            # Manage invalid form
            messages.error(request, "Invalid Form: Unable to filter episodes")
            return render(request, "playlists/forms/filter_episodes.html", context)

    class NewPlaylist:
        @staticmethod
        def form(request: HttpRequest) -> HttpResponse:
            form = NewPlaylistForm()
            context = {"form": form}
            return render(request, "playlists/forms/new_playlist.html", context)

        @staticmethod
        def submit(request: HttpRequest) -> HttpResponse:
            """Form for creating a new playlist"""
            form = NewPlaylistForm(request.POST)
            context = {"form": form}
            # Form will only be valid when the submit button is clicked
            if form.is_valid():
                existing_playlists = Playlist.objects.filter(name=form.cleaned_data["name"]).first()

                # If this playlist already exists and is visible just display an error
                if existing_playlists:
                    messages.error(request, "Playlist with this name already exists")
                    return render(request, "playlists/forms/new_playlist.html", context)

                # If neither of the above checks where true create a new playlist using the specified name
                form.save()
                messages.success(request, "Playlist created")
                response = render(request, "playlists/forms/new_playlist.html", context)
                response["HX-Trigger"] = "refreshPlaylists"
                return response

            # Manage invalid form
            messages.error(request, "Invalid Form: Unable to create playlist")
            return render(request, "playlists/forms/new_playlist.html", context)

    class EditPlaylist:
        @staticmethod
        def form(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = EditPlaylistForm(instance=playlist)
            context = {"playlist": playlist, "form": form}
            return render(request, "playlists/forms/edit_playlist.html", context)

        @staticmethod
        def submit(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = EditPlaylistForm(request.POST, instance=playlist)
            context = {"playlist": playlist, "form": form}

            if form.is_valid():
                if form.cleaned_data.get("deleted"):
                    # Soft delete a playlist by appending the timestamp just in case the user wants to restore it
                    # because it was deleted accidentally
                    form.cleaned_data["name"] += f" {datetime.now().timestamp()}"
                    form.save()
                    messages.success(request, "Deleted playlist")
                else:
                    form.save()
                    messages.success(request, "Updated playlist")

                # When the form is valid the playlists should be refresh so the changes are immediately visible
                response = render(request, "playlists/forms/edit_playlist.html", context)
                response["HX-Trigger"] = "refreshPlaylists"
                return response

            # Manage invalid form
            messages.error(request, "Invalid Form: Unable to update playlist")
            return render(request, "playlists/forms/edit_playlist.html", context)

    class VisualConfig:
        @staticmethod
        def form(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            columns = request.COOKIES.get(f"playlist_{playlist_id}_columns", 4)
            image_width = request.COOKIES.get(f"playlist_{playlist_id}_image_width", 1920)
            form = VisualConfigForm(initial={"columns": columns, "image_width": image_width})
            context = {"playlist": playlist, "form": form}
            return render(request, "playlists/forms/visual_config.html", context)

        @staticmethod
        def submit(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = VisualConfigForm(request.POST)
            context = {"playlist": playlist, "form": form}

            if form.is_valid():
                columns = form.cleaned_data["columns"]
                image_width = form.cleaned_data["image_width"]
                response = render(request, "playlists/forms/visual_config.html", context)
                response.set_cookie(f"playlist_{playlist_id}_columns", columns)
                response.set_cookie(f"playlist_{playlist_id}_image_width", image_width)
                messages.success(request, "Visual configuration updated")
                return response

            # Manage invalid form
            messages.error(request, "Invalid Form: Unable to update visual configuration form")
            return render(request, "playlists/forms/visual_config.html", context)

    class AddShow:
        @staticmethod
        def form(request: HttpRequest, playlist_id: int) -> HttpResponse:
            urls = PlaylistImportQueue.objects.filter(playlist=playlist_id)
            urls_string = "\n".join([url.url for url in urls])
            form = AddShowForm(initial={"urls": urls_string})
            playlist = Playlist.objects.filter(id=playlist_id)[0]
            context = {"form": form, "playlist": playlist}
            return render(request, "playlists/forms/add_show.html", context)

        @staticmethod
        @transaction.atomic
        def submit(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = AddShowForm(request.POST)
            context = {"form": form, "playlist": playlist}

            if form.is_valid():
                # Delete all of the old entries because they are going to be replaced with the new ones
                PlaylistImportQueue.objects.filter(playlist=playlist).delete()

                urls = form.cleaned_data["urls"].split("\n")  # Treat each line as a separate URL
                urls = [url for url in urls if url != ""]  # Remove blank URLs
                urls = list(set(urls))  # Remove duplicate urls

                url_html_list = ""
                for url in urls:
                    PlaylistImportQueue.objects.create(url=url, playlist=playlist)
                    try:
                        scraper = Scraper(url)
                        url_html_list += f"""  <ul class="list-group list-group-horizontal">
                                            <li class="list-group-item">{escape(scraper.website_name())}</li>
                                            <li class="list-group-item">{escape(url)}</li></ul>"""
                    except InvalidURLError:
                        url_html_list += f"""  <ul class="list-group list-group-horizontal">
                                            <li class="list-group-item text-danger">Invalid</li>
                                            <li class="list-group-item">{escape(url)}</li></ul>"""

                messages.success(request, "Added URLs", extra_tags=mark_safe(url_html_list))
                return render(request, "playlists/forms/add_show.html", context)

            messages.success(request, "Invalid Form: Unable to add URLs", extra_tags=mark_safe(url_html_list))
            return render(request, "playlists/forms/add_show.html", context)

    class RemoveShow:
        @staticmethod
        def form(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = RemoveShowForm({"playlist_id": playlist_id})
            context = {"playlist": playlist, "form": form}
            return render(request, "playlists/forms/remove_show.html", context)

        @staticmethod
        def submit(request: HttpRequest, playlist_id: int) -> HttpResponse:
            playlist = get_object_or_404(Playlist, id=playlist_id)
            form = RemoveShowForm(request.POST)
            context = {"playlist": playlist, "form": form}

            if form.is_valid():
                shows = form.cleaned_data["remove_show"]

                # Delete all of these shows from PlaylistShow
                for show in shows:
                    PlaylistShow.objects.filter(playlist=playlist, show=show).delete()
                    messages.success(request, "Removed shows from playlist")
                response = render(request, "playlists/forms/remove_show.html", context)
                response["HX-Trigger"] = "refreshEpisodes"
                return response

            return render(request, "playlists/forms/remove_show.html", context)


def episode_info_footer(request: HttpRequest, episode_id: int) -> HttpResponse:
    episode = get_object_or_404(Episode, id=episode_id)
    content = {"episode": episode}
    return render(request, "playlists/episode_info_footer.html", content)
