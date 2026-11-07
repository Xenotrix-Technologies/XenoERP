from django import forms
from .models import Event

class EventForm(forms.ModelForm):
    start_time = forms.DateTimeField(
        input_formats=['iso-8601', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={
                'type': 'datetime-local',
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary'
            }
        )
    )
    end_time = forms.DateTimeField(
        input_formats=['iso-8601', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={
                'type': 'datetime-local',
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary'
            }
        )
    )

    class Meta:
        model = Event
        fields = ['title', 'description', 'start_time', 'end_time', 'recurring', 'color']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary',
                'placeholder': 'Event Title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary',
                'placeholder': 'Event description...',
                'rows': 3
            }),
            'recurring': forms.CheckboxInput(attrs={
                'class': 'rounded border-outline-variant text-primary focus:ring-primary h-4 w-4'
            }),
            'color': forms.Select(
                choices=[
                    ('#004ac6', 'Meeting (Blue)'),
                    ('#10b981', 'Demo (Green)'),
                    ('#ef4444', 'Deadline (Red)'),
                    ('#8b5cf6', 'Follow-up (Purple)'),
                    ('#f97316', 'Personal (Orange)'),
                ],
                attrs={
                    'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary'
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'color' in self.fields:
            self.fields['color'].required = False
        if 'description' in self.fields:
            self.fields['description'].required = False

