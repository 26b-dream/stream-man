"""Django urls for the media app."""
from django.urls import path

from . import views

app_name = "media"
urlpatterns = [
    # Pages
    path("", views.media_page, name="media"),
    path("show/<int:show_id>/", views.show_page, name="show"),
    path("season/<int:season_id>/", views.season_page, name="season"),
    path("episode/<int:episode_id>/", views.episode_page, name="episode"),
    path("episode_image/<int:episode_id>/<int:image_width>", views.episode_image, name="episode_image"),
    # Forms
    path(
        "forms/mark_episode_watched/<int:episode_id>",
        views.mark_episode_watched_form,
        name="forms/mark_episode_watched",
    ),
]
