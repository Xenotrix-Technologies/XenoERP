from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse
from django.contrib import messages

PERM_REDIRECT_ORDER = [
    ('dashboard', 'dashboard'),
    ('leads', 'leads'),
    ('clients', 'clients'),
    ('support', 'customer_support'),
    ('projects', 'projects'),
    ('agreements', 'agreements'),
    ('quotations', 'quotations'),
    ('campaigns', 'campaign'),
    ('calendar', 'calendar'),
    ('staff', 'staff'),
    ('services', 'services'),
    ('finance', 'finance_dashboard'),
    ('hr', 'hr_dashboard'),
]


def page_permission_required(permission_name):
    """Require a UserProfile permission check."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user and request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            try:
                profile = getattr(request.user, 'profile', None)
            except Exception:
                profile = None

            has_perm = False
            if profile:
                perm_prop = f'has_access_{permission_name}'
                if hasattr(profile, perm_prop):
                    has_perm = getattr(profile, perm_prop)
                if not has_perm:
                    has_perm = profile.check_page_permission(permission_name)

            if has_perm:
                return view_func(request, *args, **kwargs)

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'You do not have permission to access this page.'}, status=403)

            messages.error(request, 'You do not have permission to access this page.')

            if profile:
                for perm, target_name in PERM_REDIRECT_ORDER:
                    if perm != permission_name and (getattr(profile, f'has_access_{perm}', False) or profile.check_page_permission(perm)):
                        return redirect(target_name)

            if request.user and request.user.is_authenticated:
                from django.shortcuts import render
                return render(request, 'access_denied.html', {'error': 'You do not have permission to access this page. Please contact your organization administrator.'}, status=403)

            return redirect('login')
        return wrapper
    return decorator
