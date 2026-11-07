from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from core.models import Organization
from leads.models import Lead
from services.models import Service
from projects.models import Agreement
from finance.models import (
    DocumentSettings, Quotation, QuotationItem, QuotationPackage, QuotationDomainOption,
    QuotationPaymentStage, QuotationTerm, QuotationExclusion, QuotationActivity, DocumentTemplate
)


class Command(BaseCommand):
    help = 'Seeds sample Quotation and Agreement demo data (Veta Spoken English Academy)'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding Document Management sample data...")

        org, _ = Organization.objects.get_or_create(name='Xenotrix Technologies')

        # 1. Ensure Document Settings exist
        doc_settings, _ = DocumentSettings.objects.get_or_create(
            organization=org,
            defaults={
                'company_name': 'Xenotrix Technologies',
                'address': '123 Tech Park, Suite 400, Hyderabad, Telangana, India',
                'phone': '+91 98765 43210',
                'email': 'contact@xenotrix.in',
                'website': 'https://xenotrix.in',
                'gstin': '36AAAAA0000A1Z5',
                'pan': 'ABCDE1234F',
                'bank_name': 'HDFC Bank',
                'account_name': 'Xenotrix Technologies Pvt Ltd',
                'account_number': '50200012345678',
                'ifsc_code': 'HDFC0001234',
                'upi_id': 'xenotrix@hdfcbank',
                'opening_balance': Decimal('0.00'),
                'quotation_prefix': 'XT-QT',
                'agreement_prefix': 'XT-AGR',
                'footer_text': 'Thank you for choosing Xenotrix Technologies. For any queries, contact info@xenotrix.in.',
                'authorized_person_name': 'Sanju (Authorized Signatory)',
            }
        )

        # 2. Create or fetch demo lead Veta Spoken English Academy
        lead, _ = Lead.objects.get_or_create(
            organization=org,
            name='Veta Spoken English Academy',
            defaults={
                'company': 'Veta Academy Pvt Ltd',
                'email': 'contact@vetaenglish.in',
                'phone_number': '+91 98765 12345',
                'location': 'Ameerpet, Hyderabad, Telangana - 500016',
                'status': 'Qualified',
                'score': 85,
                'value': Decimal('13799.00'),
                'is_client': True
            }
        )

        # 3. Create Quotation XT-QT-2026-0001
        quotation, created = Quotation.objects.get_or_create(
            organization=org,
            quotation_number='XT-QT-2026-0001',
            defaults={
                'lead': lead,
                'client_name': 'Veta Spoken English Academy',
                'company_name': 'Veta Academy Pvt Ltd',
                'email': 'contact@vetaenglish.in',
                'phone': '+91 98765 12345',
                'address': 'Ameerpet, Hyderabad, Telangana - 500016',
                'gstin': '36ABCDE1234F1Z9',
                'salesperson': 'Sanju',
                'date': timezone.now().date(),
                'valid_until': timezone.now().date() + timedelta(days=10),
                'currency': 'INR',
                'payment_terms_summary': '30% Advance / 40% Second / 30% Final',
                'template_style': 'default',
                'status': 'Sent',
                'subtotal': Decimal('13799.00'),
                'grand_total': Decimal('13799.00'),
                'one_time_total': Decimal('13799.00'),
                'monthly_recurring_total': Decimal('18000.00'),
            }
        )

        if created:
            # Add Included Line Items
            QuotationItem.objects.create(
                quotation=quotation,
                section_name='Website Development',
                title='Business Website Development',
                description='Responsive 5-page business website with contact form & SEO setup',
                pricing_type='fixed',
                quantity=Decimal('1.00'),
                unit='Project',
                unit_price=Decimal('12000.00'),
                line_total=Decimal('12000.00'),
                is_optional=False,
                position=0
            )

            QuotationItem.objects.create(
                quotation=quotation,
                section_name='Domain',
                title='Domain Registration – 3 Years',
                description='vetaspoken.in 3-year domain registration & DNS setup',
                pricing_type='one_time',
                quantity=Decimal('1.00'),
                unit='Domain',
                unit_price=Decimal('1799.00'),
                line_total=Decimal('1799.00'),
                is_optional=False,
                position=1
            )

            # Add Optional Items
            QuotationItem.objects.create(
                quotation=quotation,
                section_name='Optional Services',
                title='Google Maps Integration',
                description='Location map integration on contact page',
                pricing_type='fixed',
                quantity=Decimal('1.00'),
                unit='Setup',
                unit_price=Decimal('500.00'),
                line_total=Decimal('500.00'),
                is_optional=True,
                position=2
            )

            QuotationItem.objects.create(
                quotation=quotation,
                section_name='Optional Services',
                title='Additional Website Page',
                description='Custom content page design',
                pricing_type='fixed',
                quantity=Decimal('1.00'),
                unit='Page',
                unit_price=Decimal('750.00'),
                line_total=Decimal('750.00'),
                is_optional=True,
                position=3
            )

            # Add Starter Growth Package (Recurring ₹18,000/mo)
            QuotationPackage.objects.create(
                quotation=quotation,
                package_name='Starter Growth Package',
                price=Decimal('18000.00'),
                billing_frequency='Monthly',
                description='Full social media management and brand growth activities',
                deliverables_text='10 Social Media Posts, 8 Ad Creatives, Social Media Management, Content Planning, Monthly Performance Report, Brand Awareness Activities',
                inclusions_text='Design, Copywriting, Scheduling, Monthly Analytics',
                exclusions_text='Paid Advertising Ad Spend'
            )

            # Add Domain Choices
            QuotationDomainOption.objects.create(
                quotation=quotation,
                domain_name='vetaspokenenglish.com',
                period='3-Year Registration',
                price=Decimal('3199.00'),
                is_recommended=True,
                is_selected=False
            )
            QuotationDomainOption.objects.create(
                quotation=quotation,
                domain_name='vetaspoken.in',
                period='3-Year Registration',
                price=Decimal('1799.00'),
                is_recommended=False,
                is_selected=True
            )

            # Add Payment Milestones: 30% = ₹5,400, 40% = ₹7,200, 30% = ₹5,400
            QuotationPaymentStage.objects.create(
                quotation=quotation,
                stage_name='30% Advance Payment',
                percentage=Decimal('30.00'),
                amount=Decimal('5400.00'),
                description='Upon signing quotation',
                position=0
            )
            QuotationPaymentStage.objects.create(
                quotation=quotation,
                stage_name='40% Second Payment',
                percentage=Decimal('40.00'),
                amount=Decimal('7200.00'),
                description='Upon design approval',
                position=1
            )
            QuotationPaymentStage.objects.create(
                quotation=quotation,
                stage_name='30% Final Payment',
                percentage=Decimal('30.00'),
                amount=Decimal('5400.00'),
                description='Before final website launch',
                position=2
            )

            # Terms
            QuotationTerm.objects.create(quotation=quotation, content='This quotation is valid for 10 days.', position=0)
            QuotationTerm.objects.create(quotation=quotation, content='The Starter Growth Package is billed at ₹18,000 per month.', position=1)
            QuotationTerm.objects.create(quotation=quotation, content='Payment will follow the agreed 30%-40%-30% structure.', position=2)
            QuotationTerm.objects.create(quotation=quotation, content='Paid advertising spend is not included.', position=3)
            QuotationTerm.objects.create(quotation=quotation, content='Additional services will be charged separately.', position=4)

            # Exclusions
            QuotationExclusion.objects.create(quotation=quotation, service_name='Premium Plugins', charges_description='At actual cost + setup', position=0)
            QuotationExclusion.objects.create(quotation=quotation, service_name='Paid APIs', charges_description='At actual cost + integration', position=1)
            QuotationExclusion.objects.create(quotation=quotation, service_name='Professional Photography', charges_description='Starting from ₹3,000/session', position=2)

            # Activity log
            QuotationActivity.objects.create(
                quotation=quotation,
                activity_type='Created',
                description='Quotation XT-QT-2026-0001 seeded for Veta Spoken English Academy.'
            )

        # 4. Create Agreement XT-AGR-2026-0001
        Agreement.objects.get_or_create(
            organization=org,
            agreement_number='XT-AGR-2026-0001',
            defaults={
                'quotation': quotation,
                'lead': lead,
                'date': timezone.now().date(),
                'start_date': timezone.now().date(),
                'end_date': timezone.now().date() + timedelta(days=365),
                'client_name': 'Veta Spoken English Academy',
                'company_name': 'Veta Academy Pvt Ltd',
                'client_email': 'contact@vetaenglish.in',
                'client_phone': '+91 98765 12345',
                'client_address': 'Ameerpet, Hyderabad, Telangana - 500016',
                'agreement_type': 'Digital Marketing & Website Agreement',
                'project_name': 'Veta Spoken English Website & Growth Package',
                'monthly_fee': Decimal('18000.00'),
                'advance_payment': Decimal('5400.00'),
                'total_value': Decimal('13799.00'),
                'scope_of_work': '• Business Website Development (5-page responsive site)\n• 3-Year Domain Registration (vetaspoken.in)\n• Starter Growth Package (18,000/month)',
                'deliverables_text': 'Website, Domain, 10 Social Media Posts, 8 Ad Creatives, Content Plan, Monthly Reports',
                'payment_terms_text': '30% Advance (₹5,400)\n40% Second Payment (₹7,200)\n30% Final Payment (₹5,400)',
                'status': 'Draft'
            }
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded Veta Spoken English Academy demo quotation & agreement data!"))
