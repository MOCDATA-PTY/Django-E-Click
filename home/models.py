from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
import random
import string
import os


def user_profile_picture_path(instance, filename):
    """Custom upload path for user profile pictures: users/admin/profile.jpg or admin/adminname/profile.jpg"""
    # Check if user is admin/staff
    if instance.user.is_staff or instance.user.is_superuser:
        base_folder = 'admin'
    else:
        base_folder = 'users'
    
    # Ensure the folder exists
    user_folder = os.path.join(settings.MEDIA_ROOT, base_folder, instance.user.username)
    os.makedirs(user_folder, exist_ok=True)
    
    return f'{base_folder}/{instance.user.username}/{filename}'


def client_profile_picture_path(instance, filename):
    """Custom upload path for client profile pictures: clients/clientname/profile.jpg"""
    # Ensure the folder exists
    client_folder = os.path.join(settings.MEDIA_ROOT, 'clients', instance.username)
    os.makedirs(client_folder, exist_ok=True)
    
    return f'clients/{instance.username}/{filename}'


def admin_profile_picture_path(instance, filename):
    """Custom upload path for admin profile pictures: admin/adminname/profile.jpg"""
    # Ensure the folder exists
    admin_folder = os.path.join(settings.MEDIA_ROOT, 'admin', instance.user.username)
    os.makedirs(admin_folder, exist_ok=True)
    
    return f'admin/{instance.user.username}/{filename}'


class Project(models.Model):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('in_progress_guidance_required', 'In Progress (Guidance Required)'),
        ('completed', 'Completed'),
        ('completed_review_pending', 'Completed (Review Pending)'),
        ('completed_data_discrepancy_addressing', 'Completed (Data Discrepancy addressing)'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    name = models.CharField(max_length=200)
    client = models.CharField(max_length=200)
    client_email = models.EmailField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='planned')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', help_text='Priority level of this project')
    assigned_users = models.ManyToManyField(User, blank=True, related_name='assigned_projects', help_text='Users assigned to this project')
    client_username = models.CharField(max_length=100, blank=True, help_text="Client's username for login")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def start_date(self):
        """Start date is determined by the earliest task start date"""
        earliest_task = self.tasks.filter(start_date__isnull=False).order_by('start_date').first()
        return earliest_task.start_date if earliest_task else None

    @property
    def end_date(self):
        """End date is determined by the latest task end date"""
        latest_task = self.tasks.filter(end_date__isnull=False).order_by('end_date').last()
        return latest_task.end_date if latest_task else None

    class Meta:
        ordering = ['-created_at']


class Task(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('in_progress_guidance_required', 'In Progress (Guidance Required)'),
        ('completed', 'Completed'),
        ('completed_review_pending', 'Completed (Review Pending)'),
        ('completed_data_discrepancy_addressing', 'Completed (Data Discrepancy addressing)'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled'),
    ]
    
    DEVELOPMENT_STATUS_CHOICES = [
        ('original_quoted', 'Original/Quoted Development'),
        ('new_development', 'New Development'),
        ('new_development_qms', 'New Development – QMS must be involved'),
        ('new_development_qms_change', 'New Development – QMS Change'),
        ('new_quoted_development', 'New Development/Quoted Development'),
        ('ongoing_development', 'Ongoing Development'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='not_started')
    development_status = models.CharField(max_length=50, choices=DEVELOPMENT_STATUS_CHOICES, default='original_quoted', help_text='Type of development for this task')
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', help_text='Priority level of this task')
    
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text='Estimated hours to complete this task')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    assigned_users = models.ManyToManyField(User, blank=True, related_name='assigned_tasks', help_text='Users assigned to this specific task')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.project.name}"

    def save(self, *args, **kwargs):
        # Update project dates when task dates change
        old_instance = None
        if self.pk:
            try:
                old_instance = Task.objects.get(pk=self.pk)
            except Task.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # If dates changed, update project dates
        if old_instance:
            if (old_instance.start_date != self.start_date or 
                old_instance.end_date != self.end_date):
                self.project.save()  # This will trigger project date recalculation

    class Meta:
        ordering = ['start_date', 'created_at']


class SubTask(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('in_progress_guidance_required', 'In Progress (Guidance Required)'),
        ('completed', 'Completed'),
        ('completed_review_pending', 'Completed (Review Pending)'),
        ('completed_data_discrepancy_addressing', 'Completed (Data Discrepancy addressing)'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='not_started')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.task.title}"

    class Meta:
        ordering = ['created_at']


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_comments')
    comment = models.TextField()
    is_admin_response = models.BooleanField(default=False, help_text='Whether this is an admin response to a team comment')
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='replies', help_text='Parent comment if this is a reply')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Comment by {self.user.username} on {self.task.title}"

    class Meta:
        ordering = ['-created_at']


