from django.db import models
from django.contrib.auth.models import User
from core.models import Organization, UserProfile, StatusStyleMixin


class CalendarStatus(models.Model, StatusStyleMixin):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='calendar_statuses')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20, default='#64748b')
    position = models.IntegerField(default=0)

    class Meta:
        unique_together = ('organization', 'name')
        ordering = ['position', 'id']
        db_table = 'calendar_statuses'

    def __str__(self):
        return self.name


class Activity(models.Model):
    TYPE_CHOICES = [
        ('Email', 'Email'),
        ('Call', 'Call'),
        ('Meeting', 'Meeting'),
        ('Task', 'Task'),
        ('Stage Update', 'Stage Update'),
        ('Creation', 'Creation'),
    ]

    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='activities')
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'activities'

    def __str__(self):
        return f"{self.type} on {self.lead.name} at {self.timestamp}"


class WhatsAppMessage(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='whatsapp_messages')
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='whatsapp_messages', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    recipient_phone = models.CharField(max_length=50)
    template_name = models.CharField(max_length=100, blank=True, null=True)
    message_content = models.TextField()
    meta_message_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, default='Sent')
    error_message = models.TextField(blank=True, null=True)
    buttons_json = models.TextField(default='[]')
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'whatsapp_messages'
        ordering = ['-sent_at']

    def __str__(self):
        return f"WhatsApp to {self.recipient_phone} ({self.status}) - {self.sent_at}"


