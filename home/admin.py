from django.contrib import admin
from .models import Project, Task, SubTask, UserProfile, Client, ClientOTP, UserOTP, Notification, TaskUpdate, SystemLog, TaskComment, SubTaskComment

# Register your models here.


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'client', 'status', 'start_date', 'end_date', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'client', 'client_email']
    filter_horizontal = ['assigned_users']
    date_hierarchy = 'created_at'


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'status', 'priority', 'development_status', 'start_date', 'end_date']
    list_filter = ['status', 'priority', 'development_status', 'created_at']
    search_fields = ['title', 'description', 'project__name']
    date_hierarchy = 'created_at'


@admin.register(SubTask)
class SubTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'task', 'status', 'priority', 'is_completed', 'created_at']
    list_filter = ['status', 'priority', 'is_completed', 'created_at']
    search_fields = ['title', 'description', 'task__title']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'user__email']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'is_active', 'has_changed_password', 'created_at']
    list_filter = ['is_active', 'has_changed_password', 'created_at']
    search_fields = ['username', 'email']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['cleanup_orphaned_clients']
    
    def cleanup_orphaned_clients(self, request, queryset):
        """Clean up clients that are not associated with any projects"""
        from .models import Project
        
        cleaned_count = 0
        for client in queryset:
            # Check if this client is associated with any active projects
            has_active_projects = Project.objects.filter(
                client_email=client.email
            ).exists()
            
            if not has_active_projects:
                # Delete related OTPs first
                from .models import ClientOTP
                ClientOTP.objects.filter(client=client).delete()
                
                # Delete the client
                client.delete()
                cleaned_count += 1
        
        if cleaned_count > 0:
            self.message_user(request, f"Successfully cleaned up {cleaned_count} orphaned client records.")
        else:
            self.message_user(request, "No orphaned client records found in the selection.")
    
    cleanup_orphaned_clients.short_description = "Clean up orphaned clients (no active projects)"


@admin.register(ClientOTP)
class ClientOTPAdmin(admin.ModelAdmin):
    list_display = ['client', 'otp', 'is_used', 'expires_at', 'created_at']
    list_filter = ['is_used', 'expires_at', 'created_at']
    search_fields = ['client__username', 'client__email']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(UserOTP)
class UserOTPAdmin(admin.ModelAdmin):
    list_display = ['user', 'otp', 'is_used', 'expires_at', 'created_at']
    list_filter = ['is_used', 'expires_at', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'title', 'is_read', 'is_admin_notification', 'created_at']
    list_filter = ['notification_type', 'is_read', 'is_admin_notification', 'created_at']
    search_fields = ['title', 'message', 'recipient__username']
    readonly_fields = ['created_at']
    list_editable = ['is_read']
    actions = ['mark_as_read', 'mark_as_unread', 'delete_selected']
    
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
        self.message_user(request, f"{queryset.count()} notifications marked as read.")
    mark_as_read.short_description = "Mark selected notifications as read"
    
    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False)
        self.message_user(request, f"{queryset.count()} notifications marked as unread.")
    mark_as_unread.short_description = "Mark selected notifications as unread"


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'task', 'is_admin_response', 'created_at', 'comment_preview']
    list_filter = ['is_admin_response', 'created_at', 'user']
    search_fields = ['comment', 'user__username', 'task__title']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_admin_response']
    
    def comment_preview(self, obj):
        return obj.comment[:100] + '...' if len(obj.comment) > 100 else obj.comment
    comment_preview.short_description = 'Comment Preview'


@admin.register(SubTaskComment)
class SubTaskCommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'subtask', 'is_admin_response', 'created_at', 'comment_preview']
    list_filter = ['is_admin_response', 'created_at', 'user']
    search_fields = ['comment', 'user__username', 'subtask__title']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_admin_response']
    
    def comment_preview(self, obj):
        return obj.comment[:100] + '...' if len(obj.comment) > 100 else obj.comment
    comment_preview.short_description = 'Comment Preview'


@admin.register(TaskUpdate)
class TaskUpdateAdmin(admin.ModelAdmin):
    list_display = ['task', 'user', 'update_type', 'estimated_completion', 'created_at']
    list_filter = ['update_type', 'created_at']
    search_fields = ['task__title', 'user__username', 'reason']
    readonly_fields = ['created_at']


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'timestamp', 'ip_address', 'os_info', 'browser_info']
    list_filter = ['action', 'timestamp', 'os_info', 'browser_info']
    search_fields = ['user__username', 'user__email', 'ip_address']
    readonly_fields = ['timestamp', 'ip_address', 'user_agent', 'os_info', 'browser_info', 'additional_info']
    ordering = ['-timestamp']
    
    def has_add_permission(self, request):
        return False  # System logs should only be created automatically
    
    def has_change_permission(self, request, obj=None):
        return False  # System logs should not be editable