class SubTaskComment(models.Model):
    subtask = models.ForeignKey(SubTask, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subtask_comments')
    comment = models.TextField()
    is_admin_response = models.BooleanField(default=False, help_text='Whether this is an admin response to a team comment')
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='replies', help_text='Parent comment if this is a reply')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Comment by {self.user.username} on {self.subtask.title}"

    class Meta:
        ordering = ['-created_at']


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to=user_profile_picture_path, blank=True, null=True)
    bio = models.TextField(max_length=500, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    
    # Permission fields
    can_access_dashboard = models.BooleanField(default=True)
    can_access_projects = models.BooleanField(default=True)
    can_access_reports = models.BooleanField(default=True)
    can_access_analytics = models.BooleanField(default=True)
    can_access_admin = models.BooleanField(default=False)
    can_manage_users = models.BooleanField(default=False)
    can_manage_clients = models.BooleanField(default=False)
    can_access_system_logs = models.BooleanField(default=False)
    
    # Additional access control fields
    can_create_projects = models.BooleanField(default=False)
    can_edit_projects = models.BooleanField(default=False)
    can_delete_projects = models.BooleanField(default=False)
    can_create_tasks = models.BooleanField(default=False)
    can_edit_tasks = models.BooleanField(default=False)
    can_delete_tasks = models.BooleanField(default=False)
    can_view_system_logs = models.BooleanField(default=False)
    can_access_backup_management = models.BooleanField(default=False)
    can_access_system_monitoring = models.BooleanField(default=False)
    
    # Account status fields
    is_suspended = models.BooleanField(default=False)
    suspension_reason = models.TextField(blank=True, null=True)
    suspension_until = models.DateTimeField(blank=True, null=True)
    
    # Login restrictions
    max_login_attempts = models.IntegerField(default=5)
    current_login_attempts = models.IntegerField(default=0)
    last_failed_login = models.DateTimeField(blank=True, null=True)
    account_locked_until = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def get_profile_picture_url(self):
        """Return the URL of the profile picture or a default avatar"""
        if self.profile_picture and hasattr(self.profile_picture, 'url'):
            return self.profile_picture.url
        else:
            # Return a default avatar URL or generate initials
            return f"/static/images/default-avatar.png"
    
    def is_account_active(self):
        """Check if account is active and not suspended"""
        if self.is_suspended:
            if self.suspension_until and self.suspension_until > timezone.now():
                return False
            else:
                # Auto-unsuspend if suspension period has passed
                self.is_suspended = False
                self.save()
                return True
        return True
    
    def is_account_locked(self):
        """Check if account is locked due to failed login attempts"""
        if self.account_locked_until and self.account_locked_until > timezone.now():
            return True
        return False
    
    def record_failed_login(self):
        """Record a failed login attempt"""
        self.current_login_attempts += 1
        self.last_failed_login = timezone.now()
        
        if self.current_login_attempts >= self.max_login_attempts:
            # Lock account for 30 minutes
            self.account_locked_until = timezone.now() + timedelta(minutes=30)
        
        self.save()
    
    def reset_login_attempts(self):
        """Reset failed login attempts on successful login"""
        self.current_login_attempts = 0
        self.account_locked_until = None
        self.save()
    
    def has_permission(self, permission_name):
        """Check if user has a specific permission"""
        permission_map = {
            'dashboard': self.can_access_dashboard,
            'projects': self.can_access_projects,
            'reports': self.can_access_reports,
            'analytics': self.can_access_analytics,
            'admin': self.can_access_admin,
            'manage_users': self.can_manage_users,
            'manage_clients': self.can_manage_clients,
            'create_projects': self.can_create_projects,
            'edit_projects': self.can_edit_projects,
            'delete_projects': self.can_delete_projects,
            'create_tasks': self.can_create_tasks,
            'edit_tasks': self.can_edit_tasks,
            'delete_tasks': self.can_delete_tasks,
            'system_logs': self.can_access_system_logs,
            'backup_management': self.can_access_backup_management,
            'system_monitoring': self.can_access_system_monitoring,
        }
        
        return permission_map.get(permission_name, False)
    
    def get_permission_level(self):
        """Get user's permission level for display purposes"""
        if self.user.is_superuser:
            return "Super Admin"
        elif self.user.is_staff and self.can_access_admin:
            return "Administrator"
        elif self.can_manage_users or self.can_manage_clients:
            return "Manager"
        elif self.can_create_projects or self.can_create_tasks:
            return "Editor"
        else:
            return "Viewer"


class Client(models.Model):
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128, blank=True)
    profile_picture = models.ImageField(upload_to=client_profile_picture_path, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    has_changed_password = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username

    def generate_otp(self):
        """Generate a 6-digit OTP for the client"""
        otp = ''.join(random.choices(string.digits, k=6))
        expires_at = timezone.now() + timedelta(minutes=10)
        
        # Mark all existing OTPs for this client as used
        ClientOTP.objects.filter(client=self).update(is_used=True)
        
        # Create new OTP
        otp_obj = ClientOTP.objects.create(
            client=self,
            otp=otp,
            expires_at=expires_at,
            is_used=False
        )
        
        return otp


class ClientOTP(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OTP for {self.client.username}"

    def is_valid(self):
        """Check if OTP is still valid and not used"""
        return not self.is_used and self.expires_at > timezone.now()

    class Meta:
        ordering = ['-created_at']
        # Ensure only one active (unused) OTP per client
        # Note: Multiple used OTPs are allowed, only one unused OTP per client
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'is_used'],
                condition=models.Q(is_used=False),
                name='unique_active_client_otp'
            )
        ]


class UserOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OTP for {self.user.username}"

    def is_valid(self):
        """Check if OTP is still valid and not used"""
        return not self.is_used and self.expires_at > timezone.now()

    class Meta:
        ordering = ['-created_at']
        # Ensure only one active (unused) OTP per user
        # Note: Multiple used OTPs are allowed, only one unused OTP per user
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'is_used'],
                condition=models.Q(is_used=False),
                name='unique_active_user_otp'
            )
        ]


