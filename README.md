# XenoERP Enterprise CRM & Business Suite

A modular, scalable, multi-tenant Django ERP and CRM architecture designed for enterprise agency operations, digital studios, and service businesses.

---

## 🏗️ Architecture & Module Organization

The codebase is organized into dedicated, domain-driven Django applications with separation of concerns:

```text
XenoERP/
│
├── xenocrm/                     # Project Configuration & Settings
│   ├── settings.py              # Central settings, databases, auth, middleware
│   ├── urls.py                  # Root URL configuration
│   ├── wsgi.py                  # Production WSGI application
│   ├── asgi.py                  # Production ASGI application
│   └── views.py                 # System health-check & storage probes
│
├── core/                        # Organization Multi-Tenancy & Auth Foundation
│   ├── models.py                # Organization, UserProfile, Department, StaffRole, SystemNotification
│   ├── views.py                 # Authentication, user profiles, staff CRUD, role & permission management
│   ├── permissions.py           # Multi-tier RBAC decorator (page_permission_required)
│   ├── hashers.py               # Configured password hashers
│   ├── context_processors.py    # Unread notifications count
│   ├── forms.py                 # ProfileForm
│   ├── admin.py                 # Organization & user profile admin
│   └── urls.py                  # /login/, /signup/, /logout/, /staff/, /settings/
│
├── leads/                       # Sales Pipeline & Lead Intelligence
│   ├── models.py                # Lead, LeadStatus, badge stylers
│   ├── views.py                 # Leads table, kanban pipeline, lead CRUD, CSV import/export
│   ├── utils.py                 # CSV header mappers, phone/email validators, status seeding
│   ├── admin.py                 # LeadAdmin, LeadStatusAdmin
│   └── urls.py                  # /leads/, /pipeline/, /leads/add/, /statuses/leads/
│
├── services/                    # Products & Service Catalog
│   ├── models.py                # Service (name, description, pricing)
│   ├── views.py                 # Service catalog CRUD
│   ├── admin.py                 # ServiceAdmin
│   └── urls.py                  # /services/, /services/add/, /services/<id>/edit/
│
├── support/                     # Customer Support & Helpdesk
│   ├── models.py                # Ticket, TicketStatus, PriorityStatus
│   ├── views.py                 # Ticket listing, ticket CRUD, status settings
│   ├── admin.py                 # TicketAdmin, TicketStatusAdmin, PriorityStatusAdmin
│   └── urls.py                  # /customer-support/, /customer-support/create/
│
├── projects/                    # Client Accounts, Projects & Agreements
│   ├── models.py                # ClientStatus, ProjectStatus, Agreement, AgreementVersion, Deliverables
│   ├── views.py                 # Clients view, project board, timelines, agreement generator & public portal
│   ├── admin.py                 # AgreementAdmin, ClientStatusAdmin, ProjectStatusAdmin
│   └── urls.py                  # /clients/, /projects/, /agreements/, /agreement/view/<token>/
│
├── activities/                  # Tasks, Calendar, Meetings & WhatsApp Integration
│   ├── models.py                # Task, TaskTodo, TaskFile, TaskMilestone, Event, Activity, WhatsAppMessage
│   ├── views.py                 # Task CRUD, todos, comments, FullCalendar JSON, Meta WhatsApp Cloud API
│   ├── forms.py                 # EventForm
│   ├── services/                # WhatsApp API client, automated event notification services
│   ├── admin.py                 # TaskAdmin, EventAdmin, ActivityAdmin, WhatsAppMessageAdmin
│   └── urls.py                  # /calendar/, /task/add/, /activity/log/, /api/whatsapp/
│
├── campaigns/                   # Meta Ads & Marketing Campaign Intelligence
│   ├── models.py                # Campaign (budget, spend, impressions, 18% GST calculation, CPR)
│   ├── views.py                 # Campaign manager, metrics dashboard, launch campaign modal
│   ├── admin.py                 # CampaignAdmin, CampaignStatusAdmin
│   └── urls.py                  # /campaign/, /campaign/dashboard/, /statuses/campaigns/
│
├── content_tracker/             # Media Production Pipeline & Video Studio
│   ├── models.py                # ContentItem, ContentDropdownOption
│   ├── views.py                 # Content kanban, editor dashboard, post management, batch CSV import
│   ├── admin.py                 # ContentItemAdmin, ContentDropdownOptionAdmin
│   └── urls.py                  # /settings/content-tracker/, /editor-dashboard/, /post-management/
│
├── finance/                     # General Ledger, Invoices & Quotations
│   ├── models.py                # Income, Expense, DeletedIncome, Invoice, Quotation, DocumentSettings
│   ├── views.py                 # Financial dashboard, income/expense ledgers, reports, partner payouts
│   ├── invoice_views.py         # GST invoice generator, multi-status invoice dashboard, payment tracking
│   ├── document_views.py        # Quotations builder, PDF generators, public quotation portal
│   ├── management/commands/     # backup_finance_data, seed_document_data
│   ├── admin.py                 # IncomeAdmin, ExpenseAdmin, InvoiceAdmin, QuotationAdmin
│   └── urls.py                  # /finance/dashboard/, /finance/invoices/, /quotations/
│
├── hr/                          # Human Resource & Payroll Management
│   ├── models.py                # EmployeeProfile, LeaveRequest, Attendance, Payroll
│   ├── views.py                 # HR dashboard, attendance logging, leave approval, salary slips
│   ├── admin.py                 # HR model admin registrations
│   └── urls.py                  # /hr/dashboard/, /hr/attendance/, /hr/leaves/
│
├── crm/                         # Enterprise Gateway & Backward-Compatibility Layer
│   ├── views.py                 # Cross-module executive ERP dashboard, dynamic status dispatcher, re-exports
│   ├── urls.py                  # Unified route aggregator including all modular domain app routes
│   ├── invoice_views.py         # Re-export bridge to finance.invoice_views
│   ├── document_views.py        # Re-export bridge to finance.document_views and projects.views
│   ├── forms.py                 # Re-export bridge to core.forms and activities.forms
│   └── tests.py                 # Comprehensive system test suite (36 test cases)
│
├── templates/                   # Global HTML Templates (Tailwind CSS UI)
├── static/                      # Static Assets, CSS, JS, Vendor Libraries
├── manage.py                    # Django management CLI
└── requirements.txt             # Python dependencies
```

