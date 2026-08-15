from django import forms

from .engagement_helpers import _engagement_select_label

class EngagementModelChoiceField(forms.ModelChoiceField):
    """Uses readable labels; submitted value remains the engagement primary key."""

    def label_from_instance(self, obj):
        return _engagement_select_label(obj)
