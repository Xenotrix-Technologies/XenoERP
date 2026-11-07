from django.contrib import admin

# Admin registrations are modularly distributed across each domain app:
# - core: Organization, UserProfile, Department, StaffRole, SystemNotification
# - leads: Lead, LeadStatus
# - services: Service
# - support: Ticket, TicketStatus, PriorityStatus
# - projects: ClientStatus, ProjectStatus, Agreement, AgreementVersion, Deliverable, etc.
# - activities: Activity, Task, Meeting, Event, CalendarStatus, WhatsAppMessage
# - campaigns: Campaign, CampaignStatus
# - content_tracker: ContentItem, ContentDropdownOption
# - finance: Income, Expense, Quotation, Invoice, DocumentSettings, etc.
# - hr: EmployeeProfile, Attendance, LeaveRequest, Payroll, etc.