---

## ⚙️ Environment Configuration

Create a `.env` file in the project root:

```env
# Application
SECRET_KEY="your-production-secret-key"
DEBUG=False
ALLOWED_HOSTS="localhost,127.0.0.1,yourdomain.com"

# Database (PostgreSQL recommended; SQLite supported for local dev/testing)
DATABASE_URL="postgresql://user:password@localhost:5432/xenocrm"
DB_SSL_REQUIRE=False

# Media & Storage (Cloudinary supported)
CLOUDINARY_CLOUD_NAME="your-cloud-name"
CLOUDINARY_API_KEY="your-api-key"
CLOUDINARY_API_SECRET="your-api-secret"

# Meta WhatsApp Cloud API (Optional)
WHATSAPP_TOKEN="your-whatsapp-token"
WHATSAPP_PHONE_NUMBER_ID="your-phone-number-id"
```

---

## 🚀 Installation & Setup

1. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

2. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify system health:**
   ```bash
   python manage.py check
   ```

4. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Seed demo data (Optional):**
   ```bash
   python manage.py seed_data
   python manage.py seed_document_data
   ```

6. **Start the development server:**
   ```bash
   python manage.py runserver
   ```
   Open your browser at `http://127.0.0.1:8000/`.

---

## 🧪 Testing Instructions

Run the complete test suite:

```bash
python manage.py test
```

To run tests with in-memory SQLite without database dependencies:
```bash
python -c "
import os, sys
sys.path.insert(0, '.')
sys.argv = ['manage.py', 'test', '--verbosity=2']
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['DB_SSL_REQUIRE'] = 'False'
os.environ['DJANGO_SETTINGS_MODULE'] = 'xenocrm.settings'
import django
from django.conf import settings
settings.MIGRATION_MODULES = {app.split('.')[-1]: None for app in settings.INSTALLED_APPS}
settings.DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
django.setup()
from django.core.management import call_command
call_command('test', 'crm', verbosity=2)
"
```

---

## 🛡️ Database & Migration Safety

- Every model specifies an explicit `db_table` attribute (e.g. `organizations`, `leads`, `agreements`, `incomes`, `crm_invoice`).
- Database schema and table names remain strictly backward-compatible.
- Existing migration history (`crm/migrations/0001` through `0063`) is preserved.

---

## 📡 API & Route Structure

| Module | Route Prefix | Key Endpoints |
|---|---|---|
| **Executive** | `/` | `/` (Dashboard), `/dashboard/`, `/offline/` |
| **Core & Auth** | `/` | `/login/`, `/logout/`, `/staff/`, `/settings/` |
| **Leads** | `/leads/`, `/pipeline/` | `/leads/add/`, `/leads/<id>/edit/`, `/statuses/leads/` |
| **Services** | `/services/` | `/services/`, `/services/add/`, `/services/<id>/edit/` |
| **Support** | `/customer-support/` | `/customer-support/`, `/customer-support/create/` |
| **Projects** | `/clients/`, `/projects/` | `/clients/`, `/projects/`, `/agreements/`, `/agreement/view/<token>/` |
| **Activities** | `/calendar/`, `/task/` | `/calendar/events-json/`, `/task/add/`, `/activity/log/`, `/api/whatsapp/` |
| **Campaigns** | `/campaign/` | `/campaign/`, `/campaign/dashboard/`, `/statuses/campaigns/` |
| **Content** | `/settings/content-tracker/`| `/settings/content-tracker/`, `/editor-dashboard/`, `/post-management/` |
| **Finance** | `/finance/` | `/finance/dashboard/`, `/finance/income/`, `/finance/expenses/`, `/finance/invoices/`, `/quotations/` |
| **HR** | `/hr/` | `/hr/dashboard/`, `/hr/attendance/`, `/hr/leaves/` |
| **Admin** | `/admin/` | Dedicated Django ModelAdmin dashboards for all domain apps |
