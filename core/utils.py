def get_or_create_dynamic_statuses(org, category_str, model_class):
    """
    Get or seed dynamic statuses for an organization based on category.
    """
    qs = model_class.objects.filter(organization=org)
    DEFAULT_STATUSES_MAP = {
        'clients': [
            {'name': 'Active', 'color': '#10b981'},
            {'name': 'Inactive', 'color': '#64748b'},
            {'name': 'Pending', 'color': '#f59e0b'},
            {'name': 'Suspended', 'color': '#ef4444'}
        ],
        'projects': [
            {'name': 'Planning', 'color': '#3b82f6'},
            {'name': 'In Progress', 'color': '#f59e0b'},
            {'name': 'On Hold', 'color': '#64748b'},
            {'name': 'Completed', 'color': '#10b981'},
            {'name': 'Cancelled', 'color': '#ef4444'}
        ],
        'campaigns': [
            {'name': 'Planning', 'color': '#64748b'},
            {'name': 'Active', 'color': '#0053db'},
            {'name': 'Completed', 'color': '#22c55e'}
        ],
        'calendar': [
            {'name': 'Meetings', 'color': '#004ac6'},
            {'name': 'Calls', 'color': '#10b981'},
            {'name': 'Deadlines', 'color': '#ef4444'},
            {'name': 'Follow-ups', 'color': '#8b5cf6'},
            {'name': 'Personal', 'color': '#f97316'}
        ],
        'tickets': [
            {'name': 'Open', 'color': '#ef4444'},
            {'name': 'Pending', 'color': '#f59e0b'},
            {'name': 'Resolved', 'color': '#10b981'},
            {'name': 'Closed', 'color': '#64748b'}
        ],
        'priority': [
            {'name': 'Low', 'color': '#64748b'},
            {'name': 'Medium', 'color': '#f59e0b'},
            {'name': 'High', 'color': '#ef4444'},
            {'name': 'Critical', 'color': '#8b5cf6'}
        ],
        'invoices': [
            {'name': 'Pending', 'color': '#f59e0b'},
            {'name': 'Paid', 'color': '#10b981'},
            {'name': 'Partial', 'color': '#3b82f6'},
            {'name': 'Overdue', 'color': '#ef4444'},
            {'name': 'Draft', 'color': '#64748b'}
        ]
    }
    if not qs.exists():
        defaults = DEFAULT_STATUSES_MAP.get(category_str, [])
        for idx, s in enumerate(defaults):
            model_class.objects.create(organization=org, name=s['name'], color=s['color'], position=idx)
        qs = model_class.objects.filter(organization=org)
    elif category_str == 'invoices':
        if not qs.filter(name__iexact='Draft').exists():
            model_class.objects.create(organization=org, name='Draft', color='#64748b', position=4)
            qs = model_class.objects.filter(organization=org)
    return qs

