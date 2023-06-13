from django.contrib import admin

from .models import Episode, EpisodeWatch, Season, Show, UpdateQue

admin.site.register(Show)
admin.site.register(Season)
admin.site.register(Episode)
admin.site.register(EpisodeWatch)
admin.site.register(UpdateQue)
