"""
Backward-compatibility layer for crm forms.
ProfileForm has moved to core.forms.
EventForm has moved to activities.forms.
"""
from core.forms import ProfileForm
from activities.forms import EventForm

__all__ = ['ProfileForm', 'EventForm']