def generate_user_otp(user):
    """Generate a 6-digit OTP for the user"""
    import random
    import string
    from datetime import timedelta
    
    otp = ''.join(random.choices(string.digits, k=6))
    expires_at = timezone.now() + timedelta(minutes=10)
    
    # Mark all existing OTPs for this user as used
    UserOTP.objects.filter(user=user).update(is_used=True)
    
    # Create new OTP
    otp_obj = UserOTP.objects.create(
        user=user,
        otp=otp,
        expires_at=expires_at,
        is_used=False
    )
    
    return otp


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('task_completed', 'Task Completed'),
        ('task_delayed', 'Task Delayed'),
        ('task_on_hold', 'Task On Hold'),
        ('task_update', 'Task Update'),
        ('task_status_change', 'Task Status Change'),
        ('task_duration_extended', 'Task Duration Extended'),
        ('task_comment_added', 'Task Comment Added'),
        ('task_comment_response', 'Admin Response to Task Comment'),
        ('subtask_comment_added', 'Subtask Comment Added'),
        ('subtask_comment_response', 'Admin Response to Subtask Comment'),
        ('project_update', 'Project Update'),
        ('admin_message', 'Admin Message'),
        ('project_status_change', 'Project Status Change'),
        ('project_created', 'Project Created'),
        ('task_created', 'Task Created'),
        ('subtask_created', 'Subtask Created'),
        ('deadline_extended', 'Deadline Extended'),
        ('priority_changed', 'Priority Changed'),
    ]
    
    recipient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications', help_text='Leave blank for system-wide notifications')
    notification_type = models.CharField(max_length=25, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    is_admin_notification = models.BooleanField(default=False, help_text='Whether this is an admin-generated notification')
    # Track which user made the change that triggered this notification
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='triggered_notifications', help_text='User who triggered this notification')
    related_project = models.ForeignKey(Project, on_delete=models.CASCADE, blank=True, null=True)
    related_task = models.ForeignKey(Task, on_delete=models.CASCADE, blank=True, null=True)
    related_subtask = models.ForeignKey(SubTask, on_delete=models.CASCADE, blank=True, null=True)
    related_comment = models.ForeignKey(TaskComment, on_delete=models.CASCADE, blank=True, null=True)
    related_subtask_comment = models.ForeignKey(SubTaskComment, on_delete=models.CASCADE, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.recipient:
            return f"{self.notification_type} - {self.recipient.username}"
        else:
            return f"{self.notification_type} - System Notification"

    class Meta:
        ordering = ['-created_at']
        # Add unique constraint to prevent duplicates at database level
        # This prevents the same notification from being created multiple times for the same user
        unique_together = [
            ('recipient', 'notification_type', 'related_task', 'related_project'),
            ('recipient', 'notification_type', 'related_subtask'),
        ]

    @classmethod
    def create_if_not_exists(cls, **kwargs):
        """Create notification only if it doesn't already exist"""
        from django.db import transaction
        from django.utils import timezone
        from datetime import timedelta
        
        # Use database transaction to prevent race conditions
        with transaction.atomic():
            # Check if similar notification exists within the last 24 hours to prevent spam
            twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
            
                    # Build filter based on what's provided - this is the main duplicate detection
        filter_kwargs = {
            'notification_type': kwargs.get('notification_type'),
            'created_at__gte': twenty_four_hours_ago
        }
        
        # For system-wide notifications (null recipient), we don't include recipient in the filter
        # For user-specific notifications, we include the recipient
        if kwargs.get('recipient') is not None:
            filter_kwargs['recipient'] = kwargs.get('recipient')
        else:
            # System-wide notification - check for other system-wide notifications
            filter_kwargs['recipient__isnull'] = True
            
            # Add related objects to filter if they exist
            if kwargs.get('related_task'):
                filter_kwargs['related_task'] = kwargs.get('related_task')
            if kwargs.get('related_project'):
                filter_kwargs['related_project'] = kwargs.get('related_project')
            if kwargs.get('related_subtask'):
                filter_kwargs['related_subtask'] = kwargs.get('related_subtask')
            
            # Also check if the triggered_by user is the same to prevent spam from same user
            if kwargs.get('triggered_by'):
                filter_kwargs['triggered_by'] = kwargs.get('triggered_by')
            
            # Check if similar notification exists
            existing = cls.objects.filter(**filter_kwargs).first()
            if existing:
                # Update existing notification instead of creating new one
                existing.is_read = False  # Mark as unread since it's a new update
                existing.message = kwargs.get('message', existing.message)
                existing.title = kwargs.get('title', existing.title)
                existing.save()
                print(f"DEBUG: Updated existing notification {existing.id} instead of creating duplicate")
                return existing
            
            # Additional check: look for notifications with exact same message and title within last 6 hours
            six_hours_ago = timezone.now() - timedelta(hours=6)
            exact_match_filter = {
                'recipient': kwargs.get('recipient'),
                'message': kwargs.get('message'),
                'title': kwargs.get('title'),
                'created_at__gte': six_hours_ago
            }
            
            exact_match = cls.objects.filter(**exact_match_filter).first()
            if exact_match:
                print(f"DEBUG: Found exact match notification {exact_match.id}, updating instead of creating duplicate")
                exact_match.is_read = False
                exact_match.save()
                return exact_match
            
            # Final check: look for any notification with same content within last hour (very strict)
            one_hour_ago = timezone.now() - timedelta(hours=1)
            strict_filter = {
                'recipient': kwargs.get('recipient'),
                'notification_type': kwargs.get('notification_type'),
                'message': kwargs.get('message'),
                'created_at__gte': one_hour_ago
            }
            
            strict_match = cls.objects.filter(**strict_filter).first()
            if strict_match:
                print(f"DEBUG: Found strict match notification {strict_match.id}, updating instead of creating duplicate")
                strict_match.is_read = False
                strict_match.save()
                return strict_match
            
            # Create new notification if none exists
            new_notification = cls.objects.create(**kwargs)
            print(f"DEBUG: Created new notification {new_notification.id} for {kwargs.get('recipient')}")
            return new_notification

    @classmethod
    def create_notification_with_tracking(cls, recipient, notification_type, title, message, triggered_by=None, **kwargs):
        """Create notification with user tracking"""
        notification_data = {
            'recipient': recipient,
            'notification_type': notification_type,
            'title': title,
            'message': message,
            'triggered_by': triggered_by,
            **kwargs
        }
        return cls.create_if_not_exists(**notification_data)


class TaskUpdate(models.Model):
    UPDATE_TYPES = [
        ('completed', 'Completed'),
        ('delayed', 'Delayed'),
        ('on_hold', 'On Hold'),
        ('in_progress', 'In Progress'),
        ('not_started', 'Not Started'),
        ('status_changed', 'Status Changed'),
        ('priority_changed', 'Priority Changed'),
        ('deadline_extended', 'Deadline Extended'),
        ('assigned', 'Assigned'),
        ('reassigned', 'Reassigned'),
    ]
    
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='updates')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_updates', help_text='User who made the update')
    update_type = models.CharField(max_length=20, choices=UPDATE_TYPES)
    reason = models.TextField(blank=True, help_text='Reason for delay or status change')
    estimated_completion = models.DateField(blank=True, null=True, help_text='New estimated completion date if delayed')
    old_value = models.CharField(max_length=100, blank=True, help_text='Previous value before the change')
    new_value = models.CharField(max_length=100, blank=True, help_text='New value after the change')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.task.title} - {self.update_type} by {self.user.username}"

    class Meta:
        ordering = ['-created_at']


class ProjectUpdate(models.Model):
    UPDATE_TYPES = [
        ('created', 'Created'),
        ('status_changed', 'Status Changed'),
        ('deadline_extended', 'Deadline Extended'),
        ('assigned', 'Assigned'),
        ('reassigned', 'Reassigned'),
        ('description_updated', 'Description Updated'),
        ('client_changed', 'Client Changed'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='updates')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_updates', help_text='User who made the update')
    update_type = models.CharField(max_length=25, choices=UPDATE_TYPES)
    reason = models.TextField(blank=True, help_text='Reason for the change')
    old_value = models.CharField(max_length=100, blank=True, help_text='Previous value before the change')
    new_value = models.CharField(max_length=100, blank=True, help_text='New value after the change')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.name} - {self.update_type} by {self.user.username}"

    class Meta:
        ordering = ['-created_at']


