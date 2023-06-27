from django.urls import path

from . import views
from .views import Cards, Forms, Pages

app_name = "playlists"
urlpatterns = [
    # Pages
    path("", Pages.playlists, name="playlists"),
    path("<int:playlist_id>/", Pages.playlist, name="playlist"),
    # Forms - NewPlaylist
    path("forms/new_playlist/form", Forms.NewPlaylist.form, name="forms/new_playlist/form"),
    path("forms/new_playlist/submit", Forms.NewPlaylist.submit, name="forms/new_playlist/submit"),
    # Forms - EditPlaylist
    path("forms/edit_playlist/<int:playlist_id>/form", Forms.EditPlaylist.form, name="forms/edit_playlist/form"),
    path("forms/edit_playlist/<int:playlist_id>/submit", Forms.EditPlaylist.submit, name="forms/edit_playlist/submit"),
    # Forms - VisualConfig
    path("forms/visual_config/<int:playlist_id>/form", Forms.VisualConfig.form, name="forms/visual_config/form"),
    path("forms/visual_config/<int:playlist_id>/submit", Forms.VisualConfig.submit, name="forms/visual_config/submit"),
    # Forms - AddShow
    path("forms/add_show/<int:playlist_id>/form", Forms.AddShow.form, name="forms/add_show/form"),
    path("forms/add_show/<int:playlist_id>/submit", Forms.AddShow.submit, name="forms/add_show/submit"),
    # Forms - RemoveShow
    path("forms/remove_show/<int:playlist_id>/form", Forms.RemoveShow.form, name="forms/remove_show/form"),
    path("forms/remove_show/<int:playlist_id>/submit", Forms.RemoveShow.submit, name="forms/remove_show/submit"),
    # Forms - PlaylistFilter
    path("forms/playlist_filter/<int:playlist_id>/get", Forms.PlaylistFilter.form, name="forms/playlist_filter/form"),
    path(
        "forms/playlist_filter/<int:playlist_id>/set_defaults",
        Forms.PlaylistFilter.set_defaults,
        name="forms/playlist_filter/set_defaults",
    ),
    path(
        "forms/playlist_filter/<int:playlist_id>/submit",
        Forms.PlaylistFilter.submit,
        name="forms/playlist_filter/submit",
    ),
    # Cards
    path("cards/playlist", Cards.playlists, name="cards/playlist"),
    path(
        "cards/episodes/<int:playlist_id>/",
        Cards.episodes,
        name="cards/episodes",
    ),
    # Other
    path("episode_info_footer/<int:episode_id>/", views.episode_info_footer, name="episode_info_footer"),
]
