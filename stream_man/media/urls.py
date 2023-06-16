"""URLs for the media app."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.Indexes.media, name="media"),
    path("show/<int:show_id>/", views.Indexes.show, name="show"),
    path("season/<int:season_id>/", views.Indexes.season, name="season"),
    path("episode/<int:episode_id>/", views.Indexes.episode, name="episode"),
    path("mark_episode_watched_form/", views.mark_episode_watched_form, name="mark_episode_watched_form"),
]
