"""
Backward-compatibility layer for invoice views.
All implementations have moved to finance.invoice_views.
"""
from finance.invoice_views import (
    get_user_profile,
    get_invoice_stats,
    invoice_dashboard,
    invoice_create,
    invoice_detail,
    invoice_edit,
    invoice_delete,
    invoice_update_status,
)
