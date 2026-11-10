import json
from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from core.models import Organization, UserProfile
from leads.models import Lead
from services.models import Service
from activities.models import Task, TaskMilestone, TaskTodo, Event
from activities.views import (
    calendar_events_json_view, toggle_task_milestone,
    reschedule_task_milestone, toggle_task_todo, calendar_view,
    edit_task_milestone, add_task_milestone
)


class CalendarSprintDeliverablesTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.org = Organization.objects.create(name='Test Agency')
        self.user = User.objects.create_user(username='test_user', password='password123')
        self.profile = UserProfile.objects.create(
            user=self.user,
            organization=self.org,
            role='Director',
            department=None
        )
        self.service = Service.objects.create(organization=self.org, name='Website Development')
        self.client = Lead.objects.create(
            organization=self.org,
            name='Test Client Lead',
            company='Acme Corp',
            is_client=True
        )
        self.client.services.add(self.service)

        self.task = Task.objects.create(
            organization=self.org,
            lead=self.client,
            title='Acme Website Redesign',
            due_date=date(2026, 11, 20),
            priority='High',
            progress=0,
            completed=False
        )

        self.milestone = TaskMilestone.objects.create(
            task=self.task,
            title='UI Wireframes Delivery',
            due_date=date(2026, 11, 10),
            completed=False
        )

        self.todo = TaskTodo.objects.create(
            task=self.task,
            title='Setup Tailwind CSS',
            completed=False
        )

    def test_calendar_events_json_includes_sprint_deliverables(self):
        req = self.rf.get('/calendar/events-json/?t=123')
        req.user = self.user
        res = calendar_events_json_view(req)
        self.assertEqual(res.status_code, 200)

        data = json.loads(res.content)
        # Should include milestone, todo, and target deadline
        milestone_events = [e for e in data if e.get('id') == f"deliverable-milestone-{self.milestone.id}"]
        self.assertEqual(len(milestone_events), 1)
        m_ev = milestone_events[0]

        self.assertEqual(m_ev['title'], 'UI Wireframes Delivery')
        self.assertEqual(m_ev['start'], '2026-11-10')
        self.assertEqual(m_ev['is_deliverable'], True)
        self.assertEqual(m_ev['completed'], False)
        self.assertEqual(m_ev['client_name'], 'Acme Corp')
        self.assertEqual(m_ev['service_name'], 'Website Development')

    def test_calendar_events_json_completed_strikethrough_flag(self):
        # Mark milestone as completed
        self.milestone.completed = True
        self.milestone.save()

        req = self.rf.get('/calendar/events-json/?t=123')
        req.user = self.user
        res = calendar_events_json_view(req)
        data = json.loads(res.content)

        m_ev = next(e for e in data if e.get('id') == f"deliverable-milestone-{self.milestone.id}")
        self.assertEqual(m_ev['completed'], True)
        self.assertEqual(m_ev['status'], 'Completed')

    def test_toggle_task_milestone(self):
        req = self.rf.post(f'/task/milestone/{self.milestone.id}/toggle/')
        req.user = self.user
        res = toggle_task_milestone(req, self.milestone.id)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['completed'])

        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)

        # Toggle back
        res2 = toggle_task_milestone(req, self.milestone.id)
        data2 = json.loads(res2.content)
        self.assertFalse(data2['completed'])
        self.milestone.refresh_from_db()
        self.assertFalse(self.milestone.completed)

    def test_reschedule_task_milestone(self):
        req = self.rf.post(
            f'/task/milestone/{self.milestone.id}/reschedule/',
            {'due_date': '2026-11-15'}
        )
        req.user = self.user
        res = reschedule_task_milestone(req, self.milestone.id)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['due_date'], '2026-11-15')

        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.due_date, date(2026, 11, 15))

    def test_toggle_task_todo(self):
        req = self.rf.post(f'/task/todo/{self.todo.id}/toggle/')
        req.user = self.user
        res = toggle_task_todo(req, self.todo.id)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['completed'])
        self.todo.refresh_from_db()
        self.assertTrue(self.todo.completed)

    def test_calendar_category_filter(self):
        # Filtering for client_meeting should exclude milestone_deliverable
        req = self.rf.get('/calendar/events-json/?category=client_meeting')
        req.user = self.user
        res = calendar_events_json_view(req)
        data = json.loads(res.content)
        self.assertEqual(len(data), 0)

        # Filtering for milestone_deliverable should include it
        req2 = self.rf.get('/calendar/events-json/?category=milestone_deliverable')
        req2.user = self.user
        res2 = calendar_events_json_view(req2)
        data2 = json.loads(res2.content)
        self.assertTrue(any(e.get('is_deliverable') for e in data2))

    def test_edit_task_milestone(self):
        # Test editing title, category to ad_campaign, and due date
        req = self.rf.post(
            f'/task/milestone/{self.milestone.id}/edit/',
            {
                'title': 'Diwali Festive Video Ad',
                'category': 'ad_campaign',
                'due_date': '2026-11-18'
            }
        )
        req.user = self.user
        res = edit_task_milestone(req, self.milestone.id)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['success'])
        m = data['milestone']
        self.assertEqual(m['title'], 'Diwali Festive Video Ad')
        self.assertEqual(m['category'], 'ad_campaign')
        self.assertEqual(m['category_label'], 'Ad / Campaign')
        self.assertEqual(m['category_color'], '#06B6D4')

        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.title, 'Diwali Festive Video Ad')
        self.assertEqual(self.milestone.category, 'ad_campaign')
        self.assertEqual(self.milestone.due_date, date(2026, 11, 18))

    def test_add_task_milestone_with_category(self):
        req = self.rf.post(
            f'/task/{self.task.id}/milestone/add/',
            {
                'title': 'Weekly Review Meeting',
                'category': 'client_meeting',
                'due_date': '2026-11-12'
            }
        )
        req.user = self.user
        res = add_task_milestone(req, self.task.id)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['success'])
        m = data['milestone']
        self.assertEqual(m['category'], 'client_meeting')
        self.assertEqual(m['category_label'], 'Meeting')
        self.assertEqual(m['category_color'], '#00BAFF')
