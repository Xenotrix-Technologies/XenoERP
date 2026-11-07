"""
Backward-compatibility layer for document views.
All implementations have moved to finance.document_views and projects.views.
"""
from finance.document_views import (
    get_user_profile,
    get_or_create_document_settings,
    generate_next_quotation_number,
    generate_next_agreement_number,
    recalculate_quotation_totals,
    create_quotation_activity,
    create_quotation_version_snapshot,
    quotation_quick_create_client,
    quotation_list,
    quotation_create,
    quotation_edit,
    quotation_detail,
    quotation_duplicate,
    quotation_update_status,
    quotation_delete,
    quotation_convert_to_agreement,
    public_quotation_view,
    public_quotation_accept,
    public_quotation_reject,
    document_settings_view,
    document_templates_view,
    document_template_delete,
    convert_lead_to_client,
)
from projects.views import (
    public_agreement_view,
    public_agreement_sign,
)
