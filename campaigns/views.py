import json
from datetime import date, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.urls import reverse

from core.permissions import page_permission_required
from core.models import SystemNotification
from core.utils import get_or_create_dynamic_statuses
from .models import Campaign, CampaignStatus


@login_required
@page_permission_required('campaigns')
def campaign_view(request):
    org = request.user.profile.organization
    campaigns = Campaign.objects.filter(organization=org).order_by('-created_at')
    
    # Auto-seed realistic demo Meta campaigns if empty
    if not campaigns.exists():
        Campaign.objects.create(
            organization=org, name='49th Kids kurta mund 10/8/26 - campaign',
            is_active=True, status='Active', results_count=119, results_type='Messaging conversations',
            cost_per_result=4.97, budget=600.00, budget_type='Lifetime', spend=591.51,
            impressions=9494, reach=6159, end_date=date(2026, 8, 15), platform='Meta Ads', leads_generated=119
        )
        Campaign.objects.create(
            organization=org, name='50th davani video ad 11/8/26 – campaign',
            is_active=False, status='Paused', results_count=10, results_type='Messaging conversations',
            cost_per_result=15.65, budget=250.00, budget_type='Lifetime', spend=156.48,
            impressions=2777, reach=2493, end_date=date(2026, 8, 13), platform='Meta Ads', leads_generated=10
        )
        campaigns = Campaign.objects.filter(organization=org).order_by('-created_at')

    # Aggregated metrics for header cards
    total_spend = sum(float(c.spend) for c in campaigns)
    total_gst = sum(c.calc_gst_amount for c in campaigns)
    total_spend_with_gst = round(total_spend + total_gst, 2)
    total_budget = sum(float(c.budget) for c in campaigns)
    total_results = sum(c.effective_results for c in campaigns)
    total_impressions = sum(c.impressions for c in campaigns)
    total_reach = sum(c.reach for c in campaigns)
    avg_cost_per_result = round(total_spend / total_results, 2) if total_results > 0 else 0.00
    active_count = campaigns.filter(is_active=True).count()
    
    context = {
        'campaigns': campaigns,
        'total_spend': total_spend,
        'total_gst': total_gst,
        'total_spend_with_gst': total_spend_with_gst,
        'total_budget': total_budget,
        'total_results': total_results,
        'total_impressions': total_impressions,
        'total_reach': total_reach,
        'avg_cost_per_result': avg_cost_per_result,
        'active_count': active_count,
        'total_count': campaigns.count(),
    }
    return render(request, 'campaign.html', context)


@login_required
@page_permission_required('campaigns')
def campaign_dashboard_view(request):
    org = request.user.profile.organization
    campaigns = Campaign.objects.filter(organization=org).order_by('-created_at')

    total_spend = sum(float(c.spend) for c in campaigns)
    total_budget = sum(float(c.budget) for c in campaigns)
    total_results = sum(c.effective_results for c in campaigns)
    total_impressions = sum(c.impressions for c in campaigns)
    total_reach = sum(c.reach for c in campaigns)
    avg_cost_per_result = round(total_spend / total_results, 2) if total_results > 0 else 0.00
    active_count = campaigns.filter(is_active=True).count()

    # Chart datasets
    chart_names = [c.name[:25] + ('...' if len(c.name) > 25 else '') for c in campaigns[:6]]
    chart_spends = [float(c.spend) for c in campaigns[:6]]
    chart_results = [c.effective_results for c in campaigns[:6]]
    chart_cpr = [c.calc_cost_per_result for c in campaigns[:6]]

    context = {
        'campaigns': campaigns,
        'total_spend': total_spend,
        'total_budget': total_budget,
        'total_results': total_results,
        'total_impressions': total_impressions,
        'total_reach': total_reach,
        'avg_cost_per_result': avg_cost_per_result,
        'active_count': active_count,
        'total_count': campaigns.count(),
        'chart_names_json': json.dumps(chart_names),
        'chart_spends_json': json.dumps(chart_spends),
        'chart_results_json': json.dumps(chart_results),
        'chart_cpr_json': json.dumps(chart_cpr),
    }
    return render(request, 'campaign_dashboard.html', context)


@login_required
@require_POST
@page_permission_required('campaigns')
def toggle_campaign_active(request, campaign_id):
    org = request.user.profile.organization
    campaign = get_object_or_404(Campaign, id=campaign_id, organization=org)
    
    campaign.is_active = not campaign.is_active
    campaign.status = 'Active' if campaign.is_active else 'Paused'
    campaign.save()
    
    return JsonResponse({
        'success': True,
        'is_active': campaign.is_active,
        'status': campaign.status,
        'message': f"Campaign is now {'Active' if campaign.is_active else 'Paused'}."
    })