class SystemLog(models.Model):
    LOGIN = 'login'
    LOGOUT = 'logout'
    TASK_STATUS_CHANGE = 'task_status_change'
    TASK_PRIORITY_CHANGE = 'task_priority_change'
    TASK_CREATED = 'task_created'
    TASK_EDITED = 'task_edited'
    TASK_DELETED = 'task_deleted'
    TASK_ASSIGNED = 'task_assigned'
    TASK_COMMENT_ADDED = 'task_comment_added'
    PROJECT_CREATED = 'project_created'
    PROJECT_EDITED = 'project_edited'
    PROJECT_DELETED = 'project_deleted'
    PROJECT_STATUS_CHANGE = 'project_status_change'
    PROJECT_ASSIGNED = 'project_assigned'
    USER_CREATED = 'user_created'
    USER_EDITED = 'user_edited'
    USER_DELETED = 'user_deleted'
    USER_PERMISSIONS_CHANGED = 'user_permissions_changed'
    USER_SUSPENDED = 'user_suspended'
    USER_ACTIVATED = 'user_activated'
    CLIENT_CREATED = 'client_created'
    CLIENT_EDITED = 'client_edited'
    CLIENT_DELETED = 'client_deleted'
    CLIENT_ACTIVATED = 'client_activated'
    CLIENT_DEACTIVATED = 'client_deactivated'
    SUBTASK_CREATED = 'subtask_created'
    SUBTASK_EDITED = 'subtask_edited'
    SUBTASK_DELETED = 'subtask_deleted'
    SUBTASK_STATUS_CHANGE = 'subtask_status_change'
    REPORT_GENERATED = 'report_generated'
    REPORT_SENT = 'report_sent'
    BACKUP_CREATED = 'backup_created'
    BACKUP_RESTORED = 'backup_restored'
    SYSTEM_SETTINGS_CHANGED = 'system_settings_changed'
    LOGIN_ATTEMPT_FAILED = 'login_attempt_failed'
    ACCOUNT_LOCKED = 'account_locked'
    ACCOUNT_UNLOCKED = 'account_unlocked'
    NAVIGATION = 'navigation'
    
    ACTION_CHOICES = [
        (LOGIN, 'Login'),
        (LOGOUT, 'Logout'),
        (TASK_STATUS_CHANGE, 'Task Status Change'),
        (TASK_PRIORITY_CHANGE, 'Task Priority Change'),
        (TASK_CREATED, 'Task Created'),
        (TASK_EDITED, 'Task Edited'),
        (TASK_DELETED, 'Task Deleted'),
        (TASK_ASSIGNED, 'Task Assigned'),
        (TASK_COMMENT_ADDED, 'Task Comment Added'),
        (PROJECT_CREATED, 'Project Created'),
        (PROJECT_EDITED, 'Project Edited'),
        (PROJECT_DELETED, 'Project Deleted'),
        (PROJECT_STATUS_CHANGE, 'Project Status Change'),
        (PROJECT_ASSIGNED, 'Project Assigned'),
        (USER_CREATED, 'User Created'),
        (USER_EDITED, 'User Edited'),
        (USER_DELETED, 'User Deleted'),
        (USER_PERMISSIONS_CHANGED, 'User Permissions Changed'),
        (USER_SUSPENDED, 'User Suspended'),
        (USER_ACTIVATED, 'User Activated'),
        (CLIENT_CREATED, 'Client Created'),
        (CLIENT_EDITED, 'Client Edited'),
        (CLIENT_DELETED, 'Client Deleted'),
        (CLIENT_ACTIVATED, 'Client Activated'),
        (CLIENT_DEACTIVATED, 'Client Deactivated'),
        (SUBTASK_CREATED, 'Subtask Created'),
        (SUBTASK_EDITED, 'Subtask Edited'),
        (SUBTASK_DELETED, 'Subtask Deleted'),
        (SUBTASK_STATUS_CHANGE, 'Subtask Status Change'),
        (REPORT_GENERATED, 'Report Generated'),
        (REPORT_SENT, 'Report Sent'),
        (BACKUP_CREATED, 'Backup Created'),
        (BACKUP_RESTORED, 'Backup Restored'),
        (SYSTEM_SETTINGS_CHANGED, 'System Settings Changed'),
        (LOGIN_ATTEMPT_FAILED, 'Login Attempt Failed'),
        (ACCOUNT_LOCKED, 'Account Locked'),
        (ACCOUNT_UNLOCKED, 'Account Unlocked'),
        (NAVIGATION, 'Navigation'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    os_info = models.CharField(max_length=100, blank=True, null=True)
    browser_info = models.CharField(max_length=100, blank=True, null=True)
    additional_info = models.JSONField(default=dict, blank=True)
    
    # Related objects for better tracking
    related_project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    related_task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    related_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs_about_user')
    related_client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'System Log'
        verbose_name_plural = 'System Logs'

    def __str__(self):
        return f"{self.user.username} - {self.get_action_display()} - {self.timestamp}"

    @classmethod
    def log_login(cls, user, request):
        """Log user login"""
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        ip_address = cls.get_client_ip(request)
        os_info, browser_info = cls.parse_user_agent(user_agent)
        
        return cls.objects.create(
            user=user,
            action=cls.LOGIN,
            ip_address=ip_address,
            user_agent=user_agent,
            os_info=os_info,
            browser_info=browser_info
        )

    @classmethod
    def log_logout(cls, user, request):
        """Log user logout"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.LOGOUT,
            ip_address=ip_address
        )

    @classmethod
    def log_task_status_change(cls, user, task, old_status, new_status, request):
        """Log task status change"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.TASK_STATUS_CHANGE,
            ip_address=ip_address,
            related_project=task.project,
            related_task=task,
            additional_info={
                'task_id': task.id,
                'task_title': task.title,
                'project_id': task.project.id,
                'project_name': task.project.name,
                'old_status': old_status,
                'new_status': new_status,
                'change_reason': 'Status updated by user'
            }
        )

    @classmethod
    def log_task_priority_change(cls, user, task, old_priority, new_priority, request):
        """Log task priority change"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.TASK_PRIORITY_CHANGE,
            ip_address=ip_address,
            related_project=task.project,
            related_task=task,
            additional_info={
                'task_id': task.id,
                'task_title': task.title,
                'project_id': task.project.id,
                'project_name': task.project.name,
                'old_priority': old_priority,
                'new_priority': new_priority
            }
        )

    @classmethod
    def log_task_created(cls, user, task, request):
        """Log task creation"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.TASK_CREATED,
            ip_address=ip_address,
            related_project=task.project,
            related_task=task,
            additional_info={
                'task_id': task.id,
                'task_title': task.title,
                'project_id': task.project.id,
                'project_name': task.project.name,
                'priority': task.priority,
                'status': task.status,
                'estimated_hours': str(task.estimated_hours) if task.estimated_hours else None
            }
        )

    @classmethod
    def log_task_edited(cls, user, task, old_data, new_data, request):
        """Log task editing"""
        ip_address = cls.get_client_ip(request)
        
        changes = {}
        for field in old_data:
            if old_data[field] != new_data[field]:
                changes[field] = {
                    'old': str(old_data[field]) if old_data[field] is not None else 'None',
                    'new': str(new_data[field]) if new_data[field] is not None else 'None'
                }
        
        return cls.objects.create(
            user=user,
            action=cls.TASK_EDITED,
            ip_address=ip_address,
            related_project=task.project,
            related_task=task,
            additional_info={
                'task_id': task.id,
                'task_title': task.title,
                'project_id': task.project.id,
                'project_name': task.project.name,
                'changes': changes
            }
        )

    @classmethod
    def log_task_deleted(cls, user, task_title, project_name, request):
        """Log task deletion"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.TASK_DELETED,
            ip_address=ip_address,
            additional_info={
                'task_title': task_title,
                'project_name': project_name,
                'deletion_reason': 'Task removed by user'
            }
        )

    @classmethod
    def log_task_assigned(cls, user, task, assigned_users, request):
        """Log task assignment"""
        ip_address = cls.get_client_ip(request)
        
        # Safely extract usernames from assigned_users
        try:
            if assigned_users is None:
                assigned_usernames = []
            elif hasattr(assigned_users, '__iter__') and not isinstance(assigned_users, str):
                # Handle QuerySet, list, or other iterable
                assigned_usernames = []
                for u in assigned_users:
                    if hasattr(u, 'username'):
                        assigned_usernames.append(str(u.username))
                    elif isinstance(u, str):
                        assigned_usernames.append(str(u))
                    else:
                        assigned_usernames.append(str(u))
            else:
                # Handle single user object
                if hasattr(assigned_users, 'username'):
                    assigned_usernames = [str(assigned_users.username)]
                else:
                    assigned_usernames = [str(assigned_users)]
        except Exception as e:
            # Fallback if there's any error processing assigned users
            assigned_usernames = ['Error processing assigned users']
            print(f"Error processing assigned users in log_project_assigned: {e}")
            print(f"assigned_users type: {type(assigned_users)}")
            print(f"assigned_users value: {assigned_users}")
        
        return cls.objects.create(
            user=user,
            action=cls.TASK_ASSIGNED,
            ip_address=ip_address,
            related_project=task.project,
            related_task=task,
            additional_info={
                'task_id': task.id,
                'task_title': task.title,
                'project_id': task.project.id,
                'project_name': task.project.name,
                'assigned_users': assigned_usernames,
                'assigned_user_count': len(assigned_usernames)
            }
        )

    @classmethod
    def log_task_comment_added(cls, user, task, comment, request):
        """Log task comment addition"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.TASK_COMMENT_ADDED,
            ip_address=ip_address,
            related_project=task.project,
            related_task=task,
            additional_info={
                'task_id': task.id,
                'task_title': task.title,
                'project_id': task.project.id,
                'project_name': task.project.name,
                'comment_preview': comment[:100] + '...' if len(comment) > 100 else comment
            }
        )

    @classmethod
    def log_project_created(cls, user, project, request):
        """Log project creation"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.PROJECT_CREATED,
            ip_address=ip_address,
            related_project=project,
            additional_info={
                'project_id': project.id,
                'project_name': project.name,
                'client': project.client,
                'client_email': project.client_email,
                'status': project.status,
                'assigned_users_count': project.assigned_users.count()
            }
        )

    @classmethod
    def log_project_edited(cls, user, project, old_data, new_data, request):
        """Log project editing"""
        ip_address = cls.get_client_ip(request)
        
        changes = {}
        for field in old_data:
            if old_data[field] != new_data[field]:
                changes[field] = {
                    'old': str(old_data[field]) if old_data[field] is not None else 'None',
                    'new': str(new_data[field]) if new_data[field] is not None else 'None'
                }
        
        return cls.objects.create(
            user=user,
            action=cls.PROJECT_EDITED,
            ip_address=ip_address,
            related_project=project,
            additional_info={
                'project_id': project.id,
                'project_name': project.name,
                'changes': changes
            }
        )

    @classmethod
    def log_project_deleted(cls, user, project_name, client_name, request):
        """Log project deletion"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.PROJECT_DELETED,
            ip_address=ip_address,
            additional_info={
                'project_name': project_name,
                'client_name': client_name,
                'deletion_reason': 'Project removed by user'
            }
        )

    @classmethod
    def log_project_status_change(cls, user, project, old_status, new_status, request):
        """Log project status change"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.PROJECT_STATUS_CHANGE,
            ip_address=ip_address,
            related_project=project,
            additional_info={
                'project_id': project.id,
                'project_name': project.name,
                'old_status': old_status,
                'new_status': new_status,
                'change_reason': 'Status updated by user'
            }
        )

    @classmethod
    def log_project_assigned(cls, user, project, assigned_users, request):
        """Log project assignment"""
        ip_address = cls.get_client_ip(request)
        
        # Safely extract usernames from assigned_users
        try:
            if assigned_users is None:
                assigned_usernames = []
            elif hasattr(assigned_users, '__iter__') and not isinstance(assigned_users, str):
                # Handle QuerySet, list, or other iterable
                assigned_usernames = []
                for u in assigned_users:
                    if hasattr(u, 'username'):
                        assigned_usernames.append(str(u.username))
                    elif isinstance(u, str):
                        assigned_usernames.append(str(u))
                    else:
                        assigned_usernames.append(str(u))
            else:
                # Handle single user object
                if hasattr(assigned_users, 'username'):
                    assigned_usernames = [str(assigned_users.username)]
                else:
                    assigned_usernames = [str(assigned_users)]
        except Exception as e:
            # Fallback if there's any error processing assigned users
            assigned_usernames = ['Error processing assigned users']
        
        return cls.objects.create(
            user=user,
            action=cls.PROJECT_ASSIGNED,
            ip_address=ip_address,
            related_project=project,
            additional_info={
                'project_id': project.id,
                'project_name': project.name,
                'assigned_users': assigned_usernames,
                'assigned_user_count': len(assigned_usernames)
            }
        )

    @classmethod
    def log_user_created(cls, user, new_user, request):
        """Log user creation"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.USER_CREATED,
            ip_address=ip_address,
            related_user=new_user,
            additional_info={
                'new_user_id': new_user.id,
                'new_username': new_user.username,
                'new_email': new_user.email,
                'new_user_full_name': new_user.get_full_name() or 'Not provided'
            }
        )

    @classmethod
    def log_user_edited(cls, user, edited_user, old_data, new_data, request):
        """Log user editing"""
        ip_address = cls.get_client_ip(request)
        
        changes = {}
        for field in old_data:
            if old_data[field] != new_data[field]:
                changes[field] = {
                    'old': str(old_data[field]) if old_data[field] is not None else 'None',
                    'new': str(new_data[field]) if new_data[field] is not None else 'None'
                }
        
        return cls.objects.create(
            user=user,
            action=cls.USER_EDITED,
            ip_address=ip_address,
            related_user=edited_user,
            additional_info={
                'edited_user_id': edited_user.id,
                'edited_username': edited_user.username,
                'changes': changes
            }
        )

    @classmethod
    def log_user_permissions_changed(cls, user, target_user, old_permissions, new_permissions, request):
        """Log user permissions change"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.USER_PERMISSIONS_CHANGED,
            ip_address=ip_address,
            related_user=target_user,
            additional_info={
                'target_user_id': target_user.id,
                'target_username': target_user.username,
                'old_permissions': old_permissions,
                'new_permissions': new_permissions
            }
        )

    @classmethod
    def log_user_suspended(cls, user, target_user, reason, until_date, request):
        """Log user suspension"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.USER_SUSPENDED,
            ip_address=ip_address,
            related_user=target_user,
            additional_info={
                'target_user_id': target_user.id,
                'target_username': target_user.username,
                'suspension_reason': reason,
                'suspended_until': str(until_date) if until_date else 'Indefinitely'
            }
        )

    @classmethod
    def log_user_activated(cls, user, target_user, request):
        """Log user activation"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.USER_ACTIVATED,
            ip_address=ip_address,
            related_user=target_user,
            additional_info={
                'target_user_id': target_user.id,
                'target_username': target_user.username,
                'activation_reason': 'Account reactivated by admin'
            }
        )

    @classmethod
    def log_client_created(cls, user, client, request):
        """Log client creation"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.CLIENT_CREATED,
            ip_address=ip_address,
            related_client=client,
            additional_info={
                'client_id': client.id,
                'client_username': client.username,
                'client_email': client.email
            }
        )

    @classmethod
    def log_client_edited(cls, user, client, old_data, new_data, request):
        """Log client editing"""
        ip_address = cls.get_client_ip(request)
        
        changes = {}
        for field in old_data:
            if old_data[field] != new_data[field]:
                changes[field] = {
                    'old': str(old_data[field]) if old_data[field] is not None else 'None',
                    'new': str(new_data[field]) if new_data[field] is not None else 'None'
                }
        
        return cls.objects.create(
            user=user,
            action=cls.CLIENT_EDITED,
            ip_address=ip_address,
            related_client=client,
            additional_info={
                'client_id': client.id,
                'client_username': client.username,
                'changes': changes
            }
        )

    @classmethod
    def log_subtask_status_change(cls, user, subtask, old_status, new_status, request):
        """Log subtask status change"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.SUBTASK_STATUS_CHANGE,
            ip_address=ip_address,
            related_project=subtask.task.project,
            related_task=subtask.task,
            additional_info={
                'subtask_id': subtask.id,
                'subtask_title': subtask.title,
                'task_id': subtask.task.id,
                'task_title': subtask.task.title,
                'project_id': subtask.task.project.id,
                'project_name': subtask.task.project.name,
                'old_status': old_status,
                'new_status': new_status
            }
        )

    @classmethod
    def log_report_generated(cls, user, report_type, project=None, request=None):
        """Log report generation"""
        ip_address = cls.get_client_ip(request) if request else None
        
        additional_info = {
            'report_type': report_type,
            'generated_at': str(timezone.now())
        }
        
        if project:
            additional_info.update({
                'project_id': project.id,
                'project_name': project.name
            })
        
        return cls.objects.create(
            user=user,
            action=cls.REPORT_GENERATED,
            ip_address=ip_address,
            related_project=project,
            additional_info=additional_info
        )

    @classmethod
    def log_backup_created(cls, user, backup_file, request):
        """Log backup creation"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.BACKUP_CREATED,
            ip_address=ip_address,
            additional_info={
                'backup_name': backup_file.filename,
                'backup_size': backup_file.file_size_mb,
                'backup_type': backup_file.get_backup_type_display(),
                'backup_path': backup_file.file_path,
                'backup_checksum': backup_file.backup_checksum,
                'total_records': backup_file.total_records
            }
        )

    @classmethod
    def log_backup_uploaded(cls, user, backup_file, request):
        """Log backup upload"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.BACKUP_CREATED,  # Use same action for consistency
            ip_address=ip_address,
            additional_info={
                'backup_name': backup_file.filename,
                'backup_size': backup_file.file_size_mb,
                'backup_type': 'Uploaded Backup',
                'backup_path': backup_file.file_path,
                'backup_checksum': backup_file.backup_checksum,
                'upload_time': str(timezone.now())
            }
        )

    @classmethod
    def log_backup_restored(cls, user, backup_file, request):
        """Log backup restoration"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.BACKUP_RESTORED,
            ip_address=ip_address,
            additional_info={
                'backup_name': backup_file.filename,
                'backup_size': backup_file.file_size_mb,
                'backup_type': backup_file.get_backup_type_display(),
                'restore_time': str(timezone.now()),
                'backup_checksum': backup_file.backup_checksum
            }
        )

    @classmethod
    def log_backup_deleted(cls, user, backup_file, request):
        """Log backup deletion"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.SYSTEM_SETTINGS_CHANGED,  # Use system settings for deletion
            ip_address=ip_address,
            additional_info={
                'action_type': 'backup_deleted',
                'backup_name': backup_file.filename,
                'backup_size': backup_file.file_size_mb,
                'backup_type': backup_file.get_backup_type_display(),
                'deletion_time': str(timezone.now())
            }
        )

    @classmethod
    def log_backup_downloaded(cls, user, backup_file, request):
        """Log backup download"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.SYSTEM_SETTINGS_CHANGED,  # Use system settings for download
            ip_address=ip_address,
            additional_info={
                'action_type': 'backup_downloaded',
                'backup_name': backup_file.filename,
                'backup_size': backup_file.file_size_mb,
                'backup_type': backup_file.get_backup_type_display(),
                'download_time': str(timezone.now())
            }
        )

    @classmethod
    def log_backup_failed(cls, user, backup_type, error_message, request):
        """Log backup operation failure"""
        ip_address = cls.get_client_ip(request)
        
        return cls.objects.create(
            user=user,
            action=cls.SYSTEM_SETTINGS_CHANGED,  # Use system settings for failures
            ip_address=ip_address,
            additional_info={
                'action_type': 'backup_failed',
                'backup_type': backup_type,
                'error_message': error_message,
                'failure_time': str(timezone.now())
            }
        )

    @classmethod
    def log_navigation(cls, user, page_name, page_url, request):
        """Log user navigation to different pages"""
        ip_address = cls.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        os_info, browser_info = cls.parse_user_agent(user_agent)
        
        return cls.objects.create(
            user=user,
            action=cls.NAVIGATION,
            ip_address=ip_address,
            user_agent=user_agent,
            os_info=os_info,
            browser_info=browser_info,
            additional_info={
                'page_name': page_name,
                'page_url': page_url,
                'navigation_time': str(timezone.now())
            }
        )

    @classmethod
    def log_login_attempt_failed(cls, username, ip_address, user_agent, request):
        """Log failed login attempt"""
        os_info, browser_info = cls.parse_user_agent(user_agent)
        
        return cls.objects.create(
            user=None,  # No user for failed attempts
            action=cls.LOGIN_ATTEMPT_FAILED,
            ip_address=ip_address,
            user_agent=user_agent,
            os_info=os_info,
            browser_info=browser_info,
            additional_info={
                'attempted_username': username,
                'failure_reason': 'Invalid credentials',
                'timestamp': str(timezone.now())
            }
        )

    @staticmethod
    def get_client_ip(request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    @staticmethod
    def parse_user_agent(user_agent):
        """Parse user agent to extract OS and browser info"""
        os_info = "Unknown"
        browser_info = "Unknown"
        
        if user_agent:
            user_agent_lower = user_agent.lower()
            
            # OS Detection
            if 'windows' in user_agent_lower:
                os_info = "Windows"
            elif 'mac' in user_agent_lower:
                os_info = "macOS"
            elif 'linux' in user_agent_lower:
                os_info = "Linux"
            elif 'android' in user_agent_lower:
                os_info = "Android"
            elif 'ios' in user_agent_lower:
                os_info = "iOS"
            
            # Browser Detection
            if 'chrome' in user_agent_lower:
                browser_info = "Chrome"
            elif 'firefox' in user_agent_lower:
                browser_info = "Firefox"
            elif 'safari' in user_agent_lower:
                browser_info = "Safari"
            elif 'edge' in user_agent_lower:
                browser_info = "Edge"
            elif 'opera' in user_agent_lower:
                browser_info = "Opera"
        
        return os_info, browser_info


class SentReport(models.Model):
    """Track all reports that have been sent"""
    REPORT_TYPES = [
        ('general', 'General Report'),
        ('project', 'Project Report'),
        ('client', 'Client Report'),
        ('friday', 'Friday Report'),
        ('complete', 'Complete Report'),
    ]
    
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    sent_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_reports')
    recipient_email = models.EmailField()
    report_title = models.CharField(max_length=200, blank=True)
    report_data = models.JSONField(default=dict, blank=True)
    custom_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='sent', choices=[
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('delivered', 'Delivered'),
    ])
    
    # Related objects for better tracking
    related_project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    related_client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Sent Report'
        verbose_name_plural = 'Sent Reports'
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.recipient_email} - {self.sent_at.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def log_report_sent(cls, report_type, sent_by, recipient_email, report_title='', report_data=None, custom_message='', related_project=None, related_client=None, status='sent'):
        """Log a report being sent"""
        return cls.objects.create(
            report_type=report_type,
            sent_by=sent_by,
            recipient_email=recipient_email,
            report_title=report_title,
            report_data=report_data or {},
            custom_message=custom_message,
            related_project=related_project,
            related_client=related_client,
            status=status
        )


class BackupFile(models.Model):
    """Model to track backup files and their metadata"""
    BACKUP_TYPE_CHOICES = [
        ('manual', 'Manual Backup'),
        ('automatic', 'Automatic Backup'),
        ('uploaded', 'Uploaded Backup'),
    ]
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('corrupted', 'Corrupted'),
        ('restored', 'Restored'),
    ]
    
    filename = models.CharField(max_length=255, unique=True)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(help_text='File size in bytes')
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPE_CHOICES, default='manual')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    description = models.TextField(blank=True, help_text='Optional description of this backup')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_backups')
    created_at = models.DateTimeField(auto_now_add=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='restored_backups')
    
    # Backup metadata
    database_version = models.CharField(max_length=50, blank=True)
    total_records = models.IntegerField(default=0)
    backup_checksum = models.CharField(max_length=64, blank=True, help_text='SHA256 checksum for integrity verification')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Backup File'
        verbose_name_plural = 'Backup Files'
    
    def __str__(self):
        return f"{self.filename} ({self.get_backup_type_display()}) - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    @property
    def file_size_mb(self):
        """Return file size in MB"""
        return round(self.file_size / (1024 * 1024), 2)
    
    @property
    def is_available(self):
        """Check if backup file is available for restore"""
        import os
        try:
            return os.path.exists(self.file_path) and self.status == 'available'
        except Exception:
            return False

