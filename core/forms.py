from django import forms
from .models import UserProfile

class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['profile_image_url', 'phone_number', 'location', 'role']
        widgets = {
            'profile_image_url': forms.URLInput(attrs={
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary',
                'placeholder': 'https://example.com/avatar.jpg'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary',
                'placeholder': '+1 (555) 000-0000'
            }),
            'location': forms.TextInput(attrs={
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary',
                'placeholder': 'e.g. New York, USA'
            }),
            'role': forms.TextInput(attrs={
                'class': 'w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-body-sm focus:ring-1 focus:ring-primary focus:border-primary opacity-70 cursor-not-allowed',
                'placeholder': 'e.g. Sales Director',
                'readonly': 'readonly'
            })
        }

