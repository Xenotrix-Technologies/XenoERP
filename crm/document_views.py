import json
import uuid
from decimal import Decimal
from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Organization, UserProfile, Lead, Service, SystemNotification,
    DocumentSettings, Quotation, QuotationItem, QuotationPackage,
    QuotationDomainOption, QuotationPaymentStage, QuotationTerm,
    QuotationExclusion, QuotationActivity, QuotationVersion,
    Agreement, AgreementVersion, DocumentTemplate
)
from .views import page_permission_required



def get_user_profile(user):
    profile = UserProfile.objects.filter(user=user).first()
    if not profile:
        org = Organization.objects.first()
        if not org:
            org = Organization.objects.create(name='Xenotrix Technologies')
        profile = UserProfile.objects.create(user=user, organization=org)
    elif not profile.organization:
        org = Organization.objects.first()
        if not org:
            org = Organization.objects.create(name='Xenotrix Technologies')
        profile.organization = org
        profile.save(update_fields=['organization'])
    return profile


def get_or_create_document_settings(organization):
    settings, created = DocumentSettings.objects.get_or_create(
        organization=organization,
        defaults={
            'company_name': organization.name or 'Xenotrix Technologies',
            'address': '123 Tech Park, Suite 400, Hyderabad, Telangana, India',
            'phone': '+91 98765 43210',
            'email': 'contact@xenotrix.in',
            'website': 'https://xenotrix.in',
            'gstin': '36AAAAA0000A1Z5',
            'pan': 'ABCDE1234F',
            'bank_name': 'HDFC Bank',
            'account_name': (organization.name or 'Xenotrix Technologies') + ' Pvt Ltd',
            'account_number': '50200012345678',
            'ifsc_code': 'HDFC0001234',
            'upi_id': 'xenotrix@hdfcbank',
            'quotation_prefix': 'XT-QT',
            'agreement_prefix': 'XT-AGR',
            'next_quotation_number': 1,
            'next_agreement_number': 1,
            'footer_text': 'Thank you for choosing Xenotrix Technologies. For any queries, contact info@xenotrix.in.',
            'authorized_person_name': 'Authorized Signatory',
        }
    )
    return settings


def generate_next_quotation_number(organization):
    settings = get_or_create_document_settings(organization)
    year = datetime.now().year
    prefix = settings.quotation_prefix or 'XT-QT'
    
    count = Quotation.objects.filter(organization=organization).count() + 1
    num_str = f"{count:04d}"
    candidate = f"{prefix}-{year}-{num_str}"
    
    while Quotation.objects.filter(quotation_number=candidate).exists():
        count += 1
        num_str = f"{count:04d}"
        candidate = f"{prefix}-{year}-{num_str}"
        
    return candidate


def generate_next_agreement_number(organization):
    settings = get_or_create_document_settings(organization)
    year = datetime.now().year
    prefix = settings.agreement_prefix or 'XT-AGR'
    
    count = Agreement.objects.filter(organization=organization).count() + 1
    num_str = f"{count:04d}"
    candidate = f"{prefix}-{year}-{num_str}"
    
    while Agreement.objects.filter(agreement_number=candidate).exists():
        count += 1
        num_str = f"{count:04d}"
        candidate = f"{prefix}-{year}-{num_str}"
        
    return candidate


def recalculate_quotation_totals(quotation):
    items = quotation.items.filter(is_optional=False)
    
    subtotal = Decimal('0.00')
    total_discount = Decimal('0.00')
    total_tax = Decimal('0.00')
    
    one_time = Decimal('0.00')
    monthly = Decimal('0.00')
    yearly = Decimal('0.00')

    for item in items:
        qty = item.quantity or Decimal('1.00')
        price = item.unit_price or Decimal('0.00')
        disc = item.discount or Decimal('0.00')
        tax_pct = item.tax_rate or Decimal('0.00')

        line_base = qty * price
        line_disc = disc
        line_after_disc = max(Decimal('0.00'), line_base - line_disc)
        line_tax = (line_after_disc * tax_pct) / Decimal('100.00')
        line_total = line_after_disc + line_tax

        item.line_total = line_total
        item.save()

        subtotal += line_base
        total_discount += line_disc
        total_tax += line_tax

        ptype = (item.pricing_type or 'fixed').lower()
        if ptype in ['monthly']:
            monthly += line_total
        elif ptype in ['yearly']:
            yearly += line_total
        else:
            one_time += line_total

    # Add package prices if any
    for pkg in quotation.packages.all():
        pkg_price = pkg.price or Decimal('0.00')
        if pkg.billing_frequency and pkg.billing_frequency.lower() == 'monthly':
            monthly += pkg_price
        elif pkg.billing_frequency and pkg.billing_frequency.lower() == 'yearly':
            yearly += pkg_price
        else:
            one_time += pkg_price
        subtotal += pkg_price

    grand_total = max(Decimal('0.00'), subtotal - total_discount + total_tax)

    quotation.subtotal = subtotal
    quotation.discount_amount = total_discount
    quotation.tax_amount = total_tax
    quotation.grand_total = grand_total
    quotation.one_time_total = one_time
    quotation.monthly_recurring_total = monthly
    quotation.yearly_recurring_total = yearly
    quotation.save()

    return quotation