@login_required
@require_POST
@page_permission_required('campaigns')
def add_campaign(request):
    org = request.user.profile.organization
    name = request.POST.get('name')
    status = request.POST.get('status', 'Active')
    is_active = request.POST.get('is_active') == 'true' or status == 'Active'
    
    results_count = int(request.POST.get('results_count') or request.POST.get('leads_generated') or 0)
    results_type = request.POST.get('results_type') or 'Messaging conversations'
    cost_per_result = float(request.POST.get('cost_per_result') or 0.0)
    budget = float(request.POST.get('budget') or 0)
    budget_type = request.POST.get('budget_type') or 'Lifetime'
    spend = float(request.POST.get('spend') or 0)
    gst_percentage = float(request.POST.get('gst_percentage') or 18.0)
    gst_amount = float(request.POST.get('gst_amount') or 0.0)
    impressions = int(request.POST.get('impressions') or 0)
    reach = int(request.POST.get('reach') or 0)
    end_date_str = request.POST.get('end_date')
    platform = request.POST.get('platform') or 'Meta Ads'
    cost_center = request.POST.get('cost_center') or ''
    
    end_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

    try:
        Campaign.objects.create(
            organization=org,
            name=name,
            status=status,
            is_active=is_active,
            results_count=results_count,
            results_type=results_type,
            cost_per_result=cost_per_result,
            budget=budget,
            budget_type=budget_type,
            spend=spend,
            gst_percentage=gst_percentage,
            gst_amount=gst_amount,
            impressions=impressions,
            reach=reach,
            end_date=end_date,
            platform=platform,
            cost_center=cost_center,
            leads_generated=results_count
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Campaign launched successfully.'})
        SystemNotification.objects.create(user=request.user, message='Campaign launched successfully.', type='success')
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'Error launching campaign: {str(e)}')
    
    return redirect('campaign')


@login_required
@require_POST
@page_permission_required('campaigns')
def edit_campaign(request, campaign_id):
    org = request.user.profile.organization
    campaign = get_object_or_404(Campaign, id=campaign_id, organization=org)
    
    name = request.POST.get('name')
    status = request.POST.get('status')
    if 'is_active' in request.POST:
        campaign.is_active = request.POST.get('is_active') == 'true'
    else:
        campaign.is_active = (status == 'Active')
        
    campaign.name = name
    campaign.status = status
    campaign.results_count = int(request.POST.get('results_count') or request.POST.get('leads_generated') or campaign.results_count)
    campaign.results_type = request.POST.get('results_type') or campaign.results_type
    campaign.cost_per_result = float(request.POST.get('cost_per_result') or campaign.cost_per_result)
    campaign.budget = float(request.POST.get('budget') or campaign.budget)
    campaign.budget_type = request.POST.get('budget_type') or campaign.budget_type
    campaign.spend = float(request.POST.get('spend') or campaign.spend)
    campaign.gst_percentage = float(request.POST.get('gst_percentage') or campaign.gst_percentage or 18.0)
    campaign.gst_amount = float(request.POST.get('gst_amount') or campaign.gst_amount or 0.0)
    campaign.impressions = int(request.POST.get('impressions') or campaign.impressions)
    campaign.reach = int(request.POST.get('reach') or campaign.reach)
    campaign.platform = request.POST.get('platform') or campaign.platform
    campaign.cost_center = request.POST.get('cost_center') or campaign.cost_center
    campaign.leads_generated = campaign.results_count
    
    end_date_str = request.POST.get('end_date')
    if end_date_str:
        try:
            campaign.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

    try:
        campaign.save()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Campaign updated successfully.'})
        SystemNotification.objects.create(user=request.user, message='Campaign updated successfully.', type='success')
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'Error updating campaign: {str(e)}')
        
    return redirect('campaign')


@login_required
@require_POST
@page_permission_required('campaigns')
def delete_campaign(request, campaign_id):
    org = request.user.profile.organization
    campaign = get_object_or_404(Campaign, id=campaign_id, organization=org)
    
    try:
        campaign.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Campaign deleted successfully.'})
        SystemNotification.objects.create(user=request.user, message='Campaign deleted successfully.', type='success')
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'Error deleting campaign: {str(e)}')
        
    return redirect('campaign')


@login_required
@page_permission_required('campaigns_status')
def campaign_status_settings(request):
    org = request.user.profile.organization
    statuses = get_or_create_dynamic_statuses(org, 'campaigns', CampaignStatus)
    return render(request, 'generic_status_settings.html', {
        'category_title': 'Campaigns',
        'statuses': statuses,
        'add_url': reverse('add_dynamic_status', args=['campaigns']),
        'edit_url_prefix': '/statuses/category/campaigns/',
        'delete_url_prefix': '/statuses/category/campaigns/',
        'reorder_url': reverse('reorder_dynamic_statuses', args=['campaigns'])
    })
