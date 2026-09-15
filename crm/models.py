from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

# Re-export core domain models
from core.models import (
    Organization, Department, StaffRole, UserProfile, SystemNotification
)

# Re-export lead domain models
from leads.models import (
    LeadStatus, Lead, get_default_badge_class
)

# Re-export service domain models
from services.models import (
    Service
)

# Re-export support domain models
from support.models import (
    StatusStyleMixin, TicketStatus, PriorityStatus, Ticket
)

# Re-export project domain models
from projects.models import (
    ClientStatus, ProjectStatus, Agreement, AgreementVersion,
    AgreementService, ClientResponsibility, Deliverable
)

# Re-export activity domain models
from activities.models import (
    CalendarStatus, Activity, WhatsAppMessage, Task, TaskTodo, TaskFile, TaskMilestone, TaskComment, Meeting, Event
)

# Re-export campaign domain models
from campaigns.models import (
    CampaignStatus, Campaign
)

# Re-export content domain models
from content_tracker.models import (
    ContentItem, ContentDropdownOption
)

# Re-export finance domain models
from finance.models import (
    FinancePaymentMethod, FinanceExpenseCategory, FinancePaymentStatus, FinanceCommissionType,
    Income, Expense, DeletedIncome, DeletedExpense, PartnerPayout,
    DocumentSettings, DocumentTemplate, Quotation, QuotationSection, QuotationItem, QuotationPackage, QuotationDomainOption,
    QuotationPaymentStage, QuotationTerm, QuotationExclusion, QuotationActivity, QuotationVersion,
    InvoiceStatus, Invoice, InvoiceItem
)