def create_quotation_activity(quotation, user, activity_type, description, request=None):
    ip_addr = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            ip_addr = x_forwarded.split(',')[0].strip()
        else:
            ip_addr = request.META.get('REMOTE_ADDR')

    QuotationActivity.objects.create(
        quotation=quotation,
        user=user,
        activity_type=activity_type,
        description=description,
        ip_address=ip_addr
    )


def create_quotation_version_snapshot(quotation, user, summary="Saved version"):
    items_data = list(quotation.items.values())
    packages_data = list(quotation.packages.values())
    domains_data = list(quotation.domain_options.values())
    stages_data = list(quotation.payment_stages.values())
    terms_data = list(quotation.terms.values())
    exclusions_data = list(quotation.exclusions.values())

    snapshot = {
        'quotation_number': quotation.quotation_number,
        'client_name': quotation.client_name,
        'company_name': quotation.company_name,
        'date': str(quotation.date),
        'valid_until': str(quotation.valid_until),
        'grand_total': str(quotation.grand_total),
        'status': quotation.status,
        'items': items_data,
        'packages': packages_data,
        'domain_options': domains_data,
        'payment_stages': stages_data,
        'terms': terms_data,
        'exclusions': exclusions_data,
    }

    QuotationVersion.objects.create(
        quotation=quotation,
        version_number=quotation.version,
        data_snapshot_json=json.dumps(snapshot, default=str),
        created_by=user.user if user else None,
        change_summary=summary
    )


# ==========================================
# QUOTATIONS MANAGEMENT VIEWS
# ==========================================

@login_required
@page_permission_required('agreements')
def quotation_list(request):
    profile = get_user_profile(request.user)
    org = profile.organization
    
    # Auto-expire outdated quotations
    today = timezone.now().date()
    Quotation.objects.filter(
        organization=org,
        valid_until__lt=today,
        status__in=['Draft', 'Sent', 'Viewed']
    ).update(status='Expired')

    quotations = Quotation.objects.filter(organization=org).order_by('-created_at')

    search_q = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if search_q:
        quotations = quotations.filter(
            Q(quotation_number__icontains=search_q) |
            Q(client_name__icontains=search_q) |
            Q(company_name__icontains=search_q) |
            Q(email__icontains=search_q) |
            Q(phone__icontains=search_q)
        )

    if status_filter:
        quotations = quotations.filter(status=status_filter)

    all_qs = Quotation.objects.filter(organization=org)
    total_count = all_qs.count()
    draft_count = all_qs.filter(status='Draft').count()
    sent_count = all_qs.filter(status='Sent').count()
    viewed_count = all_qs.filter(status='Viewed').count()
    accepted_count = all_qs.filter(status='Accepted').count()
    rejected_count = all_qs.filter(status='Rejected').count()
    expired_count = all_qs.filter(status='Expired').count()

    total_quoted_val = all_qs.aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')

    doc_settings = get_or_create_document_settings(org)

    context = {
        'quotations': quotations,
        'search_q': search_q,
        'status_filter': status_filter,
        'total_count': total_count,
        'draft_count': draft_count,
        'sent_count': sent_count,
        'viewed_count': viewed_count,
        'accepted_count': accepted_count,
        'rejected_count': rejected_count,
        'expired_count': expired_count,
        'total_quoted_val': total_quoted_val,
        'doc_settings': doc_settings,
        'profile': profile,
    }
    return render(request, 'quotations/quotation_list.html', context)


