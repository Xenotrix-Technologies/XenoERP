from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from crm.models import Organization, UserProfile, Lead, Task, Activity, Event, LeadStatus, StaffRole, Service

class XenoCRMTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Org 1
        self.org1 = Organization.objects.create(name="Org One")
        self.user1 = User.objects.create_user(username="user1", password="password123", email="user1@org1.com")
        self.profile1 = UserProfile.objects.create(user=self.user1, organization=self.org1, role="Manager")
        
        # Lead for Org 1
        self.lead1 = Lead.objects.create(
            organization=self.org1,
            name="John Doe",
            email="john@doe.com",
            company="Doe Corp",
            score=90,
            status="New",
            stage="New",
            value=10000,
            owner=self.profile1
        )
        
        # Task for Lead 1
        self.task1 = Task.objects.create(
            lead=self.lead1,
            description="Send quote",
            due_date="2026-10-10",
            priority="High",
            completed=False
        )

        # Org 2
        self.org2 = Organization.objects.create(name="Org Two")
        self.user2 = User.objects.create_user(username="user2", password="password123", email="user2@org2.com")
        self.profile2 = UserProfile.objects.create(user=self.user2, organization=self.org2, role="Representative")
        
        # Lead for Org 2
        self.lead2 = Lead.objects.create(
            organization=self.org2,
            name="Jane Smith",
            email="jane@smith.com",
            company="Smith Ltd",
            score=85,
            status="Contacted",
            stage="Qualified",
            value=25000,
            owner=self.profile2
        )

    def test_signup_disabled(self):
        response = self.client.post(reverse('signup'), {
            'org_name': 'Test New Org',
            'first_name': 'Test',
            'last_name': 'User',
            'username': 'testuser',
            'email': 'test@test.com',
            'password': 'testpassword123',
            'password_confirm': 'testpassword123'
        })
        self.assertRedirects(response, reverse('login'))
        self.assertFalse(User.objects.filter(username='testuser').exists())
        self.assertFalse(Organization.objects.filter(name='Test New Org').exists())

    def test_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'user1',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_dashboard_multi_tenancy(self):
        # Log in user 1
        self.client.login(username='user1', password='password123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Context should show org 1's lead but not org 2's lead
        leads = response.context['new_leads']
        self.assertIn(self.lead1, leads)
        self.assertNotIn(self.lead2, leads)
        
        # Total revenue should only sum Org 1's leads in Won stage (currently 0)
        self.assertEqual(response.context['total_revenue'], 0)

    def test_leads_view_multi_tenancy(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(reverse('leads'))
        self.assertEqual(response.status_code, 200)
        
        leads = response.context['leads']
        self.assertIn(self.lead1, [l for l in leads])
        self.assertNotIn(self.lead2, [l for l in leads])

    def test_leads_view_search_by_name_and_company(self):
        self.client.login(username='user1', password='password123')
        
        lead_extra = Lead.objects.create(
            organization=self.org1,
            name="Alice Wonder",
            email="alice@acme.com",
            company="Acme Corporation",
            score=70,
            status="New",
            stage="New",
            value=5000,
            owner=self.profile1
        )
        
        # 1. Search by lead name ("Alice")
        response = self.client.get(reverse('leads') + '?q=Alice')
        self.assertEqual(response.status_code, 200)
        leads = list(response.context['leads'])
        self.assertIn(lead_extra, leads)
        self.assertNotIn(self.lead1, leads)
        
        # 2. Search by company name ("Acme")
        response = self.client.get(reverse('leads') + '?q=Acme')
        self.assertEqual(response.status_code, 200)
        leads = list(response.context['leads'])
        self.assertIn(lead_extra, leads)
        self.assertNotIn(self.lead1, leads)
        
        # 3. Search by partial company name ("Doe Corp" -> "Doe")
        response = self.client.get(reverse('leads') + '?q=Doe')
        self.assertEqual(response.status_code, 200)
        leads = list(response.context['leads'])
        self.assertIn(self.lead1, leads)
        self.assertNotIn(lead_extra, leads)
        
        # 4. Search via AJAX
        response_ajax = self.client.get(reverse('leads') + '?q=Acme', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response_ajax.status_code, 200)
        data = response_ajax.json()
        self.assertIn('Alice Wonder', data['html'])
        self.assertIn('Acme Corporation', data['html'])
        self.assertNotIn('John Doe', data['html'])

    def test_leads_view_excludes_qualified(self):
        self.client.login(username='user1', password='password123')
        
        # Change lead1 status to Qualified
        self.lead1.status = 'Qualified'
        self.lead1.save()
        
        response = self.client.get(reverse('leads'))
        self.assertEqual(response.status_code, 200)
        
        leads = response.context['leads']
        self.assertNotIn(self.lead1, [l for l in leads])

    def test_update_lead_stage_ajax(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('update_lead_stage'), {
            'lead_id': self.lead1.id,
            'stage': 'Proposal'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Refresh and assert stage updated
        self.lead1.refresh_from_db()
        self.assertEqual(self.lead1.stage, 'Proposal')
        self.assertTrue(Activity.objects.filter(lead=self.lead1, type='Stage Update').exists())

    def test_complete_task_ajax(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('complete_task'), {
            'task_id': self.task1.id
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['completed'])
        
        self.task1.refresh_from_db()
        self.assertTrue(self.task1.completed)

    def test_log_activity_ajax(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('log_activity'), {
            'lead_id': self.lead1.id,
            'type': 'Call',
            'description': 'Discovery call logged.'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['activity']['type'], 'Call')
        self.assertEqual(data['activity']['description'], 'Discovery call logged.')
        
        self.assertTrue(Activity.objects.filter(lead=self.lead1, type='Call', description='Discovery call logged.').exists())

    def test_new_views_require_login(self):
        new_views = [
            'clients', 
            'customer_support', 'projects', 'project_reports', 
            'campaign'
        ]
        # Test anonymous access redirects to login
        for view_name in new_views:
            response = self.client.get(reverse(view_name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse('login'), response.url)

    def test_new_views_authenticated(self):
        new_views = [
            'clients', 
            'customer_support', 'projects', 'project_reports', 
            'campaign'
        ]
        # Log in user
        self.client.login(username='user1', password='password123')
        for view_name in new_views:
            response = self.client.get(reverse(view_name))
            self.assertEqual(response.status_code, 200, f"Failed for view {view_name}")

    def test_quick_create_lead_ajax(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('quick_create_lead'), {
            'name': 'Test AJAX Lead',
            'email': 'ajax@lead.com',
            'company': 'AJAX Corp',
            'value': 50000,
            'score': 75
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['lead']['name'], 'Test AJAX Lead')
        self.assertTrue(Lead.objects.filter(name='Test AJAX Lead', organization=self.org1).exists())

    def test_leads_view_ajax_fragment(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(reverse('leads'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('html', data)
        self.assertIn('John Doe', data['html'])

    def test_calendar_events_json(self):
        self.client.login(username='user1', password='password123')
        # Create an event first
        event = Event.objects.create(
            title="Meeting 1",
            start_time="2026-06-20T10:00:00Z",
            end_time="2026-06-20T11:00:00Z",
            owner=self.user1,
            organization=self.org1
        )
        response = self.client.get(reverse('calendar_events_json'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Meeting 1')

    def test_event_create_ajax(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('event_create_ajax'), {
            'title': 'New AJAX Event',
            'description': 'AJAX event desc',
            'start_time': '2026-06-20T12:00',
            'end_time': '2026-06-20T13:00',
            'recurring': 'false'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['event']['title'], 'New AJAX Event')
        self.assertTrue(Event.objects.filter(title='New AJAX Event', organization=self.org1).exists())

    def test_event_edit_ajax(self):
        self.client.login(username='user1', password='password123')
        event = Event.objects.create(
            title="Old Event Title",
            start_time="2026-06-20T10:00:00Z",
            end_time="2026-06-20T11:00:00Z",
            owner=self.user1,
            organization=self.org1
        )
        response = self.client.post(reverse('event_edit_ajax', args=[event.id]), {
            'title': 'Updated Event Title',
            'description': 'Updated description',
            'start_time': '2026-06-20T10:30',
            'end_time': '2026-06-20T11:30',
            'recurring': 'true'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        event.refresh_from_db()
        self.assertEqual(event.title, 'Updated Event Title')
        self.assertTrue(event.recurring)

    def test_event_delete_ajax(self):
        self.client.login(username='user1', password='password123')
        event = Event.objects.create(
            title="Event to Delete",
            start_time="2026-06-20T10:00:00Z",
            end_time="2026-06-20T11:00:00Z",
            owner=self.user1,
            organization=self.org1
        )
        response = self.client.post(reverse('event_delete_ajax', args=[event.id]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(Event.objects.filter(id=event.id).exists())

    def test_add_lead_view(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('add_lead'), {
            'name': 'New Lead Test',
            'company': 'Lead Company',
            'email': 'new@leadcompany.com',
            'phone_number': '123-456-7890',
            'alt_phone_number': '098-765-4321',
            'date_time': '2026-06-20T18:15',
            'status': 'New',
            'owner': self.profile1.id,
            'last_followup_date_time': '2026-06-21T10:00'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Verify database record
        lead = Lead.objects.get(name='New Lead Test')
        self.assertEqual(lead.phone_number, '123-456-7890')
        self.assertEqual(lead.alt_phone_number, '098-765-4321')
        self.assertEqual(lead.status, 'New')
        self.assertEqual(lead.owner, self.profile1)
        self.assertIsNotNone(lead.date_time)
        self.assertIsNotNone(lead.last_followup_date_time)

    def test_edit_lead_view(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('edit_lead', args=[self.lead1.id]), {
            'name': 'Updated Name',
            'company': 'Updated Company',
            'email': 'updated@doe.com',
            'phone_number': '999-999-9999',
            'alt_phone_number': '888-888-8888',
            'date_time': '2026-06-22T14:30',
            'status': 'Qualified',
            'owner': self.profile1.id,
            'last_followup_date_time': '2026-06-23T11:00'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Refresh and verify
        self.lead1.refresh_from_db()
        self.assertEqual(self.lead1.name, 'Updated Name')
        self.assertEqual(self.lead1.phone_number, '999-999-9999')
        self.assertEqual(self.lead1.alt_phone_number, '888-888-8888')
        self.assertEqual(self.lead1.status, 'Active')
        self.assertTrue(self.lead1.is_client)
        self.assertIsNotNone(self.lead1.date_time)
        self.assertIsNotNone(self.lead1.last_followup_date_time)

    def test_lead_json_view(self):
        self.client.login(username='user1', password='password123')
        self.lead1.phone_number = '555-555-5555'
        self.lead1.save()
        
        response = self.client.get(reverse('lead_json', args=[self.lead1.id]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['lead']['name'], 'John Doe')
        self.assertEqual(data['lead']['phone_number'], '555-555-5555')

    def test_lead_statuses_view_authenticated(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(reverse('lead_statuses'))
        self.assertEqual(response.status_code, 200)
        # Check that default statuses are populated and returned
        statuses = response.context['statuses']
        self.assertTrue(statuses.exists())
        self.assertEqual(statuses.count(), 5) # New, Contacted, Qualified, Cold Lead, Lost

    def test_add_lead_status_ajax(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('add_lead_status'), {
            'name': 'Negotiating',
            'color': 'yellow'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(LeadStatus.objects.filter(organization=self.org1, name='Negotiating').exists())

    def test_edit_lead_status_ajax(self):
        self.client.login(username='user1', password='password123')
        # Force default seed
        response = self.client.get(reverse('lead_statuses'))
        status_obj = LeadStatus.objects.filter(organization=self.org1, name='New').first()
        self.assertIsNotNone(status_obj)
        
        # Associate lead1 with 'New' status
        self.lead1.status = 'New'
        self.lead1.save()

        response = self.client.post(reverse('edit_lead_status', args=[status_obj.id]), {
            'name': 'Brand New',
            'color': 'blue'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        status_obj.refresh_from_db()
        self.assertEqual(status_obj.name, 'Brand New')
        self.assertEqual(status_obj.color, 'blue')
        
        # Verify the lead's status is updated
        self.lead1.refresh_from_db()
        self.assertEqual(self.lead1.status, 'Brand New')

    def test_delete_lead_status_ajax(self):
        self.client.login(username='user1', password='password123')
        # Force seed
        self.client.get(reverse('lead_statuses'))
        status_to_delete = LeadStatus.objects.filter(organization=self.org1, name='Cold Lead').first()
        default_status = LeadStatus.objects.filter(organization=self.org1, is_default=True).first()
        self.assertIsNotNone(status_to_delete)
        self.assertIsNotNone(default_status)

        # Assign lead1 to 'Cold Lead'
        self.lead1.status = 'Cold Lead'
        self.lead1.save()

        response = self.client.post(reverse('delete_lead_status', args=[status_to_delete.id]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Verify it is deleted
        self.assertFalse(LeadStatus.objects.filter(id=status_to_delete.id).exists())
        
        # Verify lead is reassigned to default
        self.lead1.refresh_from_db()
        self.assertEqual(self.lead1.status, default_status.name)

    def test_reorder_lead_statuses_ajax(self):
        self.client.login(username='user1', password='password123')
        self.client.get(reverse('lead_statuses'))
        statuses = list(LeadStatus.objects.filter(organization=self.org1).order_by('position'))
        self.assertEqual(len(statuses), 5)

        # Reverse the order
        reversed_ids = [s.id for s in reversed(statuses)]
        import json
        response = self.client.post(
            reverse('reorder_lead_statuses'),
            data=json.dumps({'order': reversed_ids}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Verify order in DB
        new_ordered = list(LeadStatus.objects.filter(organization=self.org1).order_by('position'))
        self.assertEqual(new_ordered[0].id, reversed_ids[0])
        self.assertEqual(new_ordered[-1].id, reversed_ids[-1])

    def test_staff_list_view(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(reverse('staff'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.profile1, response.context['staff_members'])
        self.assertNotIn(self.profile2, response.context['staff_members'])

    def test_add_staff_view(self):
        self.client.login(username='user1', password='password123')
        # GET
        response = self.client.get(reverse('add_staff'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'staff_form.html')
        self.assertIn('Add New Staff Member', response.content.decode())

        # POST
        response = self.client.post(reverse('add_staff'), {
            'username': 'newstaff',
            'email': 'newstaff@org1.com',
            'first_name': 'New',
            'last_name': 'Staff',
            'role': 'Representative',
            'password': 'StaffPassword123',
            'profile_image_url': 'https://example.com/pic.jpg',
            'phone_number': '123-456-7890',
            'location': 'New York'
        })
        self.assertRedirects(response, reverse('staff'))
        self.assertTrue(User.objects.filter(username='newstaff').exists())
        profile = UserProfile.objects.get(user__username='newstaff')
        self.assertEqual(profile.organization, self.org1)
        self.assertEqual(profile.role, 'Representative')
        self.assertEqual(profile.profile_image_url, 'https://example.com/pic.jpg')
        self.assertEqual(profile.phone_number, '123-456-7890')
        self.assertEqual(profile.location, 'New York')

    def test_edit_staff_view_get_and_post(self):
        self.client.login(username='user1', password='password123')
        # Create a staff member under org1 first
        u = User.objects.create_user(username='editstaff', email='edit@org1.com')
        p = UserProfile.objects.create(user=u, organization=self.org1, role='Sales Executive')

        # GET
        response = self.client.get(reverse('edit_staff', args=[p.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'staff_form.html')
        self.assertIn('Edit Staff Member: editstaff', response.content.decode())

        # POST
        response = self.client.post(reverse('edit_staff', args=[p.id]), {
            'username': 'updatedstaff',
            'email': 'updated@org1.com',
            'first_name': 'Updated',
            'last_name': 'Name',
            'role': 'Manager',
            'profile_image_url': 'https://example.com/new.jpg',
            'phone_number': '987-654-3210',
            'location': 'London'
        })
        self.assertRedirects(response, reverse('staff'))
        
        p.refresh_from_db()
        self.assertEqual(p.user.username, 'updatedstaff')
        self.assertEqual(p.role, 'Manager')
        self.assertEqual(p.profile_image_url, 'https://example.com/new.jpg')
        self.assertEqual(p.phone_number, '987-654-3210')
        self.assertEqual(p.location, 'London')

    def test_delete_staff_ajax(self):
        self.client.login(username='user1', password='password123')
        u = User.objects.create_user(username='delstaff', email='del@org1.com')
        p = UserProfile.objects.create(user=u, organization=self.org1, role='Representative')

        response = self.client.post(reverse('delete_staff', args=[p.id]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(UserProfile.objects.filter(id=p.id).exists())
        self.assertFalse(User.objects.filter(id=u.id).exists())

    def test_staff_roles_list_view(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(reverse('staff_roles'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'staff_roles.html')
        # Check seeding of default roles
        self.assertEqual(StaffRole.objects.filter(organization=self.org1).count(), 4)
        self.assertIn('Sales Executive', response.content.decode())

    def test_add_staff_role_ajax(self):
        self.client.login(username='user1', password='password123')
        # Seed defaults first
        self.client.get(reverse('staff_roles'))
        
        response = self.client.post(reverse('add_staff_role'), {
            'name': 'Chief Executive Officer'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertTrue(StaffRole.objects.filter(organization=self.org1, name='Chief Executive Officer').exists())

    def test_edit_staff_role_ajax(self):
        self.client.login(username='user1', password='password123')
        # Seed defaults
        self.client.get(reverse('staff_roles'))
        role = StaffRole.objects.get(organization=self.org1, name='Sales Executive')
        
        # Edit role
        response = self.client.post(reverse('edit_staff_role', args=[role.id]), {
            'name': 'Senior Account Executive'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        
        role.refresh_from_db()
        self.assertEqual(role.name, 'Senior Account Executive')

    def test_delete_staff_role_ajax(self):
        self.client.login(username='user1', password='password123')
        # Seed defaults
        self.client.get(reverse('staff_roles'))
        role_to_del = StaffRole.objects.get(organization=self.org1, name='Sales Executive')
        fallback = StaffRole.objects.filter(organization=self.org1).exclude(id=role_to_del.id).first()
        
        # Assign user1 to have role_to_del and grant permissions via custom_permissions
        import json
        self.profile1.role = role_to_del.name
        self.profile1.custom_permissions_json = json.dumps({'staff_roles': True, 'staff': True})
        self.profile1.save()
        
        # Delete role
        response = self.client.post(reverse('delete_staff_role', args=[role_to_del.id]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        
        self.assertFalse(StaffRole.objects.filter(id=role_to_del.id).exists())
        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.role, fallback.name)

    def test_clients_view_qualified_leads_only(self):
        self.client.login(username='user1', password='password123')
        
        # Create a qualified lead under org1
        qualified_lead = Lead.objects.create(
            organization=self.org1,
            name="Qualified Lead",
            email="qualified@lead.com",
            company="Qualified Inc",
            score=95,
            status="Qualified",
            stage="Proposal",
            value=50000,
            owner=self.profile1
        )
        
        response = self.client.get(reverse('clients'))
        self.assertEqual(response.status_code, 200)
        
        # Context should contain "Qualified Inc" but not "Doe Corp" (which has status "New")
        clients = response.context['clients']
        companies = [c['company'] for c in clients]
        
        self.assertIn("Qualified Inc", companies)
        self.assertNotIn("Doe Corp", companies)

    def test_services_view_and_crud(self):
        self.client.login(username='user1', password='password123')

        # List services
        response = self.client.get(reverse('services'))
        self.assertEqual(response.status_code, 200)

        # Add service
        response = self.client.post(reverse('add_service'), {
            'name': 'Cloud Strategy',
            'description': 'Strategy consulting for cloud platforms',
            'price': '150.00'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertTrue(Service.objects.filter(name='Cloud Strategy', organization=self.org1).exists())
        service_obj = Service.objects.get(name='Cloud Strategy', organization=self.org1)

        # Edit service
        response = self.client.post(reverse('edit_service', args=[service_obj.id]), {
            'name': 'Cloud Strategy V2',
            'description': 'Updated strategy',
            'price': '200.00'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        service_obj.refresh_from_db()
        self.assertEqual(service_obj.name, 'Cloud Strategy V2')
        self.assertEqual(float(service_obj.price), 200.00)

        # Delete service
        response = self.client.post(reverse('delete_service', args=[service_obj.id]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(Service.objects.filter(id=service_obj.id).exists())

    def test_lead_service_assignment(self):
        self.client.login(username='user1', password='password123')
        service = Service.objects.create(organization=self.org1, name='Web Development', price=5000)

        # Case 1: Status is 'Qualified' -> Service is assigned
        response = self.client.post(reverse('add_lead'), {
            'name': 'Bob Qualified',
            'company': 'Bob Co',
            'email': 'bob@qualified.com',
            'phone_number': '123-456-7890',
            'status': 'Qualified',
            'service': service.id
        })
        self.assertEqual(response.status_code, 302)
        lead = Lead.objects.get(name='Bob Qualified')
        self.assertEqual(lead.service, service)

        # Case 2: Status is NOT 'Qualified' -> Service is NOT assigned (or cleared)
        response = self.client.post(reverse('add_lead'), {
            'name': 'Bob Unqualified',
            'company': 'Bob Co',
            'email': 'bob@unqualified.com',
            'phone_number': '123-456-7890',
            'status': 'New',
            'service': service.id
        })
        self.assertEqual(response.status_code, 302)
        lead2 = Lead.objects.get(name='Bob Unqualified')
        self.assertNil = self.assertIsNone(lead2.service)

        # Case 3: Edit lead from Qualified to New -> Service is cleared
        response = self.client.post(reverse('edit_lead', args=[lead.id]), {
            'name': 'Bob Qualified',
            'company': 'Bob Co',
            'email': 'bob@qualified.com',
            'status': 'New',
            'service': service.id
        })
        self.assertEqual(response.status_code, 302)
        lead.refresh_from_db()
        self.assertIsNone(lead.service)



