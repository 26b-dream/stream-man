"""Forms for the playlists app."""
from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .builder import Builder, get_functions
from .models import Playlist, PlaylistShow, Show

if TYPE_CHECKING:
    from typing import Any

    from django.db.models.query import QuerySet
    from django.utils.safestring import SafeText


class WebsitesField(forms.ModelChoiceField):
    """A website ModelChoiceField that displays the website favicon next to the website name."""

    # Ignore the type here because Show is a more accurate subclass of Model
    def label_from_instance(self, obj: Show) -> SafeText:  # pyright: ignore [reportIncompatibleMethodOverride]
        """Label that is automatically displayed in forms."""
        # This line is secure enough. The favicon_url and website are both hardcoded values for each plugin. If XSS is
        # occuring here it is because the user installed a bad plugin in which case it can do a lot more than just an
        # XSS exploit.
        return mark_safe(f"<img width='16' height='16' src='{escape(obj.favicon.url)}'></img> {escape(obj.website)}")  # noqa: S308

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
    """Form for creating a new playlist."""

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        model = Playlist
        fields = ("name",)


class AddShowForm(forms.Form):
    """Form for adding a show to a playlist."""

    # A big text entry field is the easiest way to input values but requires extra work compared to a ModelForm
    urls = forms.CharField(required=False, widget=forms.Textarea)


class VisualConfigForm(forms.Form):
    """Form for configuring the visual settings of a playlist."""

    columns = forms.IntegerField()
    image_width = forms.IntegerField()


class EditPlaylistForm(forms.ModelForm):
    """Form for editing a playlist."""

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        model = Playlist
        fields = ("name", "deleted", "thumbnail")


class PlaylistFilterForm(forms.Form):
    """Form for filtering a playlist."""

    show_order = forms.ChoiceField(
        choices=get_functions(Builder.ShowOrder),
        widget=forms.RadioSelect,
        initial="shuffle",
    )
    episode_order = forms.ChoiceField(
        choices=get_functions(Builder.EpisodeOrder),
        widget=forms.RadioSelect,
        initial="chronological",
    )

    change_show = forms.ChoiceField(
        choices=get_functions(Builder.ChangeShowIf),
        widget=forms.RadioSelect,
        initial="after_every_episode",
    )

    rotate_type = forms.ChoiceField(
        choices=get_functions(Builder.Rotate),
        widget=forms.RadioSelect,
        initial="rotate",
    )

    REVERSE_OPTIONS = (("shows", "Shows"), ("episodes", "Episodes"))
    reverse = forms.MultipleChoiceField(choices=REVERSE_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False)

    filter_episodes = forms.MultipleChoiceField(
        choices=get_functions(Builder.FilterEpisodes),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    number_of_episodes = forms.IntegerField(initial=1000, required=False)

    playlist = forms.ModelChoiceField(queryset=Playlist.objects.all(), widget=forms.HiddenInput())

    websites = WebsitesField(
        queryset=Show.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        to_field_name="website",
        required=False,  # Not required because a blank value is used to indicate all websites
    )

    include_deleted_episodes = forms.BooleanField(required=False)

    # Method to dynamically set the queryset
    # See: https://stackoverflow.com/questions/4880842/
    # TODO: Clean this up, check if I can initialize the fields in a seperate function afterwards so I don't have to do
    # the messy args/kwargs Any stuff
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Args are passed in a kind of ugly way that require triple checking to see if the key exists
        if args and args[0] and args[0].get("playlist"):
            self.fields["websites"].queryset = WebsitesField.unique_websites(args[0]["playlist"])

    @staticmethod
    def initial_values() -> dict[str, Any]:
        """Get the initial values for the form, useful when trying to compile a valid form from a POST or GET
        response"""
        initial_values: dict[str, Any] = {}
        for field_name in PlaylistFilterForm().fields.keys():
            if PlaylistFilterForm().fields[field_name].initial:
                initial_values[field_name] = PlaylistFilterForm().fields[field_name].initial
        return initial_values


class ShowsField(forms.ModelMultipleChoiceField):
    """A ModelChoiceField for shows that displays the website favicon next to the show name"""

    # Ignore the type here because Show is a more accurate subclass of Model
    def label_from_instance(self, obj: Show):  # pyright: ignore [reportIncompatibleMethodOverride]
        return obj.pretty_html_name()


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