@login_required
@page_permission_required('agreements')
def quotation_create(request):
    profile = get_user_profile(request.user)
    org = profile.organization
    doc_settings = get_or_create_document_settings(org)

    lead_id = request.GET.get('lead_id')
    selected_lead = None
    if lead_id:
        selected_lead = Lead.objects.filter(organization=org, id=lead_id).first()

    leads = Lead.objects.filter(organization=org).order_by('-created_at')
    services = Service.objects.filter(organization=org).order_by('name')
    templates = DocumentTemplate.objects.filter(organization=org, is_active=True)

    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

            q_num = data.get('quotation_number') or generate_next_quotation_number(org)
            lead_fk = None
            if data.get('lead_id'):
                lead_fk = Lead.objects.filter(organization=org, id=data.get('lead_id')).first()

            valid_until_str = data.get('valid_until')
            if valid_until_str:
                valid_until_dt = datetime.strptime(valid_until_str, '%Y-%m-%d').date()
            else:
                valid_until_dt = timezone.now().date() + timedelta(days=10)

            quotation = Quotation.objects.create(
                organization=org,
                quotation_number=q_num,
                lead=lead_fk,
                client_name=data.get('client_name', 'Unnamed Client'),
                company_name=data.get('company_name', ''),
                email=data.get('email', ''),
                phone=data.get('phone', ''),
                address=data.get('address', ''),
                gstin=data.get('gstin', ''),
                contact_person=data.get('contact_person', ''),
                lead_source=data.get('lead_source', ''),
                date=data.get('date') or timezone.now().date(),
                valid_until=valid_until_dt,
                prepared_by=profile,
                salesperson=data.get('salesperson', profile.user.get_full_name() or profile.user.username),
                currency=data.get('currency', doc_settings.default_currency),
                payment_terms_summary=data.get('payment_terms_summary', '50% Advance / 50% Completion'),
                notes=data.get('notes', ''),
                template_style=data.get('template_style', 'default'),
                status=data.get('status', 'Draft'),
            )

            # Insert Line Items
            items_list = data.get('items', [])
            for idx, item in enumerate(items_list):
                QuotationItem.objects.create(
                    quotation=quotation,
                    section_name=item.get('section_name') or 'Services',
                    title=item.get('title', 'Service Item'),
                    description=item.get('description', ''),
                    pricing_type=item.get('pricing_type', 'fixed'),
                    quantity=Decimal(str(item.get('quantity', 1))),
                    unit=item.get('unit', 'Item'),
                    unit_price=Decimal(str(item.get('unit_price', 0))),
                    discount=Decimal(str(item.get('discount', 0))),
                    tax_rate=Decimal(str(item.get('tax_rate', 0))),
                    is_optional=bool(item.get('is_optional', False)),
                    position=idx
                )

            # Insert Package if selected
            pkg_data = data.get('package')
            if pkg_data and isinstance(pkg_data, dict) and pkg_data.get('package_name'):
                QuotationPackage.objects.create(
                    quotation=quotation,
                    package_name=pkg_data.get('package_name'),
                    price=Decimal(str(pkg_data.get('price', 0))),
                    billing_frequency=pkg_data.get('billing_frequency', 'Monthly'),
                    description=pkg_data.get('description', ''),
                    deliverables_text=pkg_data.get('deliverables_text', ''),
                    inclusions_text=pkg_data.get('inclusions_text', ''),
                    exclusions_text=pkg_data.get('exclusions_text', ''),
                    terms_text=pkg_data.get('terms_text', '')
                )

            # Insert Domain Options
            domains_list = data.get('domain_options', [])
            for dom in domains_list:
                if dom.get('domain_name'):
                    QuotationDomainOption.objects.create(
                        quotation=quotation,
                        domain_name=dom.get('domain_name'),
                        period=dom.get('period', '3 Years'),
                        price=Decimal(str(dom.get('price', 0))),
                        is_recommended=bool(dom.get('is_recommended', False)),
                        is_selected=bool(dom.get('is_selected', False))
                    )

            # Insert Payment Stages
            stages_list = data.get('payment_stages', [])
            for idx, stage in enumerate(stages_list):
                if stage.get('stage_name'):
                    due_dt = None
                    if stage.get('due_date'):
                        try: due_dt = datetime.strptime(stage['due_date'], '%Y-%m-%d').date()
                        except: pass
                    QuotationPaymentStage.objects.create(
                        quotation=quotation,
                        stage_name=stage.get('stage_name'),
                        percentage=Decimal(str(stage.get('percentage', 0))),
                        amount=Decimal(str(stage.get('amount', 0))),
                        due_date=due_dt,
                        description=stage.get('description', ''),
                        position=idx
                    )

            # Insert Terms & Conditions
            terms_list = data.get('terms', [])
            for idx, t in enumerate(terms_list):
                if isinstance(t, dict) and t.get('content'):
                    QuotationTerm.objects.create(
                        quotation=quotation,
                        clause_title=t.get('clause_title', ''),
                        content=t.get('content'),
                        position=idx
                    )
                elif isinstance(t, str) and t.strip():
                    QuotationTerm.objects.create(
                        quotation=quotation,
                        content=t.strip(),
                        position=idx
                    )

            # Insert Exclusions
            exclusions_list = data.get('exclusions', [])
            for idx, ex in enumerate(exclusions_list):
                if isinstance(ex, dict) and ex.get('service_name'):
                    QuotationExclusion.objects.create(
                        quotation=quotation,
                        service_name=ex.get('service_name'),
                        charges_description=ex.get('charges_description', ''),
                        position=idx
                    )

            recalculate_quotation_totals(quotation)
            create_quotation_activity(quotation, profile, 'Created', f'Quotation {quotation.quotation_number} created.', request)
            create_quotation_version_snapshot(quotation, profile, 'Initial creation')

            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'quotation_id': quotation.id,
                    'quotation_number': quotation.quotation_number,
                    'redirect_url': f'/quotations/{quotation.id}/'
                })
            
            return redirect('quotation_detail', quotation_id=quotation.id)

        except Exception as e:
            if request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
            return render(request, 'quotations/quotation_form.html', {
                'error': str(e),
                'leads': leads,
                'services': services,
                'doc_settings': doc_settings,
                'default_q_num': generate_next_quotation_number(org),
                'selected_lead': selected_lead,
            })

    default_q_num = generate_next_quotation_number(org)
    context = {
        'leads': leads,
        'services': services,
        'templates': templates,
        'doc_settings': doc_settings,
        'default_q_num': default_q_num,
        'selected_lead': selected_lead,
        'today_date': timezone.now().date().strftime('%Y-%m-%d'),
        'valid_date': (timezone.now().date() + timedelta(days=10)).strftime('%Y-%m-%d'),
        'profile': profile,
    }
    return render(request, 'quotations/quotation_form.html', context)


