from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
from core.models import Organization, UserProfile, StatusStyleMixin


class FinancePaymentMethod(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='finance_payment_methods')
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'crm_financepaymentmethod'

    def __str__(self):
        return self.name


class FinanceExpenseCategory(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='finance_expense_categories')
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'crm_financeexpensecategory'

    def __str__(self):
        return self.name


class FinancePaymentStatus(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='finance_payment_statuses')
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'crm_financepaymentstatus'

    def __str__(self):
        return self.name


class FinanceCommissionType(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='finance_commission_types')
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'crm_financecommissiontype'

    def __str__(self):
        return self.name


class Income(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='incomes')
    date = models.DateField()
    client_name = models.CharField(max_length=255)
    project_name = models.CharField(max_length=255, blank=True, null=True)
    payment_method = models.ForeignKey(FinancePaymentMethod, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'incomes'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.client_name} - {self.amount}"


class Expense(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='expenses')
    date = models.DateField()
    category = models.ForeignKey(FinanceExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    cost_center = models.CharField(max_length=150, blank=True, null=True)
    payment_method = models.ForeignKey(FinancePaymentMethod, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.category} - {self.amount}"


class DeletedIncome(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='deleted_incomes')
    original_id = models.IntegerField(null=True, blank=True)
    date = models.DateField()
    client_name = models.CharField(max_length=255)
    project_name = models.CharField(max_length=255, blank=True, null=True)
    payment_method_name = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    deleted_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'deleted_incomes'
        ordering = ['-deleted_at']

    def __str__(self):
        return f"[DELETED] {self.client_name} - {self.amount}"


class DeletedExpense(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='deleted_expenses')
    original_id = models.IntegerField(null=True, blank=True)
    date = models.DateField()
    category_name = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    cost_center = models.CharField(max_length=150, blank=True, null=True)
    payment_method_name = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    deleted_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'deleted_expenses'
        ordering = ['-deleted_at']

    def __str__(self):
        return f"[DELETED] {self.category_name or 'Expense'} - {self.amount}"


class PartnerPayout(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='partner_payouts')
    payout_id = models.CharField(max_length=50)
    partner_name = models.CharField(max_length=255)
    project_client = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.ForeignKey(FinancePaymentMethod, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.ForeignKey(FinancePaymentStatus, on_delete=models.SET_NULL, null=True, blank=True)
    commission_type = models.ForeignKey(FinanceCommissionType, on_delete=models.SET_NULL, null=True, blank=True)
    payout_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'partner_payouts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payout_id} - {self.partner_name} - {self.status}"


class DocumentSettings(models.Model):
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='document_settings')
    company_name = models.CharField(max_length=255, default='Xenotrix Technologies')
    logo_url = models.URLField(max_length=1000, blank=True, null=True)
    address = models.TextField(default='123 Tech Park, Suite 400, Hyderabad, Telangana, India')
    phone = models.CharField(max_length=50, default='+91 98765 43210')
    email = models.EmailField(default='contact@xenotrix.in')
    website = models.URLField(default='https://xenotrix.in')
    gstin = models.CharField(max_length=50, blank=True, null=True, default='36AAAAA0000A1Z5')
    pan = models.CharField(max_length=50, blank=True, null=True, default='ABCDE1234F')
    
    bank_name = models.CharField(max_length=255, blank=True, null=True, default='HDFC Bank')
    account_name = models.CharField(max_length=255, blank=True, null=True, default='Xenotrix Technologies Pvt Ltd')
    account_number = models.CharField(max_length=100, blank=True, null=True, default='50200012345678')
    ifsc_code = models.CharField(max_length=50, blank=True, null=True, default='HDFC0001234')
    upi_id = models.CharField(max_length=100, blank=True, null=True, default='xenotrix@hdfcbank')
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    default_currency = models.CharField(max_length=10, default='INR')
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    quotation_prefix = models.CharField(max_length=20, default='XT-QT')
    agreement_prefix = models.CharField(max_length=20, default='XT-AGR')
    next_quotation_number = models.IntegerField(default=1)
    next_agreement_number = models.IntegerField(default=1)
    
    LOGO_CHOICES = [
        ('asset', 'Default Xenotrix Logo (static/images/xenotrix.png)'),
        ('upload', 'Uploaded Logo File'),
        ('url', 'Custom Logo URL'),
    ]
    SEAL_CHOICES = [
        ('asset', 'Default Company Seal (static/images/seal.png)'),
        ('upload', 'Uploaded Seal File'),
        ('url', 'Custom Seal URL'),
        ('none', 'No Seal'),
    ]

    logo_choice = models.CharField(max_length=20, choices=LOGO_CHOICES, default='asset')
    logo_file = models.FileField(upload_to='branding/', blank=True, null=True)
    seal_choice = models.CharField(max_length=20, choices=SEAL_CHOICES, default='asset')
    seal_url = models.URLField(max_length=1000, blank=True, null=True)
    seal_file = models.FileField(upload_to='branding/', blank=True, null=True)
    signature_file = models.FileField(upload_to='branding/', blank=True, null=True)
    
    footer_text = models.TextField(default='Thank you for choosing Xenotrix Technologies. For any queries, contact info@xenotrix.in.')
    authorized_person_name = models.CharField(max_length=255, default='Authorized Signatory')
    authorized_signature_url = models.URLField(max_length=1000, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'document_settings'

    def __str__(self):
        return f"Document Settings - {self.company_name}"

    @property
    def effective_logo_url(self):
        if self.logo_choice == 'upload' and self.logo_file:
            return self.logo_file.url
        elif self.logo_choice == 'url' and self.logo_url:
            return self.logo_url
        elif self.logo_url:
            return self.logo_url
        return '/static/images/xenotrix.png'

    @property
    def effective_seal_url(self):
        if self.seal_choice == 'none':
            return None
        elif self.seal_choice == 'upload' and self.seal_file:
            return self.seal_file.url
        elif self.seal_choice == 'url' and self.seal_url:
            return self.seal_url
        elif self.seal_url:
            return self.seal_url
        elif self.seal_choice == 'asset':
            return '/static/images/seal.png'
        return '/static/images/seal.png'

    @property
    def effective_signature_url(self):
        if self.signature_file:
            return self.signature_file.url
        if self.authorized_signature_url:
            return self.authorized_signature_url
        return '/static/images/signature.png'


class DocumentTemplate(models.Model):
    CATEGORY_CHOICES = [
        ('quotation', 'Quotation Template'),
        ('agreement', 'Agreement Template'),
        ('terms', 'Terms & Conditions Template'),
        ('payment', 'Payment Terms Template'),
        ('exclusion', 'Exclusions Template'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='document_templates')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    content_json = models.TextField(default='{}')
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'document_templates'
        ordering = ['category', '-is_default', 'title']

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"


class Quotation(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Viewed', 'Viewed'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Expired', 'Expired'),
        ('Cancelled', 'Cancelled'),
    ]

    TEMPLATE_CHOICES = [
        ('default', 'Xenotrix Standard'),
        ('corporate', 'Professional Corporate'),
        ('minimal', 'Minimalist Clean'),
        ('modern', 'Modern Visual'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='quotations')
    quotation_number = models.CharField(max_length=50, unique=True)
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='quotations')
    
    project_title = models.CharField(max_length=255, default='Project Proposal', blank=True)
    client_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    alt_phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True, default='India')
    gstin = models.CharField(max_length=50, blank=True, null=True)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    lead_source = models.CharField(max_length=100, blank=True, null=True)
    
    date = models.DateField(default=timezone.now)
    valid_until = models.DateField()
    prepared_by = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='prepared_quotations')
    salesperson = models.CharField(max_length=255, blank=True, null=True)
    currency = models.CharField(max_length=10, default='INR')
    payment_terms_summary = models.CharField(max_length=255, blank=True, null=True, default='50% Advance / 50% Completion')
    notes = models.TextField(blank=True, null=True)
    template_style = models.CharField(max_length=50, choices=TEMPLATE_CHOICES, default='default')
    
    # Dynamic Section Text Fields
    objective_text = models.TextField(blank=True, null=True)
    deliverables_summary_text = models.TextField(blank=True, null=True)
    success_metrics_text = models.TextField(blank=True, null=True)
    declaration_text = models.TextField(blank=True, null=True)
    sections_data_json = models.TextField(default='[]')
    show_bank_details = models.BooleanField(default=False)
    
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Draft')
    public_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    version = models.IntegerField(default=1)
    
    # Financial Totals & Discounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_type = models.CharField(max_length=20, default='fixed')  # 'fixed' or 'percentage'
    discount_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    one_time_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    monthly_recurring_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    yearly_recurring_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    rejection_reason = models.CharField(max_length=255, blank=True, null=True)
    rejection_notes = models.TextField(blank=True, null=True)
    accepted_at = models.DateTimeField(blank=True, null=True)
    accepted_by_name = models.CharField(max_length=255, blank=True, null=True)
    accepted_by_email = models.EmailField(blank=True, null=True)
    accepted_ip = models.CharField(max_length=50, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'quotations'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.quotation_number} - {self.client_name}"

    def save(self, *args, **kwargs):
        if not self.public_token:
            self.public_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        if self.status not in ['Accepted', 'Rejected', 'Cancelled'] and self.valid_until:
            return timezone.now().date() > self.valid_until
        return False