class AIKnowledgeBase(models.Model):
    """AI Knowledge Base for storing learned information"""
    question = models.TextField()
    answer = models.TextField()
    confidence_score = models.FloatField(default=0.0)
    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list, blank=True)
    
    class Meta:
        ordering = ['-confidence_score', '-usage_count']
        verbose_name = 'AI Knowledge Entry'
        verbose_name_plural = 'AI Knowledge Base'
    
    def __str__(self):
        return f"{self.question[:50]}... -> {self.answer[:50]}..."

class AIConversation(models.Model):
    """AI Conversation history for learning"""
    user_id = models.CharField(max_length=100, blank=True)  # Can be anonymous
    session_id = models.CharField(max_length=100)
    question = models.TextField()
    answer = models.TextField()
    was_helpful = models.BooleanField(null=True, blank=True)  # User feedback
    response_time = models.FloatField(default=0.0)  # Response time in seconds
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI Conversation'
        verbose_name_plural = 'AI Conversations'
    
    def __str__(self):
        return f"{self.user_id or 'Anonymous'} - {self.question[:50]}..."

class AILearningMetrics(models.Model):
    """Metrics for AI learning progress"""
    total_conversations = models.IntegerField(default=0)
    successful_responses = models.IntegerField(default=0)
    average_response_time = models.FloatField(default=0.0)
    knowledge_base_size = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'AI Learning Metric'
        verbose_name_plural = 'AI Learning Metrics'
    
    def __str__(self):
        return f"AI Metrics - {self.total_conversations} conversations"