@login_required
@page_permission_required('agreements')
def quotation_edit(request, quotation_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    quotation = get_object_or_404(Quotation, organization=org, id=quotation_id)
    doc_settings = get_or_create_document_settings(org)

    leads = Lead.objects.filter(organization=org).order_by('-created_at')
    services = Service.objects.filter(organization=org).order_by('name')

    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

            if quotation.status == 'Accepted':
                return JsonResponse({'success': False, 'error': 'Accepted quotations cannot be edited. Please create a revision or convert to agreement.'}, status=400)

            quotation.client_name = data.get('client_name', quotation.client_name)
            quotation.company_name = data.get('company_name', quotation.company_name)
            quotation.email = data.get('email', quotation.email)
            quotation.phone = data.get('phone', quotation.phone)
            quotation.address = data.get('address', quotation.address)
            quotation.gstin = data.get('gstin', quotation.gstin)
            quotation.contact_person = data.get('contact_person', quotation.contact_person)
            quotation.lead_source = data.get('lead_source', quotation.lead_source)
            quotation.currency = data.get('currency', quotation.currency)
            quotation.payment_terms_summary = data.get('payment_terms_summary', quotation.payment_terms_summary)
            quotation.notes = data.get('notes', quotation.notes)
            quotation.template_style = data.get('template_style', quotation.template_style)

            if data.get('valid_until'):
                quotation.valid_until = datetime.strptime(data['valid_until'], '%Y-%m-%d').date()

            quotation.version += 1
            quotation.save()

            if 'items' in data:
                quotation.items.all().delete()
                for idx, item in enumerate(data['items']):
                    QuotationItem.objects.create(
                        quotation=quotation,
                        section_name=item.get('section_name') or 'Services',
                        title=item.get('title', 'Service Item'),
                        description=item.get('description', ''),
                        pricing_type=item.get('pricing_type', 'fixed'),
                        quantity=Decimal(str(item.get('quantity', 1))),
                        unit=item.get('unit', 'Item'),
                        unit_price=Decimal(str(item.get('unit_price', 0))),
                        discount=Decimal(str(item.get('discount', 0))),
                        tax_rate=Decimal(str(item.get('tax_rate', 0))),
                        is_optional=bool(item.get('is_optional', False)),
                        position=idx
                    )

            if 'domain_options' in data:
                quotation.domain_options.all().delete()
                for dom in data['domain_options']:
                    if dom.get('domain_name'):
                        QuotationDomainOption.objects.create(
                            quotation=quotation,
                            domain_name=dom.get('domain_name'),
                            period=dom.get('period', '3 Years'),
                            price=Decimal(str(dom.get('price', 0))),
                            is_recommended=bool(dom.get('is_recommended', False)),
                            is_selected=bool(dom.get('is_selected', False))
                        )

            if 'payment_stages' in data:
                quotation.payment_stages.all().delete()
                for idx, stage in enumerate(data['payment_stages']):
                    if stage.get('stage_name'):
                        due_dt = None
                        if stage.get('due_date'):
                            try: due_dt = datetime.strptime(stage['due_date'], '%Y-%m-%d').date()
                            except: pass
                        QuotationPaymentStage.objects.create(
                            quotation=quotation,
                            stage_name=stage.get('stage_name'),
                            percentage=Decimal(str(stage.get('percentage', 0))),
                            amount=Decimal(str(stage.get('amount', 0))),
                            due_date=due_dt,
                            description=stage.get('description', ''),
                            position=idx
                        )

            if 'terms' in data:
                quotation.terms.all().delete()
                for idx, t in enumerate(data['terms']):
                    if isinstance(t, dict) and t.get('content'):
                        QuotationTerm.objects.create(
                            quotation=quotation,
                            clause_title=t.get('clause_title', ''),
                            content=t.get('content'),
                            position=idx
                        )
                    elif isinstance(t, str) and t.strip():
                        QuotationTerm.objects.create(
                            quotation=quotation,
                            content=t.strip(),
                            position=idx
                        )

            if 'exclusions' in data:
                quotation.exclusions.all().delete()
                for idx, ex in enumerate(data['exclusions']):
                    if isinstance(ex, dict) and ex.get('service_name'):
                        QuotationExclusion.objects.create(
                            quotation=quotation,
                            service_name=ex.get('service_name'),
                            charges_description=ex.get('charges_description', ''),
                            position=idx
                        )

            recalculate_quotation_totals(quotation)
            create_quotation_activity(quotation, profile, 'Edited', f'Updated quotation {quotation.quotation_number} (v{quotation.version}).', request)
            create_quotation_version_snapshot(quotation, profile, f'Updated to version {quotation.version}')

            if request.content_type == 'application/json':
                return JsonResponse({'success': True, 'redirect_url': f'/quotations/{quotation.id}/'})
            return redirect('quotation_detail', quotation_id=quotation.id)

        except Exception as e:
            if request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

    context = {
        'quotation': quotation,
        'leads': leads,
        'services': services,
        'doc_settings': doc_settings,
        'profile': profile,
    }
    return render(request, 'quotations/quotation_form.html', context)


@login_required
@page_permission_required('agreements')
def quotation_detail(request, quotation_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    quotation = get_object_or_404(Quotation, organization=org, id=quotation_id)
    doc_settings = get_or_create_document_settings(org)
    activities = quotation.activities.all()

    context = {
        'quotation': quotation,
        'doc_settings': doc_settings,
        'activities': activities,
        'profile': profile,
    }
    return render(request, 'quotations/quotation_detail.html', context)


@login_required
@page_permission_required('agreements')
def quotation_duplicate(request, quotation_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    orig_q = get_object_or_404(Quotation, organization=org, id=quotation_id)

    new_q_num = generate_next_quotation_number(org)
    new_q = Quotation.objects.create(
        organization=org,
        quotation_number=new_q_num,
        lead=orig_q.lead,
        client_name=orig_q.client_name,
        company_name=orig_q.company_name,
        email=orig_q.email,
        phone=orig_q.phone,
        address=orig_q.address,
        gstin=orig_q.gstin,
        contact_person=orig_q.contact_person,
        lead_source=orig_q.lead_source,
        date=timezone.now().date(),
        valid_until=timezone.now().date() + timedelta(days=10),
        prepared_by=profile,
        salesperson=orig_q.salesperson,
        currency=orig_q.currency,
        payment_terms_summary=orig_q.payment_terms_summary,
        notes=orig_q.notes,
        template_style=orig_q.template_style,
        status='Draft',
        subtotal=orig_q.subtotal,
        discount_amount=orig_q.discount_amount,
        tax_amount=orig_q.tax_amount,
        grand_total=orig_q.grand_total,
        one_time_total=orig_q.one_time_total,
        monthly_recurring_total=orig_q.monthly_recurring_total,
        yearly_recurring_total=orig_q.yearly_recurring_total
    )

    for item in orig_q.items.all():
        QuotationItem.objects.create(
            quotation=new_q,
            section_name=item.section_name,
            service=item.service,
            title=item.title,
            description=item.description,
            pricing_type=item.pricing_type,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=item.unit_price,
            discount=item.discount,
            tax_rate=item.tax_rate,
            line_total=item.line_total,
            is_optional=item.is_optional,
            position=item.position
        )

    for pkg in orig_q.packages.all():
        QuotationPackage.objects.create(
            quotation=new_q,
            package_name=pkg.package_name,
            price=pkg.price,
            billing_frequency=pkg.billing_frequency,
            description=pkg.description,
            deliverables_text=pkg.deliverables_text,
            inclusions_text=pkg.inclusions_text,
            exclusions_text=pkg.exclusions_text,
            terms_text=pkg.terms_text
        )

    for dom in orig_q.domain_options.all():
        QuotationDomainOption.objects.create(
            quotation=new_q,
            domain_name=dom.domain_name,
            period=dom.period,
            price=dom.price,
            is_recommended=dom.is_recommended,
            is_selected=dom.is_selected
        )

    for stg in orig_q.payment_stages.all():
        QuotationPaymentStage.objects.create(
            quotation=new_q,
            stage_name=stg.stage_name,
            percentage=stg.percentage,
            amount=stg.amount,
            due_date=stg.due_date,
            description=stg.description,
            position=stg.position
        )

    for t in orig_q.terms.all():
        QuotationTerm.objects.create(quotation=new_q, clause_title=t.clause_title, content=t.content, position=t.position)
    for ex in orig_q.exclusions.all():
        QuotationExclusion.objects.create(quotation=new_q, service_name=ex.service_name, charges_description=ex.charges_description, position=ex.position)

    create_quotation_activity(new_q, profile, 'Created', f'Duplicated from {orig_q.quotation_number}.', request)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'redirect_url': f'/quotations/{new_q.id}/'})
    return redirect('quotation_detail', quotation_id=new_q.id)


@login_required
@page_permission_required('agreements')
def quotation_update_status(request, quotation_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    quotation = get_object_or_404(Quotation, organization=org, id=quotation_id)

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        new_status = data.get('status')

        if new_status in dict(Quotation.STATUS_CHOICES):
            old_status = quotation.status
            quotation.status = new_status
            quotation.save()
            create_quotation_activity(quotation, profile, 'Status Changed', f'Status changed from {old_status} to {new_status}.', request)

            return JsonResponse({'success': True, 'new_status': new_status})

    return JsonResponse({'success': False, 'error': 'Invalid status update request.'}, status=400)


@login_required
@page_permission_required('agreements')
def quotation_delete(request, quotation_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    quotation = get_object_or_404(Quotation, organization=org, id=quotation_id)

    if request.method == 'POST':
        q_num = quotation.quotation_number
        quotation.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f'Quotation {q_num} deleted.'})
        return redirect('quotation_list')

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@page_permission_required('agreements')
def quotation_convert_to_agreement(request, quotation_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    quotation = get_object_or_404(Quotation, organization=org, id=quotation_id)

    agr_num = generate_next_agreement_number(org)

    scope_lines = []
    deliverable_lines = []
    for item in quotation.items.all():
        scope_lines.append(f"• {item.title}: {item.description or 'Standard service execution'}")
        deliverable_lines.append(f"• {item.title} ({item.quantity} {item.unit})")

    for pkg in quotation.packages.all():
        scope_lines.append(f"• Package: {pkg.package_name} - {pkg.description}")
        if pkg.deliverables_text:
            deliverable_lines.append(f"• {pkg.deliverables_text}")

    scope_str = "\n".join(scope_lines)
    deliverables_str = "\n".join(deliverable_lines)

    pmt_lines = []
    for stage in quotation.payment_stages.all():
        pmt_lines.append(f"• {stage.stage_name}: {stage.percentage}% (₹{stage.amount}) - Due: {stage.due_date or 'On Milestone'}")
    payment_terms_str = "\n".join(pmt_lines) if pmt_lines else quotation.payment_terms_summary

    agreement = Agreement.objects.create(
        organization=org,
        agreement_number=agr_num,
        quotation=quotation,
        lead=quotation.lead,
        date=timezone.now().date(),
        start_date=timezone.now().date(),
        end_date=timezone.now().date() + timedelta(days=365),
        client_name=quotation.client_name,
        company_name=quotation.company_name,
        client_email=quotation.email,
        client_phone=quotation.phone,
        client_address=quotation.address,
        gstin=quotation.gstin,
        agreement_type='Website Development Agreement' if 'Website' in (quotation.items.first().title if quotation.items.exists() else '') else 'Service Agreement',
        project_name=quotation.items.first().title if quotation.items.exists() else 'CRM Digital Service',
        monthly_fee=quotation.monthly_recurring_total,
        advance_payment=quotation.payment_stages.first().amount if quotation.payment_stages.exists() else Decimal('0.00'),
        total_value=quotation.grand_total,
        scope_of_work=scope_str,
        deliverables_text=deliverables_str,
        payment_terms_text=payment_terms_str,
        governing_law='Laws of Telangana, India',
        status='Draft'
    )

    create_quotation_activity(quotation, profile, 'Converted', f'Converted quotation {quotation.quotation_number} into agreement {agreement.agreement_number}.', request)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'agreement_id': agreement.id, 'redirect_url': f'/agreements/{agreement.id}/edit/'})

    return redirect('edit_agreement', agreement_id=agreement.id)