class QuotationSection(models.Model):
    SECTION_TYPES = [
        ('objective', 'Project Objective'),
        ('deliverables', 'Deliverables Summary'),
        ('pricing_table', 'Pricing & Services Table'),
        ('milestones', 'Development & Delivery Schedule'),
        ('terms', 'Commercial Terms & Conditions'),
        ('exclusions', 'Third-Party Charges & Exclusions'),
        ('success_metrics', 'What Success Looks Like'),
        ('declaration', 'Declaration & Acceptance'),
        ('important_notes', 'Important Notes'),
        ('custom_text', 'Custom Section'),
    ]

    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='sections')
    section_type = models.CharField(max_length=50, choices=SECTION_TYPES, default='custom_text')
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, null=True)
    position = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)

    class Meta:
        db_table = 'quotation_sections'
        ordering = ['position', 'id']

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.title}"


class QuotationItem(models.Model):
    PRICING_TYPES = [
        ('fixed', 'Fixed Price'),
        ('monthly', 'Monthly Recurring'),
        ('yearly', 'Yearly Recurring'),
        ('one_time', 'One-time Price'),
        ('custom', 'Custom Pricing'),
    ]

    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items')
    section_name = models.CharField(max_length=255, default='Services')
    service = models.ForeignKey('services.Service', on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    deliverables = models.TextField(blank=True, null=True)
    features = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    pricing_type = models.CharField(max_length=50, choices=PRICING_TYPES, default='fixed')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    unit = models.CharField(max_length=50, default='Item')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_type = models.CharField(max_length=20, default='fixed')
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_optional = models.BooleanField(default=False)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'quotation_items'
        ordering = ['position', 'id']

    def __str__(self):
        return f"{self.title} - {self.line_total}"


class QuotationPackage(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='packages')
    package_name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    billing_frequency = models.CharField(max_length=50, default='Monthly')
    description = models.TextField(blank=True, null=True)
    deliverables_text = models.TextField(blank=True, null=True)
    inclusions_text = models.TextField(blank=True, null=True)
    exclusions_text = models.TextField(blank=True, null=True)
    terms_text = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'quotation_packages'

    def __str__(self):
        return f"{self.package_name} - {self.price}/{self.billing_frequency}"


class QuotationDomainOption(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='domain_options')
    domain_name = models.CharField(max_length=255)
    period = models.CharField(max_length=50, default='3 Years')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_recommended = models.BooleanField(default=False)
    is_selected = models.BooleanField(default=False)

    class Meta:
        db_table = 'quotation_domain_options'

    def __str__(self):
        return f"{self.domain_name} - ₹{self.price}"


class QuotationPaymentStage(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='payment_stages')
    stage_name = models.CharField(max_length=255)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    due_date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'quotation_payment_stages'
        ordering = ['position', 'id']

    def __str__(self):
        return f"{self.stage_name} ({self.percentage}%)"


class QuotationTerm(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='terms')
    clause_title = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField()
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'quotation_terms'
        ordering = ['position', 'id']

    def __str__(self):
        return self.clause_title or self.content[:30]


class QuotationExclusion(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='exclusions')
    service_name = models.CharField(max_length=255)
    charges_description = models.CharField(max_length=255)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'quotation_exclusions'
        ordering = ['position', 'id']

    def __str__(self):
        return f"{self.service_name} - {self.charges_description}"


class QuotationActivity(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True)
    activity_type = models.CharField(max_length=100)
    description = models.TextField()
    ip_address = models.CharField(max_length=50, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quotation_activities'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.activity_type}"


class QuotationVersion(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    data_snapshot_json = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    change_summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quotation_versions'
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.quotation.quotation_number} v{self.version_number}"


class InvoiceStatus(models.Model, StatusStyleMixin):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invoice_statuses')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20, default='#64748b')
    position = models.IntegerField(default=0)

    class Meta:
        unique_together = ('organization', 'name')
        ordering = ['position', 'id']
        db_table = 'invoice_statuses'

    def __str__(self):
        return self.name


class Invoice(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invoices')
    customer_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    email_address = models.EmailField(blank=True, null=True)
    billing_address = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=100, blank=True, null=True)
    
    invoice_number = models.CharField(max_length=100, unique=True)
    invoice_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=50, default='Pending')
    currency = models.CharField(max_length=10, default='INR')
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    extra_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    shipping_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    initial_amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    bank_account_details = models.TextField(blank=True, null=True)
    upi_id = models.CharField(max_length=100, blank=True, null=True)
    payment_notes = models.TextField(blank=True, null=True)
    
    notes = models.TextField(blank=True, null=True)
    terms_conditions = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'invoices'
        ordering = ['-invoice_date', '-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.customer_name}"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    class Meta:
        db_table = 'invoice_items'

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.product_name}"