# ============================================================================
# SIGNALS FOR AUTOMATIC FOLDER CREATION
# ============================================================================

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings


def create_user_folders(user, is_admin=False):
    """Create profile picture folders for a user"""
    try:
        # Determine the base folder based on user type
        if is_admin or user.is_staff or user.is_superuser:
            base_folder = 'admin'
        else:
            base_folder = 'users'
        
        # Create the user's folder
        user_folder = os.path.join(settings.MEDIA_ROOT, base_folder, user.username)
        if not os.path.exists(user_folder):
            os.makedirs(user_folder, exist_ok=True)
            print(f"📁 Created folder: {base_folder}/{user.username}/")
        
        return user_folder
    except Exception as e:
        print(f"❌ Error creating folder for {user.username}: {e}")
        return None


def create_client_folders(client):
    """Create profile picture folders for a client"""
    try:
        # Create the client's folder
        client_folder = os.path.join(settings.MEDIA_ROOT, 'clients', client.username)
        if not os.path.exists(client_folder):
            os.makedirs(client_folder, exist_ok=True)
            print(f"📁 Created folder: clients/{client.username}/")
        
        return client_folder
    except Exception as e:
        print(f"❌ Error creating folder for client {client.username}: {e}")
        return None


@receiver(post_save, sender=User)
def create_user_profile_and_folders(sender, instance, created, **kwargs):
    """Create UserProfile and folders when a User is created"""
    if created:
        # Create UserProfile
        UserProfile.objects.get_or_create(user=instance)
        
        # Create folders
        is_admin = instance.is_staff or instance.is_superuser
        create_user_folders(instance, is_admin)
        
        print(f"✅ Created profile and folders for user: {instance.username}")