# ==========================================
# PUBLIC CLIENT VIEW & E-SIGNATURE VIEWS
# ==========================================

def public_quotation_view(request, public_token):
    quotation = get_object_or_404(Quotation, public_token=public_token)
    doc_settings = get_or_create_document_settings(quotation.organization)

    if quotation.status in ['Draft', 'Sent']:
        quotation.status = 'Viewed'
        quotation.save()
        create_quotation_activity(quotation, None, 'Viewed', 'Client opened public quotation link.', request)

        for user_prof in UserProfile.objects.filter(organization=quotation.organization):
            SystemNotification.objects.create(
                user=user_prof.user,
                message=f"Client '{quotation.client_name}' viewed quotation {quotation.quotation_number}.",
                type='info'
            )

    context = {
        'quotation': quotation,
        'doc_settings': doc_settings,
        'items': quotation.items.all(),
        'included_items': quotation.items.filter(is_optional=False),
        'optional_items': quotation.items.filter(is_optional=True),
        'packages': quotation.packages.all(),
        'domain_options': quotation.domain_options.all(),
        'payment_stages': quotation.payment_stages.all(),
        'terms': quotation.terms.all(),
        'exclusions': quotation.exclusions.all(),
    }
    return render(request, 'quotations/quotation_public.html', context)


