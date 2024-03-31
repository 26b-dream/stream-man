"""URLs for the playlists app."""
from django.urls import path

from . import views
from .views import Cards, Forms, Pages

app_name = "playlists"
urlpatterns = [
    # Pages
    path("", Pages.playlists, name="playlists"),
    path("<int:playlist_id>/", Pages.playlist, name="playlist"),
    # Forms
    path("forms/new_playlist", Forms.new_playlist_form, name="forms/new_playlist"),
    path("<int:playlist_id>/forms/edit_playlist/", Forms.edit_playlist_form, name="forms/edit_playlist"),
    path("<int:playlist_id>/forms/visual_config/", Forms.visual_config_form, name="forms/visual_config"),
    path("<int:playlist_id>/forms/add_show", Forms.add_show_form, name="forms/add_show"),
    path("<int:playlist_id>/forms/remove_show", Forms.remove_show_form, name="forms/remove_show"),
    path("forms/playlist_filter/<int:playlist_id>/get", Forms.playlist_filter, name="forms/playlist_filter"),
    # Cards
    path("cards/playlist", Cards.playlists, name="cards/playlist"),
    path("<int:playlist_id>/cards/episodes/", Cards.episodes, name="cards/episodes"),
    # Other
    path("<int:episode_id>/episode_info_footer/", views.episode_info_footer, name="episode_info_footer"),
]
