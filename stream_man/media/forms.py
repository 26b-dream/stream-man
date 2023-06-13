from __future__ import annotations

from django import forms

from .models import EpisodeWatch


class MarkEpisodeWatchedForm(forms.ModelForm):
    """Form for marking an episode as watched"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        model = EpisodeWatch
        fields = ["episode", "watch_date"]
        widgets = {
            "watch_date": forms.DateInput(format=("%d-%m-%Y"), attrs={"type": "date"}),
            "episode": forms.HiddenInput(),
        }

    deleted = forms.BooleanField(widget=forms.HiddenInput(), required=False, initial=False)
