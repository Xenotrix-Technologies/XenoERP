import json
import datetime
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Sum, Count, Q

from core.models import Organization, UserProfile
from core.utils import get_or_create_dynamic_statuses
from .models import Invoice, InvoiceItem, InvoiceStatus


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


def get_invoice_stats(organization):
    invoices = Invoice.objects.filter(organization=organization)
    total_invoices = invoices.count()
    paid_invoices = invoices.filter(status__iexact='Paid').count()
    pending_invoices = invoices.filter(
        Q(status__iexact='Pending') | Q(status__iexact='Draft') | Q(status__iexact='Partial') | Q(status__iexact='Unpaid')
    ).count()
    overdue_invoices = invoices.filter(status__iexact='Overdue').count()

    total_amount = float(invoices.aggregate(total=Sum('grand_total'))['total'] or 0.00)
    
    paid_amount = 0.0
    pending_amount = 0.0
    overdue_amount = 0.0

    for inv in invoices:
        st = inv.status.strip().lower() if inv.status else ''
        if st == 'paid':
            paid_amount += float(inv.amount_paid if inv.amount_paid > 0 else inv.grand_total)
        else:
            paid_amount += float(inv.amount_paid or 0.0)
            if inv.balance_due > 0 or inv.amount_paid > 0:
                pending_amount += float(inv.balance_due)
            else:
                pending_amount += float(inv.grand_total)
            
            if st == 'overdue':
                overdue_amount += float(inv.balance_due if inv.balance_due > 0 else inv.grand_total)

    return {
        'total': total_invoices,
        'paid': paid_invoices,
        'pending': pending_invoices,
        'overdue': overdue_invoices,
        'total_amount': f"{total_amount:.2f}",
        'paid_amount': f"{paid_amount:.2f}",
        'pending_amount': f"{pending_amount:.2f}",
        'overdue_amount': f"{overdue_amount:.2f}",
    }


@login_required
def invoice_dashboard(request):
    user_profile = get_user_profile(request.user)
    organization = user_profile.organization
    
    invoices = Invoice.objects.filter(organization=organization).order_by('-invoice_date')
    stats = get_invoice_stats(organization)
    
    current_month = timezone.now().month
    current_year = timezone.now().year
    monthly_revenue = invoices.filter(status__iexact='Paid', invoice_date__year=current_year, invoice_date__month=current_month).aggregate(total=Sum('grand_total'))['total'] or 0.00
    invoice_statuses = get_or_create_dynamic_statuses(organization, 'invoices', InvoiceStatus)
    
    context = {
        'invoices': invoices,
        'total_invoices': stats['total'],
        'paid_invoices': stats['paid'],
        'pending_invoices': stats['pending'],
        'overdue_invoices': stats['overdue'],
        'total_amount': stats['total_amount'],
        'paid_amount': stats['paid_amount'],
        'pending_amount': stats['pending_amount'],
        'overdue_amount': stats['overdue_amount'],
        'monthly_revenue': monthly_revenue,
        'profile': user_profile,
        'invoice_statuses': invoice_statuses,
    }
    return render(request, 'finance/invoice_dashboard.html', context)


