"""Django apps for the playlists app."""
from django.apps import AppConfig


class PlaylistsConfig(AppConfig):
    """Playlists app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "playlists"