@receiver(post_save, sender=User)
def update_user_folders_on_status_change(sender, instance, **kwargs):
    """Update user folders when admin status changes"""
    if not kwargs.get('created', False):  # Only for updates, not creation
        try:
            # Check if admin status changed
            old_instance = User.objects.get(pk=instance.pk)
            if old_instance.is_staff != instance.is_staff or old_instance.is_superuser != instance.is_superuser:
                # Admin status changed, reorganize folders
                old_is_admin = old_instance.is_staff or old_instance.is_superuser
                new_is_admin = instance.is_staff or instance.is_superuser
                
                if old_is_admin != new_is_admin:
                    # Create new folder structure
                    create_user_folders(instance, new_is_admin)
                    print(f"🔄 Updated folder structure for {instance.username} (admin: {new_is_admin})")
        except User.DoesNotExist:
            pass  # User was just created


@receiver(post_save, sender=Client)
def create_client_folders_on_creation(sender, instance, created, **kwargs):
    """Create folders when a Client is created"""
    if created:
        create_client_folders(instance)
        print(f"✅ Created folders for client: {instance.username}")


@receiver(post_save, sender=UserProfile)
def ensure_user_folders_exist(sender, instance, created, **kwargs):
    """Ensure user folders exist when UserProfile is created/updated"""
    if created or instance.profile_picture:
        # Ensure folders exist
        is_admin = instance.user.is_staff or instance.user.is_superuser
        create_user_folders(instance.user, is_admin)