@login_required
def invoice_create(request):
    user_profile = get_user_profile(request.user)
    organization = user_profile.organization
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            raw_status = data.get('status')
            status_val = raw_status.strip() if raw_status else 'Pending'

            grand_total = float(data.get('grand_total') or 0)
            amount_paid = float(data.get('amount_paid') or 0)
            raw_balance = data.get('balance_due')
            if raw_balance is not None and str(raw_balance).strip() != '':
                balance_due = float(raw_balance)
            else:
                balance_due = max(0.0, grand_total - amount_paid)

            if status_val.lower() == 'paid':
                if amount_paid == 0:
                    amount_paid = grand_total
                balance_due = 0.0
                initial_amount_paid = 0.0
            else:
                initial_amount_paid = amount_paid

            with transaction.atomic():
                invoice = Invoice.objects.create(
                    organization=organization,
                    customer_name=data.get('customer_name', ''),
                    company_name=data.get('company_name', ''),
                    phone_number=data.get('phone_number', ''),
                    email_address=data.get('email_address', ''),
                    billing_address=data.get('billing_address', ''),
                    gst_number=data.get('gst_number', ''),
                    invoice_number=data.get('invoice_number') or f"INV-{Invoice.objects.filter(organization=organization).count() + 1:06d}",
                    invoice_date=data.get('invoice_date') or timezone.now().date(),
                    due_date=data.get('due_date') or timezone.now().date(),
                    status=status_val,
                    currency=data.get('currency', 'USD'),
                    subtotal=float(data.get('subtotal') or 0),
                    total_tax=float(data.get('total_tax') or 0),
                    total_discount=float(data.get('total_discount') or 0),
                    extra_discount=float(data.get('extra_discount') or 0),
                    shipping_charge=float(data.get('shipping_charge') or 0),
                    grand_total=grand_total,
                    amount_paid=amount_paid,
                    initial_amount_paid=initial_amount_paid,
                    balance_due=balance_due,
                    payment_method=data.get('payment_method', ''),
                    bank_account_details=data.get('bank_account_details', ''),
                    upi_id=data.get('upi_id', ''),
                    payment_notes=data.get('payment_notes', ''),
                    notes=data.get('notes', ''),
                    terms_conditions=data.get('terms_conditions', '')
                )
                
                items = data.get('items', [])
                for item in items:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        product_name=item.get('product_name', ''),
                        description=item.get('description', ''),
                        quantity=float(item.get('quantity') or 1),
                        unit_price=float(item.get('unit_price') or 0),
                        tax_percentage=float(item.get('tax_percentage') or 0),
                        discount_amount=float(item.get('discount_amount') or 0),
                        line_total=float(item.get('line_total') or 0)
                    )
            
            return JsonResponse({'success': True, 'invoice_id': invoice.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    invoice_count = Invoice.objects.filter(organization=organization).count()
    default_inv_number = f"INV-{invoice_count + 1:06d}"
    invoice_statuses = get_or_create_dynamic_statuses(organization, 'invoices', InvoiceStatus)
    
    return render(request, 'finance/invoice_form.html', {
        'profile': user_profile,
        'default_inv_number': default_inv_number,
        'today': timezone.now().date().isoformat(),
        'invoice_statuses': invoice_statuses,
    })


@login_required
def invoice_detail(request, invoice_id):
    user_profile = get_user_profile(request.user)
    invoice = get_object_or_404(Invoice, id=invoice_id, organization=user_profile.organization)
    
    return render(request, 'finance/invoice_detail.html', {
        'invoice': invoice,
        'profile': user_profile
    })


@login_required
def invoice_edit(request, invoice_id):
    user_profile = get_user_profile(request.user)
    organization = user_profile.organization
    invoice = get_object_or_404(Invoice, id=invoice_id, organization=organization)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            with transaction.atomic():
                invoice.customer_name = data.get('customer_name', '')
                invoice.company_name = data.get('company_name', '')
                invoice.phone_number = data.get('phone_number', '')
                invoice.email_address = data.get('email_address', '')
                invoice.billing_address = data.get('billing_address', '')
                invoice.gst_number = data.get('gst_number', '')
                invoice.invoice_date = data.get('invoice_date') or invoice.invoice_date
                invoice.due_date = data.get('due_date') or invoice.due_date
                
                raw_status = data.get('status')
                if raw_status:
                    invoice.status = raw_status.strip()
                
                invoice.subtotal = float(data.get('subtotal') or 0)
                invoice.total_tax = float(data.get('total_tax') or 0)
                invoice.total_discount = float(data.get('total_discount') or 0)
                invoice.extra_discount = float(data.get('extra_discount') or 0)
                invoice.shipping_charge = float(data.get('shipping_charge') or 0)
                invoice.grand_total = float(data.get('grand_total') or 0)
                invoice.amount_paid = float(data.get('amount_paid') or 0)
                
                raw_balance = data.get('balance_due')
                if raw_balance is not None and str(raw_balance).strip() != '':
                    invoice.balance_due = float(raw_balance)
                else:
                    invoice.balance_due = max(0.0, invoice.grand_total - invoice.amount_paid)

                if invoice.status and invoice.status.strip().lower() == 'paid':
                    if (not invoice.initial_amount_paid or invoice.initial_amount_paid == 0) and invoice.amount_paid > 0 and invoice.amount_paid < invoice.grand_total:
                        invoice.initial_amount_paid = invoice.amount_paid
                    invoice.amount_paid = invoice.grand_total
                    invoice.balance_due = 0.0
                else:
                    invoice.initial_amount_paid = invoice.amount_paid

                invoice.payment_method = data.get('payment_method', '')
                invoice.bank_account_details = data.get('bank_account_details', '')
                invoice.upi_id = data.get('upi_id', '')
                invoice.payment_notes = data.get('payment_notes', '')
                invoice.notes = data.get('notes', '')
                invoice.terms_conditions = data.get('terms_conditions', '')
                invoice.save()
                
                invoice.items.all().delete()
                
                items = data.get('items', [])
                for item in items:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        product_name=item.get('product_name', ''),
                        description=item.get('description', ''),
                        quantity=float(item.get('quantity') or 1),
                        unit_price=float(item.get('unit_price') or 0),
                        tax_percentage=float(item.get('tax_percentage') or 0),
                        discount_amount=float(item.get('discount_amount') or 0),
                        line_total=float(item.get('line_total') or 0)
                    )
            
            return JsonResponse({'success': True, 'invoice_id': invoice.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    invoice_statuses = get_or_create_dynamic_statuses(organization, 'invoices', InvoiceStatus)
    
    return render(request, 'finance/invoice_form.html', {
        'profile': user_profile,
        'invoice': invoice,
        'invoice_statuses': invoice_statuses,
    })


@login_required
def invoice_delete(request, invoice_id):
    user_profile = get_user_profile(request.user)
    invoice = get_object_or_404(Invoice, id=invoice_id, organization=user_profile.organization)
    
    if request.method == 'POST':
        invoice.delete()
        return redirect('invoice_dashboard')
    
    return redirect('invoice_dashboard')


@login_required
def invoice_update_status(request, invoice_id):
    if request.method == 'POST':
        user_profile = get_user_profile(request.user)
        invoice = get_object_or_404(Invoice, id=invoice_id, organization=user_profile.organization)
        try:
            data = json.loads(request.body)
            new_status = data.get('status')
            if new_status:
                new_status_str = new_status.strip()
                invoice.status = new_status_str
                update_fields = ['status']
                
                if new_status_str.lower() == 'paid':
                    if (not invoice.initial_amount_paid or invoice.initial_amount_paid == 0) and invoice.amount_paid > 0 and invoice.amount_paid < invoice.grand_total:
                        invoice.initial_amount_paid = invoice.amount_paid
                        update_fields.append('initial_amount_paid')
                    
                    invoice.amount_paid = invoice.grand_total
                    invoice.balance_due = 0.00
                    update_fields.extend(['amount_paid', 'balance_due'])
                
                invoice.save(update_fields=list(set(update_fields)))
                
                stats = get_invoice_stats(user_profile.organization)
                return JsonResponse({
                    'success': True,
                    'stats': stats,
                    'balance_due': f"{invoice.balance_due:.2f}",
                    'amount_paid': f"{invoice.amount_paid:.2f}",
                    'status': invoice.status
                })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