class Task(models.Model):
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]

    RISK_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]

    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    title = models.CharField(max_length=255, default='Project Task')
    description = models.TextField(blank=True, null=True)
    assignees = models.ManyToManyField(UserProfile, blank=True, related_name='assigned_tasks')
    start_date = models.DateField(blank=True, null=True)
    due_date = models.DateField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default='Low')
    progress = models.IntegerField(default=0)
    status = models.ForeignKey('projects.ProjectStatus', on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    completed = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tasks'

    def __str__(self):
        return f"{self.title} - {self.description} ({'Completed' if self.completed else 'Pending'})"

    @property
    def calculated_progress(self):
        total_t = self.todos.count()
        total_m = self.milestones.count()
        total = total_t + total_m
        if total > 0:
            done_t = self.todos.filter(completed=True).count()
            done_m = self.milestones.filter(completed=True).count()
            return int(((done_t + done_m) / total) * 100)
        if self.progress is not None and self.progress > 0:
            return self.progress
        return 100 if self.completed else 0

    @property
    def deliverables_total(self):
        return self.todos.count() + self.milestones.count()

    @property
    def deliverables_done(self):
        return self.todos.filter(completed=True).count() + self.milestones.filter(completed=True).count()

    @property
    def unified_deliverables(self):
        items = []
        for m in self.milestones.all().order_by('due_date', 'id'):
            items.append({
                'id': m.id,
                'kind': 'milestone',
                'title': m.title,
                'completed': m.completed,
                'due_date': m.due_date,
                'category': m.category or 'milestone_deliverable',
                'category_label': m.category_label,
                'category_color': m.category_color,
                'category_badge_class': m.category_badge_class,
            })
        for t in self.todos.all().order_by('created_at', 'id'):
            items.append({
                'id': t.id,
                'kind': 'todo',
                'title': t.title,
                'completed': t.completed,
                'due_date': self.due_date,
                'category': t.category or 'milestone_deliverable',
                'category_label': t.category_label,
                'category_color': t.category_color,
                'category_badge_class': t.category_badge_class,
            })
        return items


class TaskTodo(models.Model):
    CATEGORY_CHOICES = [
        ('milestone_deliverable', 'Deliverable Deadline'),
        ('ad_campaign', 'Ad & Social Campaign'),
        ('client_meeting', 'Client Meeting'),
        ('payment_followup', 'Follow-up & Sync'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='todos')
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='milestone_deliverable', blank=True, null=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'task_todos'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.title} ({'Completed' if self.completed else 'Pending'})"

    @property
    def category_label(self):
        labels = {
            'ad_campaign': 'Ad / Campaign',
            'social_post': 'Social Post',
            'client_meeting': 'Meeting',
            'payment_followup': 'Follow-up',
            'website_milestone': 'Website',
            'milestone_deliverable': 'Deliverable',
        }
        return labels.get(self.category or 'milestone_deliverable', 'Deliverable')

    @property
    def category_color(self):
        colors = {
            'ad_campaign': '#06B6D4',
            'social_post': '#00D0C6',
            'client_meeting': '#00BAFF',
            'payment_followup': '#FB923C',
            'website_milestone': '#34D399',
            'milestone_deliverable': '#10B981',
        }
        return colors.get(self.category or 'milestone_deliverable', '#10B981')

    @property
    def category_badge_class(self):
        classes = {
            'ad_campaign': 'bg-cyan-50 text-cyan-700 border-cyan-200',
            'social_post': 'bg-teal-50 text-teal-700 border-teal-200',
            'client_meeting': 'bg-sky-50 text-sky-700 border-sky-200',
            'payment_followup': 'bg-orange-50 text-orange-700 border-orange-200',
            'website_milestone': 'bg-emerald-50 text-emerald-700 border-emerald-200',
            'milestone_deliverable': 'bg-emerald-50 text-emerald-700 border-emerald-200',
        }
        return classes.get(self.category or 'milestone_deliverable', 'bg-emerald-50 text-emerald-700 border-emerald-200')


class TaskFile(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='project_files/')
    filename = models.CharField(max_length=255)
    file_size = models.CharField(max_length=50, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'task_files'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.filename} ({self.task.title})"


class TaskMilestone(models.Model):
    CATEGORY_CHOICES = [
        ('milestone_deliverable', 'Deliverable Deadline'),
        ('ad_campaign', 'Ad & Social Campaign'),
        ('client_meeting', 'Client Meeting'),
        ('payment_followup', 'Follow-up & Sync'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='milestone_deliverable', blank=True, null=True)
    due_date = models.DateField()
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'task_milestones'
        ordering = ['due_date']

    def __str__(self):
        return f"{self.title} - {self.task.title}"

    @property
    def category_label(self):
        labels = {
            'ad_campaign': 'Ad / Campaign',
            'social_post': 'Social Post',
            'client_meeting': 'Meeting',
            'payment_followup': 'Follow-up',
            'website_milestone': 'Website',
            'milestone_deliverable': 'Deliverable',
        }
        return labels.get(self.category or 'milestone_deliverable', 'Deliverable')

    @property
    def category_color(self):
        colors = {
            'ad_campaign': '#06B6D4',
            'social_post': '#00D0C6',
            'client_meeting': '#00BAFF',
            'payment_followup': '#FB923C',
            'website_milestone': '#34D399',
            'milestone_deliverable': '#10B981',
        }
        return colors.get(self.category or 'milestone_deliverable', '#10B981')

    @property
    def category_badge_class(self):
        classes = {
            'ad_campaign': 'bg-cyan-50 text-cyan-700 border-cyan-200',
            'social_post': 'bg-teal-50 text-teal-700 border-teal-200',
            'client_meeting': 'bg-sky-50 text-sky-700 border-sky-200',
            'payment_followup': 'bg-orange-50 text-orange-700 border-orange-200',
            'website_milestone': 'bg-emerald-50 text-emerald-700 border-emerald-200',
            'milestone_deliverable': 'bg-emerald-50 text-emerald-700 border-emerald-200',
        }
        return classes.get(self.category or 'milestone_deliverable', 'bg-emerald-50 text-emerald-700 border-emerald-200')


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_comments')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'task_comments'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username} on {self.task.title}: {self.message[:30]}"


class Meeting(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='meetings')
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='meetings')
    title = models.CharField(max_length=255)
    date_time = models.DateTimeField()
    location = models.CharField(max_length=255, default='Zoom')

    class Meta:
        db_table = 'meetings'

    def __str__(self):
        return f"{self.title} at {self.date_time}"


class Event(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    recurring = models.BooleanField(default=False)
    color = models.CharField(max_length=50, default='#004ac6')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='events')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='events')
    notified_10h = models.BooleanField(default=False)
    notified_1h = models.BooleanField(default=False)

    class Meta:
        db_table = 'events'

    def __str__(self):
        return f"{self.title} ({self.start_time} - {self.end_time})"