@csrf_exempt
def public_quotation_accept(request, public_token):
    quotation = get_object_or_404(Quotation, public_token=public_token)

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

        client_name = data.get('name') or quotation.client_name
        client_email = data.get('email') or quotation.email

        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        client_ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')

        quotation.status = 'Accepted'
        quotation.accepted_at = timezone.now()
        quotation.accepted_by_name = client_name
        quotation.accepted_by_email = client_email
        quotation.accepted_ip = client_ip
        quotation.save()

        if quotation.lead:
            quotation.lead.status = 'Qualified'
            quotation.lead.is_client = True
            quotation.lead.save()

        create_quotation_activity(quotation, None, 'Accepted', f'Quotation accepted by {client_name} ({client_email}).', request)

        for user_prof in UserProfile.objects.filter(organization=quotation.organization):
            SystemNotification.objects.create(
                user=user_prof.user,
                message=f"🎉 Quotation {quotation.quotation_number} was ACCEPTED by {client_name}!",
                type='success'
            )

        return JsonResponse({
            'success': True,
            'message': 'Quotation accepted successfully!',
            'accepted_at': quotation.accepted_at.strftime('%b %d, %Y %I:%M %p')
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@csrf_exempt
def public_quotation_reject(request, public_token):
    quotation = get_object_or_404(Quotation, public_token=public_token)

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

        reason = data.get('reason', 'Other')
        notes = data.get('notes', '')

        quotation.status = 'Rejected'
        quotation.rejection_reason = reason
        quotation.rejection_notes = notes
        quotation.save()

        create_quotation_activity(quotation, None, 'Rejected', f'Quotation rejected by client. Reason: {reason}. Notes: {notes}', request)

        for user_prof in UserProfile.objects.filter(organization=quotation.organization):
            SystemNotification.objects.create(
                user=user_prof.user,
                message=f"Quotation {quotation.quotation_number} was REJECTED by client ({reason}).",
                type='error'
            )

        return JsonResponse({'success': True, 'message': 'Feedback submitted.'})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


def public_agreement_view(request, public_token):
    agreement = get_object_or_404(Agreement, public_token=public_token)
    doc_settings = get_or_create_document_settings(agreement.organization)

    if agreement.status in ['Draft', 'Sent']:
        agreement.status = 'Viewed'
        agreement.save()

    context = {
        'agreement': agreement,
        'doc_settings': doc_settings,
    }
    return render(request, 'agreements/agreement_public.html', context)


@csrf_exempt
def public_agreement_sign(request, public_token):
    agreement = get_object_or_404(Agreement, public_token=public_token)

    if agreement.status == 'Signed':
        return JsonResponse({'success': False, 'error': 'Agreement is already signed.'}, status=400)

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

        signer_name = data.get('signer_name', agreement.client_name)
        signer_email = data.get('signer_email', agreement.client_email)
        sig_type = data.get('signature_type', 'draw')
        sig_data = data.get('signature_data')

        if not sig_data:
            return JsonResponse({'success': False, 'error': 'Signature data is required.'}, status=400)

        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        client_ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')

        agreement.status = 'Signed'
        agreement.signature_type = sig_type
        agreement.signature_data = sig_data
        agreement.signed_at = timezone.now()
        agreement.signed_by_name = signer_name
        agreement.signed_by_email = signer_email
        agreement.signed_ip = client_ip
        agreement.save()

        if agreement.lead:
            agreement.lead.status = 'Qualified'
            agreement.lead.is_client = True
            agreement.lead.save()

        for user_prof in UserProfile.objects.filter(organization=agreement.organization):
            SystemNotification.objects.create(
                user=user_prof.user,
                message=f"✍️ Agreement {agreement.agreement_number} HAS BEEN SIGNED by {signer_name}!",
                type='success'
            )

        return JsonResponse({
            'success': True,
            'message': 'Agreement signed successfully!',
            'signed_at': agreement.signed_at.strftime('%b %d, %Y %I:%M %p')
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


# ==========================================
# DOCUMENT SETTINGS & TEMPLATES VIEWS
# ==========================================

@login_required
@page_permission_required('settings')
def document_settings_view(request):
    profile = get_user_profile(request.user)
    org = profile.organization
    settings_obj = get_or_create_document_settings(org)

    if request.method == 'POST':
        settings_obj.company_name = request.POST.get('company_name', settings_obj.company_name)
        settings_obj.address = request.POST.get('address', settings_obj.address)
        settings_obj.phone = request.POST.get('phone', settings_obj.phone)
        settings_obj.email = request.POST.get('email', settings_obj.email)
        settings_obj.website = request.POST.get('website', settings_obj.website)
        settings_obj.gstin = request.POST.get('gstin', settings_obj.gstin)
        settings_obj.pan = request.POST.get('pan', settings_obj.pan)
        
        settings_obj.bank_name = request.POST.get('bank_name', settings_obj.bank_name)
        settings_obj.account_name = request.POST.get('account_name', settings_obj.account_name)
        settings_obj.account_number = request.POST.get('account_number', settings_obj.account_number)
        settings_obj.ifsc_code = request.POST.get('ifsc_code', settings_obj.ifsc_code)
        settings_obj.upi_id = request.POST.get('upi_id', settings_obj.upi_id)
        if request.POST.get('opening_balance') is not None and request.POST.get('opening_balance') != '':
            try:
                settings_obj.opening_balance = float(request.POST.get('opening_balance'))
            except (ValueError, TypeError):
                pass
        
        settings_obj.default_currency = request.POST.get('default_currency', settings_obj.default_currency)
        settings_obj.quotation_prefix = request.POST.get('quotation_prefix', settings_obj.quotation_prefix)
        settings_obj.agreement_prefix = request.POST.get('agreement_prefix', settings_obj.agreement_prefix)
        settings_obj.footer_text = request.POST.get('footer_text', settings_obj.footer_text)
        settings_obj.authorized_person_name = request.POST.get('authorized_person_name', settings_obj.authorized_person_name)

        settings_obj.logo_url = request.POST.get('logo_url', '').strip() or None
        settings_obj.authorized_signature_url = request.POST.get('authorized_signature_url', '').strip() or None

        settings_obj.save()
        return redirect('document_settings')

    context = {
        'settings': settings_obj,
        'profile': profile,
    }
    return render(request, 'documents/document_settings.html', context)


@login_required
@page_permission_required('settings')
def document_templates_view(request):
    profile = get_user_profile(request.user)
    org = profile.organization
    templates = DocumentTemplate.objects.filter(organization=org)

    if request.method == 'POST':
        cat = request.POST.get('category', 'quotation')
        title = request.POST.get('title')
        desc = request.POST.get('description', '')
        content = request.POST.get('content_json', '{}')

        DocumentTemplate.objects.create(
            organization=org,
            category=cat,
            title=title,
            description=desc,
            content_json=content,
            is_default=bool(request.POST.get('is_default'))
        )
        return redirect('document_templates')

    context = {
        'templates': templates,
        'profile': profile,
    }
    return render(request, 'documents/document_templates.html', context)


@login_required
@page_permission_required('settings')
def document_template_delete(request, template_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    tmpl = get_object_or_404(DocumentTemplate, organization=org, id=template_id)
    tmpl.delete()
    return redirect('document_templates')


# ==========================================
# LEAD TO CLIENT CONVERSION VIEW
# ==========================================

@login_required
@page_permission_required('leads')
def convert_lead_to_client(request, lead_id):
    profile = get_user_profile(request.user)
    org = profile.organization
    lead = get_object_or_404(Lead, organization=org, id=lead_id)

    lead.is_client = True
    lead.status = 'Qualified'
    lead.stage = 'Won'
    lead.save()

    SystemNotification.objects.create(
        user=profile.user,
        message=f"Lead '{lead.name}' ({lead.company}) was successfully converted to a CLIENT!",
        type='success'
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Lead converted to Client successfully.'})

    return redirect('client_contact_detail', lead_id=lead.id)
