import json
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DUMP_PATH = os.path.join(os.path.dirname(__file__), 'database_dump.json')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'XenoERP_Database_Export.xlsx')

with open(DUMP_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

wb = openpyxl.Workbook()
# Remove default sheet
wb.remove(wb.active)

# Styling helpers
header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
header_fill = PatternFill(start_color='1E40AF', end_color='1E40AF', fill_type='solid') # Slate Blue
sub_header_fill = PatternFill(start_color='3B82F6', end_color='3B82F6', fill_type='solid')

title_font = Font(name='Calibri', size=14, bold=True, color='1E3A8A')
meta_font = Font(name='Calibri', size=10, italic=True, color='6B7280')
bold_font = Font(name='Calibri', size=11, bold=True, color='111827')
regular_font = Font(name='Calibri', size=11, color='1F2937')

thin_border = Border(
    left=Side(style='thin', color='E5E7EB'),
    right=Side(style='thin', color='E5E7EB'),
    top=Side(style='thin', color='E5E7EB'),
    bottom=Side(style='thin', color='E5E7EB')
)

def format_sheet(ws, title_text, headers, rows):
    # Title row
    ws.append([title_text])
    ws.cell(row=1, column=1).font = title_font
    ws.row_dimensions[1].height = 28
    
    # Empty spacer row
    ws.append([])
    ws.row_dimensions[2].height = 8

    # Header row
    ws.append(headers)
    header_row_idx = 3
    ws.row_dimensions[header_row_idx].height = 24
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row_idx, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Data rows
    for row in rows:
        formatted_row = []
        for val in row:
            if val is None:
                formatted_row.append('-')
            elif isinstance(val, (dict, list)):
                formatted_row.append(json.dumps(val))
            elif isinstance(val, str) and 'T' in val and (val.endswith('Z') or '+' in val):
                # Clean ISO dates to YYYY-MM-DD
                try:
                    formatted_row.append(val.split('T')[0])
                except:
                    formatted_row.append(str(val))
            else:
                formatted_row.append(val)
        ws.append(formatted_row)

    # Styling data cells
    for row_idx in range(4, len(rows) + 4):
        ws.row_dimensions[row_idx].height = 20
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            # Align numbers right, text left
            if isinstance(cell.value, (int, float)):
                cell.alignment = Alignment(horizontal='right', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='left', vertical='center')

    # Auto-fit columns
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            if cell.row < 3: # Skip title & spacer
                continue
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

# -------------------------------------------------------------
# 1. Summary Sheet
# -------------------------------------------------------------
ws_sum = wb.create_sheet('Summary & Tables')
ws_sum.append(['XenoERP Database Overview & System Inventory'])
ws_sum.cell(row=1, column=1).font = title_font
ws_sum.append([f"Export Date: {data.get('metadata', {}).get('timestamp', '2026-11-01')} | Database: Neon PostgreSQL Serverless (AWS US-East-2)"])
ws_sum.cell(row=2, column=1).font = meta_font
ws_sum.append([])

ws_sum.append(['Table Name', 'Active Row Count', 'System Category'])
ws_sum.row_dimensions[4].height = 24
for col_idx in range(1, 4):
    c = ws_sum.cell(row=4, column=col_idx)
    c.font = header_font
    c.fill = header_fill
    c.alignment = Alignment(horizontal='center', vertical='center')

for t in data.get('table_counts', []):
    name = t.get('table_name', '')
    count = t.get('row_count', 0)
    category = 'General / Config'
    if count == 0:
        continue
    if 'auth' in name or 'user' in name: category = 'Auth & Access Control'
    elif 'lead' in name or 'client' in name or 'activit' in name: category = 'CRM & Pipeline'
    elif 'expense' in name or 'income' in name or 'invoice' in name or 'finance' in name: category = 'Finance & Accounts'
    elif 'content' in name or 'post' in name or 'campaign' in name: category = 'Marketing & CMS'
    elif 'hr' in name or 'leave' in name or 'payroll' in name: category = 'HR & Team'
    elif 'project' in name or 'task' in name: category = 'Projects & Operations'
    elif 'quotation' in name or 'agreement' in name: category = 'Sales & Legal'

    ws_sum.append([name, count, category])

for row in ws_sum.iter_rows(min_row=5, max_col=3):
    ws_sum.row_dimensions[row[0].row].height = 20
    for c in row:
        c.font = regular_font
        c.border = thin_border

ws_sum.column_dimensions['A'].width = 35
ws_sum.column_dimensions['B'].width = 20
ws_sum.column_dimensions['C'].width = 30

# -------------------------------------------------------------
# 2. Organizations Sheet
# -------------------------------------------------------------
ws_org = wb.create_sheet('Organizations')
org_rows = [[o.get('id'), o.get('name'), o.get('created_at')] for o in data.get('organizations', [])]
format_sheet(ws_org, 'Tenants & Organizations', ['Organization ID', 'Organization Name', 'Created At'], org_rows)

# -------------------------------------------------------------
# 3. Users & Staff Sheet
# -------------------------------------------------------------
ws_users = wb.create_sheet('Users & Staff')
user_map = {u.get('id'): u for u in data.get('users', [])}
staff_rows = []
for p in data.get('user_profiles', []):
    u_info = p.get('auth_user') or user_map.get(p.get('user_id'), {})
    dept = p.get('departments', {}) or {}
    staff_rows.append([
        p.get('id'),
        p.get('user_id'),
        u_info.get('username'),
        f"{u_info.get('first_name', '')} {u_info.get('last_name', '')}".strip() or '-',
        u_info.get('email') or '-',
        p.get('role') or 'Staff',
        dept.get('name') if isinstance(dept, dict) else '-',
        p.get('location') or '-',
        p.get('phone_number') or '-',
        p.get('organization_id') or '-',
        'Active' if u_info.get('is_active', True) else 'Inactive'
    ])
format_sheet(
    ws_users,
    'System Users & Staff Directory',
    ['Profile ID', 'User ID', 'Username', 'Full Name', 'Email', 'Role / Designation', 'Department', 'Location', 'Phone', 'Org ID', 'Status'],
    staff_rows
)

# -------------------------------------------------------------
# 4. Leads & Clients Sheet
# -------------------------------------------------------------
ws_leads = wb.create_sheet('Leads & Clients')
lead_rows = []
for l in data.get('leads', []):
    lead_rows.append([
        l.get('id'),
        l.get('name') or '-',
        l.get('company') or '-',
        l.get('email') or '-',
        l.get('phone_number') or '-',
        l.get('location') or '-',
        l.get('status') or '-',
        l.get('stage') or '-',
        float(l.get('value') or 0),
        float(l.get('paid_amount') or 0),
        'Client' if l.get('is_client') else 'Lead',
        l.get('notes') or '-',
        l.get('date_time') or l.get('created_at')
    ])
format_sheet(
    ws_leads,
    'CRM Leads & Converted Clients (47 Records)',
    ['ID', 'Contact Name', 'Company Name', 'Email', 'Phone', 'Location', 'Status', 'Stage', 'Deal Value (₹)', 'Paid Amount (₹)', 'Type', 'Notes', 'Created Date'],
    lead_rows
)

# -------------------------------------------------------------
# 5. Invoices & Billing
# -------------------------------------------------------------
ws_inv = wb.create_sheet('Invoices')
inv_rows = []
for inv in data.get('invoices', []):
    inv_rows.append([
        inv.get('id'),
        inv.get('invoice_number'),
        inv.get('customer_name') or inv.get('client_name') or '-',
        inv.get('company_name') or '-',
        inv.get('status') or 'Pending',
        inv.get('invoice_date') or inv.get('issue_date'),
        inv.get('due_date'),
        float(inv.get('subtotal') or 0),
        float(inv.get('total_tax') or 0),
        float(inv.get('grand_total') or 0),
        float(inv.get('amount_paid') or 0),
        float(inv.get('balance_due') or 0),
        inv.get('notes') or '-'
    ])
format_sheet(
    ws_inv,
    'Accounts Receivable & GST Invoices',
    ['ID', 'Invoice #', 'Customer Name', 'Company', 'Status', 'Invoice Date', 'Due Date', 'Subtotal (₹)', 'Tax (₹)', 'Grand Total (₹)', 'Amount Paid (₹)', 'Balance Due (₹)', 'Notes'],
    inv_rows
)

# Invoice items sheet
ws_inv_items = wb.create_sheet('Invoice Line Items')
inv_item_rows = []
for inv in data.get('invoices', []):
    for it in inv.get('invoice_items', []):
        inv_item_rows.append([
            it.get('id'),
            inv.get('invoice_number'),
            it.get('product_name'),
            it.get('description') or '-',
            float(it.get('quantity') or 1),
            float(it.get('unit_price') or 0),
            float(it.get('tax_percentage') or 0),
            float(it.get('line_total') or 0)
        ])
format_sheet(
    ws_inv_items,
    'Itemized Invoice Details',
    ['Item ID', 'Invoice #', 'Product / Service Description', 'Details', 'Qty', 'Unit Price (₹)', 'Tax %', 'Line Total (₹)'],
    inv_item_rows
)

# -------------------------------------------------------------
# 6. Quotations Sheet
# -------------------------------------------------------------
ws_quo = wb.create_sheet('Quotations & Scopes')
quo_rows = []
for q in data.get('quotations', []):
    quo_rows.append([
        q.get('id'),
        q.get('quotation_number'),
        q.get('project_title') or q.get('title') or '-',
        q.get('client_name') or '-',
        q.get('status') or 'Draft',
        q.get('date'),
        q.get('valid_until'),
        float(q.get('grand_total') or 0),
        q.get('notes') or '-'
    ])
format_sheet(
    ws_quo,
    'Estimates, Scopes & Quotations',
    ['ID', 'Quotation #', 'Proposal Title', 'Client Name', 'Status', 'Date', 'Valid Until', 'Total Value (₹)', 'Terms & Notes'],
    quo_rows
)

# -------------------------------------------------------------
# 7. Marketing Campaigns
# -------------------------------------------------------------
ws_camp = wb.create_sheet('Ad Campaigns')
camp_rows = []
for c in data.get('campaigns', []):
    spend = float(c.get('spend') or 0)
    results = float(c.get('results_count') or 0)
    cpr = round(spend / results, 2) if results > 0 else float(c.get('cost_per_result') or 0)
    camp_rows.append([
        c.get('id'),
        c.get('name'),
        c.get('platform') or 'Meta Ads',
        c.get('status') or 'Active',
        float(c.get('budget') or 0),
        spend,
        float(c.get('gst_amount') or (spend * 0.18)),
        results,
        cpr,
        c.get('end_date')
    ])
format_sheet(
    ws_camp,
    'Performance Marketing & Meta Ads Campaigns',
    ['ID', 'Campaign Name', 'Platform', 'Status', 'Budget (₹)', 'Net Spend (₹)', '18% GST (₹)', 'Results / Conversions', 'CPR (₹)', 'End Date'],
    camp_rows
)

# -------------------------------------------------------------
# 8. Content Tracker (Videos)
# -------------------------------------------------------------
ws_content = wb.create_sheet('Content & Video Pipeline')
content_rows = []
for ci in data.get('content_items', []):
    content_rows.append([
        ci.get('id'),
        ci.get('video_title') or ci.get('title') or '-',
        ci.get('content_type') or 'Reel',
        ci.get('platform') or 'Instagram',
        ci.get('status') or 'Ideation',
        ci.get('priority') or 'Medium',
        ci.get('due_date'),
        ci.get('drive_link') or '-',
        ci.get('notes') or '-'
    ])
format_sheet(
    ws_content,
    'Video Production, Editing & Content Pipeline (56 Items)',
    ['ID', 'Video Title / Hook', 'Format', 'Platform', 'Pipeline Stage', 'Priority', 'Due Date', 'Drive Asset Folder', 'Notes'],
    content_rows
)

# -------------------------------------------------------------
# 9. Services Catalog
# -------------------------------------------------------------
ws_srv = wb.create_sheet('Services Catalog')
srv_rows = []
for s in data.get('services', []):
    srv_rows.append([
        s.get('id'),
        s.get('name'),
        s.get('description') or '-',
        float(s.get('price') or 0),
        s.get('created_at')
    ])
format_sheet(
    ws_srv,
    'Standard Enterprise SaaS & Digital Solutions',
    ['ID', 'Service Package Name', 'Description / Scope', 'Standard Price (₹)', 'Created At'],
    srv_rows
)

# -------------------------------------------------------------
# 10. Finance - Incomes
# -------------------------------------------------------------
ws_inc = wb.create_sheet('Finance - Incomes')
inc_rows = []
for inc in data.get('incomes', []):
    pm = inc.get('crm_financepaymentmethod', {}) or {}
    inc_rows.append([
        inc.get('id'),
        float(inc.get('amount') or 0),
        inc.get('date'),
        inc.get('description') or '-',
        pm.get('name') if isinstance(pm, dict) else '-',
        inc.get('reference_number') or '-',
        inc.get('invoice_id') or '-'
    ])
format_sheet(
    ws_inc,
    'Accounts Receivable Incomes (30 Transactions)',
    ['Income ID', 'Amount Received (₹)', 'Transaction Date', 'Description / Client', 'Payment Method', 'Reference #', 'Invoice ID'],
    inc_rows
)

# -------------------------------------------------------------
# 11. Finance - Expenses
# -------------------------------------------------------------
ws_exp = wb.create_sheet('Finance - Expenses')
exp_rows = []
for exp in data.get('expenses', []):
    cat = exp.get('crm_financeexpensecategory', {}) or {}
    pm = exp.get('crm_financepaymentmethod', {}) or {}
    exp_rows.append([
        exp.get('id'),
        float(exp.get('amount') or 0),
        exp.get('date'),
        cat.get('name') if isinstance(cat, dict) else '-',
        exp.get('description') or '-',
        pm.get('name') if isinstance(pm, dict) else '-',
        exp.get('reference_number') or '-',
        float(exp.get('gst_amount') or 0)
    ])
format_sheet(
    ws_exp,
    'Operating & Agency Expenses (186 Transactions)',
    ['Expense ID', 'Amount (₹)', 'Date', 'Expense Category', 'Description', 'Payment Method', 'Receipt / Ref #', 'GST (₹)'],
    exp_rows
)

# -------------------------------------------------------------
# 12. Client Agreements
# -------------------------------------------------------------
ws_agr = wb.create_sheet('Client Agreements')
agr_rows = []
for a in data.get('agreements', []):
    agr_rows.append([
        a.get('id'),
        a.get('agreement_number'),
        a.get('client_name'),
        a.get('company_name') or '-',
        a.get('agreement_type') or 'SaaS SLA',
        a.get('start_date'),
        a.get('end_date'),
        float(a.get('monthly_fee') or 0),
        float(a.get('advance_payment') or 0),
        float(a.get('total_value') or 0),
        a.get('status') or 'Active'
    ])
format_sheet(
    ws_agr,
    'Executed Master Service Agreements & Retainers',
    ['ID', 'Agreement #', 'Client Name', 'Company Name', 'Contract Type', 'Start Date', 'End Date', 'Monthly Retainer (₹)', 'Advance (₹)', 'Total Contract Value (₹)', 'Status'],
    agr_rows
)

# Save workbook
wb.save(OUTPUT_PATH)
file_size_kb = os.path.getsize(OUTPUT_PATH) / 1024
print(f"Successfully created Excel file at: {OUTPUT_PATH} ({file_size_kb:.1f} KB)")

