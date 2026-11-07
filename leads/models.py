from django.db import models
from django.utils import timezone
from core.models import Organization, UserProfile


class LeadStatus(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='lead_statuses')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20, default='#0053db')
    position = models.IntegerField(default=0)
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ('organization', 'name')
        ordering = ['position', 'id']
        db_table = 'lead_statuses'

    def __str__(self):
        return self.name

    @property
    def color_hex(self):
        color_map = {
            'blue': '#0053db',
            'grey': '#64748b',
            'green': '#10b981',
            'yellow': '#f59e0b',
            'red': '#ef4444',
            'orange': '#f97316',
            'purple': '#a855f7',
            'pink': '#ec4899',
            'teal': '#14b8a6',
        }
        if self.color.startswith('#'):
            return self.color
        return color_map.get(self.color.lower(), '#0053db')

    @property
    def badge_style(self):
        hex_val = self.color_hex
        return f"background-color: {hex_val}1a; color: {hex_val}; border: 1px solid {hex_val}33;"

    @property
    def badge_class(self):
        return ''


def get_default_badge_class(status):
    if status == 'Qualified':
        return 'bg-primary-container/10 text-primary border border-primary/20'
    elif status == 'Contacted':
        return 'bg-surface-variant text-on-surface-variant border border-outline-variant/30'
    elif status == 'New':
        return 'bg-tertiary-container/20 text-tertiary border border-tertiary/20'
    elif status == 'Cold Lead':
        return 'bg-error-container/40 text-error border border-error/20'
    return 'bg-error/10 text-error border border-error/20'


class Lead(models.Model):
    STATUS_CHOICES = [
        ('New', 'New'),
        ('Contacted', 'Contacted'),
        ('Qualified', 'Qualified'),
        ('Cold Lead', 'Cold Lead'),
        ('Lost', 'Lost'),
    ]

    STAGE_CHOICES = [
        ('New', 'New'),
        ('Qualified', 'Qualified'),
        ('Proposal', 'Proposal'),
        ('Negotiation', 'Negotiation'),
        ('Won', 'Won'),
        ('Lost', 'Lost'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='leads')
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=50)
    alt_phone_number = models.CharField(max_length=50, blank=True, null=True)
    company = models.CharField(max_length=255)
    score = models.IntegerField(default=50)
    status = models.CharField(max_length=50, default='New')
    stage = models.CharField(max_length=50, choices=STAGE_CHOICES, default='New')
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, blank=True, null=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, blank=True, null=True)
    owner = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_leads')
    services = models.ManyToManyField('services.Service', blank=True, related_name='leads')

    @property
    def service(self):
        return self.services.first()
    lifecycle_stage = models.CharField(max_length=100, default='Prospect')
    annual_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    health_score = models.IntegerField(default=50)
    profile_image_url = models.URLField(max_length=1000, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    date_time = models.DateTimeField(default=timezone.now, blank=True, null=True)
    last_followup_date_time = models.DateTimeField(blank=True, null=True)
    followup_wanted_date_time = models.DateTimeField(blank=True, null=True)
    last_activity = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    is_client = models.BooleanField(default=False)

    class Meta:
        db_table = 'leads'

    def save(self, *args, **kwargs):
        if self.status == 'Qualified':
            self.is_client = True
        super().save(*args, **kwargs)

    @property
    def status_badge_style(self):
        try:
            from projects.models import ClientStatus
            if self.is_client:
                status_obj = ClientStatus.objects.filter(organization=self.organization, name=self.status).first()
            else:
                status_obj = LeadStatus.objects.filter(organization=self.organization, name=self.status).first()
            if status_obj:
                return status_obj.badge_style
        except Exception:
            pass
        color_map = {
            'New': '#10b981',
            'Contacted': '#64748b',
            'Qualified': '#0053db',
            'Cold Lead': '#ef4444',
            'Lost': '#ef4444',
            'Active': '#10b981',
            'Completed': '#0053db',
        }
        hex_val = color_map.get(self.status, '#0053db')
        return f"background-color: {hex_val}1a; color: {hex_val}; border: 1px solid {hex_val}33;"

    @property
    def status_badge_class(self):
        if hasattr(self, '_badge_class'):
            return self._badge_class
        try:
            from projects.models import ClientStatus
            if self.is_client:
                status_obj = ClientStatus.objects.filter(organization=self.organization, name=self.status).first()
            else:
                status_obj = LeadStatus.objects.filter(organization=self.organization, name=self.status).first()
            if status_obj:
                self._badge_class = status_obj.badge_class
                return self._badge_class
        except Exception:
            pass
        return get_default_badge_class(self.status)

    def __str__(self):
        return f"{self.name} ({self.company})"