@receiver(post_delete, sender=User)
def cleanup_user_folders(sender, instance, **kwargs):
    """Clean up user folders when User is deleted"""
    try:
        # Determine folder path
        if instance.is_staff or instance.is_superuser:
            folder_path = os.path.join(settings.MEDIA_ROOT, 'admin', instance.username)
        else:
            folder_path = os.path.join(settings.MEDIA_ROOT, 'users', instance.username)
        
        # Remove folder if it exists and is empty
        if os.path.exists(folder_path):
            if not os.listdir(folder_path):  # Empty folder
                os.rmdir(folder_path)
                print(f"🗑️ Removed empty folder: {folder_path}")
            else:
                print(f"⚠️ Folder not empty, keeping: {folder_path}")
    except Exception as e:
        print(f"❌ Error cleaning up folders for {instance.username}: {e}")


@receiver(post_delete, sender=Client)
def cleanup_client_folders(sender, instance, **kwargs):
    """Clean up client folders when Client is deleted"""
    try:
        folder_path = os.path.join(settings.MEDIA_ROOT, 'clients', instance.username)
        
        # Remove folder if it exists and is empty
        if os.path.exists(folder_path):
            if not os.listdir(folder_path):  # Empty folder
                os.rmdir(folder_path)
                print(f"🗑️ Removed empty folder: {folder_path}")
            else:
                print(f"⚠️ Folder not empty, keeping: {folder_path}")
    except Exception as e:
        print(f"❌ Error cleaning up folders for client {instance.username}: {e}")


# ============================================================================
# UTILITY FUNCTIONS FOR FOLDER MANAGEMENT
# ============================================================================

def ensure_all_user_folders_exist():
    """Ensure all existing users have their folders created"""
    print("🔍 Checking and creating user folders...")
    
    # Create folders for all existing users
    for user in User.objects.all():
        is_admin = user.is_staff or user.is_superuser
        create_user_folders(user, is_admin)
    
    # Create folders for all existing clients
    for client in Client.objects.all():
        create_client_folders(client)
    
    print("✅ All user folders checked and created!")


def cleanup_empty_folders():
    """Remove empty profile picture folders"""
    print("🧹 Cleaning up empty folders...")
    
    base_folders = ['admin', 'users', 'clients']
    
    for base_folder in base_folders:
        base_path = os.path.join(settings.MEDIA_ROOT, base_folder)
        if os.path.exists(base_path):
            for user_folder in os.listdir(base_path):
                user_folder_path = os.path.join(base_path, user_folder)
                if os.path.isdir(user_folder_path) and not os.listdir(user_folder_path):
                    try:
                        os.rmdir(user_folder_path)
                        print(f"🗑️ Removed empty folder: {base_folder}/{user_folder}/")
                    except Exception as e:
                        print(f"❌ Error removing {user_folder_path}: {e}")
    
    print("✅ Empty folder cleanup completed!")