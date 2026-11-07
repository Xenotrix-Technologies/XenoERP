import os
import json
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime, parse_date
from finance.models import Income, Expense, DeletedIncome, DeletedExpense

class DecimalAndDateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

class Command(BaseCommand):
    help = 'Backup active and deleted Income and Expense data into JSON files.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--restore-to-db',
            action='store_true',
            help='Restore deleted historical income/expense from datadump.json into DeletedIncome and DeletedExpense models.',
        )

    def handle(self, *args, **options):
        # If --restore-to-db is passed, import items from datadump that are missing from active Income/Expense & DeletedIncome/DeletedExpense
        if options.get('restore_to_db') and os.path.exists('datadump.json'):
            try:
                with open('datadump.json', 'r', encoding='utf-8') as f:
                    datadump = json.load(f)
                    historical_inc = [item for item in datadump if item.get('model') == 'crm.income']
                    historical_exp = [item for item in datadump if item.get('model') == 'crm.expense']

                active_inc_pks = set(Income.objects.values_list('id', flat=True))
                deleted_inc_orig_ids = set(DeletedIncome.objects.exclude(original_id=None).values_list('original_id', flat=True))
                new_dinc = []
                for item in historical_inc:
                    pk = item['pk']
                    fields = item['fields']
                    if pk not in active_inc_pks and pk not in deleted_inc_orig_ids:
                        created_dt = parse_datetime(fields.get('created_at')) if fields.get('created_at') else None
                        date_val = parse_date(fields['date']) if isinstance(fields['date'], str) else fields['date']
                        new_dinc.append(DeletedIncome(
                            organization_id=fields['organization'],
                            original_id=pk,
                            date=date_val,
                            client_name=fields['client_name'],
                            project_name=fields.get('project_name', ''),
                            payment_method_name=str(fields.get('payment_method')) if fields.get('payment_method') else None,
                            amount=Decimal(str(fields['amount'])),
                            created_at=created_dt
                        ))
                if new_dinc:
                    DeletedIncome.objects.bulk_create(new_dinc, ignore_conflicts=True)

                active_exp_pks = set(Expense.objects.values_list('id', flat=True))
                deleted_exp_orig_ids = set(DeletedExpense.objects.exclude(original_id=None).values_list('original_id', flat=True))
                new_dexp = []
                for item in historical_exp:
                    pk = item['pk']
                    fields = item['fields']
                    if pk not in active_exp_pks and pk not in deleted_exp_orig_ids:
                        created_dt = parse_datetime(fields.get('created_at')) if fields.get('created_at') else None
                        date_val = parse_date(fields['date']) if isinstance(fields['date'], str) else fields['date']
                        new_dexp.append(DeletedExpense(
                            organization_id=fields['organization'],
                            original_id=pk,
                            date=date_val,
                            category_name=str(fields.get('category')) if fields.get('category') else None,
                            description=fields.get('description', ''),
                            cost_center=fields.get('cost_center', ''),
                            payment_method_name=str(fields.get('payment_method')) if fields.get('payment_method') else None,
                            amount=Decimal(str(fields['amount'])),
                            created_at=created_dt
                        ))
                if new_dexp:
                    DeletedExpense.objects.bulk_create(new_dexp, ignore_conflicts=True)
            except Exception as e:
                self.stderr.write(f"Error restoring historical data: {e}")

        # 1. Gather active income
        incomes = []
        for inc in Income.objects.all():
            incomes.append({
                'id': inc.id,
                'organization_id': inc.organization_id,
                'organization_name': inc.organization.name if inc.organization else None,
                'date': str(inc.date),
                'client_name': inc.client_name,
                'project_name': inc.project_name,
                'payment_method': inc.payment_method.name if inc.payment_method else None,
                'amount': float(inc.amount),
                'created_at': str(inc.created_at) if inc.created_at else None,
            })

        # 2. Gather active expenses
        expenses = []
        for exp in Expense.objects.all():
            expenses.append({
                'id': exp.id,
                'organization_id': exp.organization_id,
                'organization_name': exp.organization.name if exp.organization else None,
                'date': str(exp.date),
                'category': exp.category.name if exp.category else None,
                'description': exp.description,
                'cost_center': exp.cost_center,
                'payment_method': exp.payment_method.name if exp.payment_method else None,
                'amount': float(exp.amount),
                'created_at': str(exp.created_at) if exp.created_at else None,
            })

        # 3. Gather deleted income
        deleted_incomes = []
        for dinc in DeletedIncome.objects.all():
            deleted_incomes.append({
                'id': dinc.id,
                'original_id': dinc.original_id,
                'organization_id': dinc.organization_id,
                'organization_name': dinc.organization.name if dinc.organization else None,
                'date': str(dinc.date),
                'client_name': dinc.client_name,
                'project_name': dinc.project_name,
                'payment_method_name': dinc.payment_method_name,
                'amount': float(dinc.amount),
                'deleted_at': str(dinc.deleted_at) if dinc.deleted_at else None,
                'deleted_by': dinc.deleted_by.username if dinc.deleted_by else None,
                'created_at': str(dinc.created_at) if dinc.created_at else None,
            })

        # 4. Gather deleted expenses
        deleted_expenses = []
        for dexp in DeletedExpense.objects.all():
            deleted_expenses.append({
                'id': dexp.id,
                'original_id': dexp.original_id,
                'organization_id': dexp.organization_id,
                'organization_name': dexp.organization.name if dexp.organization else None,
                'date': str(dexp.date),
                'category_name': dexp.category_name,
                'description': dexp.description,
                'cost_center': dexp.cost_center,
                'payment_method_name': dexp.payment_method_name,
                'amount': float(dexp.amount),
                'deleted_at': str(dexp.deleted_at) if dexp.deleted_at else None,
                'deleted_by': dexp.deleted_by.username if dexp.deleted_by else None,
                'created_at': str(dexp.created_at) if dexp.created_at else None,
            })

        # 5. Extract historical datadump items
        historical_datadump_income = []
        historical_datadump_expense = []
        if os.path.exists('datadump.json'):
            try:
                with open('datadump.json', 'r', encoding='utf-8') as f:
                    datadump = json.load(f)
                    historical_datadump_income = [item for item in datadump if item.get('model') == 'crm.income']
                    historical_datadump_expense = [item for item in datadump if item.get('model') == 'crm.expense']
            except Exception as e:
                self.stderr.write(f"Error reading datadump.json: {e}")

        backup_data = {
            'backed_up_at': datetime.now().isoformat(),
            'counts': {
                'active_incomes': len(incomes),
                'active_expenses': len(expenses),
                'deleted_incomes': len(deleted_incomes),
                'deleted_expenses': len(deleted_expenses),
                'historical_datadump_incomes': len(historical_datadump_income),
                'historical_datadump_expenses': len(historical_datadump_expense),
            },
            'active_incomes': incomes,
            'active_expenses': expenses,
            'deleted_incomes': deleted_incomes,
            'deleted_expenses': deleted_expenses,
            'historical_datadump_incomes': historical_datadump_income,
            'historical_datadump_expenses': historical_datadump_expense,
        }

        os.makedirs('backups', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ts_filepath = os.path.join('backups', f'income_expense_backup_{timestamp}.json')
        latest_filepath = os.path.join('backups', 'income_expense_backup_latest.json')

        with open(ts_filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, cls=DecimalAndDateEncoder)

        with open(latest_filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, cls=DecimalAndDateEncoder)

        self.stdout.write(self.style.SUCCESS(f"Successfully backed up financial data to '{latest_filepath}' and '{ts_filepath}'"))
