from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import LeadStatus, get_default_badge_class

DEFAULT_STATUSES = [
    {'name': 'New',       'color': 'green',  'position': 0, 'is_default': True},
    {'name': 'Contacted', 'color': 'grey',   'position': 1, 'is_default': False},
    {'name': 'Qualified', 'color': 'blue',   'position': 2, 'is_default': False},
    {'name': 'Cold Lead', 'color': 'red',    'position': 3, 'is_default': False},
    {'name': 'Lost',      'color': 'red',    'position': 4, 'is_default': False},
]

def get_or_create_default_statuses(org):
    """Return the queryset of LeadStatus for `org`, seeding defaults if empty."""
    qs = LeadStatus.objects.filter(organization=org)
    if not qs.exists():
        for s in DEFAULT_STATUSES:
            LeadStatus.objects.create(organization=org, **s)
        qs = LeadStatus.objects.filter(organization=org)
    return qs

def annotate_lead_badges(leads, org):
    """Attach _badge_class to each lead object to avoid N+1 queries."""
    statuses = {s.name: s.badge_class for s in get_or_create_default_statuses(org)}
    iterable = leads if hasattr(leads, '__iter__') else [leads]
    for lead in iterable:
        badge = statuses.get(lead.status)
        if badge is None:
            badge = get_default_badge_class(lead.status)
        lead._badge_class = badge

def map_headers(headers):
    """Map lowercase versions of headers to normalized internal fields."""
    field_mappings = {
        'name': ['name', 'lead name', 'full name', 'contact name'],
        'email': ['email', 'email address'],
        'company': ['company', 'company name'],
        'phone_number': ['phone', 'phone number', 'contact phone'],
        'alt_phone_number': ['alt phone', 'alt phone number'],
        'value': ['value', 'deal value', 'lead value'],
        'score': ['score', 'lead score', 'health score'],
        'status': ['status', 'lead status'],
        'stage': ['stage', 'lead stage'],
        'owner': ['owner', 'assigned owner', 'assigned to'],
        'annual_revenue': ['annual revenue', 'revenue'],
        'lifecycle_stage': ['lifecycle stage', 'lifecycle'],
        'last_followup': ['last followup', 'last followup date and time', 'last followup date/time', 'last followup datetime'],
        'followup_wanted': ['followup wanted', 'follow up wanted', 'followup wanted date and time', 'follow up wanted date/time', 'next followup', 'next followup date and time', 'next followup date/time'],
        'date_time': ['date and time', 'date/time', 'date', 'datetime', 'date time'],
        'location': ['location', 'address', 'city']
    }

    mapped = {}
    for header in headers:
        if not header:
            continue
        header_lower = header.lower().strip()
        for field, aliases in field_mappings.items():
            if header_lower in aliases:
                mapped[field] = header
                break

    if 'name' not in mapped:
        for h in headers:
            if h and 'name' in h.lower():
                mapped['name'] = h
                break
    if 'email' not in mapped:
        for h in headers:
            if h and 'email' in h.lower():
                mapped['email'] = h
                break
    if 'company' not in mapped:
        for h in headers:
            if h and 'company' in h.lower():
                mapped['company'] = h
                break

    return mapped

def is_valid_email(email_str):
    try:
        validate_email(email_str)
        return True
    except ValidationError:
        return False

def safe_parse_decimal(val, default=0.00):
    if not val:
        return Decimal(str(default))
    val = str(val).strip().replace('$', '').replace(',', '')
    try:
        return Decimal(val)
    except (InvalidOperation, ValueError):
        return Decimal(str(default))

def safe_parse_int(val, default=50):
    if not val:
        return default
    val = str(val).strip()
    try:
        return int(float(val))
    except ValueError:
        return default

def safe_parse_datetime(val):
    if not val:
        return None
    val = str(val).strip()
    if not val:
        return None
    dt = parse_datetime(val)
    if dt:
        try:
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except Exception:
            return dt
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M',
        '%m/%d/%Y',
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%d/%m/%Y',
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(val, fmt)
            try:
                return timezone.make_aware(dt)
            except Exception:
                return dt
        except ValueError:
            continue
    return None
