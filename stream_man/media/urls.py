"""URLs for the media app."""
from django.urls import path

from .views import Forms, Pages

app_name = "media"
urlpatterns = [
    # Pages
    path("", Pages.media, name="media"),
    path("show/<int:show_id>/", Pages.show, name="show"),
    path("season/<int:season_id>/", Pages.season, name="season"),
    path("episode/<int:episode_id>/", Pages.episode, name="episode"),
    path("episode_image/<int:episode_id>/<int:image_width>", Pages.episode_image, name="episode_image"),
    # Forms
    path(
        "forms/mark_episode_watched/<int:episode_id>",
        Forms.mark_episode_watched,
        name="forms/mark_episode_watched",
    ),
]
