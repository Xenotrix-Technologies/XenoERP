from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Service
from leads.utils import safe_parse_decimal
from core.permissions import page_permission_required

@login_required
@page_permission_required('services')
def services_view(request):
    """List all services for the current organization."""
    org = request.user.profile.organization
    services = Service.objects.filter(organization=org)
    return render(request, 'services.html', {'services': services})

@login_required
@page_permission_required('services')
def add_service(request):
    """Create a new service via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        price_val = request.POST.get('price', '0.00').strip()
        price = safe_parse_decimal(price_val, 0.00)

        if not name:
            return JsonResponse({'success': False, 'error': 'Service name is required.'})

        if Service.objects.filter(organization=org, name=name).exists():
            return JsonResponse({'success': False, 'error': f"Service '{name}' already exists."})

        Service.objects.create(organization=org, name=name, description=description, price=price)
        return JsonResponse({'success': True, 'message': f"Service '{name}' created."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
@page_permission_required('services')
def edit_service(request, service_id):
    """Edit an existing service via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            service_obj = Service.objects.get(id=service_id, organization=org)
        except Service.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Service not found.'})

        new_name = request.POST.get('name', '').strip()
        new_description = request.POST.get('description', '').strip()
        new_price_val = request.POST.get('price', '').strip()
        new_price = safe_parse_decimal(new_price_val, service_obj.price)

        if not new_name:
            return JsonResponse({'success': False, 'error': 'Service name is required.'})

        if Service.objects.filter(organization=org, name=new_name).exclude(id=service_id).exists():
            return JsonResponse({'success': False, 'error': f"Service '{new_name}' already exists."})

        service_obj.name = new_name
        service_obj.description = new_description
        service_obj.price = new_price
        service_obj.save()

        return JsonResponse({'success': True, 'message': f"Service updated to '{new_name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
@page_permission_required('services')
def delete_service(request, service_id):
    """Delete a service via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            service_obj = Service.objects.get(id=service_id, organization=org)
        except Service.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Service not found.'})

        deleted_name = service_obj.name
        service_obj.delete()

        return JsonResponse({'success': True, 'message': f"Service '{deleted_name}' deleted."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})
