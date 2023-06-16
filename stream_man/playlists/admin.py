"""Admin configuration for the playlists app."""
from django.contrib import admin

from .models import Playlist, PlaylistImportQueue, PlaylistShow

admin.site.register(Playlist)
admin.site.register(PlaylistShow)
admin.site.register(PlaylistImportQueue)
