"""URLs for the media app."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.media_index, name="media_index"),
    path("show_index/<int:show_id>/", views.show_index, name="show_index"),
    path("season_index/<int:season_id>/", views.season_index, name="season_index"),
    path("episode_index/<int:episode_id>/", views.episode_index, name="episode_index"),
    path("mark_episode_watched_form/", views.mark_episode_watched_form, name="mark_episode_watched_form"),
]
