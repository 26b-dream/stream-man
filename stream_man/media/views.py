"""Django views for the media app."""
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from paved_path import PavedPath

# sorl doesn't have type hints so this has an error
from sorl.thumbnail import get_thumbnail  # type: ignore  # noqa: PGH003

from stream_man.settings import MEDIA_ROOT

from .forms import MarkEpisodeWatchedForm
from .models import Episode, EpisodeWatch, Season, Show


def media_page(request: HttpRequest) -> HttpResponse:
    # TODO: Not yet implemented
    """Index page for all of the media."""
    return render(request, "media/index.html", {})


def show_page(request: HttpRequest, show_id: int) -> HttpResponse:
    # TODO: Not yet implemented
    """Index page for a show."""
    show = Show.objects.get(id=show_id)
    context = {"show": show}
    return render(request, "media/index.html", context)


def season_page(request: HttpRequest, season_id: int) -> HttpResponse:
    # TODO: Not yet implemented
    """Index page for a season."""
    season = Season.objects.get(id=season_id)
    context = {"season": season}
    return render(request, "media/index.html", context)


def episode_page(request: HttpRequest, episode_id: int) -> HttpResponse:
    # TODO: Not yet implemented
    """Index page for an episode."""
    episode = Episode.objects.get(id=episode_id)
    context = {"episode": episode}
    return render(request, "media/index.html", context)


def episode_image(_request: HttpRequest, episode_id: int, image_width: int) -> HttpResponse:
    # TODO: This can probably be improved
    """Return an episode image."""
    episode = Episode.objects.get(id=episode_id)
    image = str(get_thumbnail(episode.image, f"{image_width}", quality=100))
    image_path = PavedPath(MEDIA_ROOT / image)
    return HttpResponse(image_path.read_bytes(), content_type="image/jpeg")


@transaction.atomic
def mark_episode_watched_form(request: HttpRequest, episode_id: int) -> HttpResponse:
    """Form for marking an episode as watched."""
    episode = get_object_or_404(Episode, id=episode_id)
    form = MarkEpisodeWatchedForm(request.POST)

    if form.is_valid():
        # The entry must be deleted before the form is checked for validity to make sure the form doesn't return an
        # error because the entry already exists, this also does the work of deleting old entries
        EpisodeWatch.objects.filter(episode_id=form.data["episode"], watch_date=form.data["watch_date"]).delete()

        if not form.cleaned_data["deleted"]:
            form.save()

    content = {"form": form, "episode": episode}
    return render(request, "media/forms/mark_episode_watched_form.html", content)
