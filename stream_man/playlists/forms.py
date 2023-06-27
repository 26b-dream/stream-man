"""Forms for the playlists app"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .builder import Builder
from .models import Playlist, PlaylistShow, Show

if TYPE_CHECKING:
    from typing import Any, Optional

    from django.db.models.query import QuerySet
    from media.models import Episode


class WebsitesField(forms.ModelChoiceField):
    """A website ModelChoiceField that displays the website favicon next to the website name"""

    # Ignore the type here because Show is a more accurate subclass of Model
    def label_from_instance(self, obj: Show):  # pyright: ignore [reportIncompatibleMethodOverride]
        """Label that is automatically displayed in forms"""
        return mark_safe(f"<img width='16' height='16' src='{escape(obj.favicon_url)}'></img> {escape(obj.website)}")

    # TODO: Maybe filter the results based on the playlist
    @staticmethod
    def unique_websites(playlist_id: int) -> QuerySet[Show]:
        """Return a list of shows that can be treated as a list of unique websites"""
        show_ids: list[int] = []  # Shows that are all from unique websites
        website_names: list[str] = []  # The name of the websites as strings

        # sqlite3 does not support .distinct("website") so the distinct values will be manually compiled in the loop
        # instead
        for show in Show.objects.filter(playlistshow__playlist=playlist_id):
            if show.website not in website_names:
                website_names.append(show.website)
                show_ids.append(show.id)

        return Show.objects.filter(id__in=show_ids).all()


class NewPlaylistForm(forms.ModelForm):
    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        model = Playlist
        fields = ["name"]


# Don't use a ModelForm or ModelFormSet because it makes it harder to manage empty strings.
class AddShowForm(forms.Form):
    urls = forms.CharField(required=False, widget=forms.Textarea)


class VisualConfigForm(forms.Form):
    columns = forms.IntegerField()


class EditPlaylistForm(forms.ModelForm):
    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        model = Playlist
        fields = ["name", "deleted", "thumbnail"]


class PlaylistSortForm(forms.Form):
    show_order = forms.ChoiceField(
        choices=Builder.ShowOrder.acceptable_functions,
        widget=forms.RadioSelect,
        initial="shuffle",
    )
    episode_order = forms.ChoiceField(
        choices=Builder.EpisodeOrder.acceptable_functions,
        widget=forms.RadioSelect,
        initial="chronological",
    )

    change_show = forms.ChoiceField(
        choices=Builder.ChangeShowIf.acceptable_functions,
        widget=forms.RadioSelect,
        initial="after_every_episode",
    )

    rotate_type = forms.ChoiceField(
        choices=Builder.Rotate.acceptable_functions,
        widget=forms.RadioSelect,
        initial="rotate",
    )

    REVERSE_OPTIONS = (("shows", "Shows"), ("episodes", "Episodes"))
    reverse = forms.MultipleChoiceField(choices=REVERSE_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False)

    filter = forms.MultipleChoiceField(
        choices=Builder.Filter.acceptable_functions, widget=forms.CheckboxSelectMultiple, required=False
    )

    number_of_episodes = forms.IntegerField(initial=1000, required=False)

    playlist = forms.ModelChoiceField(queryset=Playlist.objects.all(), widget=forms.HiddenInput())

    websites = WebsitesField(
        queryset=Show.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        to_field_name="website",
        required=False,  # Not required because a blank value is used to indicate all websites
    )

    # Method to dynamically set the queryset
    # See: https://stackoverflow.com/questions/4880842/
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Args are passed in a kind of ugly way that require triple checking to see if the key exists
        if args and args[0] and args[0].get("playlist"):
            self.fields["websites"].queryset = WebsitesField.unique_websites(args[0]["playlist"])

    @staticmethod
    def initial_values() -> dict[str, Any]:
        """Get the initial values for the form, useful when trying to compile a valid form from a POST or GET
        response"""
        initial_values = {}
        for field_name in PlaylistSortForm().fields.keys():
            if PlaylistSortForm().fields[field_name].initial:
                initial_values[field_name] = PlaylistSortForm().fields[field_name].initial
        return initial_values


class ShowsField(forms.ModelMultipleChoiceField):
    """A ModelChoiceField for shows that displays the website favicon next to the show name"""

    # Ignore the type here because Show is a more accurate subclass of Model
    def label_from_instance(self, obj: Show):  # pyright: ignore [reportIncompatibleMethodOverride]
        return mark_safe(f"<img width='16' height='16' src='{escape(obj.favicon_url)}'></img> {escape(obj.name)}")


# methods for setting up values
class RemoveShowForm(forms.Form):
    """Form used to remove shows form a playlist"""

    # Start with a
    remove_show = ShowsField(queryset=PlaylistShow.objects.none(), widget=forms.CheckboxSelectMultiple, required=False)
    playlist_id = forms.ModelChoiceField(queryset=Playlist.objects.all(), widget=forms.HiddenInput())

    # Method to dynamically set the queryset
    # See: https://stackoverflow.com/questions/4880842/
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Args are passed in a kind of ugly way that require triple checking to see if the key exists
        if args and args[0] and args[0].get("playlist_id"):
            self.fields["remove_show"].queryset = Playlist.objects.get(id=args[0]["playlist_id"]).shows.all()
