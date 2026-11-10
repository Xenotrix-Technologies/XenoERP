import json
from datetime import date
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from core.models import Organization, UserProfile
from hr.models import Payroll
from hr.views import hr_payroll


class EmployeeSpendingsPayrollTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.org = Organization.objects.create(name='Acme Global Org')

        # Create Admin User
        self.admin_user = User.objects.create_user(username='admin_user', password='password123')
        self.admin_profile = UserProfile.objects.create(
            user=self.admin_user,
            organization=self.org,
            role='Administrator',
            department=None
        )

        # Create Staff 1
        self.user1 = User.objects.create_user(username='john_doe', first_name='John', last_name='Doe')
        self.profile1 = UserProfile.objects.create(
            user=self.user1,
            organization=self.org,
            role='Senior Developer',
            department=None
        )

        # Create Staff 2
        self.user2 = User.objects.create_user(username='jane_smith', first_name='Jane', last_name='Smith')
        self.profile2 = UserProfile.objects.create(
            user=self.user2,
            organization=self.org,
            role='Product Designer',
            department=None
        )

        # Create Payroll records for Staff 1:
        # Cycle 1: Base 3000, Bonus 500, Advance 200, Deductions 100 => Net 3200
        Payroll.objects.create(
            organization=self.org,
            user_profile=self.profile1,
            cycle_start_date=date(2026, 9, 1),
            cycle_end_date=date(2026, 9, 30),
            base_salary=Decimal('3000.00'),
            bonuses=Decimal('500.00'),
            advance=Decimal('200.00'),
            deductions=Decimal('100.00'),
            net_pay=Decimal('3200.00'),
            status='Paid'
        )
        # Cycle 2: Base 3000, Bonus 0, Advance 0, Deductions 100 => Net 2900
        Payroll.objects.create(
            organization=self.org,
            user_profile=self.profile1,
            cycle_start_date=date(2026, 10, 1),
            cycle_end_date=date(2026, 10, 31),
            base_salary=Decimal('3000.00'),
            bonuses=Decimal('0.00'),
            advance=Decimal('0.00'),
            deductions=Decimal('100.00'),
            net_pay=Decimal('2900.00'),
            status='Paid'
        )

        # Create Payroll record for Staff 2:
        # Cycle 1: Base 2500, Bonus 250, Advance 0, Deductions 50 => Net 2700
        Payroll.objects.create(
            organization=self.org,
            user_profile=self.profile2,
            cycle_start_date=date(2026, 10, 1),
            cycle_end_date=date(2026, 10, 31),
            base_salary=Decimal('2500.00'),
            bonuses=Decimal('250.00'),
            advance=Decimal('0.00'),
            deductions=Decimal('50.00'),
            net_pay=Decimal('2700.00'),
            status='Paid'
        )

    def test_payroll_employee_spendings_aggregates(self):
        """
        Verify that hr_payroll view computes correct employee-based total spendings,
        cycles, bonuses, advances, deductions, and org-wide totals.
        """
        request = self.rf.get('/hr/payroll/')
        request.user = self.admin_user
        # Simulate session / messages framework
        request._messages = []

        response = hr_payroll(request)
        self.assertEqual(response.status_code, 200)

        ctx = response.context_data
        # Org totals
        # Net: 3200 + 2900 + 2700 = 8800.00
        self.assertEqual(ctx['org_total_net'], Decimal('8800.00'))
        # Base: 3000 + 3000 + 2500 = 8500.00
        self.assertEqual(ctx['org_total_base'], Decimal('8500.00'))
        # Bonuses: 500 + 0 + 250 = 750.00
        self.assertEqual(ctx['org_total_bonuses'], Decimal('750.00'))
        # Advances: 200 + 0 + 0 = 200.00
        self.assertEqual(ctx['org_total_advance'], Decimal('200.00'))
        # Deductions: 100 + 100 + 50 = 250.00
        self.assertEqual(ctx['org_total_deductions'], Decimal('250.00'))

        # Employee spendings breakdown
        emp_spendings = ctx['employee_spendings']
        self.assertEqual(len(emp_spendings), 2)

        # Staff 1 (John Doe) has higher total spendings (6100 vs 2700), so ordered first
        emp1 = emp_spendings[0]
        self.assertEqual(emp1['id'], self.profile1.id)
        self.assertEqual(emp1['name'], 'John Doe')
        self.assertEqual(emp1['role'], 'Senior Developer')
        self.assertEqual(emp1['cycle_count'], 2)
        self.assertEqual(emp1['total_net'], 6100.0)
        self.assertEqual(emp1['total_base'], 6000.0)
        self.assertEqual(emp1['total_bonuses'], 500.0)
        self.assertEqual(emp1['total_advance'], 200.0)
        self.assertEqual(emp1['total_deductions'], 200.0)
        self.assertEqual(emp1['avg_cycle'], 3050.0)

        # Staff 2 (Jane Smith)
        emp2 = emp_spendings[1]
        self.assertEqual(emp2['id'], self.profile2.id)
        self.assertEqual(emp2['name'], 'Jane Smith')
        self.assertEqual(emp2['role'], 'Product Designer')
        self.assertEqual(emp2['cycle_count'], 1)
        self.assertEqual(emp2['total_net'], 2700.0)
        self.assertEqual(emp2['total_base'], 2500.0)
        self.assertEqual(emp2['total_bonuses'], 250.0)
        self.assertEqual(emp2['avg_cycle'], 2700.0)

        # Verify JSON serialization contains the same data
        spendings_data = json.loads(ctx['employee_spendings_json'])
        self.assertEqual(len(spendings_data), 2)
        self.assertEqual(spendings_data[0]['name'], 'John Doe')

    def test_payroll_filter_by_employee(self):
        """
        Verify that passing ?employee=<id> correctly filters the payroll records
        and sets selected_employee.
        """
        request = self.rf.get(f'/hr/payroll/?employee={self.profile2.id}')
        request.user = self.admin_user
        request._messages = []

        response = hr_payroll(request)
        self.assertEqual(response.status_code, 200)

        ctx = response.context_data
        # Filtered payrolls should only contain Staff 2's 1 cycle
        self.assertEqual(ctx['payrolls'].count(), 1)
        self.assertEqual(ctx['payrolls'].first().user_profile, self.profile2)

        # Selected employee should match Staff 2
        self.assertIsNotNone(ctx['selected_employee'])
        self.assertEqual(ctx['selected_employee']['id'], self.profile2.id)
        self.assertEqual(ctx['selected_employee']['name'], 'Jane Smith')
        self.assertEqual(ctx['selected_employee']['total_net'], 2700.0)
