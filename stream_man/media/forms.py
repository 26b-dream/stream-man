"""Django forms for the media app."""
from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms

from .models import EpisodeWatch

if TYPE_CHECKING:
    from typing import ClassVar


class MarkEpisodeWatchedForm(forms.ModelForm):
    """Form for marking an episode as watched."""

    class Meta:  # type: ignore[reportIncompatibleVariableOverride] # noqa: D106 - Meta has false positives
        model = EpisodeWatch
        fields = ("episode", "watch_date")
        widgets: ClassVar = {
            "watch_date": forms.DateInput(format=("%d-%m-%Y"), attrs={"type": "date"}),
            "episode": forms.HiddenInput(),
        }

    deleted = forms.BooleanField(widget=forms.HiddenInput(), required=False, initial=False)
