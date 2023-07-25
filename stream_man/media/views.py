"""Views for the media app."""
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from extended_path import ExtendedPath
from sorl.thumbnail import get_thumbnail

from stream_man.settings import MEDIA_ROOT

from .forms import MarkEpisodeWatchedForm
from .models import Episode, EpisodeWatch, Season, Show


class Pages:
    """Views for the pages for the media app."""

    @staticmethod
    def media(request: HttpRequest):
        """Index page for all of the media."""
        context = {}
        return render(request, "media/index.html", context)

    @staticmethod
    def show(request: HttpRequest, show_id: int):
        """Index page for a show."""
        show = Show.objects.get(id=show_id)
        context = {"show": show}
        return render(request, "media/index.html", context)

    @staticmethod
    def season(request: HttpRequest, season_id: int):
        """Index page for a season."""
        season = Season.objects.get(id=season_id)
        context = {"season": season}
        return render(request, "media/index.html", context)

    @staticmethod
    def episode(request: HttpRequest, episode_id: int):
        """Index page for an episode."""
        episode = Episode.objects.get(id=episode_id)
        context = {"episode": episode}
        return render(request, "media/index.html", context)

    @staticmethod
    def episode_image(request: HttpRequest, episode_id: int, image_width: int):
        """Index page for an episode."""
        episode = Episode.objects.get(id=episode_id)
        image = str(get_thumbnail(episode.image, f"{image_width}", quality=100))
        asd = ExtendedPath(MEDIA_ROOT / image)
        response = HttpResponse(asd.read_bytes(), content_type="image/jpeg")

        return response


class Forms:
    """Views for the forms for the media app."""

    @staticmethod
    @transaction.atomic
    def mark_episode_watched(request: HttpRequest, episode_id: int):
        """Form for marking an episode as watched."""
        episode = get_object_or_404(Episode, id=episode_id)
        form = MarkEpisodeWatchedForm(request.POST)

        # The episode must be deleted before the form is checked for validity to make sure the form doesn't return an error
        # because the entry already exists
        EpisodeWatch.objects.filter(episode_id=form.data["episode"], watch_date=form.data["watch_date"]).delete()

        if form.is_valid() and not form.cleaned_data["deleted"]:
            form.save()

        content = {"form": form, "episode": episode}
        return render(request, "media/forms/mark_episode_watched.html", content)
