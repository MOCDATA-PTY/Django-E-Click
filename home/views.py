from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings as django_settings
from django.utils import timezone
from django.db.models import Min, Max, Count, Q, Avg, F, ExpressionWrapper, fields
from django.core.paginator import Paginator
from django.db import transaction
from django.core.cache import cache
import json
import os
import shutil
# Matplotlib removed - charts will be disabled
MATPLOTLIB_AVAILABLE = False
from datetime import datetime, timedelta
from .models import Project, Task, SubTask, UserProfile, Client, ClientOTP, TaskUpdate, Notification, SystemLog, UserOTP, TaskComment, SubTaskComment, BackupFile
# from .email_service import SimpleEmailService  # No longer used - using Gmail API instead
import hashlib
import secrets
import random
import json
from .ai_service import ai_service
from .decorators import require_admin_access
from .services import GoogleCloudEmailService
from .db_utils import optimize_dashboard_queries, monitor_query_performance
import uuid

# Create email service instance - now using Gmail API with OAuth2
# email_service = SimpleEmailService()  # Commented out - using Gmail API instead

def home(request):
    return render(request, 'home/index.html')

def about(request):
    """Public About page"""
    return render(request, 'home/about.html')

def solutions(request):
    """Public Solutions page"""
    return render(request, 'home/solutions.html')

def contact(request):
    """Public Contact page"""
    return render(request, 'home/contact.html')

def services(request):
    """Public Services page (supports existing template links)"""
    return render(request, 'home/services.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # First try to authenticate as a Django user (admin/staff)
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if user account is active
            if not user.is_active:
                messages.error(request, 'Account is disabled. Please contact administrator.')
                return render(request, 'home/login.html')
            
            # Check account status (suspension, locking)
            try:
                profile = user.profile
                
                # Check if account is suspended
                if not profile.is_account_active():
                    messages.error(request, f'Account suspended: {profile.suspension_reason or "No reason provided"}')
                    return render(request, 'home/login.html')
                
                # Check if account is locked
                if profile.is_account_locked():
                    messages.error(request, 'Account temporarily locked due to multiple failed login attempts. Please try again later.')
                    return render(request, 'home/login.html')
                
                # Reset login attempts on successful login
                profile.reset_login_attempts()
                
            except UserProfile.DoesNotExist:
                # Create profile if it doesn't exist
                profile = UserProfile.objects.create(user=user)
            
            # User login successful
            login(request, user)
            # Log the login activity
            SystemLog.log_login(user, request)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            # Failed login attempt - record it if user exists
            try:
                user = User.objects.get(username=username)
                try:
                    profile = user.profile
                    profile.record_failed_login()
                    
                    # Check if account should be locked
                    if profile.is_account_locked():
                        messages.error(request, 'Account temporarily locked due to multiple failed login attempts. Please try again later.')
                        return render(request, 'home/login.html')
                    
                except UserProfile.DoesNotExist:
                    profile = UserProfile.objects.create(user=user)
                    profile.record_failed_login()
            except User.DoesNotExist:
                pass
            
            # Try to authenticate as a client
            try:
                client = Client.objects.get(username=username, is_active=True)
                # Check if client has a password set
                if client.password:
                    # Hash the provided password and compare
                    password_hash = hashlib.sha256(password.encode()).hexdigest()
                    if client.password == password_hash:
                        # Client login successful
                        request.session['client_id'] = client.id
                        request.session['client_username'] = client.username
                        messages.success(request, f'Welcome back, {client.username}!')
                        return redirect('client_dashboard')
                    else:
                        messages.error(request, 'Invalid password.')
                else:
                    messages.error(request, 'Account not set up. Please check your email for setup instructions.')
            except Client.DoesNotExist:
                messages.error(request, 'Invalid username or password.')
    
    return render(request, 'home/login.html')

@login_required
@monitor_query_performance
def dashboard(request):
    from django.utils import timezone
    from datetime import timedelta
    
    # Log navigation to dashboard
    SystemLog.log_navigation(
        user=request.user,
        page_name='Dashboard',
        page_url=request.path,
        request=request
    )
    
    # Get current date for display
    current_date = timezone.now()
    
    # Try to get cached dashboard data first
    cache_key = f'dashboard_data_{request.user.id}_{request.user.is_staff}'
    cached_context = cache.get(cache_key)
    
    if cached_context and not request.GET.get('refresh'):
        return render(request, 'home/dashboard.html', cached_context)
    
    if request.user.is_staff:
        # Admin/Staff Dashboard - Show all projects and statistics
        # Use optimized queries with select_related
        projects = Project.objects.all()
        tasks = Task.objects.select_related('project')
        
        # Calculate statistics efficiently
        total_projects = projects.count()
        active_projects = projects.filter(status='in_progress').count()
        completed_projects = projects.filter(status='completed').count()
        
        # Calculate new projects this week
        week_ago = current_date - timedelta(days=7)
        new_projects = projects.filter(created_at__gte=week_ago).count()
        
        # Calculate active percentage
        active_percentage = (active_projects / total_projects * 100) if total_projects > 0 else 0
        
        # Task statistics
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(status='completed').count()
        pending_tasks = tasks.filter(status__in=['not_started', 'in_progress']).count()
        
        # Calculate completed tasks this week
        completed_this_week = tasks.filter(
            status='completed',
            updated_at__gte=week_ago
        ).count()
        
        # Calculate pending percentage
        pending_percentage = (pending_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Performance metrics
        completion_rate = (completed_projects / total_projects * 100) if total_projects > 0 else 0
        efficiency_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Calculate on-time delivery rate (simplified)
        overdue_tasks = tasks.filter(
            end_date__lt=current_date.date(),
            status__in=['not_started', 'in_progress']
        ).count()
        on_time_rate = ((total_tasks - overdue_tasks) / total_tasks * 100) if total_tasks > 0 else 0
        
        # Recent activities (simplified for now)
        recent_activities = []
        
        # Add recent project activities with optimized queries
        recent_projects = projects.order_by('-updated_at')[:5]
        for project in recent_projects:
            recent_activities.append({
                'text': f'Project "{project.name}" was updated',
                'time': project.updated_at.strftime('%b %d, %H:%M')
            })
        
        # Add recent task activities
        recent_tasks = tasks.order_by('-updated_at')[:5]
        for task in recent_tasks:
            recent_activities.append({
                'text': f'Task "{task.title}" status changed to {task.status}',
                'time': task.updated_at.strftime('%b %d, %H:%M')
            })
        
        # Sort activities by time and take the most recent 10
        recent_activities.sort(key=lambda x: x['time'], reverse=True)
        recent_activities = recent_activities[:10]
        
        context = {
            'current_date': current_date,
            'total_projects': total_projects,
            'active_projects': active_projects,
            'new_projects': new_projects,
            'active_percentage': round(active_percentage, 1),
            'completed_tasks': completed_tasks,
            'completed_this_week': completed_this_week,
            'pending_tasks': pending_tasks,
            'pending_percentage': round(pending_percentage, 1),
            'completion_rate': round(completion_rate, 1),
            'efficiency_rate': round(efficiency_rate, 1),
            'on_time_rate': round(on_time_rate, 1),
            'recent_activities': recent_activities,
            'is_admin_dashboard': True,
        }
        
    else:
        # User Dashboard - Show only assigned projects and tasks
        # Get user's assigned projects with optimized queries
        assigned_projects = Project.objects.filter(
            assigned_users=request.user
        )
        
        # Calculate user-specific statistics efficiently
        total_assigned_projects = assigned_projects.count()
        active_assigned_projects = assigned_projects.filter(status='in_progress').count()
        completed_assigned_projects = assigned_projects.filter(status='completed').count()
        
        # Get user's assigned tasks with optimized queries
        assigned_tasks = Task.objects.filter(
            project__in=assigned_projects
        ).select_related('project')
        
        total_assigned_tasks = assigned_tasks.count()
        completed_assigned_tasks = assigned_tasks.filter(status='completed').count()
        pending_assigned_tasks = assigned_tasks.filter(status__in=['not_started', 'in_progress']).count()
        
        # Calculate completed tasks this week
        week_ago = current_date - timedelta(days=7)
        completed_this_week = assigned_tasks.filter(
            status='completed',
            updated_at__gte=week_ago
        ).count()
        
        # Calculate percentages
        active_percentage = (active_assigned_projects / total_assigned_projects * 100) if total_assigned_projects > 0 else 0
        pending_percentage = (pending_assigned_tasks / total_assigned_tasks * 100) if total_assigned_tasks > 0 else 0
        completion_rate = (completed_assigned_projects / total_assigned_projects * 100) if total_assigned_projects > 0 else 0
        efficiency_rate = (completed_assigned_tasks / total_assigned_tasks * 100) if total_assigned_tasks > 0 else 0
        
        # Get overdue tasks
        overdue_tasks = assigned_tasks.filter(
            end_date__lt=current_date.date(),
            status__in=['not_started', 'in_progress']
        ).count()
        on_time_rate = ((total_assigned_tasks - overdue_tasks) / total_assigned_tasks * 100) if total_assigned_tasks > 0 else 0
        
        # Recent activities for user's projects
        recent_activities = []
        
        # Add recent project activities for assigned projects
        recent_projects = assigned_projects.order_by('-updated_at')[:5]
        for project in recent_projects:
            recent_activities.append({
                'text': f'Project "{project.name}" was updated',
                'time': project.updated_at.strftime('%b %d, %H:%M')
            })
        
        # Add recent task activities for assigned tasks
        recent_tasks = assigned_tasks.order_by('-updated_at')[:5]
        for task in recent_tasks:
            recent_activities.append({
                'text': f'Task "{task.title}" status changed to {task.status}',
                'time': task.updated_at.strftime('%b %d, %H:%M')
            })
        
        # Sort activities by time and take the most recent 10
        recent_activities.sort(key=lambda x: x['time'], reverse=True)
        recent_activities = recent_activities[:10]
        
        # Get upcoming tasks (due in next 7 days)
        upcoming_tasks = assigned_tasks.filter(
            end_date__gte=current_date.date(),
            end_date__lte=current_date.date() + timedelta(days=7),
            status__in=['not_started', 'in_progress']
        ).order_by('end_date')[:5]
        
        # Get urgent tasks (tasks due soon)
        urgent_tasks = assigned_tasks.filter(
            end_date__lte=current_date.date() + timedelta(days=3),
            status__in=['not_started', 'in_progress']
        ).order_by('end_date')[:5]
        
        context = {
            'current_date': current_date,
            'total_projects': total_assigned_projects,
            'active_projects': active_assigned_projects,
            'new_projects': 0,  # Not relevant for user dashboard
            'active_percentage': round(active_percentage, 1),
            'completed_tasks': completed_assigned_tasks,
            'completed_this_week': completed_this_week,
            'pending_tasks': pending_assigned_tasks,
            'pending_percentage': round(pending_percentage, 1),
            'completion_rate': round(completion_rate, 1),
            'efficiency_rate': round(efficiency_rate, 1),
            'on_time_rate': round(on_time_rate, 1),
            'recent_activities': recent_activities,
            'upcoming_tasks': upcoming_tasks,
            'urgent_tasks': urgent_tasks,
            'assigned_projects': assigned_projects.order_by('-updated_at')[:5],
            'is_admin_dashboard': False,
        }
    
    # Cache the context for 5 minutes to improve performance
    cache.set(cache_key, context, 300)
    
    return render(request, 'home/dashboard.html', context)

@login_required
def analytics(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    # Get real data from database
    from datetime import timedelta
    from django.utils import timezone
    
    # Current date and previous month for comparison
    current_date = timezone.now()
    previous_month = current_date - timedelta(days=30)
    
    # Project statistics
    total_projects = Project.objects.count()
    active_projects = Project.objects.filter(status='in_progress').count()
    completed_projects = Project.objects.filter(status='completed').count()
    planned_projects = Project.objects.filter(status='planned').count()
    
    # Task statistics
    total_tasks = Task.objects.count()
    completed_tasks = Task.objects.filter(status='completed').count()
    in_progress_tasks = Task.objects.filter(status='in_progress').count()
    not_started_tasks = Task.objects.filter(status='not_started').count()
    on_hold_tasks = Task.objects.filter(status='on_hold').count()
    
    # Task priority statistics
    low_priority_tasks = Task.objects.filter(priority='low').count()
    medium_priority_tasks = Task.objects.filter(priority='medium').count()
    high_priority_tasks = Task.objects.filter(priority='high').count()
    urgent_priority_tasks = Task.objects.filter(priority='urgent').count()
    
    # SubTask priority statistics
    low_priority_subtasks = SubTask.objects.filter(priority='low').count()
    medium_priority_subtasks = SubTask.objects.filter(priority='medium').count()
    high_priority_subtasks = SubTask.objects.filter(priority='high').count()
    urgent_priority_subtasks = SubTask.objects.filter(priority='urgent').count()
    
    # User statistics
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    
    # Client statistics
    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(is_active=True).count()
    
    # Calculate completion rates
    project_completion_rate = (completed_projects / total_projects * 100) if total_projects > 0 else 0
    task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # Calculate trends (compare with previous month)
    previous_month_projects = Project.objects.filter(
        created_at__gte=previous_month,
        created_at__lt=current_date
    ).count()
    
    current_month_projects = Project.objects.filter(
        created_at__gte=current_date.replace(day=1)
    ).count()
    
    project_trend = ((current_month_projects - previous_month_projects) / previous_month_projects * 100) if previous_month_projects > 0 else 0
    project_trend_abs = abs(project_trend)
    
    # Monthly data for charts (last 6 months)
    monthly_data = []
    for i in range(6):
        month_start = current_date - timedelta(days=30 * (i + 1))
        month_end = current_date - timedelta(days=30 * i)
        
        projects_created = Project.objects.filter(
            created_at__gte=month_start,
            created_at__lt=month_end
        ).count()
        
        tasks_created = Task.objects.filter(
            created_at__gte=month_start,
            created_at__lt=month_end
        ).count()
        
        monthly_data.append({
            'month': month_start.strftime('%b'),
            'projects': projects_created,
            'tasks': tasks_created
        })
    
    # Reverse to show oldest to newest
    monthly_data.reverse()
    
    # Project status data for pie chart
    project_status_data = {
        'planned': planned_projects,
        'in_progress': active_projects,
        'completed': completed_projects
    }
    
    # Task status data for bar chart
    task_status_data = {
        'not_started': not_started_tasks,
        'in_progress': in_progress_tasks,
        'on_hold': on_hold_tasks,
        'completed': completed_tasks
    }
    
    # Task priority data for pie chart
    task_priority_data = {
        'low': low_priority_tasks,
        'medium': medium_priority_tasks,
        'high': high_priority_tasks,
        'urgent': urgent_priority_tasks
    }
    
    # SubTask priority data for pie chart
    subtask_priority_data = {
        'low': low_priority_subtasks,
        'medium': medium_priority_subtasks,
        'high': high_priority_subtasks,
        'urgent': urgent_priority_subtasks
    }
    

    
    # Client project distribution
    client_project_data = []
    for client in Client.objects.filter(is_active=True):
        client_projects = Project.objects.filter(client_username=client.username)
        if client_projects.exists():
            client_project_data.append({
                'client': client.username,
                'projects': client_projects.count(),
                'completed': client_projects.filter(status='completed').count(),
                'in_progress': client_projects.filter(status='in_progress').count()
            })
    
    # Top performing projects
    top_projects = []
    for project in Project.objects.all():
        project_tasks = project.tasks.all()
        if project_tasks.exists():
            completion_rate = (project_tasks.filter(status='completed').count() / project_tasks.count()) * 100
            top_projects.append({
                'name': project.name,
                'completion_rate': round(completion_rate, 1),
                'total_tasks': project_tasks.count(),
                'completed_tasks': project_tasks.filter(status='completed').count()
            })
    
    # Sort by completion rate and take top 5
    top_projects.sort(key=lambda x: x['completion_rate'], reverse=True)
    top_projects = top_projects[:5]
    
    # Recent activity (last 7 days)
    recent_activity = []
    
    # Recent projects
    recent_projects = Project.objects.filter(
        updated_at__gte=current_date - timedelta(days=7)
    ).order_by('-updated_at')[:5]
    
    for project in recent_projects:
        recent_activity.append({
            'type': 'project',
            'title': f'Project "{project.name}" updated',
            'time': project.updated_at.strftime('%b %d, %H:%M'),
            'status': project.status
        })
    
    # Recent tasks
    recent_tasks = Task.objects.filter(
        updated_at__gte=current_date - timedelta(days=7)
    ).order_by('-updated_at')[:5]
    
    for task in recent_tasks:
        recent_activity.append({
            'type': 'task',
            'title': f'Task "{task.title}" status: {task.status}',
            'time': task.updated_at.strftime('%b %d, %H:%M'),
            'status': task.status
        })
    
    # Sort by time and take most recent 8
    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:8]
    
    # Performance metrics for radar chart
    performance_metrics = {
        'project_completion': round(project_completion_rate, 1),
        'task_completion': round(task_completion_rate, 1),
        'user_activity': round((active_users / total_users * 100) if total_users > 0 else 0, 1),
        'client_engagement': round((active_clients / total_clients * 100) if total_clients > 0 else 0, 1),
        'system_health': 85  # Placeholder - could be calculated based on various metrics
    }
    
    context = {
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'planned_projects': planned_projects,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'not_started_tasks': not_started_tasks,
        'on_hold_tasks': on_hold_tasks,
        'low_priority_tasks': low_priority_tasks,
        'medium_priority_tasks': medium_priority_tasks,
        'high_priority_tasks': high_priority_tasks,
        'urgent_priority_tasks': urgent_priority_tasks,
        'low_priority_subtasks': low_priority_subtasks,
        'medium_priority_subtasks': medium_priority_subtasks,
        'high_priority_subtasks': high_priority_subtasks,
        'urgent_priority_subtasks': urgent_priority_subtasks,
        'total_users': total_users,
        'active_users': active_users,
        'total_clients': total_clients,
        'active_clients': active_clients,
        'project_completion_rate': round(project_completion_rate, 1),
        'task_completion_rate': round(task_completion_rate, 1),
        'project_trend': round(project_trend, 1),
        'project_trend_abs': round(project_trend_abs, 1),
        'monthly_data': monthly_data,
        'project_status_data': project_status_data,
        'task_status_data': task_status_data,
        'task_priority_data': task_priority_data,
        'subtask_priority_data': subtask_priority_data,

        'client_project_data': client_project_data,
        'top_projects': top_projects,
        'recent_activity': recent_activity,
        'performance_metrics': performance_metrics,
    }
    
    return render(request, 'home/analytics.html', context)

@login_required
def add_project(request):
    # Check if user has permission to create projects
    try:
        profile = request.user.profile
        if not profile.can_create_projects and not request.user.is_staff:
            messages.error(request, 'Access denied. You do not have permission to create projects.')
            return redirect('projects_page')
    except UserProfile.DoesNotExist:
        if not request.user.is_staff:
            messages.error(request, 'Access denied. Only administrators can create projects.')
            return redirect('projects_page')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        client = request.POST.get('client')
        client_username = request.POST.get('client_username', '')
        client_email = request.POST.get('client_email')
        status = request.POST.get('status', 'planned')
        assigned_user_ids = request.POST.getlist('assigned_users')
        is_existing_client = request.POST.get('is_existing_client') == 'true'
        
        if name and client and client_email:
            try:
                # Project dates will be calculated automatically from task dates
                
                # Handle existing client selection
                existing_client_id = request.POST.get('existing_client_id')
                existing_client = None
                
                if is_existing_client and existing_client_id:
                    # User selected an existing client from dropdown
                    try:
                        existing_client = Client.objects.get(id=existing_client_id)
                        client_username = existing_client.username
                        client_email = existing_client.email
                        client = existing_client.username  # Use username as client name
                        messages.info(request, f'Using existing client: {existing_client.username}')
                    except Client.DoesNotExist:
                        messages.error(request, 'Selected client not found. Please try again.')
                        return redirect('projects_page')
                elif is_existing_client and not existing_client_id:
                    # User marked as existing but didn't select a client
                    messages.error(request, 'Please select an existing client from the dropdown.')
                    return redirect('projects_page')
                else:
                    # New client - check if email already exists
                    try:
                        existing_client = Client.objects.get(email=client_email)
                        messages.error(request, f'Client with email {client_email} already exists. Please select "Existing Client" or use a different email.')
                        return redirect('projects_page')
                    except Client.DoesNotExist:
                        # New client - will need OTP
                        if not client_username:
                            # Generate username from email if not provided
                            client_username = client_email.split('@')[0]
                        
                        # Create new client
                        new_client = Client.objects.create(
                            username=client_username,
                            email=client_email,
                            is_active=True
                        )
                        
                        # Generate and send OTP for new client
                        otp = new_client.generate_otp()
                        
                        # Send OTP email using Gmail API
                        site_url = "http://127.0.0.1:8000"
                        gmail_service = GoogleCloudEmailService()
                        email_result = gmail_service.send_email(
                            to_email=client_email,
                            subject=f"Set Your Password - {name} Project",
                            body=f"""
                            Dear {client_username},

                            Welcome to the {name} project! Please use the following OTP to set your password:

                            🔐 Your OTP: {otp}

                            Please visit: {site_url}/client/setup-password/

                            Best regards,
                            E-Click Project Management Team
                            """,
                            from_email=None  # Will use OAuth2 account email
                        )
                        
                        if email_result['success']:
                            messages.success(request, f'Project "{name}" created successfully! OTP sent to {client_email} for client setup.')
                        else:
                            messages.warning(request, f'Project "{name}" created successfully, but OTP email failed: {email_result["error"]}')
                
                # Create project (dates will be calculated from tasks)
                project = Project.objects.create(
                    name=name,
                    client=client,
                    client_username=client_username,
                    client_email=client_email,
                    status=status
                )
                
                # Log project creation
                SystemLog.log_project_created(request.user, project, request)
                
                # Create tasks from the form data
                task_counter = 1
                tasks_created = 0
                earliest_start = None
                latest_end = None
                
                while f'task_title_{task_counter}' in request.POST:
                    task_title = request.POST.get(f'task_title_{task_counter}')
                    task_start = request.POST.get(f'task_start_{task_counter}')
                    task_end = request.POST.get(f'task_end_{task_counter}')
                    task_status = request.POST.get(f'task_status_{task_counter}')
                    task_description = request.POST.get(f'task_description_{task_counter}', '')
                    
                    if task_title and task_start and task_end:
                        # Parse task dates
                        task_start_date = datetime.strptime(task_start, '%Y-%m-%d').date()
                        task_end_date = datetime.strptime(task_end, '%Y-%m-%d').date()
                        
                        # Get development status for this task
                        task_development_status = request.POST.get(f'task_development_status_{task_counter}', 'original_quoted')
                        
                        # Create task
                        task = Task.objects.create(
                            project=project,
                            title=task_title,
                            description=task_description,
                            status=task_status,
                            development_status=task_development_status,
                            start_date=task_start_date,
                            end_date=task_end_date
                        )
                        
                        # Handle estimated hours if provided
                        estimated_hours = request.POST.get(f'task_estimated_hours_{task_counter}')
                        if estimated_hours and estimated_hours.strip():
                            try:
                                task.estimated_hours = float(estimated_hours)
                                task.save()
                            except ValueError:
                                pass  # Skip if invalid number
                        
                        # Handle task assignees if provided
                        task_assignee_ids = request.POST.getlist(f'task_assigned_to_{task_counter}')
                        if task_assignee_ids and task_assignee_ids[0]:  # Check if not empty
                            assignees = User.objects.filter(id__in=task_assignee_ids)
                            task.assigned_users.set(assignees)
                        
                        tasks_created += 1
                        
                        # Track earliest start and latest end dates
                        if not earliest_start or task_start_date < earliest_start:
                            earliest_start = task_start_date
                        if not latest_end or task_end_date > latest_end:
                            latest_end = task_end_date
                        
                        # Create subtasks for this task
                        subtask_counter = 1
                        while f'subtask_title_{task_counter}_{subtask_counter}' in request.POST:
                            subtask_title = request.POST.get(f'subtask_title_{task_counter}_{subtask_counter}')
                            subtask_description = request.POST.get(f'subtask_description_{task_counter}_{subtask_counter}', '')
                            subtask_status = request.POST.get(f'subtask_status_{task_counter}_{subtask_counter}', 'not_started')
                            
                            if subtask_title:
                                # Parse subtask dates if provided
                                subtask_start_date = None
                                subtask_end_date = None
                                
                                subtask_start = request.POST.get(f'subtask_start_{task_counter}_{subtask_counter}')
                                subtask_end = request.POST.get(f'subtask_end_{task_counter}_{subtask_counter}')
                                
                                if subtask_start:
                                    try:
                                        subtask_start_date = datetime.strptime(subtask_start, '%Y-%m-%d').date()
                                    except ValueError:
                                        pass
                                
                                if subtask_end:
                                    try:
                                        subtask_end_date = datetime.strptime(subtask_end, '%Y-%m-%d').date()
                                    except ValueError:
                                        pass
                                
                                SubTask.objects.create(
                                    task=task,
                                    title=subtask_title,
                                    description=subtask_description,
                                    status=subtask_status,
                                    start_date=subtask_start_date,
                                    end_date=subtask_end_date
                                )
                            
                            subtask_counter += 1
                    
                    task_counter += 1
                
                # Project dates are automatically calculated from task dates
                # No need to set them manually - they are read-only properties
                
                if tasks_created > 0:
                    if not existing_client or not is_existing_client:
                        messages.success(request, f'Project "{name}" created successfully with {tasks_created} tasks!')
                    else:
                        messages.success(request, f'Project "{name}" created successfully with {tasks_created} tasks for existing client!')
                else:
                    if not existing_client or not is_existing_client:
                        messages.success(request, f'Project "{name}" created successfully!')
                    else:
                        messages.success(request, f'Project "{name}" created successfully for existing client!')
                
                # Assign users if selected
                if assigned_user_ids:
                    users = User.objects.filter(id__in=assigned_user_ids)
                    project.assigned_users.set(users)
                
                return redirect('projects_page')
                
            except Exception as e:
                messages.error(request, f'Error creating project: {str(e)}')
        else:
            messages.error(request, 'Please fill in all required fields.')
    
    # If not POST or validation failed, redirect to projects page
    return redirect('projects_page')
def edit_project(request, project_id):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        try:
            # Store old data for logging
            old_data = {
                'name': project.name,
                'client': project.client,
                'client_username': project.client_username,
                'client_email': project.client_email,
                'status': project.status,
                'assigned_users': [user.username for user in project.assigned_users.all()]
            }
            
            project.name = request.POST.get('name')
            project.client = request.POST.get('client')
            project.client_username = request.POST.get('client_username', '')
            project.client_email = request.POST.get('client_email')
            project.status = request.POST.get('status')
            
            # Project dates are automatically calculated from task dates
            # No manual editing allowed
            
            project.save()
            
            # Update assigned users
            assigned_user_ids = request.POST.getlist('assigned_users')
            if assigned_user_ids:
                assigned_users = User.objects.filter(id__in=assigned_user_ids)
                project.assigned_users.set(assigned_users)
            else:
                project.assigned_users.clear()
            
            # Store new data for logging
            new_data = {
                'name': project.name,
                'client': project.client,
                'client_username': project.client_username,
                'client_email': project.client_email,
                'status': project.status,
                'assigned_users': [user.username for user in project.assigned_users.all()]
            }
            
            # Log project editing
            SystemLog.log_project_edited(request.user, project, old_data, new_data, request)
            
            # Log project assignment changes if users were changed
            if old_data['assigned_users'] != new_data['assigned_users']:
                SystemLog.log_project_assigned(request.user, project, project.assigned_users.all(), request)
            
            # Log project status change if status was changed
            if old_data['status'] != new_data['status']:
                SystemLog.log_project_status_change(request.user, project, old_data['status'], new_data['status'], request)
            
            messages.success(request, f'Project {project.name} updated successfully.')
            return redirect('projects_page')
        except Exception as e:
            messages.error(request, f'Error updating project: {str(e)}')
    
    # Get all users for assignment dropdown
    all_users = User.objects.all().order_by('username')
    
    return render(request, 'home/edit_project.html', {
        'project': project,
        'all_users': all_users
    })

@login_required
def delete_project(request, project_id):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    if request.method == 'POST':
        project = get_object_or_404(Project, id=project_id)
        try:
            # Store project info for logging before deletion
            project_name = project.name
            client_email = project.client_email
            client_username = project.client_username
            
            # Log project deletion
            client_name = project.client if project.client else 'No Client'
            SystemLog.log_project_deleted(request.user, project_name, client_name, request)
            
            # Delete the project first
            project.delete()
            
            # Check if we should clean up client records
            if client_email:
                # Check if this client email is used by any other projects
                other_projects_with_same_email = Project.objects.filter(client_email=client_email).exists()
                
                if not other_projects_with_same_email:
                    # No other projects use this email, so we can safely delete client records
                    try:
                        # Delete related client OTPs
                        from .models import ClientOTP
                        ClientOTP.objects.filter(client__email=client_email).delete()
                        
                        # Delete the client
                        from .models import Client
                        Client.objects.filter(email=client_email).delete()
                        
                        print(f"Cleaned up client records for email: {client_email}")
                    except Exception as client_cleanup_error:
                        print(f"Warning: Could not clean up client records: {client_cleanup_error}")
            
            messages.success(request, f'Project {project_name} and all related data deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting project: {str(e)}')
    
    return redirect('projects_page')

@login_required
def complete_task(request, project_id, task_id):
    """Allow users to mark tasks as completed"""
    project = get_object_or_404(Project, id=project_id)
    task = get_object_or_404(Task, id=task_id, project=project)
    
    # Check if user is assigned to this project
    if request.user not in project.assigned_users.all():
        messages.error(request, 'You are not assigned to this project.')
        return redirect('project_tasks', project_id=project_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        old_status = task.status
        
        if action == 'complete':
            task.status = 'completed'
            messages.success(request, f'Task "{task.title}" marked as completed!')
        elif action == 'in_progress':
            task.status = 'in_progress'
            messages.info(request, f'Task "{task.title}" marked as in progress.')
        elif action == 'not_started':
            task.status = 'not_started'
            messages.info(request, f'Task "{task.title}" marked as not started.')
        
        task.save()
        
        # Log the task status change
        SystemLog.log_task_status_change(request.user, task, old_status, task.status, request)
        
        # Send system-wide notification to all admins
        Notification.create_if_not_exists(
            recipient=None,  # System-wide notification
            notification_type='task_update',
            title=f'Task Status Updated',
            message=f"{request.user.get_full_name() or request.user.username} changed task '{task.title}' status from {old_status} to {task.status} in project '{project.name}'",
            related_project=project,
            related_task=task,
            triggered_by=request.user,
            is_admin_notification=True
        )
    
    return redirect('project_tasks', project_id=project_id)

@login_required
def settings(request):
    
    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            profile.profile_picture = request.FILES['profile_picture']
        
        # Update user information
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        
        # Update profile information
        profile.bio = request.POST.get('bio', profile.bio)
        profile.phone = request.POST.get('phone', profile.phone)
        profile.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('settings')
    
    context = {
        'profile': profile,
        'user': request.user,
    }
    return render(request, 'home/settings.html', context)

@login_required
def reports(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    # Get date range for filtering (default to last 30 days)
    days_filter = request.GET.get('days', 30)
    try:
        days_filter = int(days_filter)
    except ValueError:
        days_filter = 30
    
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days_filter)
    
    # Project Statistics
    total_projects = Project.objects.count()
    projects_in_progress = Project.objects.filter(status='in_progress').count()
    projects_completed = Project.objects.filter(status='completed').count()
    projects_planned = Project.objects.filter(status='planned').count()
    
    # Recent projects (last 30 days)
    recent_projects = Project.objects.filter(
        created_at__gte=start_date
    ).order_by('-created_at')[:5]
    
    # Task Statistics
    total_tasks = Task.objects.count()
    completed_tasks = Task.objects.filter(status='completed').count()
    in_progress_tasks = Task.objects.filter(status='in_progress').count()
    not_started_tasks = Task.objects.filter(status='not_started').count()
    pending_subtasks = SubTask.objects.filter(is_completed=False).count()
    
    # SubTask Statistics
    total_subtasks = SubTask.objects.count()
    completed_subtasks = SubTask.objects.filter(is_completed=True).count()
    
    # User Activity
    total_users = User.objects.count()
    active_users = User.objects.filter(last_login__gte=start_date).count()
    inactive_users = total_users - active_users
    
    # Calculate percentages for charts
    planned_percentage = (projects_planned / total_projects * 100) if total_projects > 0 else 0
    in_progress_percentage = (projects_in_progress / total_projects * 100) if total_projects > 0 else 0
    completed_percentage = (projects_completed / total_projects * 100) if total_projects > 0 else 0
    
    # Generate matplotlib charts
    if MATPLOTLIB_AVAILABLE:
        charts = generate_report_charts(days_filter, start_date, end_date)
    else:
        charts = {}
    
    # Top performing projects (by task completion rate)
    projects_with_tasks = Project.objects.annotate(
        total_tasks=Count('tasks'),
        completed_tasks=Count('tasks', filter=Q(tasks__status='completed'))
    ).filter(total_tasks__gt=0)
    
    top_projects = []
    for project in projects_with_tasks:
        completion_rate = (project.completed_tasks / project.total_tasks) * 100 if project.total_tasks > 0 else 0
        top_projects.append({
            'name': project.name,
            'client': project.client,
            'status': project.status,
            'status_display': project.get_status_display(),
            'total_tasks': project.total_tasks,
            'completed_tasks': project.completed_tasks,
            'completion_rate': round(completion_rate, 1),
            'start_date': project.start_date,
            'end_date': project.end_date,
            'created_at': project.created_at,
        })
    
    # Sort by completion rate
    top_projects.sort(key=lambda x: x['completion_rate'], reverse=True)
    top_projects = top_projects[:10]  # Top 10 projects
    
    # User activity summary
    user_activity = []
    for user in User.objects.all():
        projects_created = Project.objects.filter(created_at__gte=start_date).count()
        last_login = user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never'
        
        user_activity.append({
            'username': user.username,
            'email': user.email,
            'last_login': last_login,
            'projects_created': projects_created,
            'is_staff': user.is_staff,
        })
    
    # Performance metrics - calculate average completion time from tasks
    completed_tasks_with_dates = Task.objects.filter(
        project__status='completed',
        start_date__isnull=False,
        end_date__isnull=False
    ).annotate(
        duration_days=ExpressionWrapper(
            F('end_date') - F('start_date'),
            output_field=fields.DurationField()
        )
    )
    
    avg_completion_time = completed_tasks_with_dates.aggregate(
        avg_days=Avg('duration_days')
    )['avg_days']
    
    avg_completion_time = avg_completion_time.days if avg_completion_time else 0
    
    # Task efficiency metrics
    task_efficiency = {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'not_started_tasks': not_started_tasks,
        'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
        'avg_completion_time': avg_completion_time,
    }
    
    # Get clients with their projects
    clients_with_projects = []
    for client in Client.objects.filter(is_active=True).order_by('username'):
        # Get projects for this client
        client_projects = Project.objects.filter(client_username=client.username)
        client.projects = client_projects
        client.projects_count = client_projects.count()
        clients_with_projects.append(client)
    
    context = {
        'total_projects': total_projects,
        'projects_planned': projects_planned,
        'projects_in_progress': projects_in_progress,
        'projects_completed': projects_completed,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'not_started_tasks': not_started_tasks,
        'total_subtasks': total_subtasks,
        'completed_subtasks': completed_subtasks,
        'pending_subtasks': pending_subtasks,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'top_projects': top_projects,
        'user_activity': user_activity,
        'recent_projects': recent_projects,
        'clients_with_projects': clients_with_projects,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'days_filter': days_filter,
        'planned_percentage': planned_percentage,
        'in_progress_percentage': in_progress_percentage,
        'completed_percentage': completed_percentage,
        'task_efficiency': task_efficiency,
        'charts': charts,
    }
    
    return render(request, 'home/reports.html', context)


def generate_report_charts(days_filter, start_date, end_date):
    """Generate charts for the reports page - matplotlib removed"""
    # Charts disabled - return empty dict
    return {}


def generate_pdf_report_data(days_filter=30):
    """
    Generate the same report data that's used for PDF generation in the reports view
    This function extracts the data generation logic to be reusable
    """
    from django.db.models import Count, Q
    from django.utils import timezone
    from datetime import timedelta
    from .models import Project, Task, SubTask, User
    
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days_filter)
    
    # Project Statistics
    total_projects = Project.objects.count()
    projects_in_progress = Project.objects.filter(status='in_progress').count()
    projects_completed = Project.objects.filter(status='completed').count()
    projects_planned = Project.objects.filter(status='planned').count()
    
    # Recent projects (last 30 days)
    recent_projects = Project.objects.filter(
        created_at__gte=start_date
    ).order_by('-created_at')[:5]
    
    # Project status distribution
    status_distribution = {
        'planned': projects_planned,
        'in_progress': projects_in_progress,
        'completed': projects_completed,
    }
    
    # Task Statistics
    total_tasks = Task.objects.count()
    completed_tasks = Task.objects.filter(status='completed').count()
    in_progress_tasks = Task.objects.filter(status='in_progress').count()
    not_started_tasks = Task.objects.filter(status='not_started').count()
    
    # SubTask Statistics
    total_subtasks = SubTask.objects.count()
    completed_subtasks = SubTask.objects.filter(is_completed=True).count()
    pending_subtasks = total_subtasks - completed_subtasks
    
    # User Activity
    total_users = User.objects.count()
    active_users = User.objects.filter(last_login__gte=start_date).count()
    inactive_users = total_users - active_users
    
    # Top performing projects (by task completion rate)
    projects_with_tasks = Project.objects.annotate(
        total_tasks=Count('tasks'),
        completed_tasks=Count('tasks', filter=Q(tasks__status='completed'))
    ).filter(total_tasks__gt=0)
    
    top_projects = []
    for project in projects_with_tasks:
        completion_rate = (project.completed_tasks / project.total_tasks) * 100
        top_projects.append({
            'name': project.name,
            'client': project.client_username if project.client_username else project.client if project.client else 'N/A',
            'completion_rate': round(completion_rate, 1),
            'total_tasks': project.total_tasks,
            'completed_tasks': project.completed_tasks,
            'start_date': project.start_date,
            'end_date': project.end_date,
        })
    
    # Sort by completion rate
    top_projects.sort(key=lambda x: x['completion_rate'], reverse=True)
    top_projects = top_projects[:5]
    
    # User activity data
    user_activity = []
    for user in User.objects.all()[:10]:  # Top 10 users
        user_tasks = Task.objects.filter(assigned_users=user).count()
        user_completed = Task.objects.filter(assigned_users=user, status='completed').count()
        user_activity.append({
            'username': user.username,
            'total_tasks': user_tasks,
            'completed_tasks': user_completed,
            'completion_rate': round((user_completed / user_tasks * 100) if user_tasks > 0 else 0, 1)
        })
    
    # Weekly activity (simplified)
    weekly_activity = {
        'current_week': projects_in_progress,
        'previous_week': projects_completed,
        'trend': 'stable'
    }
    
    # Calculate percentages
    planned_percentage = (projects_planned / total_projects * 100) if total_projects > 0 else 0
    in_progress_percentage = (projects_in_progress / total_projects * 100) if total_projects > 0 else 0
    completed_percentage = (projects_completed / total_projects * 100) if total_projects > 0 else 0
    
    return {
        'total_projects': total_projects,
        'projects_in_progress': projects_in_progress,
        'projects_completed': projects_completed,
        'projects_planned': projects_planned,
        'status_distribution': status_distribution,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'not_started_tasks': not_started_tasks,
        'total_subtasks': total_subtasks,
        'completed_subtasks': completed_subtasks,
        'pending_subtasks': pending_subtasks,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'recent_projects': recent_projects,
        'top_projects': top_projects,
        'user_activity': user_activity,
        'weekly_activity': weekly_activity,
        'start_date': start_date,
        'end_date': end_date,
        'planned_percentage': round(planned_percentage, 1),
        'in_progress_percentage': round(in_progress_percentage, 1),
        'completed_percentage': round(completed_percentage, 1),
    }
def generate_exact_pdf_report(days_filter=30):
    """
    Generate the exact same PDF report as the reports view
    This function uses the same logic and styling as the PDF export in reports view
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem, KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String, Circle, Wedge, Line
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    from io import BytesIO
    from datetime import datetime
    import tempfile
    
    # Get the same data as the reports view
    report_data = generate_pdf_report_data(days_filter)
    
    # Extract variables from report_data
    start_date = report_data['start_date']
    end_date = report_data['end_date']
    total_projects = report_data['total_projects']
    projects_in_progress = report_data['projects_in_progress']
    projects_completed = report_data['projects_completed']
    projects_planned = report_data['projects_planned']
    total_tasks = report_data['total_tasks']
    completed_tasks = report_data['completed_tasks']
    in_progress_tasks = report_data['in_progress_tasks']
    not_started_tasks = report_data['not_started_tasks']
    total_subtasks = report_data['total_subtasks']
    completed_subtasks = report_data['completed_subtasks']
    pending_subtasks = report_data['pending_subtasks']
    total_users = report_data['total_users']
    active_users = report_data['active_users']
    inactive_users = report_data['inactive_users']
    top_projects = report_data['top_projects']
    
    # Create descriptive temporary file for PDF
    import os
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    descriptive_filename = f"Executive_Report_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, descriptive_filename)
    
    # Create PDF document with slightly reduced side margins to allow wider tables
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=72,
        bottomMargin=60,
    )
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles for professional report with red, black, white theme
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=20,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#dc2626'),  # Red
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=15,
        alignment=1,
        textColor=colors.HexColor('#6b7280'),  # Gray
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=15,
        textColor=colors.HexColor('#dc2626'),  # Red headings
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=4,
        textColor=colors.HexColor('#000000'),  # Black text
        fontName='Helvetica'
    )
    
    insight_style = ParagraphStyle(
        'InsightText',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        leftIndent=20,
        fontName='Helvetica',
        textColor=colors.HexColor('#000000')  # Black text
    )
    
    # Company signature style
    signature_style = ParagraphStyle(
        'CompanySignature',
        parent=styles['Normal'],
        fontSize=16,
        spaceAfter=0,
        alignment=0,  # Left alignment
        textColor=colors.HexColor('#dc2626'),  # Red
        fontName='Helvetica-Bold'
    )
    
    # Page header/footer (logo left, contacts right, footer tagline)
    from django.conf import settings as django_settings
    import os
    PAGE_WIDTH, PAGE_HEIGHT = A4

    def draw_header_footer(canvas, doc):
        canvas.saveState()
        # Logo (left side)
        try:
            logo_path = os.path.join(django_settings.BASE_DIR, 'home', 'Logo.png')
            if os.path.exists(logo_path):
                canvas.drawImage(logo_path, 40, PAGE_HEIGHT - 100, width=120, height=60, mask='auto')
        except Exception:
            pass
        # Contacts (right) - replace "E-Click Support" text with small logo
        try:
            # Add small logo instead of "E-Click Support" text
            logo_path = os.path.join(django_settings.BASE_DIR, 'home', 'Logo.png')
            if os.path.exists(logo_path):
                canvas.drawImage(logo_path, PAGE_WIDTH - 220, PAGE_HEIGHT - 80, width=60, height=30, mask='auto')
            else:
                # Fallback to text if logo not found
                canvas.setFont('Helvetica-Bold', 10)
                canvas.drawString(PAGE_WIDTH - 220, PAGE_HEIGHT - 60, 'E-Click Support')
            
            canvas.setFont('Helvetica', 10)
            canvas.drawString(PAGE_WIDTH - 220, PAGE_HEIGHT - 75, '(+27)')
            canvas.drawString(PAGE_WIDTH - 220, PAGE_HEIGHT - 90, 'support@eclick.com')
        except Exception:
            pass
        # Footer tagline
        canvas.setFont('Helvetica-Bold', 9)
        canvas.setFillColor(colors.HexColor('#dc2626'))  # Red footer text
        canvas.drawCentredString(PAGE_WIDTH / 2, 30, 'WE CARE, WE CAN, WE DELIVER')
        canvas.restoreState()

    # Title block in content area
    story.append(Paragraph('Your Client Progress Report', title_style))
    story.append(Paragraph(f'Generated on {end_date.strftime("%B %d, %Y at %I:%M %p")}', subtitle_style))
    story.append(Spacer(1, 15))
    
    # Executive Summary with Deep Insights (exact same as reports view)
    story.append(Paragraph('Executive Summary', heading_style))
    
    # Calculate insights (exact same as reports view)
    project_completion_rate = (projects_completed / total_projects * 100) if total_projects > 0 else 0
    task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    subtask_completion_rate = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
    user_engagement_rate = (active_users / total_users * 100) if total_users > 0 else 0
    
    # Key insights (exact same as reports view)
    insights = []
    insights.append(f"Project Performance: {project_completion_rate:.1f}% completion rate with {projects_in_progress} active projects")
    insights.append(f"Task Efficiency: {task_completion_rate:.1f}% task completion with {completed_tasks} tasks delivered")
    insights.append(f"SubTask Progress: {subtask_completion_rate:.1f}% subtask completion showing detailed execution")
    insights.append(f"User Engagement: {user_engagement_rate:.1f}% active users with {active_users} engaged team members")
    
    for insight in insights:
        story.append(Paragraph(insight, insight_style))
    
    story.append(Spacer(1, 10))
    
    # Performance Analysis
    story.append(Paragraph('Performance Analysis', heading_style))
    
    # Create comprehensive analysis table (exact same as reports view)
    analysis_data = [
        ['Metric', 'Current', 'Target', 'Performance', 'Trend'],
        ['Project Completion', f"{project_completion_rate:.1f}%", '80%', 'Green' if project_completion_rate >= 80 else 'Yellow' if project_completion_rate >= 60 else 'Red', 'Up' if projects_completed > projects_planned else 'Stable'],
        ['Task Completion', f"{task_completion_rate:.1f}%", '75%', 'Green' if task_completion_rate >= 75 else 'Yellow' if task_completion_rate >= 50 else 'Red', 'Up' if completed_tasks > in_progress_tasks else 'Stable'],
        ['SubTask Completion', f"{subtask_completion_rate:.1f}%", '70%', 'Green' if subtask_completion_rate >= 70 else 'Yellow' if subtask_completion_rate >= 50 else 'Red', 'Up' if completed_subtasks > pending_subtasks else 'Stable'],
        ['User Engagement', f"{user_engagement_rate:.1f}%", '85%', 'Green' if user_engagement_rate >= 85 else 'Yellow' if user_engagement_rate >= 60 else 'Red', 'Up' if active_users > inactive_users else 'Stable']
    ]
    
    analysis_table = Table(analysis_data, colWidths=[1.5*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.6*inch])
    analysis_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),  # Red header
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # White background
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#000000')),  # Black text
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#000000')),  # Black grid lines
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.white]),  # All white rows
    ]))
    story.append(analysis_table)
    story.append(Spacer(1, 15))

    # Charts Section
    try:
        # Project Status Distribution Pie Chart
        status_values = [projects_planned, projects_in_progress, projects_completed]
        status_labels = ['Planned', 'In Progress', 'Completed']
        if sum(status_values) > 0:
            drawing = Drawing(400, 220)
            pie = Pie()
            pie.x = 130
            pie.y = 10
            pie.width = 140
            pie.height = 140
            pie.data = status_values
            pie.labels = [f"{label} ({val})" for label, val in zip(status_labels, status_values)]
            pie.slices.strokeWidth = 0.5
            pie.slices[0].fillColor = colors.HexColor('#ef4444')  # red
            pie.slices[1].fillColor = colors.HexColor('#111827')  # near black
            pie.slices[2].fillColor = colors.HexColor('#9ca3af')  # gray
            drawing.add(pie)
            story.append(Paragraph('Project Status Distribution', heading_style))
            story.append(drawing)
            story.append(Spacer(1, 12))

        # Task Distribution Bar Chart
        task_values = [completed_tasks, in_progress_tasks, not_started_tasks]
        task_labels = ['Completed', 'In Progress', 'Not Started']
        if sum(task_values) > 0:
            drawing = Drawing(400, 220)
            bc = VerticalBarChart()
            bc.x = 40
            bc.y = 30
            bc.height = 150
            bc.width = 320
            bc.data = [task_values]
            bc.categoryAxis.categoryNames = task_labels
            bc.barWidth = 18
            bc.groupSpacing = 12
            bc.valueAxis.valueMin = 0
            bc.bars[0].fillColor = colors.HexColor('#ef4444')
            drawing.add(bc)
            story.append(Paragraph('Task Distribution', heading_style))
            story.append(drawing)
            story.append(Spacer(1, 12))

        # Weekly Activity Line Chart (projects created)
        if isinstance(report_data.get('weekly_activity'), list) and report_data['weekly_activity']:
            labels = [w['week'] for w in report_data['weekly_activity']]
            projects_series = [w['projects'] for w in report_data['weekly_activity']]
            drawing = Drawing(420, 240)
            lc = HorizontalLineChart()
            lc.x = 40
            lc.y = 40
            lc.height = 150
            lc.width = 320
            lc.data = [projects_series]
            lc.categoryAxis.categoryNames = labels
            lc.lines[0].strokeColor = colors.HexColor('#ef4444')
            story.append(Paragraph('Weekly Activity (Projects Created)', heading_style))
            drawing.add(lc)
            story.append(drawing)
            story.append(Spacer(1, 12))
    except Exception:
        # If charts fail, continue with the rest of the report
        pass
    
    # Deep Dive Analysis (exact same as reports view)
    story.append(Paragraph('Deep Dive Analysis', heading_style))
    
    # Project insights (exact same as reports view)
    project_insights = []
    if projects_completed > 0:
        project_insights.append(f"Success Rate: {projects_completed} projects successfully delivered")
    if projects_in_progress > projects_completed:
        project_insights.append(f"Pipeline Alert: {projects_in_progress} projects in progress - consider resource allocation")
    if projects_planned > projects_in_progress:
        project_insights.append(f"Planning Strength: {projects_planned} projects in planning phase")
    
    # Task insights (exact same as reports view)
    task_insights = []
    if completed_tasks > in_progress_tasks:
        task_insights.append(f"Task Velocity: High completion rate with {completed_tasks} tasks finished")
    if not_started_tasks > completed_tasks:
        task_insights.append(f"Task Backlog: {not_started_tasks} tasks pending - prioritize execution")
    
    # User insights (exact same as reports view)
    user_insights = []
    if active_users > inactive_users:
        user_insights.append(f"Team Engagement: Strong user activity with {active_users} active users")
    else:
        user_insights.append(f"Engagement Concern: {inactive_users} inactive users - consider engagement strategies")
    
    # Combine all insights (exact same as reports view)
    all_insights = project_insights + task_insights + user_insights
    for insight in all_insights:
        story.append(Paragraph(insight, insight_style))
    
    story.append(Spacer(1, 15))
    
    # Top Performers (if any) (exact same as reports view)
    if top_projects:
        story.append(Paragraph('Top Performing Projects', heading_style))
        
        # Show only top 3 projects with detailed metrics (exact same as reports view)
        top_3_projects = top_projects[:3]
        projects_data = [['Rank', 'Project', 'Client', 'Completion', 'Tasks', 'Duration']]
        
        for i, project in enumerate(top_3_projects, 1):
            # Calculate duration based on start and end dates
            duration_text = "N/A"
            if project.get('start_date') and project.get('end_date'):
                start_date = project['start_date']
                end_date = project['end_date']
                if isinstance(start_date, str):
                    start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                if isinstance(end_date, str):
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                duration_days = (end_date - start_date).days
                duration_weeks = max(1, duration_days // 7)
                duration_text = f"{duration_weeks} weeks"
            
            projects_data.append([
                f"#{i}",
                project['name'][:20] + "..." if len(project['name']) > 20 else project['name'],
                project['client'][:15] + "..." if len(project['client']) > 15 else project['client'],
                f"{project['completion_rate']}%",
                f"{project['completed_tasks']}/{project['total_tasks']}",
                duration_text
            ])
        
        projects_table = Table(projects_data, colWidths=[0.5*inch, 1.5*inch, 1.2*inch, 0.8*inch, 0.8*inch, 0.6*inch])
        projects_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),  # Red header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),  # Light gray background
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (3, 1), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.white]),  # All white rows
        ]))
        story.append(projects_table)
        story.append(Spacer(1, 15))
    
    # Strategic Recommendations (exact same as reports view)
    story.append(Paragraph('Strategic Recommendations', heading_style))
    
    recommendations = []
    
    # Performance-based recommendations (exact same as reports view)
    if project_completion_rate < 60:
        recommendations.append("Accelerate Delivery: Focus on completing projects in progress to improve overall completion rate")
    if task_completion_rate < 50:
        recommendations.append("Task Prioritization: Implement task prioritization framework to increase completion velocity")
    if user_engagement_rate < 70:
        recommendations.append("User Engagement: Develop user engagement strategies to increase active participation")
    
    # Resource-based recommendations (exact same as reports view)
    if projects_in_progress > projects_completed * 2:
        recommendations.append("Resource Optimization: Consider reallocating resources to balance project pipeline")
    if not_started_tasks > completed_tasks:
        recommendations.append("Task Management: Implement task initiation protocols to reduce backlog")
    
    # Positive reinforcement (exact same as reports view)
    if project_completion_rate >= 80:
        recommendations.append("Maintain Excellence: Current performance is excellent - continue current practices")
    if task_completion_rate >= 75:
        recommendations.append("Sustain Momentum: Task completion rate is strong - maintain current workflow")
    
    # Default recommendations if no specific ones (exact same as reports view)
    if not recommendations:
        recommendations.append("Continuous Monitoring: Track key metrics regularly to identify improvement opportunities")
        recommendations.append("Process Optimization: Review and optimize project management processes")
    
    for rec in recommendations:
        story.append(Paragraph(rec, insight_style))
    
    story.append(Spacer(1, 15))
    
    # Footer (exact same as reports view)
    story.append(Paragraph(f'Generated on {timezone.now().strftime("%B %d, %Y at %I:%M %p")} | Project Management', ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        alignment=1,
        textColor=colors.HexColor('#6b7280'),  # Gray
        fontName='Helvetica'
    )))
    
    # Build PDF with header/footer on all pages
    doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    
    return pdf_path

def generate_simple_hello_pdf():
    """Generate a simple PDF that only says 'hello'"""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    import tempfile
    import os
    from datetime import datetime
    
    # Create temporary file for PDF
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    filename = f"hello_report_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, filename)
    
    # Create PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Add "hello" to the PDF
    story.append(Paragraph("hello", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    
    return pdf_path

def generate_project_summary_pdf(project, client_name, total_tasks, completed_tasks, task_completion_rate, team_size, recent_tasks, recent_subtasks, generated_time):
    """Generate an email-style PDF report that matches the exact format shown in the image with donut chart"""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.graphics.shapes import Drawing, Circle, String
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics import renderPDF
    import tempfile
    import os
    from datetime import datetime
    
    # Working DonutChart implementation with red/black/white theme - centered and bigger
    def create_donut_chart(progress_percentage):
        """Create a centered, bigger donut chart with red/black/white theme for one-page layout"""
        try:
            drawing = Drawing(400, 150)  # Bigger size and centered
            pie = Pie()
            pie.x = 130  # Centered horizontally
            pie.y = 15
            pie.width = 120  # Bigger chart
            pie.height = 120
            
            # Ensure valid progress data
            progress = max(0, min(100, float(progress_percentage or 0)))
            remaining = 100 - progress
            
            # Create donut chart showing completed vs remaining
            pie.data = [progress, remaining] if remaining > 0 else [progress]
            pie.labels = ['', '']
            pie.slices[0].fillColor = colors.HexColor('#dc2626')  # Red for progress
            if remaining > 0:
                pie.slices[1].fillColor = colors.HexColor('#000000')  # Black for remaining
            
            pie.slices.strokeColor = colors.white
            pie.slices.strokeWidth = 2
            drawing.add(pie)
            
            # Add center circle for donut effect
            cx, cy = 190, 75  # Centered
            ring = Circle(cx, cy, 40, fillColor=colors.white, strokeColor=colors.white)  # Bigger center
            drawing.add(ring)
            
            # Add percentage in center
            pct_label = String(cx, cy - 4, f"{progress:.1f}%", textAnchor='middle')
            pct_label.fontName = 'Helvetica-Bold'
            pct_label.fontSize = 16  # Bigger text
            pct_label.fillColor = colors.HexColor('#000000')  # Black text
            drawing.add(pct_label)
            
            return drawing
        except Exception:
            # Return empty drawing if chart creation fails
            return Drawing(400, 150)
    
    # Create temporary file for PDF
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    safe_name = ''.join(c if c.isalnum() or c in ('_', '-') else '_' for c in (project.name or 'project'))[:40]
    filename = f"EClick_Project_Summary_{safe_name}_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, filename)
    
    # Create PDF document
    doc = SimpleDocTemplate(
        pdf_path, 
        pagesize=A4,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch
    )
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Compact Email-style title (RED like in image)
    title_style = ParagraphStyle(
        'EmailTitle',
        parent=styles['Heading1'],
        fontSize=16,  # Smaller for one-page
        spaceAfter=6,
        spaceBefore=0,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#dc2626'),  # Red color like in image
        fontName='Helvetica-Bold'
    )
    
    # Compact Subtitle style (gray)
    subtitle_style = ParagraphStyle(
        'EmailSubtitle',
        parent=styles['Normal'],
        fontSize=9,  # Smaller for one-page
        spaceAfter=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#6b7280'),
        fontName='Helvetica'
    )
    
    # Red/Black/White Email greeting style
    greeting_style = ParagraphStyle(
        'EmailGreeting',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=8,
        textColor=colors.HexColor('#000000'),  # Black text
        fontName='Helvetica-Bold'
    )
    
    # Red/Black/White Email body style
    body_style = ParagraphStyle(
        'EmailBody',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=6,
        textColor=colors.HexColor('#000000'),  # Black text
        fontName='Helvetica',
        leading=12
    )
    
    # Red/Black/White Section heading style
    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=11,
        spaceAfter=4,
        spaceBefore=8,
        textColor=colors.HexColor('#dc2626'),  # Red headings
        fontName='Helvetica-Bold'
    )
    
    # EMAIL HEADER (project-specific)
    story.append(Paragraph(f"Project Report: {project.name}", title_style))
    story.append(Paragraph(f"Generated on {generated_time}", subtitle_style))
    
    # EMAIL GREETING
    story.append(Paragraph(f"Dear {client_name},", greeting_style))
    story.append(Spacer(1, 6))
    
    # DONUT CHART (centered, showing project task completion)
    donut_chart = create_donut_chart(task_completion_rate)
    story.append(donut_chart)
    story.append(Spacer(1, 8))
    
    # EMAIL BODY TEXT (project-specific)
    story.append(Paragraph(f"Please find the progress summary for your project '{project.name}' below.", body_style))
    story.append(Spacer(1, 8))
    
    # PROJECT-SPECIFIC SUMMARY TABLE
    project_status = getattr(project, 'get_status_display', lambda: getattr(project, 'status', 'Unknown'))()
    
    summary_data = [
        ['Project Details', 'Information'],
        ['Project Name', project.name or 'N/A'],
        ['Current Status', project_status],
        ['Total Tasks', str(max(0, total_tasks))],
        ['Completed Tasks', str(max(0, completed_tasks))],
        ['Task Completion Rate', f'{task_completion_rate:.1f}%']
    ]
    
    summary_table = Table(summary_data, colWidths=[4.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        # Header row (red theme)
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),  # Red header
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        
        # Data rows (white background, black text)
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#000000')),  # Black text
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        
        # Grid lines (black)
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#000000'))
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8))
    
    # PROJECT HIGHLIGHTS SECTION
    story.append(Paragraph("Project Highlights", section_heading_style))
    highlights_text = f"""• Your project '{project.name}' has completed {completed_tasks} out of {total_tasks} tasks ({task_completion_rate:.1f}% completion rate).<br/>
• Current project status: {project_status}.<br/>
• Team size: {team_size} member{'s' if team_size != 1 else ''} working on this project.<br/>
• Recent activity: {recent_tasks} new tasks and {recent_subtasks} new subtasks in the last 30 days."""
    story.append(Paragraph(highlights_text, body_style))
    story.append(Spacer(1, 6))
    
    # PROJECT NEXT STEPS SECTION
    story.append(Paragraph("Next Steps", section_heading_style))
    next_steps_text = f"""• Continue monitoring progress on '{project.name}' to maintain momentum.<br/>
• Reply with any specific priorities you'd like us to focus on for this project.<br/>
• Schedule a project review if you'd like to discuss any adjustments or requirements."""
    story.append(Paragraph(next_steps_text, body_style))
    story.append(Spacer(1, 6))
    
    # EMAIL CLOSING section removed
    
    # FOOTER BANNER (exactly like image)
    footer_banner = Table([["WE CARE, WE CAN, WE DELIVER"]], colWidths=[6*inch])
    footer_banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#dc2626')),  # Red background
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(footer_banner)
    
    # Build PDF
    doc.build(story)
    return pdf_path

def generate_project_specific_pdf_report(project_id, days_filter=30):
    """
    Generate a project-specific PDF report with the exact same design as the main reports page
    This function creates a detailed report for one specific project using the same styling and structure
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String, Circle
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    from io import BytesIO
    from datetime import datetime
    import tempfile
    
    # Get the project
    project = get_object_or_404(Project, id=project_id)
    
    # Get enhanced project-specific data
    total_tasks = project.tasks.count()
    completed_tasks = project.tasks.filter(status='completed').count()
    in_progress_tasks = project.tasks.filter(status='in_progress').count()
    not_started_tasks = project.tasks.filter(status='not_started').count()
    on_hold_tasks = project.tasks.filter(status='on_hold').count()
    guidance_required_tasks = project.tasks.filter(status='in_progress_guidance_required').count()
    
    # Get priority distribution
    high_priority_tasks = project.tasks.filter(priority='high').count()
    urgent_tasks = project.tasks.filter(priority='urgent').count()
    medium_priority_tasks = project.tasks.filter(priority='medium').count()
    low_priority_tasks = project.tasks.filter(priority='low').count()
    
    # Get development status distribution
    development_statuses = project.tasks.values('development_status').annotate(count=Count('id'))
    
    total_subtasks = SubTask.objects.filter(task__project=project).count()
    completed_subtasks = SubTask.objects.filter(task__project=project, is_completed=True).count()
    pending_subtasks = total_subtasks - completed_subtasks
    
    # Calculate completion rates
    task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    subtask_completion_rate = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
    
    # Get recent activity (last 30 days)
    from django.utils import timezone
    from django.db.models import Count
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days_filter)
    
    recent_tasks = project.tasks.filter(created_at__gte=start_date).count()
    recent_subtasks = SubTask.objects.filter(task__project=project, created_at__gte=start_date).count()
    recent_comments = sum(task.comments.filter(created_at__gte=start_date).count() for task in project.tasks.all())
    
    # Get team information
    team_members = project.assigned_users.all()
    team_size = team_members.count()
    
    # Calculate average task completion time
    completed_tasks_with_dates = project.tasks.filter(status='completed', start_date__isnull=False, end_date__isnull=False)
    avg_completion_days = 0
    if completed_tasks_with_dates.exists():
        completion_times = [(task.end_date - task.start_date).days for task in completed_tasks_with_dates]
        avg_completion_days = sum(completion_times) / len(completion_times)
    
    # Calculate project timeline progress
    timeline_progress = 0
    days_remaining = 0
    if project.start_date and project.end_date:
        days_elapsed = (timezone.now().date() - project.start_date).days
        total_days = (project.end_date - project.start_date).days
        if total_days > 0:
            timeline_progress = (days_elapsed / total_days) * 100
            days_remaining = max(0, total_days - days_elapsed)
    
    # Create descriptive temporary file for PDF
    import os, re
    from django.conf import settings
    temp_dir = tempfile.gettempdir()
    safe_project = re.sub(r'[^a-zA-Z0-9_-]+', '_', project.name).strip('_')[:40]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    descriptive_filename = f"ProjectReport_{safe_project}_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, descriptive_filename)
    
    # Create PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles for professional report with red, black, white theme
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=20,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#dc2626'),  # Red
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=15,
        alignment=1,
        textColor=colors.HexColor('#6b7280'),  # Gray
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=15,
        textColor=colors.HexColor('#1f2937'),  # Dark gray/black
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=4,
        fontName='Helvetica'
    )
    
    insight_style = ParagraphStyle(
        'InsightText',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        leftIndent=20,
        fontName='Helvetica',
        textColor=colors.HexColor('#000000')  # Black text
    )
    
    # Company signature style
    signature_style = ParagraphStyle(
        'CompanySignature',
        parent=styles['Normal'],
        fontSize=16,
        spaceAfter=0,
        alignment=0,  # Left alignment
        textColor=colors.HexColor('#dc2626'),  # Red
        fontName='Helvetica-Bold'
    )
    
    # Header with company signature (exact same structure as reports view)
    # Add company signature in top left
    # Header: logo on the left, contact info on the right
    try:
        from reportlab.platypus import Image
        logo_path = os.path.join(settings.BASE_DIR, 'home', 'Logo.png')
        if os.path.exists(logo_path):
            left_cell = Image(logo_path, width=120, height=60)
        else:
            left_cell = Paragraph('E-Click', signature_style)
        # Contact info stacked on the right
        contact_lines = [
            'Kyla Schutte',
            '(012) 348 3120',
            'kyla@sdj.co.za',
            'Cindy',
            '(012) 348 3120',
            'cindy@sdj.co.za',
        ]
        contact_story = [Paragraph(line, ParagraphStyle('contact', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#111827'))) for line in contact_lines]
        right_cell = KeepInFrame(doc.width * 0.45, 60, contact_story, hAlign='RIGHT')
        header_table = Table([[left_cell, right_cell]], colWidths=[doc.width * 0.5, doc.width * 0.5])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 6))
    except Exception:
        story.append(Paragraph('E-Click', signature_style))
        story.append(Spacer(1, 6))
    
    story.append(Paragraph(f'Project Report: {project.name}', title_style))
    story.append(Paragraph(f'Client: {project.client} | {start_date.strftime("%B %d, %Y")} - {end_date.strftime("%B %d, %Y")}', subtitle_style))
    story.append(Spacer(1, 15))
    
    # Professional contact header (if available)
    try:
        contact_lines = []
        if getattr(project, 'client_username', None):
            contact_lines.append(str(project.client_username))
        if getattr(project, 'client_email', None):
            contact_lines.append(str(project.client_email))
        if getattr(project, 'client', None) and project.client not in contact_lines:
            contact_lines.insert(0, str(project.client))
        if contact_lines:
            for line in contact_lines[:3]:
                story.append(Paragraph(line, normal_style))
            story.append(Spacer(1, 8))
    except Exception:
        pass

    # Progress donut chart
    try:
        total_for_progress = max(1, total_tasks)
        progress_pct = (completed_tasks / total_for_progress) * 100
        drawing = Drawing(420, 220)
        pie = Pie()
        pie.x = 140
        pie.y = 40
        pie.width = 140
        pie.height = 140
        pie.data = [completed_tasks, max(0, total_tasks - completed_tasks)]
        pie.labels = ['Completed', 'Remaining']
        pie.slices[0].fillColor = colors.HexColor('#dc2626')
        pie.slices[1].fillColor = colors.HexColor('#e5e7eb')
        drawing.add(pie)
        # Donut hole and percentage label
        from reportlab.graphics.shapes import Circle, String
        center_x, center_y = 210, 110
        hole = Circle(center_x, center_y, 40, fillColor=colors.white, strokeColor=colors.white)
        drawing.add(hole)
        label = String(center_x, center_y - 4, f"{progress_pct:.1f}%", textAnchor='middle')
        label.fontName = 'Helvetica-Bold'
        label.fontSize = 16
        drawing.add(label)
        story.append(Paragraph('Overall Task Completion', heading_style))
        story.append(drawing)
        story.append(Spacer(1, 12))
    except Exception:
        pass
    
    # Executive Summary with Enhanced Insights
    story.append(Paragraph('Executive Summary', heading_style))
    
    # Enhanced key insights
    insights = []
    insights.append(f"Project Performance: {task_completion_rate:.1f}% completion rate with {in_progress_tasks} active tasks")
    insights.append(f"Task Efficiency: {task_completion_rate:.1f}% task completion with {completed_tasks} tasks delivered")
    insights.append(f"SubTask Progress: {subtask_completion_rate:.1f}% subtask completion showing detailed execution")
    insights.append(f"Timeline Status: {timeline_progress:.1f}% of project timeline elapsed ({days_remaining} days remaining)")
    insights.append(f"Team Resources: {team_size} team members assigned to this project")
    insights.append(f"Performance Metrics: Average task completion time is {avg_completion_days:.1f} days")
    
    # Priority insights
    if urgent_tasks > 0:
        insights.append(f"Priority Alert: {urgent_tasks} urgent tasks require immediate attention")
    if high_priority_tasks > 0:
        insights.append(f"High Priority: {high_priority_tasks} high-priority tasks in progress")
    
    # Status insights
    if on_hold_tasks > 0:
        insights.append(f"Status Alert: {on_hold_tasks} tasks are currently on hold")
    if guidance_required_tasks > 0:
        insights.append(f"Guidance Required: {guidance_required_tasks} tasks need additional guidance")
    
    # Recent activity insights
    if recent_tasks > 0 or recent_subtasks > 0:
        insights.append(f"Recent Activity: {recent_tasks} new tasks and {recent_subtasks} new subtasks in last 30 days")
    
    for insight in insights:
        story.append(Paragraph(insight, insight_style))
    
    story.append(Spacer(1, 10))
    
    # Performance Analysis (exact same structure as reports view)
    story.append(Paragraph('Performance Analysis', heading_style))
    
    # Create enhanced comprehensive analysis table
    analysis_data = [
        ['Metric', 'Current', 'Target', 'Performance', 'Trend'],
        ['Task Completion', f"{task_completion_rate:.1f}%", '75%', 'Green' if task_completion_rate >= 75 else 'Yellow' if task_completion_rate >= 50 else 'Red', 'Up' if completed_tasks > in_progress_tasks else 'Stable'],
        ['SubTask Completion', f"{subtask_completion_rate:.1f}%", '70%', 'Green' if subtask_completion_rate >= 70 else 'Yellow' if subtask_completion_rate >= 50 else 'Red', 'Up' if completed_subtasks > pending_subtasks else 'Stable'],
        ['Timeline Progress', f"{timeline_progress:.1f}%", '80%', 'Green' if timeline_progress <= 80 else 'Yellow' if timeline_progress <= 100 else 'Red', 'Up' if timeline_progress > 50 else 'Stable'],
        ['Project Status', project.get_status_display(), 'Completed', 'Green' if project.status == 'completed' else 'Yellow' if project.status == 'in_progress' else 'Red', 'Up' if project.status == 'in_progress' else 'Stable'],
        ['Team Efficiency', f"{team_size} members", 'Optimal', 'Green' if team_size >= 2 else 'Yellow' if team_size == 1 else 'Red', 'Stable'],
        ['Priority Management', f"{urgent_tasks} urgent", '0', 'Green' if urgent_tasks == 0 else 'Red', 'Down' if urgent_tasks > 0 else 'Stable'],
        ['Task Velocity', f"{avg_completion_days:.1f} days", '5 days', 'Green' if avg_completion_days <= 5 else 'Yellow' if avg_completion_days <= 10 else 'Red', 'Up' if avg_completion_days < 7 else 'Stable']
    ]
    
    analysis_table = Table(analysis_data, colWidths=[1.5*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.6*inch])
    analysis_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),  # Red header
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # White background
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#000000')),  # Black text
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#000000')),  # Black grid lines
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.white]),  # All white rows
    ]))
    story.append(analysis_table)
    story.append(Spacer(1, 15))
    
    # Action log table (Action / Date Completed)
    try:
        actions = [['Action', 'Date Completed']]
        task_qs = project.tasks.all().order_by('end_date')
        idx = 1
        for t in task_qs:
            action_name = f"{idx} {t.title}" if getattr(t, 'title', None) else f"{idx} Task"
            date_text = t.end_date.strftime('%d/%m/%Y') if getattr(t, 'end_date', None) else '-'
            actions.append([action_name, date_text])
            idx += 1
        if len(actions) > 1:
            table = Table(actions, colWidths=[4.2*inch, 2.0*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
            ]))
            story.append(table)
            story.append(Spacer(1, 12))
            story.append(Paragraph('WE CARE, WE CAN, WE DELIVER', subtitle_style))
            story.append(Spacer(1, 10))
    except Exception:
        pass
    
    # Deep Dive Analysis (exact same structure as reports view)
    story.append(Paragraph('Deep Dive Analysis', heading_style))
    
    # Project insights (exact same format as reports view)
    project_insights = []
    if completed_tasks > 0:
        project_insights.append(f"Success Rate: {completed_tasks} tasks successfully completed")
    if in_progress_tasks > completed_tasks:
        project_insights.append(f"Pipeline Alert: {in_progress_tasks} tasks in progress - consider resource allocation")
    if not_started_tasks > completed_tasks:
        project_insights.append(f"Planning Strength: {not_started_tasks} tasks in planning phase")
    
    # Task insights (exact same format as reports view)
    task_insights = []
    if completed_tasks > in_progress_tasks:
        task_insights.append(f"Task Velocity: High completion rate with {completed_tasks} tasks finished")
    if not_started_tasks > completed_tasks:
        task_insights.append(f"Task Backlog: {not_started_tasks} tasks pending - prioritize execution")
    
    # Timeline insights (exact same format as reports view)
    timeline_insights = []
    if timeline_progress > 100:
        timeline_insights.append(f"Timeline Alert: Project has exceeded its planned timeline")
    elif timeline_progress >= 80:
        timeline_insights.append(f"Timeline Status: Project is approaching its deadline")
    else:
        timeline_insights.append(f"Timeline Status: {timeline_progress:.1f}% of timeline elapsed")
    
    # Combine all insights (exact same format as reports view)
    all_insights = project_insights + task_insights + timeline_insights
    for insight in all_insights:
        story.append(Paragraph(insight, insight_style))
    
    story.append(Spacer(1, 15))
    
    # Project Details (exact same structure as reports view)
    story.append(Paragraph('Project Details', heading_style))
    
    # Show enhanced project details with comprehensive metrics
    project_data = [['Metric', 'Value', 'Status', 'Progress']]
    
    project_data.append([
        'Project Name',
        project.name[:30] + "..." if len(project.name) > 30 else project.name,
        project.get_status_display(),
        f"{task_completion_rate:.1f}%"
    ])
    
    project_data.append([
        'Client',
        project.client[:25] + "..." if len(project.client) > 25 else project.client,
        'Active',
        f"{subtask_completion_rate:.1f}%"
    ])
    
    project_data.append([
        'Duration',
        f"{(project.end_date - project.start_date).days + 1} days" if project.start_date and project.end_date else "Not set",
        'Planned',
        f"{timeline_progress:.1f}%"
    ])
    
    project_data.append([
        'Tasks',
        f"{completed_tasks}/{total_tasks}",
        'In Progress' if in_progress_tasks > 0 else 'Completed' if completed_tasks == total_tasks else 'Planning',
        f"{(completed_tasks/total_tasks*100):.1f}%" if total_tasks > 0 else "0%"
    ])
    
    project_data.append([
        'Team Size',
        f"{team_size} members",
        'Optimal' if team_size >= 2 else 'Limited' if team_size == 1 else 'None',
        f"{(team_size/3*100):.1f}%" if team_size > 0 else "0%"
    ])
    
    project_data.append([
        'Priority Tasks',
        f"{urgent_tasks} urgent, {high_priority_tasks} high",
        'Alert' if urgent_tasks > 0 else 'Good' if high_priority_tasks > 0 else 'Normal',
        f"{(urgent_tasks + high_priority_tasks)/total_tasks*100:.1f}%" if total_tasks > 0 else "0%"
    ])
    
    project_data.append([
        'Recent Activity',
        f"{recent_tasks} tasks, {recent_subtasks} subtasks",
        'Active' if recent_tasks > 0 or recent_subtasks > 0 else 'Quiet',
        f"{(recent_tasks + recent_subtasks)/max(1, total_tasks)*100:.1f}%"
    ])
    
    project_data.append([
        'Avg Completion',
        f"{avg_completion_days:.1f} days",
        'Fast' if avg_completion_days <= 5 else 'Normal' if avg_completion_days <= 10 else 'Slow',
        f"{(5/avg_completion_days*100):.1f}%" if avg_completion_days > 0 else "0%"
    ])
    
    project_table = Table(project_data, colWidths=[1.2*inch, 1.5*inch, 1*inch, 0.8*inch])
    project_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),  # Red header
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # White background
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#000000')),  # Black text
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#000000')),  # Black grid lines
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (3, 1), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.white]),  # All white rows
    ]))
    story.append(project_table)
    story.append(Spacer(1, 15))
    
    # Strategic Recommendations (exact same structure as reports view)
    # Priority and Development Status Analysis
    story.append(Paragraph('Priority and Development Analysis', heading_style))
    
    # Priority distribution table
    priority_data = [['Priority Level', 'Count', 'Percentage', 'Status']]
    total_priority_tasks = urgent_tasks + high_priority_tasks + medium_priority_tasks + low_priority_tasks
    
    if urgent_tasks > 0:
        priority_data.append(['Urgent', str(urgent_tasks), f"{(urgent_tasks/total_priority_tasks*100):.1f}%", 'Critical'])
    if high_priority_tasks > 0:
        priority_data.append(['High', str(high_priority_tasks), f"{(high_priority_tasks/total_priority_tasks*100):.1f}%", 'Important'])
    if medium_priority_tasks > 0:
        priority_data.append(['Medium', str(medium_priority_tasks), f"{(medium_priority_tasks/total_priority_tasks*100):.1f}%", 'Normal'])
    if low_priority_tasks > 0:
        priority_data.append(['Low', str(low_priority_tasks), f"{(low_priority_tasks/total_priority_tasks*100):.1f}%", 'Low'])
    
    if len(priority_data) > 1:
        priority_table = Table(priority_data, colWidths=[1.2*inch, 0.8*inch, 1*inch, 1*inch])
        priority_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.white]),  # All white rows
        ]))
        story.append(priority_table)
        story.append(Spacer(1, 12))
    
    # Development status insights
    if development_statuses:
        story.append(Paragraph('Development Status Distribution:', heading_style))
        for status in development_statuses:
            status_name = status['development_status'].replace('_', ' ').title()
            status_count = status['count']
            story.append(Paragraph(f"• {status_name}: {status_count} tasks", insight_style))
        story.append(Spacer(1, 12))
    
    story.append(Paragraph('Strategic Recommendations', heading_style))
    
    recommendations = []
    
    # Performance-based recommendations
    if task_completion_rate < 50:
        recommendations.append("Accelerate Task Completion: Focus on completing tasks in progress to improve overall completion rate")
    if subtask_completion_rate < 50:
        recommendations.append("SubTask Prioritization: Implement subtask prioritization framework to increase completion velocity")
    if timeline_progress > 100:
        recommendations.append("Timeline Management: Project has exceeded timeline - consider scope adjustment or resource allocation")
    
    # Priority-based recommendations
    if urgent_tasks > 0:
        recommendations.append("Urgent Task Resolution: Address urgent tasks immediately to prevent project delays")
    if high_priority_tasks > 3:
        recommendations.append("Priority Management: Consider reducing high-priority tasks to focus on critical deliverables")
    
    # Team-based recommendations
    if team_size < 2:
        recommendations.append("Team Expansion: Consider adding team members to improve project velocity")
    if team_size > 5:
        recommendations.append("Team Optimization: Large team size may impact coordination - consider team structure review")
    
    # Resource-based recommendations
    if in_progress_tasks > completed_tasks * 2:
        recommendations.append("Resource Optimization: Consider reallocating resources to balance task pipeline")
    if not_started_tasks > completed_tasks:
        recommendations.append("Task Management: Implement task initiation protocols to reduce backlog")
    
    # Status-based recommendations
    if on_hold_tasks > 0:
        recommendations.append("Task Unblocking: Review and resolve on-hold tasks to maintain project momentum")
    if guidance_required_tasks > 0:
        recommendations.append("Guidance Provision: Provide additional guidance for tasks requiring clarification")
    
    # Performance metrics recommendations
    if avg_completion_days > 10:
        recommendations.append("Process Optimization: Review task execution processes to reduce completion time")
    if recent_activity['tasks'] == 0 and recent_activity['subtasks'] == 0:
        recommendations.append("Activity Stimulation: Encourage team activity to maintain project momentum")
    
    # Positive reinforcement
    if task_completion_rate >= 80:
        recommendations.append("Maintain Excellence: Current performance is excellent - continue current practices")
    if subtask_completion_rate >= 75:
        recommendations.append("Sustain Momentum: SubTask completion rate is strong - maintain current workflow")
    if avg_completion_days <= 5:
        recommendations.append("Efficiency Recognition: Task completion speed is excellent - document best practices")
    
    # Status-based recommendations
    if project.status == 'completed':
        recommendations.append("Project Success: Project has been successfully completed - document lessons learned")
    elif project.status == 'in_progress' and in_progress_tasks == 0:
        recommendations.append("Project Activation: Start working on planned tasks to move project forward")
    elif project.status == 'planned' and total_tasks == 0:
        recommendations.append("Project Planning: Consider adding tasks to begin project execution")
    
    # Default recommendations if no specific ones
    if not recommendations:
        recommendations.append("Continuous Monitoring: Track key metrics regularly to identify improvement opportunities")
        recommendations.append("Process Optimization: Review and optimize project management processes")
        recommendations.append("Team Communication: Ensure regular team updates and status meetings")
    
    for rec in recommendations:
        story.append(Paragraph(rec, insight_style))
    
    story.append(Spacer(1, 15))
    
    # Footer (exact same format as reports view)
    story.append(Paragraph(f'Generated on {timezone.now().strftime("%B %d, %Y at %I:%M %p")} | Project Management', ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        alignment=1,
        textColor=colors.HexColor('#6b7280'),  # Gray
        fontName='Helvetica'
    )))
    
    # Charts Section
    try:
        # Status distribution pie chart
        status_values = [not_started_tasks, in_progress_tasks, completed_tasks]
        status_labels = ['Not Started', 'In Progress', 'Completed']
        if sum(status_values) > 0:
            drawing = Drawing(400, 220)
            pie = Pie()
            pie.x = 130
            pie.y = 10
            pie.width = 140
            pie.height = 140
            pie.data = status_values
            pie.labels = [f"{label} ({val})" for label, val in zip(status_labels, status_values)]
            pie.slices[0].fillColor = colors.HexColor('#9ca3af')
            pie.slices[1].fillColor = colors.HexColor('#111827')
            pie.slices[2].fillColor = colors.HexColor('#ef4444')
            drawing.add(pie)
            story.append(Paragraph('Status Distribution', heading_style))
            story.append(drawing)
            story.append(Spacer(1, 12))

        # Task distribution bar chart
        drawing = Drawing(400, 220)
        bc = VerticalBarChart()
        bc.x = 40
        bc.y = 30
        bc.height = 150
        bc.width = 320
        bc.data = [[completed_tasks, in_progress_tasks, not_started_tasks]]
        bc.categoryAxis.categoryNames = ['Completed', 'In Progress', 'Not Started']
        bc.bars[0].fillColor = colors.HexColor('#ef4444')
        drawing.add(bc)
        story.append(Paragraph('Task Distribution', heading_style))
        story.append(drawing)
        story.append(Spacer(1, 12))
    except Exception:
        pass

    # Build PDF with header/footer on all pages
    try:
        doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    except Exception as _e:
        doc.build(story)
    
    return pdf_path

def generate_comprehensive_project_pdf_report(project_id, days_filter=30):
    """
    Generate a comprehensive PDF report for a single project using the same format as client reports
    This function creates a detailed report for one specific project using professional styling
    OPTIMIZED TO FIT ON ONE PAGE
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem, KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String, Circle
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    from io import BytesIO
    from datetime import datetime
    import tempfile
    
    # Get the project and its tasks
    project = get_object_or_404(Project, id=project_id)
    project_tasks = project.tasks.all()
    
    # Get project-specific data
    total_tasks = project_tasks.count()
    completed_tasks = project_tasks.filter(status='completed').count()
    in_progress_tasks = project_tasks.filter(status='in_progress').count()
    not_started_tasks = project_tasks.filter(status='not_started').count()
    on_hold_tasks = project_tasks.filter(status='on_hold').count()
    
    # Get subtasks for this project
    project_subtasks = SubTask.objects.filter(task__project=project)
    total_subtasks = project_subtasks.count()
    completed_subtasks = project_subtasks.filter(is_completed=True).count()
    pending_subtasks = total_subtasks - completed_subtasks
    
    # Calculate completion rates
    task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    subtask_completion_rate = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
    
    # Calculate timeline progress
    timeline_progress = 0
    if project.start_date and project.end_date:
        from django.utils import timezone
        end_date = timezone.now()
        total_duration = (project.end_date - project.start_date).days
        elapsed_duration = (end_date - project.start_date).days
        if total_duration > 0:
            timeline_progress = (elapsed_duration / total_duration) * 100
    
    # Get recent activity (last N days)
    from django.utils import timezone
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days_filter)
    
    recent_tasks = project_tasks.filter(created_at__gte=start_date).count()
    
    # Create descriptive temporary file for PDF
    import os, re
    temp_dir = tempfile.gettempdir()
    safe_project = re.sub(r'[^a-zA-Z0-9_-]+', '_', project.name).strip('_')[:40]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    descriptive_filename = f"E-Click_ProjectReport_{safe_project}_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, descriptive_filename)
    
    # Create PDF document with tight margins to fit everything on one page
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles for professional report with red/white/black theme (single-page optimized)
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#dc2626'),  # Red
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=15,
        alignment=1,
        textColor=colors.HexColor('#6b7280'),  # Gray
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=15,
        textColor=colors.HexColor('#1f2937'),  # Dark gray/black
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        textColor=colors.HexColor('#000000'),  # Black text
        fontName='Helvetica'
    )
    
    # Build content for comprehensive project report
    elements = []

    # Title + Project Info
    # Add E-Click logo instead of text
    try:
        logo_path = os.path.join(settings.BASE_DIR, 'home', 'Logo.png')
        if os.path.exists(logo_path):
            # Create a flowable image for the logo
            from reportlab.platypus import Image
            logo_img = Image(logo_path, width=80, height=40)
            elements.append(logo_img)
            elements.append(Spacer(1, 5))
        else:
            # Fallback to text if logo not found
            elements.append(Paragraph('E-Click', title_style))
    except Exception:
        # Fallback to text if logo loading fails
        elements.append(Paragraph('E-Click', title_style))
    
    elements.append(Paragraph(f'Project Report: {project.name}', subtitle_style))
    elements.append(Spacer(1, 10))
    
    # Client and Date Range
    client_info = f'Client: {project.client} | {start_date.strftime("%B %d, %Y")} - {end_date.strftime("%B %d, %Y")}'
    elements.append(Paragraph(client_info, normal_style))
    elements.append(Spacer(1, 6))
    
    # Client Details
    elements.append(Paragraph(project.client, normal_style))
    elements.append(Paragraph(project.client_email or 'No email', normal_style))
    elements.append(Spacer(1, 12))
    
    # Overall Task Completion Section
    elements.append(Paragraph('Overall Task Completion', heading_style))
    elements.append(Spacer(1, 6))
    
    # Enhanced Task completion donut chart with better styling
    try:
        drawing = Drawing(400, 200)
        pie = Pie()
        pie.x = 150
        pie.y = 50
        pie.width = 100
        pie.height = 100
        
        # Create donut chart showing completed vs remaining
        pie.data = [completed_tasks, total_tasks - completed_tasks]
        pie.labels = ['Completed', 'Remaining']
        pie.slices[0].fillColor = colors.HexColor('#10b981')  # Green for completed
        pie.slices[1].fillColor = colors.HexColor('#e5e7eb')  # Light gray for remaining
        
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 2
        drawing.add(pie)
        
        # Add center circle for donut effect
        from reportlab.graphics.shapes import Circle, String
        cx, cy = 200, 100
        ring = Circle(cx, cy, 35, fillColor=colors.white, strokeColor=colors.white)
        drawing.add(ring)
        
        # Add percentage in center
        pct_label = String(cx, cy - 4, f"{task_completion_rate:.1f}%", textAnchor='middle')
        pct_label.fontName = 'Helvetica-Bold'
        pct_label.fontSize = 16
        pct_label.fillColor = colors.HexColor('#111827')
        drawing.add(pct_label)
        
        # Add legend
        from reportlab.graphics.charts.legends import Legend
        legend = Legend()
        legend.x = 280
        legend.y = 100
        legend.alignment = 'right'
        legend.fontName = 'Helvetica'
        legend.fontSize = 8
        legend.colorNamePairs = [
            (colors.HexColor('#10b981'), 'Completed'),
            (colors.HexColor('#e5e7eb'), 'Remaining')
        ]
        drawing.add(legend)
        
        elements.append(drawing)
        elements.append(Spacer(1, 10))
    except Exception:
        pass
    
    # Task completion labels
    elements.append(Paragraph('Completed', normal_style))
    elements.append(Paragraph('Remaining', normal_style))
    elements.append(Spacer(1, 12))
    
    # Task Status Breakdown
    elements.append(Paragraph('Task Status Breakdown', subheading_style))
    elements.append(Spacer(1, 8))
    
    task_status_data = [
        ['Status', 'Count', 'Percentage'],
        ['Completed', str(completed_tasks), f'{(completed_tasks/total_tasks*100):.1f}%' if total_tasks > 0 else '0%'],
        ['In Progress', str(in_progress_tasks), f'{(in_progress_tasks/total_tasks*100):.1f}%' if total_tasks > 0 else '0%'],
        ['Not Started', str(not_started_tasks), f'{(not_started_tasks/total_tasks*100):.1f}%' if total_tasks > 0 else '0%'],
        ['On Hold', str(on_hold_tasks), f'{(on_hold_tasks/total_tasks*100):.1f}%' if total_tasks > 0 else '0%']
    ]
    
    task_status_table = Table(task_status_data, colWidths=[doc.width * 0.4, doc.width * 0.3, doc.width * 0.3])
    task_status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('LEADING', (0, 1), (-1, -1), 10),
    ]))
    elements.append(task_status_table)
    elements.append(Spacer(1, 15))
    
    # Subtask Progress
    if total_subtasks > 0:
        elements.append(Paragraph('Subtask Progress', subheading_style))
        elements.append(Spacer(1, 8))
        
        subtask_data = [
            ['Metric', 'Count', 'Percentage'],
            ['Total Subtasks', str(total_subtasks), '100%'],
            ['Completed', str(completed_subtasks), f'{subtask_completion_rate:.1f}%'],
            ['Pending', str(pending_subtasks), f'{(pending_subtasks/total_subtasks*100):.1f}%']
        ]
        
        subtask_table = Table(subtask_data, colWidths=[doc.width * 0.4, doc.width * 0.3, doc.width * 0.3])
        subtask_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('LEADING', (0, 1), (-1, -1), 10),
        ]))
        elements.append(subtask_table)
        elements.append(Spacer(1, 15))
    
    # Executive Summary
    elements.append(Paragraph('Executive Summary', heading_style))
    elements.append(Spacer(1, 6))
    
    summary_items = [
        f'Project Performance: {task_completion_rate:.1f}% completion rate with {in_progress_tasks} active tasks',
        f'Task Efficiency: {task_completion_rate:.1f}% task completion with {completed_tasks} tasks delivered',
        f'SubTask Progress: {subtask_completion_rate:.1f}% subtask completion showing detailed execution',
        f'Timeline Status: {timeline_progress:.1f}% of project timeline elapsed'
    ]
    
    for item in summary_items:
        elements.append(Paragraph(f'• {item}', normal_style))
        elements.append(Spacer(1, 3))
    
    elements.append(Spacer(1, 8))
    
    # Performance Analysis Table
    elements.append(Paragraph('Performance Analysis', heading_style))
    elements.append(Spacer(1, 6))
    
    performance_data = [
        ['Metric', 'Current', 'Target', 'Performance', 'Trend'],
        ['Task Completion', f'{task_completion_rate:.1f}%', '75%', 'Red' if task_completion_rate < 75 else 'Green', 'Up'],
        ['SubTask Completion', f'{subtask_completion_rate:.1f}%', '70%', 'Red' if subtask_completion_rate < 70 else 'Green', 'Up'],
        ['Timeline Progress', f'{timeline_progress:.1f}%', '80%', 'Red' if timeline_progress > 80 else 'Green', 'Up'],
        ['Project Status', project.get_status_display(), 'Completed', 'Yellow' if project.status == 'in_progress' else 'Green', 'Up']
    ]
    
    performance_table = Table(performance_data, colWidths=[doc.width * 0.25, doc.width * 0.2, doc.width * 0.2, doc.width * 0.2, doc.width * 0.15])
    performance_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('LEADING', (0, 1), (-1, -1), 10),
    ]))
    elements.append(performance_table)
    elements.append(Spacer(1, 12))
    
    # Action Items Table
    elements.append(Paragraph('Action Items', heading_style))
    elements.append(Spacer(1, 6))
    
    # Get all tasks for this project with completion dates
    action_items = []
    for i, task in enumerate(project_tasks.order_by('status', 'created_at'), 1):
        if task.status == 'completed' and task.completed_at:
            completion_date = task.completed_at.strftime('%d/%m/%Y')
        else:
            completion_date = 'Pending'
        
        action_items.append([str(i), task.name, completion_date])
    
    # Add header row
    action_header = [['#', 'Action', 'Date Completed']]
    action_data = action_header + action_items
    
    action_table = Table(action_data, colWidths=[doc.width * 0.1, doc.width * 0.7, doc.width * 0.2])
    action_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('LEADING', (0, 1), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(action_table)
    
    # Build the PDF
    doc.build(elements)
    return pdf_path

def generate_comprehensive_system_pdf_report(days_filter=30):
    """
    Generate a comprehensive system-wide PDF report covering all projects, clients, and system metrics
    This function creates a detailed executive-level report with enhanced visualizations and professional styling
    OPTIMIZED TO FIT ON ONE PAGE
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem, KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String, Line, Circle
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    from reportlab.graphics.charts.legends import Legend
    from io import BytesIO
    from datetime import datetime, timedelta
    import tempfile
    from django.db.models import Count, Q, Avg
    from django.utils import timezone
    
    # Get comprehensive system data
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days_filter)
    
    # System-wide statistics
    total_projects = Project.objects.count()
    projects_in_progress = Project.objects.filter(status='in_progress').count()
    projects_completed = Project.objects.filter(status='completed').count()
    projects_planned = Project.objects.filter(status='planned').count()
    projects_on_hold = Project.objects.filter(status='on_hold').count()
    
    total_tasks = Task.objects.count()
    completed_tasks = Task.objects.filter(status='completed').count()
    in_progress_tasks = Task.objects.filter(status='in_progress').count()
    not_started_tasks = Task.objects.filter(status='not_started').count()
    on_hold_tasks = Task.objects.filter(status='on_hold').count()
    guidance_required_tasks = Task.objects.filter(status='in_progress_guidance_required').count()
    
    total_subtasks = SubTask.objects.count()
    completed_subtasks = SubTask.objects.filter(is_completed=True).count()
    pending_subtasks = total_subtasks - completed_subtasks
    
    total_users = User.objects.count()
    active_users = User.objects.filter(last_login__gte=start_date).count()
    inactive_users = total_users - active_users
    staff_users = User.objects.filter(is_staff=True).count()
    
    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(is_active=True).count()
    
    # Calculate completion rates
    project_completion_rate = (projects_completed / total_projects * 100) if total_projects > 0 else 0
    task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    subtask_completion_rate = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
    
    # Get priority distribution
    high_priority_tasks = Task.objects.filter(priority='high').count()
    urgent_tasks = Task.objects.filter(priority='urgent').count()
    medium_priority_tasks = Task.objects.filter(priority='medium').count()
    low_priority_tasks = Task.objects.filter(priority='low').count()
    
    # Get development status distribution
    development_statuses = Task.objects.values('development_status').annotate(count=Count('id'))
    
    # Recent activity metrics
    recent_projects = Project.objects.filter(created_at__gte=start_date).count()
    recent_tasks = Task.objects.filter(created_at__gte=start_date).count()
    recent_completions = Task.objects.filter(status='completed', completed_at__gte=start_date).count()
    
    # Top performing projects
    projects_with_tasks = Project.objects.annotate(
        total_tasks=Count('tasks'),
        completed_tasks=Count('tasks', filter=Q(tasks__status='completed'))
    ).filter(total_tasks__gt=0)
    
    top_projects = []
    for project in projects_with_tasks:
        completion_rate = (project.completed_tasks / project.total_tasks) * 100 if project.total_tasks > 0 else 0
        top_projects.append({
            'name': project.name,
            'client': project.client,
            'status': project.status,
            'total_tasks': project.total_tasks,
            'completed_tasks': project.completed_tasks,
            'completion_rate': round(completion_rate, 1),
        })
    
    top_projects.sort(key=lambda x: x['completion_rate'], reverse=True)
    top_projects = top_projects[:10]
    
    # Client performance metrics
    client_performance = []
    for client in Client.objects.filter(is_active=True):
        client_projects = Project.objects.filter(client_username=client.username)
        if client_projects.exists():
            total_client_tasks = Task.objects.filter(project__in=client_projects).count()
            completed_client_tasks = Task.objects.filter(project__in=client_projects, status='completed').count()
            completion_rate = (completed_client_tasks / total_client_tasks * 100) if total_client_tasks > 0 else 0
            
            client_performance.append({
                'username': client.username,
                'email': client.email,
                'total_projects': client_projects.count(),
                'total_tasks': total_client_tasks,
                'completion_rate': round(completion_rate, 1),
            })
    
    client_performance.sort(key=lambda x: x['completion_rate'], reverse=True)
    
    # Create descriptive temporary file for PDF
    import os, re
    from django.conf import settings
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    descriptive_filename = f"ComprehensiveSystemReport_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, descriptive_filename)
    
    # Create PDF document with minimal margins to fit everything on one page
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Enhanced custom styles for professional comprehensive report - OPTIMIZED FOR SINGLE PAGE
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=15,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#dc2626'),  # Red
        fontName='Helvetica-Bold',
        spaceBefore=0
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        alignment=1,
        textColor=colors.HexColor('#6b7280'),  # Gray
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=8,
        spaceBefore=12,
        textColor=colors.HexColor('#1f2937'),  # Dark gray/black
        fontName='Helvetica-Bold',
        borderWidth=1,
        borderColor=colors.HexColor('#e5e7eb'),
        borderPadding=6,
        backColor=colors.HexColor('#f9fafb')
    )
    
    subheading_style = ParagraphStyle(
        'SubSectionHeading',
        parent=styles['Heading3'],
        fontSize=10,
        spaceAfter=6,
        spaceBefore=10,
        textColor=colors.HexColor('#374151'),
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=8,
        spaceAfter=4,
        textColor=colors.HexColor('#000000'),
        fontName='Helvetica',
        leading=10
    )
    
    highlight_style = ParagraphStyle(
        'HighlightText',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=4,
        textColor=colors.HexColor('#dc2626'),
        fontName='Helvetica-Bold'
    )
    
    # Build comprehensive system report content (copied design language from project PDF)
    elements = []
    
    # Signature + header
    signature_style = ParagraphStyle(
        'CompanySignature',
        parent=styles['Normal'],
        fontSize=16,
        spaceAfter=0,
        alignment=0,
        textColor=colors.HexColor('#dc2626'),
        fontName='Helvetica-Bold'
    )
    # Add E-Click logo instead of text
    try:
        logo_path = os.path.join(settings.BASE_DIR, 'home', 'Logo.png')
        if os.path.exists(logo_path):
            # Create a flowable image for the logo
            from reportlab.platypus import Image
            logo_img = Image(logo_path, width=80, height=40)
            elements.append(logo_img)
            elements.append(Spacer(1, 5))
        else:
            # Fallback to text if logo not found
            elements.append(Paragraph('E-Click', signature_style))
            elements.append(Spacer(1, 5))
    except Exception:
        # Fallback to text if logo loading fails
        elements.append(Paragraph('E-Click', signature_style))
        elements.append(Spacer(1, 5))
    
    elements.append(Paragraph('Comprehensive System Report', title_style))
    elements.append(Paragraph(f"Period: {start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}", subtitle_style))
    elements.append(Spacer(1, 10))
    
    # Donut chart: overall task completion
    try:
        total_for_progress = max(1, total_tasks)
        progress_pct = (completed_tasks / total_for_progress) * 100
        drawing = Drawing(380, 200)
        pie = Pie()
        pie.x = 120
        pie.y = 40
        pie.width = 120
        pie.height = 120
        pie.data = [completed_tasks, max(0, total_tasks - completed_tasks)]
        pie.labels = ['Completed', 'Remaining']
        pie.slices[0].fillColor = colors.HexColor('#dc2626')
        pie.slices[1].fillColor = colors.HexColor('#e5e7eb')
        drawing.add(pie)
        center_x, center_y = 180, 100
        hole = Circle(center_x, center_y, 35, fillColor=colors.white, strokeColor=colors.white)
        drawing.add(hole)
        label = String(center_x, center_y - 3, f"{progress_pct:.1f}%", textAnchor='middle')
        label.fontName = 'Helvetica-Bold'
        label.fontSize = 14
        drawing.add(label)
        elements.append(Paragraph('Overall Task Completion', heading_style))
        elements.append(drawing)
        elements.append(Spacer(1, 8))
    except Exception:
        pass
    
    # Executive Summary (insights style)
    elements.append(Paragraph('Executive Summary', heading_style))
    insights = []
    insights.append(f"Projects: {total_projects} total • {projects_completed} completed • {projects_in_progress} in progress • {projects_planned} planned")
    insights.append(f"Tasks: {total_tasks} total • {completed_tasks} completed • {in_progress_tasks} in progress • {not_started_tasks} not started")
    if total_subtasks > 0:
        insights.append(f"Subtasks: {total_subtasks} total • {completed_subtasks} completed • {pending_subtasks} pending")
    insights.append(f"Users: {active_users}/{total_users} active • Clients: {active_clients}/{total_clients} active")
    insights.append(f"Recent: {recent_projects} new projects • {recent_tasks} new tasks • {recent_completions} tasks completed (last {days_filter} days)")
    if urgent_tasks > 0:
        insights.append(f"Priority: {urgent_tasks} urgent, {high_priority_tasks} high priority tasks")
    for insight in insights[:6]:
        elements.append(Paragraph(insight, normal_style))
    elements.append(Spacer(1, 8))
    
    # Performance Analysis (system-wide)
    elements.append(Paragraph('Performance Analysis', heading_style))
    perf_rows = [
        ['Metric', 'Current', 'Target', 'Performance', 'Trend'],
        ['Project Completion', f"{project_completion_rate:.1f}%", '80%', 'Green' if project_completion_rate >= 80 else 'Yellow' if project_completion_rate >= 60 else 'Red', 'Up' if projects_completed >= projects_in_progress else 'Stable'],
        ['Task Completion', f"{task_completion_rate:.1f}%", '75%', 'Green' if task_completion_rate >= 75 else 'Yellow' if task_completion_rate >= 50 else 'Red', 'Up' if completed_tasks >= in_progress_tasks else 'Stable'],
        ['Subtask Completion', f"{subtask_completion_rate:.1f}%", '70%', 'Green' if subtask_completion_rate >= 70 else 'Yellow' if subtask_completion_rate >= 50 else 'Red', 'Stable'],
        ['User Engagement', f"{(active_users/total_users*100 if total_users else 0):.1f}%", '60%', 'Green' if total_users and (active_users/total_users*100) >= 60 else 'Yellow' if total_users and (active_users/total_users*100) >= 40 else 'Red', 'Stable'],
        ['Client Activation', f"{(active_clients/total_clients*100 if total_clients else 0):.1f}%", '80%', 'Green' if total_clients and (active_clients/total_clients*100) >= 80 else 'Yellow' if total_clients and (active_clients/total_clients*100) >= 60 else 'Red', 'Stable'],
        ['Priority Load', f"{urgent_tasks} urgent", '0', 'Green' if urgent_tasks == 0 else 'Red', 'Down' if urgent_tasks > 0 else 'Stable'],
    ]
    perf_table = Table(perf_rows, colWidths=[doc.width*0.28, doc.width*0.18, doc.width*0.18, doc.width*0.18, doc.width*0.18])
    perf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#000000')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#000000')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
    ]))
    elements.append(perf_table)
    elements.append(Spacer(1, 10))
    
    # Project Status Distribution Chart - COMPACT
    elements.append(Paragraph('Project Status Distribution', subheading_style))
    elements.append(Spacer(1, 6))
    
    try:
        # Create compact pie chart for project status
        drawing = Drawing(300, 150)
        pie = Pie()
        pie.x = 100
        pie.y = 25
        pie.width = 80
        pie.height = 80
        
        # Project status data
        status_data = [projects_completed, projects_in_progress, projects_planned, projects_on_hold]
        status_labels = ['Completed', 'In Progress', 'Planned', 'On Hold']
        status_colors = [
            colors.HexColor('#10b981'),  # Green for completed
            colors.HexColor('#3b82f6'),  # Blue for in progress
            colors.HexColor('#f59e0b'),  # Orange for planned
            colors.HexColor('#ef4444')   # Red for on hold
        ]
        
        pie.data = status_data
        pie.labels = status_labels
        
        # Apply colors
        for i, color in enumerate(status_colors):
            if i < len(pie.slices):
                pie.slices[i].fillColor = color
                pie.slices[i].strokeColor = colors.white
                pie.slices[i].strokeWidth = 1
        
        drawing.add(pie)
        
        # Add compact legend
        legend = Legend()
        legend.x = 200
        legend.y = 60
        legend.alignment = 'right'
        legend.fontName = 'Helvetica'
        legend.fontSize = 6
        legend.colorNamePairs = [(status_colors[i], status_labels[i]) for i in range(len(status_labels))]
        drawing.add(legend)
        
        elements.append(drawing)
        elements.append(Spacer(1, 8))
    except Exception:
        pass
    
    # Task Priority Distribution - COMPACT
    elements.append(Paragraph('Task Priority Distribution', subheading_style))
    elements.append(Spacer(1, 6))
    
    try:
        # Create horizontal bar chart for task priorities
        drawing = Drawing(400, 150)
        chart = HorizontalLineChart()
        chart.x = 80
        chart.y = 30
        chart.width = 300
        chart.height = 100
        
        chart.data = [[urgent_tasks, high_priority_tasks, medium_priority_tasks, low_priority_tasks]]
        chart.categoryAxis.categoryNames = ['Urgent', 'High', 'Medium', 'Low']
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max([urgent_tasks, high_priority_tasks, medium_priority_tasks, low_priority_tasks]) * 1.2
        
        # Apply colors
        chart.lines[0].strokeColor = colors.HexColor('#dc2626')
        chart.lines[0].strokeWidth = 20
        
        drawing.add(chart)
        elements.append(drawing)
        elements.append(Spacer(1, 15))
    except Exception:
        pass
    
    # Top Performing Projects
    elements.append(Paragraph('Top Performing Projects', subheading_style))
    elements.append(Spacer(1, 8))
    
    if top_projects:
        top_projects_data = [['Rank', 'Project Name', 'Client', 'Completion Rate', 'Tasks']]
        for i, project in enumerate(top_projects[:5], 1):
            top_projects_data.append([
                f'#{i}',
                project['name'][:30] + '...' if len(project['name']) > 30 else project['name'],
                project['client'][:20] + '...' if len(str(project['client'])) > 20 else str(project['client']),
                f"{project['completion_rate']}%",
                f"{project['completed_tasks']}/{project['total_tasks']}"
            ])
        
        top_projects_table = Table(top_projects_data, colWidths=[doc.width * 0.1, doc.width * 0.3, doc.width * 0.25, doc.width * 0.2, doc.width * 0.15])
        top_projects_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('LEADING', (0, 1), (-1, -1), 10),
        ]))
        elements.append(top_projects_table)
        elements.append(Spacer(1, 15))
    
    # Client Performance Overview
    elements.append(Paragraph('Client Performance Overview', subheading_style))
    elements.append(Spacer(1, 8))
    
    if client_performance:
        client_data = [['Client', 'Projects', 'Tasks', 'Completion Rate']]
        for client in client_performance[:8]:  # Top 8 clients
            client_data.append([
                client['username'][:25] + '...' if len(client['username']) > 25 else client['username'],
                str(client['total_projects']),
                str(client['total_tasks']),
                f"{client['completion_rate']}%"
            ])
        
        client_table = Table(client_data, colWidths=[doc.width * 0.4, doc.width * 0.2, doc.width * 0.2, doc.width * 0.2])
        client_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('LEADING', (0, 1), (-1, -1), 10),
        ]))
        elements.append(client_table)
        elements.append(Spacer(1, 15))
    
    # Recent Activity (compact)
    elements.append(Paragraph('Recent Activity', subheading_style))
    elements.append(Paragraph(f"Projects created: {recent_projects} • Tasks added: {recent_tasks} • Tasks completed: {recent_completions} (last {days_filter} days)", normal_style))
    elements.append(Spacer(1, 8))
    
    # Key Performance Indicators
    elements.append(Paragraph('Key Performance Indicators (KPIs)', subheading_style))
    elements.append(Spacer(1, 8))
    
    kpi_data = [
        ['KPI', 'Current Value', 'Benchmark', 'Status'],
        ['Project Success Rate', f'{project_completion_rate:.1f}%', '80%', '🟢' if project_completion_rate >= 80 else '🟡' if project_completion_rate >= 60 else '🔴'],
        ['Task Efficiency', f'{task_completion_rate:.1f}%', '75%', '🟢' if task_completion_rate >= 75 else '🟡' if task_completion_rate >= 50 else '🔴'],
        ['Resource Utilization', f'{(active_users/total_users*100):.1f}%', '60%', '🟢' if (active_users/total_users*100) >= 60 else '🟡'],
        ['Client Retention', f'{(active_clients/total_clients*100):.1f}%', '80%', '🟢' if (active_clients/total_clients*100) >= 80 else '🟡'],
        ['System Reliability', '99.9%', '99%', '🟢']
    ]
    
    kpi_table = Table(kpi_data, colWidths=[doc.width * 0.3, doc.width * 0.25, doc.width * 0.25, doc.width * 0.2])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('LEADING', (0, 1), (-1, -1), 10),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 20))
    
    # Progress Visualization - COMPACT
    elements.append(Paragraph('Progress Visualization', heading_style))
    elements.append(Spacer(1, 6))
    
    # Create a compact visual progress bar
    try:
        drawing = Drawing(300, 40)
        
        # Background bar
        bg_bar = Drawing(300, 15)
        bg_bar.add(Line(30, 7, 270, 7, strokeColor=colors.HexColor('#e5e7eb'), strokeWidth=15))
        drawing.add(bg_bar)
        
        # Progress bar
        progress_width = (task_completion_rate / 100) * 240
        if progress_width > 0:
            progress_bar = Drawing(300, 15)
            progress_bar.add(Line(30, 7, 30 + progress_width, 7, strokeColor=colors.HexColor('#10b981'), strokeWidth=15))
            drawing.add(progress_bar)
        
        # Add percentage text
        pct_text = String(150, 25, f"{task_completion_rate:.1f}% Complete", textAnchor='middle')
        pct_text.fontName = 'Helvetica-Bold'
        pct_text.fontSize = 9
        pct_text.fillColor = colors.HexColor('#374151')
        drawing.add(pct_text)
        
        elements.append(drawing)
        elements.append(Spacer(1, 10))
    except Exception:
        pass
    
    # Recommendations Section - COMPACT
    elements.append(Paragraph('Strategic Recommendations', heading_style))
    elements.append(Spacer(1, 6))
    
    # Create compact recommendations table
    recommendations_data = []
    
    if project_completion_rate < 80:
        recommendations_data.append(['Projects', f'Focus on completion: {project_completion_rate:.1f}% vs 80% target'])
    if task_completion_rate < 75:
        recommendations_data.append(['Tasks', f'Improve execution: {task_completion_rate:.1f}% vs 75% target'])
    if urgent_tasks > 0:
        recommendations_data.append(['Urgent', f'Address {urgent_tasks} urgent tasks to prevent bottlenecks'])
    if guidance_required_tasks > 0:
        recommendations_data.append(['Guidance', f'Provide guidance for {guidance_required_tasks} tasks'])
    
    if not recommendations_data:
        recommendations_data.append(['Status', 'All KPIs meeting/exceeding targets - maintain performance'])
    
    if recommendations_data:
        rec_table = Table(recommendations_data, colWidths=[doc.width * 0.2, doc.width * 0.8])
        rec_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#374151')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('LEADING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(rec_table)
    
    elements.append(Spacer(1, 12))
    
    # Footer / motto
    elements.append(Paragraph('WE CARE, WE CAN, WE DELIVER', subtitle_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph('Generated by Project Management System', normal_style))
    
    # Build the PDF - OPTIMIZED FOR SINGLE PAGE
    doc.build(elements)
    return pdf_path

@login_required
def comprehensive_system_report(request):
    """
    View for generating and displaying the comprehensive system report
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    if request.method == 'POST':
        try:
            days_filter = int(request.POST.get('days_filter', 30))
            
            # Generate the comprehensive system report
            pdf_path = generate_comprehensive_system_pdf_report(days_filter)
            
            # Send the file as a download
            with open(pdf_path, 'rb') as pdf_file:
                response = HttpResponse(pdf_file.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="ComprehensiveSystemReport_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf"'
                
                # Clean up the temporary file
                try:
                    os.remove(pdf_path)
                except:
                    pass
                    
                return response
                
        except Exception as e:
            messages.error(request, f'Error generating comprehensive system report: {str(e)}')
            return redirect('reports')
    
    # GET request - show the form
    return render(request, 'home/comprehensive_system_report.html', {
        'days_options': [7, 14, 30, 60, 90, 180, 365]
    })

def generate_client_specific_pdf_report(client_id, days_filter=30):
    """
    Generate a client-specific PDF report with comprehensive project and task data
    This function creates a detailed report for one specific client using professional styling
    OPTIMIZED TO FIT ON ONE PAGE
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem, KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String, Circle
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    from io import BytesIO
    from datetime import datetime
    import tempfile
    
    # Get the client and their projects
    client = get_object_or_404(Client, id=client_id)
    client_projects = Project.objects.filter(client_username=client.username)
    
    # Get client-specific data
    total_projects = client_projects.count()
    completed_projects = client_projects.filter(status='completed').count()
    in_progress_projects = client_projects.filter(status='in_progress').count()
    planned_projects = client_projects.filter(status='planned').count()
    
    # Get all tasks for this client's projects
    client_tasks = Task.objects.filter(project__in=client_projects)
    total_tasks = client_tasks.count()
    completed_tasks = client_tasks.filter(status='completed').count()
    in_progress_tasks = client_tasks.filter(status='in_progress').count()
    not_started_tasks = client_tasks.filter(status='not_started').count()
    
    # Task priority counts (needed for analysis table)
    urgent_tasks = client_tasks.filter(priority='urgent').count()
    high_priority_tasks = client_tasks.filter(priority='high').count()
    
    # Get subtasks for this client's projects
    client_subtasks = SubTask.objects.filter(task__project__in=client_projects)
    total_subtasks = client_subtasks.count()
    completed_subtasks = client_subtasks.filter(is_completed=True).count()
    pending_subtasks = total_subtasks - completed_subtasks
    
    # Calculate completion rates
    project_completion_rate = (completed_projects / total_projects * 100) if total_projects > 0 else 0
    task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    subtask_completion_rate = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
    
    # Get recent activity (last 30 days)
    from django.utils import timezone
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days_filter)
    
    recent_projects = client_projects.filter(created_at__gte=start_date).count()
    recent_tasks = client_tasks.filter(created_at__gte=start_date).count()
    
    # Create descriptive temporary file for PDF
    import os, re
    from django.conf import settings
    temp_dir = tempfile.gettempdir()
    safe_client = re.sub(r'[^a-zA-Z0-9_-]+', '_', (client.username or client.email or 'Client')).strip('_')[:40]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    descriptive_filename = f"ClientReport_{safe_client}_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, descriptive_filename)
    
    # Create PDF document with minimal margins to fit everything on one page
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles for professional report with red/white/black theme
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=20,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#dc2626'),  # Red
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=10,
        alignment=1,
        textColor=colors.HexColor('#6b7280'),  # Gray
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=11,
        spaceAfter=6,
        spaceBefore=10,
        textColor=colors.HexColor('#1f2937'),  # Dark gray/black
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=8,
        spaceAfter=3,
        textColor=colors.HexColor('#000000'),  # Black text
        fontName='Helvetica'
    )
    
    # Signature + header (project report design)
    signature_style = ParagraphStyle(
        'CompanySignature',
        parent=styles['Normal'],
        fontSize=16,
        spaceAfter=0,
        alignment=0,
        textColor=colors.HexColor('#dc2626'),
        fontName='Helvetica-Bold'
    )
    # Header: logo on the left, contact info on the right
    try:
        from reportlab.platypus import Image
        logo_path = os.path.join(settings.BASE_DIR, 'home', 'Logo.png')
        if os.path.exists(logo_path):
            left_cell = Image(logo_path, width=120, height=60)
        else:
            left_cell = Paragraph('E-Click', signature_style)
        # Contact info stacked on the right - ensure it starts at the same level as logo
        contact_lines = [
            'Kyla Schutte',
            '(012) 348 3120',
            'kyla@sdj.co.za',
            'Cindy',
            '(012) 348 3120',
            'cindy@sdj.co.za',
        ]
        contact_story = [Paragraph(line, ParagraphStyle('contact', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#111827'), spaceAfter=2)) for line in contact_lines]
        
        # Create a three-column table: logo left, empty middle, contact info right
        header_table = Table([
            [left_cell, '', contact_story]  # Logo left, empty middle, contact info right
        ], colWidths=[doc.width * 0.2, doc.width * 0.6, doc.width * 0.2])
        
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, -18))
    except Exception:
        story.append(Paragraph('E-Click', signature_style))
        story.append(Spacer(1, -18))
    
    # Render the main title in black as requested
    story.append(Paragraph(f'Client Report: {client.username}', ParagraphStyle(
        'ReportTitleBlack', parent=styles['Heading1'], fontSize=20, spaceAfter=-8,
        alignment=1, textColor=colors.HexColor('#111827'), fontName='Helvetica-Bold')))
    story.append(Paragraph(f'Client: {client.username} | {start_date.strftime("%B %d, %Y")} - {end_date.strftime("%B %d, %Y")}', subtitle_style))
    story.append(Spacer(1, -16))
    
    # Gauge chart for overall completion (Power BI-style)
    try:
        total_for_progress = max(1, total_tasks)
        progress_pct = (completed_tasks / total_for_progress) * 100
        # Dimensions
        gauge_width = min(int(doc.width * 0.75), 380)
        radius = int(gauge_width / 2)
        thickness = max(14, int(radius * 0.22))
        drawing_height = radius + 55
        drawing = Drawing(gauge_width, drawing_height)

        center_x = gauge_width / 2
        center_y = radius + 10

        # Background semicircle (light gray ring)
        bg_outer = Wedge(center_x, center_y, radius, 180, 0, fillColor=colors.HexColor('#e5e7eb'), strokeColor=None)
        drawing.add(bg_outer)
        bg_inner = Wedge(center_x, center_y, radius - thickness, 180, 0, fillColor=colors.white, strokeColor=None)
        drawing.add(bg_inner)

        # Progress arc (brand red)
        progress_deg = max(0, min(180, int((progress_pct / 100.0) * 180)))
        if progress_deg > 0:
            prog_outer = Wedge(center_x, center_y, radius, 180, 180 - progress_deg, fillColor=colors.HexColor('#dc2626'), strokeColor=None)
            drawing.add(prog_outer)
            prog_inner = Wedge(center_x, center_y, radius - thickness, 180, 180 - progress_deg, fillColor=colors.white, strokeColor=None)
            drawing.add(prog_inner)

        # Ticks (optional subtle)
        try:
            for i in range(0, 181, 30):
                ang = (180 - i) * 3.14159 / 180.0
                x1 = center_x + (radius - 2) * __import__('math').cos(ang)
                y1 = center_y + (radius - 2) * __import__('math').sin(ang)
                x2 = center_x + (radius - thickness + 4) * __import__('math').cos(ang)
                y2 = center_y + (radius - thickness + 4) * __import__('math').sin(ang)
                drawing.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor('#9ca3af'), strokeWidth=0.6))
        except Exception:
            pass

        # Percentage label in center
        pct_label = String(center_x, center_y - thickness / 2, f"{progress_pct:.1f}%", textAnchor='middle')
        pct_label.fontName = 'Helvetica-Bold'
        pct_label.fontSize = max(11, int(radius * 0.22))
        pct_label.fillColor = colors.HexColor('#111827')
        drawing.add(pct_label)

        # Edge labels 0% and 100%
        left_label = String(10, 14, '0%', textAnchor='start')
        left_label.fontName = 'Helvetica'
        left_label.fontSize = 8
        left_label.fillColor = colors.HexColor('#6b7280')
        drawing.add(left_label)

        right_label = String(gauge_width - 10, 14, '100%', textAnchor='end')
        right_label.fontName = 'Helvetica'
        right_label.fontSize = 8
        right_label.fillColor = colors.HexColor('#6b7280')
        drawing.add(right_label)

        story.append(Paragraph('Overall Task Completion', heading_style))
        # Center the drawing on the page
        story.append(KeepInFrame(doc.width, drawing_height, [drawing], hAlign='CENTER'))
        story.append(Spacer(1, 6))
    except Exception:
        pass
    
    # Executive Summary donut chart (segmented like sample)
    try:
        total_for_progress_es = max(1, total_tasks)
        progress_pct_es = (completed_tasks / total_for_progress_es) * 100
        segments_es = 12
        filled_es = int(round((progress_pct_es / 100.0) * segments_es))
        # Bigger, centered donut
        es = Drawing(doc.width, 170)
        es_pie = Pie()
        # Center pie within available width
        es_pie.width = 140
        es_pie.height = 140
        es_pie.x = (doc.width - es_pie.width) / 2
        es_pie.y = 20
        es_pie.data = [completed_tasks, total_tasks - completed_tasks]
        es_pie.labels = [f'Completed ({completed_tasks})', f'Remaining ({total_tasks - completed_tasks})']
        # Black and white theme with better contrast
        es_pie.slices[0].fillColor = colors.HexColor('#111827')  # Dark for completed
        es_pie.slices[1].fillColor = colors.HexColor('#e5e7eb')  # Light for remaining
        es_pie.slices[0].strokeColor = colors.white
        es_pie.slices[1].strokeColor = colors.white
        es_pie.slices[0].strokeWidth = 1
        es_pie.slices[1].strokeWidth = 1
        es.add(es_pie)
        
        # Add legend
        legend = Legend()
        legend.x = es_pie.x
        legend.y = es_pie.y - 20
        legend.alignment = 'right'
        legend.columnMaximum = 1
        legend.colorNamePairs = [(es_pie.slices[0].fillColor, 'Completed'), 
                                (es_pie.slices[1].fillColor, 'Remaining')]
        legend.fontName = 'Helvetica'
        legend.fontSize = 8
        legend.dxTextSpace = 5
        legend.dy = 5
        legend.dx = 5
        legend.deltay = 5
        legend.boxAnchor = 'w'
        es.add(legend)
        
        # Center hole and percentage
        cx_es = es_pie.x + es_pie.width / 2
        cy_es = es_pie.y + es_pie.height / 2
        es_hole = Circle(cx_es, cy_es, 35, fillColor=colors.white, strokeColor=colors.white)
        es.add(es_hole)
        es_label = String(cx_es, cy_es - 2, f"{progress_pct_es:.1f}%", textAnchor='middle')
        es_label.fontName = 'Helvetica-Bold'
        es_label.fontSize = 16
        es_label.fillColor = colors.HexColor('#111827')
        es.add(es_label)
        story.append(es)
        story.append(Spacer(1, 10))
    except Exception:
        pass
    
    # Executive Summary Section
    story.append(Paragraph('Executive Summary', heading_style))
    insights = [
        f"Total Projects: {total_projects} ({completed_projects} completed, {in_progress_projects} in progress)",
        f"Total Tasks: {total_tasks} ({completed_tasks} completed, {in_progress_tasks} in progress)",
        f"Task Completion Rate: {task_completion_rate:.1f}%",
        f"Recent Activity (last {days_filter} days): {recent_projects} new projects • {recent_tasks} new tasks",
        f"High Priority Tasks: {high_priority_tasks} • Urgent Tasks: {urgent_tasks}",
        f"Subtasks Progress: {completed_subtasks} of {total_subtasks} completed"
    ]
    for insight in insights:
        story.append(Paragraph(insight, normal_style))
    story.append(Spacer(1, 10))

    # Function to add header to each page
    def add_page_header():
        try:
            from reportlab.platypus import Image
            from django.conf import settings
            logo_path = os.path.join(settings.BASE_DIR, 'home', 'Logo.png')
            if os.path.exists(logo_path):
                left_cell = Image(logo_path, width=120, height=60)
            else:
                left_cell = Paragraph('', signature_style)  # Empty text instead of E-Click
            
            contact_lines = [
                'Kyla Schutte',
                '(012) 348 3120',
                'kyla@sdj.co.za',
                'Cindy',
                '(012) 348 3120',
                'cindy@sdj.co.za',
            ]
            contact_story = [Paragraph(line, ParagraphStyle('contact', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#111827'), spaceAfter=2)) for line in contact_lines]
            
            header_table = Table([
                [left_cell, '', contact_story]
            ], colWidths=[doc.width * 0.2, doc.width * 0.6, doc.width * 0.2])
            
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            
            story.append(header_table)
            story.append(Spacer(1, -18))
            
            # Add client report title
            story.append(Paragraph(f'Client Report: {client.username}', ParagraphStyle(
                'ReportTitleBlack', parent=styles['Heading1'], fontSize=20, spaceAfter=-8,
                alignment=1, textColor=colors.HexColor('#111827'), fontName='Helvetica-Bold')))
            story.append(Paragraph(f'Client: {client.username} | {start_date.strftime("%B %d, %Y")} - {end_date.strftime("%B %d, %Y")}', subtitle_style))
            story.append(Spacer(1, -16))
        except Exception:
            story.append(Paragraph('', signature_style))  # Empty text instead of E-Click
            story.append(Spacer(1, -18))
    
    # Task List with pagination
    story.append(Paragraph('Recent Tasks', heading_style))
    
    # Get all client tasks for the date range, ordered by priority and creation date
    all_client_tasks = Task.objects.filter(
        project__client=client,
        created_at__gte=start_date,
        created_at__lte=end_date
    ).order_by('-priority', '-created_at')
    
    if all_client_tasks.exists():
        tasks_per_page = 12  # Reduced for better readability
        total_tasks = all_client_tasks.count()
        
        # Calculate how many pages we'll need
        total_pages = (total_tasks + tasks_per_page - 1) // tasks_per_page
        
        for page_num in range(total_pages):
            start_idx = page_num * tasks_per_page
            end_idx = min(start_idx + tasks_per_page, total_tasks)
            page_tasks = all_client_tasks[start_idx:end_idx]
            
            # Add page header for subsequent pages (not the first page)
            if page_num > 0:
                story.append(PageBreak())
                add_page_header()
                story.append(Paragraph('Recent Tasks (continued)', heading_style))
            
            task_data = [['Task Name', 'Project', 'Due Date', 'Priority', 'Status']]
            
            for task in page_tasks:
                due_date = task.end_date.strftime('%b %d, %Y') if task.end_date else 'Not set'
                priority = task.get_priority_display() if hasattr(task, 'get_priority_display') else task.priority
                status = task.get_status_display()
                task_data.append([
                    task.title[:35] + '...' if len(task.title) > 35 else task.title,
                    task.project.name[:20] + '...' if len(task.project.name) > 20 else task.project.name,
                    due_date,
                    priority,
                    status
                ])
            
            # Adjusted column widths for better content distribution
            task_table = Table(task_data, colWidths=[
                doc.width * 0.35,  # Task name
                doc.width * 0.20,  # Project
                doc.width * 0.15,  # Due date
                doc.width * 0.15,  # Priority
                doc.width * 0.15   # Status
            ])
            
            # Enhanced table styling
            task_table.setStyle(TableStyle([
                # Header styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                
                # Content styling
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                
                # Alignment
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                
                # Grid styling
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffffff')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white])
            ]))
            
            story.append(task_table)
            # Add task count and page info
            page_info = f'Showing {start_idx + 1}-{end_idx} of {total_tasks} tasks'
            story.append(Spacer(1, 8))
            story.append(Paragraph(page_info, ParagraphStyle(
                'PageInfo',
                parent=normal_style,
                textColor=colors.HexColor('#6b7280'),
                alignment=2  # Right alignment
            )))
            story.append(Spacer(1, 12))
    else:
        story.append(Paragraph('No tasks found for this date range.', normal_style))
        story.append(Spacer(1, 12))
    


    
    # Project Details Section
    if client_projects.exists():
        story.append(Paragraph("Project Overview", heading_style))
        
        # Create project details table with enhanced information
        project_details_data = [[
            'Project Name', 'Status', 'Progress', 'Tasks', 'Priority', 'Due Date'
        ]]
        
        for project in client_projects:
            # Calculate project progress
            project_tasks = project.tasks.all()
            total_project_tasks = project_tasks.count()
            completed_project_tasks = project_tasks.filter(status='completed').count()
            progress = f"{(completed_project_tasks / total_project_tasks * 100):.1f}%" if total_project_tasks > 0 else "0%"
            
            # Format due date
            due_date = project.end_date.strftime('%b %d, %Y') if project.end_date else 'Not set'
            
            project_details_data.append([
                project.name[:30] + '...' if len(project.name) > 30 else project.name,
                project.get_status_display(),
                progress,
                f"{completed_project_tasks}/{total_project_tasks}",
                project.get_priority_display(),
                due_date
            ])
        
        # Create and style the project details table
        project_table = Table(project_details_data, colWidths=[
            doc.width * 0.25,  # Project name
            doc.width * 0.15,  # Status
            doc.width * 0.15,  # Progress
            doc.width * 0.15,  # Tasks
            doc.width * 0.15,  # Priority
            doc.width * 0.15   # Due Date
        ])
        
        project_table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            
            # Content styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            
            # Alignment
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 1), (3, -1), 'CENTER'),  # Center align progress and tasks columns
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid styling
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffffff')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white])
        ]))
        
        story.append(project_table)
        story.append(Spacer(1, 12))
        
        # Recent Activity Section
        story.append(Paragraph("Recent Activity", heading_style))
        recent_activities = Activity.objects.filter(
            project__in=client_projects,
            created_at__gte=start_date
        ).order_by('-created_at')[:5]
        
        if recent_activities.exists():
            for activity in recent_activities:
                activity_date = activity.created_at.strftime('%b %d, %Y')
                activity_text = f"{activity_date} - {activity.description}"
                story.append(Paragraph(activity_text, normal_style))
        else:
            story.append(Paragraph("No recent activity in this period.", normal_style))
        
        story.append(Spacer(1, 12))
    
        # Compact recent activity summary
        story.append(Paragraph(f"Projects: {recent_projects} • Tasks: {recent_tasks} (last {days_filter} days)", normal_style))
        story.append(Spacer(1, 8))
    
    # Add footer
    story.append(Paragraph("WE CARE, WE CAN, WE DELIVER", subtitle_style))
    story.append(Paragraph("This report was generated automatically by the Project Management System.", normal_style))
    story.append(Paragraph(f"Report generated on: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}", normal_style))
    
    # Build PDF
    doc.build(story)
    
    return pdf_path

@login_required
def projects_page(request):
    SystemLog.log_navigation(
        user=request.user,
        page_name='Projects Page',
        page_url=request.path,
        request=request
    )
    
    # Try to get cached data first
    cache_key = f'projects_page_{request.user.id}_{request.user.is_staff}'
    cached_context = cache.get(cache_key)
    
    if cached_context and not request.GET.get('refresh'):
        return render(request, 'home/projects_page.html', cached_context)
    
    try:
        profile = request.user.profile
        can_create_projects = profile.can_create_projects or request.user.is_staff
        can_edit_projects = profile.can_edit_projects or request.user.is_staff
        can_delete_projects = profile.can_delete_projects or request.user.is_staff
    except UserProfile.DoesNotExist:
        can_create_projects = request.user.is_staff
        can_edit_projects = request.user.is_staff
        can_delete_projects = request.user.is_staff
    
    # Optimize database queries with select_related and prefetch_related
    if request.user.is_staff:
        # For staff users, load all projects but with optimization
        projects = Project.objects.select_related(
            'created_by', 'client'
        ).prefetch_related(
            'assigned_users', 'tasks'
        ).order_by('-created_at')
        
        # Limit users to active ones only for better performance
        all_users = User.objects.filter(is_active=True).order_by('username')
        existing_clients = Client.objects.filter(is_active=True).order_by('username')
    else:
        # For regular users, only load their assigned projects
        projects = Project.objects.filter(assigned_users=request.user).select_related(
            'created_by', 'client'
        ).prefetch_related(
            'assigned_users', 'tasks'
        ).order_by('-created_at')
        
        all_users = User.objects.filter(id=request.user.id)
        existing_clients = Client.objects.filter(is_active=True).order_by('username')
    
    # Prepare context
    context = {
        'projects': projects,
        'all_users': all_users,
        'existing_clients': existing_clients,
        'can_create_projects': can_create_projects,
        'can_edit_projects': can_edit_projects,
        'can_delete_projects': can_delete_projects,
    }
    
    # Cache the context for 5 minutes to improve performance
    cache.set(cache_key, context, 300)
    
    return render(request, 'home/projects_page.html', context)

@login_required
def get_project_users(request, project_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    try:
        project = Project.objects.get(id=project_id)
        assigned_users = list(project.assigned_users.values_list('id', flat=True))
        return JsonResponse({'assigned_users': assigned_users})
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)

@login_required
def assign_users_to_project(request, project_id):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('projects_page')
    try:
        project = Project.objects.get(id=project_id)
        if request.method == 'POST':
            assigned_user_ids = request.POST.getlist('assigned_users')
            project.assigned_users.clear()
            if assigned_user_ids:
                users = User.objects.filter(id__in=assigned_user_ids)
                project.assigned_users.add(*users)
                SystemLog.log_project_assigned(request.user, project, users, request)
                messages.success(request, f'Successfully assigned {users.count()} user(s) to project "{project.name}"')
            else:
                messages.info(request, f'No users assigned to project "{project.name}"')
        return redirect('projects_page')
    except Project.DoesNotExist:
        messages.error(request, 'Project not found.')
        return redirect('projects_page')
    except Exception as e:
        messages.error(request, f'Error assigning users: {str(e)}')
        return redirect('projects_page')

@require_admin_access
def admin_control(request):
    
    from django.db.models import Count, Q
    from django.utils import timezone
    from datetime import datetime, timedelta
    import json
    import os
    import shutil
    
    # Get system statistics
    total_users = User.objects.count()
    total_clients = Client.objects.count()
    total_projects = Project.objects.count()
    total_tasks = Task.objects.count()
    total_subtasks = SubTask.objects.count()
    
    # User statistics
    active_users = User.objects.filter(is_active=True).count()
    inactive_users = User.objects.filter(is_active=False).count()
    admin_users = User.objects.filter(is_staff=True).count()
    
    # Client statistics
    active_clients = Client.objects.filter(is_active=True).count()
    inactive_clients = Client.objects.filter(is_active=False).count()
    
    # Project statistics
    projects_in_progress = Project.objects.filter(status='in_progress').count()
    projects_completed = Project.objects.filter(status='completed').count()
    projects_planned = Project.objects.filter(status='planned').count()
    
    # Task statistics
    completed_tasks = Task.objects.filter(status='completed').count()
    in_progress_tasks = Task.objects.filter(status='in_progress').count()
    not_started_tasks = Task.objects.filter(status='not_started').count()
    
    # Recent activity
    recent_users = User.objects.order_by('-date_joined')[:5]
    for user in recent_users:
        profile, created = UserProfile.objects.get_or_create(user=user)
        user.profile_picture_url = profile.get_profile_picture_url()
    recent_projects = Project.objects.order_by('-created_at')[:5]
    
    # Handle admin actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_user':
            # Handle adding new user
            username = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            role = request.POST.get('role', 'user')
            
            # Validation
            if not all([username, first_name, last_name, email]):
                messages.error(request, 'All required fields must be filled.')
            elif User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" already exists.')
            elif User.objects.filter(email=email).exists():
                messages.error(request, f'Email "{email}" already exists.')
            else:
                try:
                    # Create new user with a temporary password (will be changed via OTP)
                    import string
                    temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
                    
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=temp_password,
                        first_name=first_name,
                        last_name=last_name
                    )
                    
                    # Set role permissions
                    if role == 'admin':
                        user.is_staff = True
                        user.is_superuser = True
                    else:  # role == 'user'
                        user.is_staff = False
                        user.is_superuser = False
                    
                    user.save()
                    
                    # Create user profile with proper defaults
                    profile = UserProfile.objects.create(
                        user=user,
                        phone=phone if phone else '',
                        # Set default permissions based on role
                        can_access_dashboard=True,
                        can_access_projects=True,
                        can_access_reports=True,
                        can_access_analytics=True,
                        can_access_admin=(role == 'admin'),
                        can_manage_users=(role == 'admin'),
                        can_manage_clients=(role == 'admin')
                    )
                    
                    # Generate OTP for the new user
                    from .models import generate_user_otp
                    otp = generate_user_otp(user)
                    
                    # Send OTP email using Gmail API
                    site_url = "http://127.0.0.1:8000"
                    gmail_service = GoogleCloudEmailService()
                    email_result = gmail_service.send_email(
                        to_email=email,
                        subject="Set Your Password - Welcome to E-Click",
                        body=f"""
                        Dear {username},

                        Welcome to E-Click! Please use the following OTP to set your password:

                        🔐 Your OTP: {otp}

                        Please visit: {site_url}/user-setup-password/

                        Best regards,
                        E-Click Team
                        """,
                        from_email=None  # Will use OAuth2 account email
                    )
                    
                    if email_result['success']:
                        messages.success(request, f'User "{username}" created successfully with {role} role. OTP sent to {email} for password setup.')
                    else:
                        messages.warning(request, f'User "{username}" created successfully with {role} role, but OTP email failed: {email_result["error"]}')
                        
                except Exception as e:
                    messages.error(request, f'Error creating user: {str(e)}')
                    # Clean up if user was created but profile creation failed
                    if user and user.id:
                        user.delete()
        
        elif action == 'toggle_user_access':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            # Prevent admin from disabling themselves
            if user == request.user:
                messages.error(request, 'You cannot disable your own account.')
                return redirect('admin_control')
            else:
                user.is_active = not user.is_active
                user.save()
                status = 'enabled' if user.is_active else 'disabled'
                messages.success(request, f'User {user.username} has been {status}.')
                return redirect('admin_control')
        
        elif action == 'toggle_admin_status':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            # Prevent admin from removing their own admin privileges
            if user == request.user:
                messages.error(request, 'You cannot remove your own admin privileges.')
                return redirect('admin_control')
            else:
                user.is_staff = not user.is_staff
                user.save()
                status = 'granted admin privileges' if user.is_staff else 'removed admin privileges'
                messages.success(request, f'User {user.username} has been {status}.')
                return redirect('admin_control')
        
        elif action == 'delete_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            # Prevent admin from deleting themselves
            if user == request.user:
                messages.error(request, 'You cannot delete your own account.')
                return redirect('admin_control')
            else:
                username = user.username
                user.delete()
                messages.success(request, f'User {username} has been deleted.')
                return redirect('admin_control')
        
        elif action == 'suspend_user':
            user_id = request.POST.get('user_id')
            suspension_days = int(request.POST.get('suspension_days', 1))
            suspension_reason = request.POST.get('suspension_reason', 'Account suspended by administrator')
            
            user = get_object_or_404(User, id=user_id)
            
            # Prevent admin from suspending themselves
            if user == request.user:
                messages.error(request, 'You cannot suspend your own account.')
                return redirect('admin_control')
            else:
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.is_suspended = True
                profile.suspension_reason = suspension_reason
                profile.suspension_until = timezone.now() + timedelta(days=suspension_days)
                profile.save()
                
                messages.success(request, f'User {user.username} has been suspended for {suspension_days} day(s).')
                return redirect('admin_control')
        
        elif action == 'unsuspend_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.is_suspended = False
            profile.suspension_reason = ''
            profile.suspension_until = None
            profile.save()
            
            messages.success(request, f'User {user.username} has been unsuspended.')
            return redirect('admin_control')
        
        elif action == 'lock_user_account':
            user_id = request.POST.get('user_id')
            lock_hours = int(request.POST.get('lock_hours', 1))
            
            user = get_object_or_404(User, id=user_id)
            
            # Prevent admin from locking themselves
            if user == request.user:
                messages.error(request, 'You cannot lock your own account.')
                return redirect('admin_control')
            else:
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.account_locked_until = timezone.now() + timedelta(hours=lock_hours)
                profile.save()
                
                messages.success(request, f'User {user.username} account has been locked for {lock_hours} hour(s).')
                return redirect('admin_control')
        
        elif action == 'unlock_user_account':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.account_locked_until = None
            profile.current_login_attempts = 0
            profile.save()
            
            messages.success(request, f'User {user.username} account has been unlocked.')
            return redirect('admin_control')
        
        elif action == 'update_user_permissions':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            # Update user permissions
            user.is_active = request.POST.get('is_active') == 'on'
            user.is_staff = request.POST.get('is_staff') == 'on'
            user.is_superuser = request.POST.get('is_superuser') == 'on'
            
            # Update custom permissions
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.can_access_dashboard = request.POST.get('can_access_dashboard') == 'on'
            profile.can_access_projects = request.POST.get('can_access_projects') == 'on'
            profile.can_access_reports = request.POST.get('can_access_reports') == 'on'
            profile.can_access_analytics = request.POST.get('can_access_analytics') == 'on'
            profile.can_access_admin = request.POST.get('can_access_admin') == 'on'
            profile.can_manage_users = request.POST.get('can_manage_users') == 'on'
            profile.can_manage_clients = request.POST.get('can_manage_clients') == 'on'
            profile.save()
            
            user.save()
            messages.success(request, f'Permissions updated for {user.username}.')
            return redirect('admin_control')
        
        elif action == 'edit_user_profile':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            # Update user basic info
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = request.POST.get('email', '')
            user.save()
            
            # Update profile
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.phone = request.POST.get('phone', '')
            profile.address = request.POST.get('address', '')
            profile.bio = request.POST.get('bio', '')
            
            if 'profile_picture' in request.FILES:
                profile.profile_picture = request.FILES['profile_picture']
            
            profile.save()
            messages.success(request, f'Profile updated for {user.username}.')
            return redirect('admin_control')
        
        elif action == 'reset_user_password':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            # Generate and send OTP for password reset
            try:
                # Ensure UserOTP is available
                from .models import UserOTP
                
                print(f"DEBUG: Starting password reset OTP process for user {user.username}")
                
                # Generate 6-digit OTP
                otp = ''.join(random.choices('0123456789', k=6))
                print(f"DEBUG: Generated OTP: {otp}")
                
                # Mark all existing OTPs for this user as used
                UserOTP.objects.filter(user=user).update(is_used=True)
                
                # Create new OTP record
                otp_obj = UserOTP.objects.create(
                    user=user,
                    otp=otp,
                    is_used=False,
                    expires_at=timezone.now() + timedelta(minutes=10)
                )
                
                print(f"DEBUG: OTP record created for user {user.username}")
                print(f"DEBUG: User email: {user.email}")
                
                # Send OTP email using Gmail API
                print(f"DEBUG: About to send email to {user.email}")
                # Get the current site URL for the reset link
                site_url = request.build_absolute_uri('/').rstrip('/')
                gmail_service = GoogleCloudEmailService()
                email_result = gmail_service.send_email(
                    to_email=user.email,
                    subject="Password Reset OTP - E-Click",
                    body=f"""
                    Dear {user.username},

                    You have requested a password reset. Please use the following OTP:

                    🔐 Your OTP: {otp}

                    This OTP will expire in 10 minutes.

                    Best regards,
                    E-Click Team
                    """,
                    from_email=None  # Will use OAuth2 account email
                )
                print(f"DEBUG: Email result: {email_result}")
                
                if not email_result['success']:
                    print(f"DEBUG: Email failed with error: {email_result['error']}")
                    messages.error(request, f'Failed to send OTP email: {email_result["error"]}')
                    return render(request, 'home/admin_control_enhanced.html')
                
                print(f"DEBUG: Email sent successfully")
                messages.success(request, f'Password reset OTP sent to {user.email}. User will receive an email with instructions.')
                return redirect('admin_control')
                
            except Exception as e:
                print(f"DEBUG: Exception occurred: {str(e)}")
                print(f"DEBUG: Exception type: {type(e)}")
                import traceback
                traceback.print_exc()
                messages.error(request, f'Failed to send password reset OTP: {str(e)}')
                return redirect('admin_control')
        
        elif action == 'toggle_client_access':
            client_id = request.POST.get('client_id')
            client = get_object_or_404(Client, id=client_id)
            
            client.is_active = not client.is_active
            client.save()
            status = 'enabled' if client.is_active else 'disabled'
            messages.success(request, f'Client {client.username} has been {status}.')
            return redirect('admin_control')
        
        elif action == 'delete_client':
            client_id = request.POST.get('client_id')
            client = get_object_or_404(Client, id=client_id)
            
            username = client.username
            client.delete()
            messages.success(request, f'Client {username} has been deleted.')
            return redirect('admin_control')
        
        elif action == 'edit_user':
            user_id = request.POST.get('user_id')
            if not user_id:
                messages.error(request, 'User ID is required for editing.')
                return redirect('admin_control')
                
            try:
                user = get_object_or_404(User, id=user_id)
            except (ValueError, User.DoesNotExist):
                messages.error(request, 'Invalid user ID provided.')
                return redirect('admin_control')
            
            # Prevent admin from editing themselves
            if user == request.user:
                messages.error(request, 'You cannot edit your own account through this interface.')
                return redirect('admin_control')
            
            try:
                # Update user basic info
                user.username = request.POST.get('username', '').strip()
                user.first_name = request.POST.get('first_name', '').strip()
                user.last_name = request.POST.get('last_name', '').strip()
                user.email = request.POST.get('email', '').strip()
                
                # Check if username is already taken by another user
                if User.objects.exclude(id=user.id).filter(username=user.username).exists():
                    messages.error(request, f'Username "{user.username}" is already taken by another user.')
                    return redirect('admin_control')
                
                # Check if email is already taken by another user
                if User.objects.exclude(id=user.id).filter(email=user.email).exists():
                    messages.error(request, f'Email "{user.email}" is already taken by another user.')
                    return redirect('admin_control')
                
                # Update role permissions
                role = request.POST.get('role', 'user')
                if role == 'admin':
                    user.is_staff = True
                    user.is_superuser = True
                else:
                    user.is_staff = False
                    user.is_superuser = False
                
                # Update active status
                user.is_active = request.POST.get('is_active') == 'true'
                
                user.save()
                
                # Update user profile
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.phone = request.POST.get('phone', '')
                
                # Update permissions - handle unchecked checkboxes properly
                # Checkboxes only send 'on' when checked, so we check if the key exists
                profile.can_access_dashboard = 'can_access_dashboard' in request.POST
                profile.can_access_projects = 'can_access_projects' in request.POST
                profile.can_access_reports = 'can_access_reports' in request.POST
                profile.can_access_analytics = 'can_access_analytics' in request.POST
                profile.can_access_admin = 'can_access_admin' in request.POST
                profile.can_manage_users = 'can_manage_users' in request.POST
                profile.can_manage_clients = 'can_manage_clients' in request.POST
                
                # Handle the new system logs permission
                if hasattr(profile, 'can_access_system_logs'):
                    profile.can_access_system_logs = 'can_access_system_logs' in request.POST
                
                profile.save()
                
                messages.success(request, f'User "{user.username}" has been updated successfully.')
                return redirect('admin_control')
                
            except Exception as e:
                messages.error(request, f'Error updating user: {str(e)}')
                return redirect('admin_control')
        
        return redirect('admin_control')
    
    # Get all users with their profiles
    users = User.objects.all().order_by('-date_joined')
    user_profiles = {}
    for user in users:
        profile, created = UserProfile.objects.get_or_create(user=user)
        user_profiles[user.id] = profile
        # Add profile picture URL directly to user object for template access
        user.profile_picture_url = profile.get_profile_picture_url()
    
    # Get suspended and locked users
    suspended_users = UserProfile.objects.filter(is_suspended=True).select_related('user')
    locked_accounts = UserProfile.objects.filter(
        Q(account_locked_until__isnull=False) & 
        Q(account_locked_until__gt=timezone.now())
    ).select_related('user')
    
    # Get all clients
    clients = Client.objects.all().order_by('-created_at')
    
    # User Activity Summary (moved from reports)
    user_activity = []
    for user in users:
        projects_assigned = Project.objects.filter(assigned_users=user).count()
        user_activity.append({
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
            'last_login': user.last_login,
            'projects_created': projects_assigned,
        })
    
    # Sort by projects assigned (most active first)
    user_activity.sort(key=lambda x: x['projects_created'], reverse=True)
    
    # System information (simplified without psutil)
    system_info = {
        'cpu_percent': 45,  # Placeholder - would be real in production
        'memory_percent': 62,  # Placeholder - would be real in production
        'disk_usage': 78,  # Placeholder - would be real in production
    }
    
    # Database size
    try:
        db_path = os.path.join(django_settings.BASE_DIR, 'db.sqlite3')
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path) / (1024 * 1024)  # MB
        else:
            db_size = 0.0
    except (OSError, IOError):
        db_size = 0.0
    
    context = {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_projects': total_projects,
        'total_tasks': total_tasks,
        'total_subtasks': total_subtasks,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'admin_users': admin_users,
        'active_clients': active_clients,
        'inactive_clients': inactive_clients,
        'projects_in_progress': projects_in_progress,
        'projects_completed': projects_completed,
        'projects_planned': projects_planned,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'not_started_tasks': not_started_tasks,
        'recent_users': recent_users,
        'recent_projects': recent_projects,
        'users': users,
        'user_profiles': user_profiles,
        'clients': clients,
        'user_activity': user_activity,
        'system_info': system_info,
        'db_size': round(db_size, 2),
        'current_admin': request.user,
        'suspended_users': suspended_users,
        'locked_accounts': locked_accounts,
        'suspended_users_count': suspended_users.count(),
        'locked_accounts_count': locked_accounts.count(),
    }
    
    return render(request, 'home/admin_control_enhanced.html', context)

@login_required
def admin_user_details(request, user_id):
    """API endpoint to get user details for admin control"""
    print(f"DEBUG: admin_user_details called with user_id: {user_id}")
    print(f"DEBUG: request.user: {request.user}")
    print(f"DEBUG: request.user.is_staff: {request.user.is_staff}")
    print(f"DEBUG: request.method: {request.method}")
    print(f"DEBUG: request.path: {request.path}")
    
    if not request.user.is_staff:
        print("DEBUG: Access denied - user is not staff")
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        print(f"DEBUG: Looking for user with ID: {user_id}")
        user = User.objects.get(id=user_id)
        print(f"DEBUG: Found user: {user.username}")
        
        profile, created = UserProfile.objects.get_or_create(user=user)
        print(f"DEBUG: Profile created: {created}, Profile: {profile}")
        
        data = {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_active': user.is_active,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M:%S') if user.date_joined else None,
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None,
            'phone': profile.phone,
            'address': profile.address,
            'bio': profile.bio,
            'role': 'Admin' if user.is_staff else 'User',
            'can_access_dashboard': profile.can_access_dashboard,
            'can_access_projects': profile.can_access_projects,
            'can_access_reports': profile.can_access_reports,
            'can_access_analytics': profile.can_access_analytics,
            'can_access_admin': profile.can_access_admin,
            'can_manage_users': profile.can_manage_users,
            'can_manage_clients': profile.can_manage_clients,
            'can_access_system_logs': getattr(profile, 'can_access_system_logs', False),
        }
        
        print(f"DEBUG: Returning data: {data}")
        return JsonResponse(data)
    except User.DoesNotExist:
        print(f"DEBUG: User with ID {user_id} not found")
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        print(f"DEBUG: Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)

@login_required
def admin_user_permissions(request, user_id):
    """API endpoint to get user permissions for admin control"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        user = User.objects.get(id=user_id)
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        data = {
            'id': user.id,
            'username': user.username,
            'is_active': user.is_active,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'can_access_dashboard': profile.can_access_dashboard,
            'can_access_projects': profile.can_access_projects,
            'can_access_reports': profile.can_access_reports,
            'can_access_analytics': profile.can_access_analytics,
            'can_access_admin': profile.can_access_admin,
            'can_manage_users': profile.can_manage_users,
            'can_manage_clients': profile.can_manage_clients,
        }
        
        return JsonResponse(data)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

@login_required
def project_details(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    
    # Check if user is assigned to this project or is staff
    if not request.user.is_staff and request.user not in project.assigned_users.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    return JsonResponse({
        'id': project.id,
        'name': project.name,
        'client': project.client,
        'client_email': project.client_email,
        'duration': "Not set",  # Duration calculation removed due to computed properties
        'status': project.status,
        'status_display': project.get_status_display(),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
    })

@login_required
def project_tasks(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    
    # Check if user is assigned to this project or is staff
    if not request.user.is_staff and request.user not in project.assigned_users.all():
        messages.error(request, 'You are not assigned to this project.')
        return redirect('projects_page')
    
    tasks = project.tasks.all().order_by('start_date')
    
    # Calculate project progress
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='completed').count()
    progress_percentage = 0
    if total_tasks > 0:
        progress_percentage = (completed_tasks / total_tasks) * 100
    
    context = {
        'project': project,
        'tasks': tasks,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'progress_percentage': progress_percentage,
        'is_assigned_user': request.user in project.assigned_users.all(),
        'is_staff': request.user.is_staff,
    }
    
    return render(request, 'home/project_tasks.html', context)

@login_required
def add_task(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        try:
            project_id = request.POST.get('project_id')
            project = get_object_or_404(Project, id=project_id)
            
            # Get assigned users if specified
            assigned_user_ids = request.POST.getlist('assigned_users')
            
            # Get dates
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            # Convert empty strings to None for dates
            if start_date == '':
                start_date = None
            if end_date == '':
                end_date = None
            
            task = Task.objects.create(
                project=project,
                title=request.POST.get('title'),
                description=request.POST.get('description', ''),
                status=request.POST.get('status', 'not_started'),
                priority=request.POST.get('priority', 'medium'),
                development_status=request.POST.get('development_status', 'original_quoted'),
                start_date=start_date,
                end_date=end_date
            )
            
            # Add assigned users after creating the task
            if assigned_user_ids:
                users = User.objects.filter(id__in=assigned_user_ids)
                task.assigned_users.add(*users)
            
            return JsonResponse({'success': True, 'task_id': task.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def add_subtask(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        try:
            task_id = request.POST.get('task_id')
            task = get_object_or_404(Task, id=task_id)
            
            subtask = SubTask.objects.create(
                task=task,
                title=request.POST.get('title'),
                description=request.POST.get('description', ''),
                status=request.POST.get('status', 'not_started')
            )
            
            # Handle dates
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            if start_date:
                subtask.start_date = start_date
            if end_date:
                subtask.end_date = end_date
            subtask.save()
            
            return JsonResponse({'success': True, 'subtask_id': subtask.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def toggle_subtask(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            subtask_id = data.get('subtask_id')
            is_completed = data.get('is_completed')
            
            subtask = get_object_or_404(SubTask, id=subtask_id)
            subtask.is_completed = is_completed
            subtask.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def delete_task(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')
            
            task = get_object_or_404(Task, id=task_id)
            task.delete()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})
def delete_subtask(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            subtask_id = data.get('subtask_id')
            
            subtask = get_object_or_404(SubTask, id=subtask_id)
            subtask.delete()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def dashboard_gantt_data(request):
    print("\n🚀 === DASHBOARD GANTT DATA FUNCTION CALLED ===")
    print(f"👤 User: {request.user.username}")
    print(f"🔑 Is staff: {request.user.is_staff}")
    print(f"⏰ Timestamp: {timezone.now()}")
    print("=== FUNCTION START ===\n")
    
    try:
        # Get projects based on user role
        if request.user.is_staff:
            # Admin users can see all projects
            projects = Project.objects.all().order_by('-created_at')
        else:
            # Regular users can only see projects they are assigned to
            projects = Project.objects.filter(assigned_users=request.user).order_by('-created_at')
        
        print("🚀 === DASHBOARD GANTT DATA FUNCTION STARTED ===")
        print(f"📊 Total projects found: {projects.count()}")
        
        projects_data = []
        for project in projects:
            print(f"\n🔍 === PROCESSING PROJECT: {project.name} ===")
            print(f"   Project ID: {project.id}")
            print(f"   Project status: {project.status}")
            print(f"   Total tasks: {project.tasks.count()}")
            
            # Get project-level values from tasks (since Project model doesn't have these fields)
            project_priority = 'medium'  # default
            project_development_status = 'original_quoted'  # default
            
            # Get the most common priority and development status from project tasks
            if project.tasks.exists():
                print(f"   📋 Tasks exist, analyzing priority and development status...")
                
                # Get priority from tasks
                priority_counts = {}
                dev_status_counts = {}
                
                for task in project.tasks.all():
                    print(f"      🔍 Task: {task.title}")
                    print(f"         - Task priority: {getattr(task, 'priority', 'NOT_FOUND')}")
                    print(f"         - Task development_status: {getattr(task, 'development_status', 'NOT_FOUND')}")
                    
                    if hasattr(task, 'priority') and task.priority:
                        priority_counts[task.priority] = priority_counts.get(task.priority, 0) + 1
                        print(f"         ✅ Priority '{task.priority}' added to counts")
                    if hasattr(task, 'development_status') and task.development_status:
                        dev_status_counts[task.development_status] = dev_status_counts.get(task.development_status, 0) + 1
                        print(f"         ✅ Development status '{task.development_status}' added to counts")
                
                print(f"   📊 Priority counts: {priority_counts}")
                print(f"   📊 Development status counts: {dev_status_counts}")
                
                # Use most common values, or defaults if none found
                if priority_counts:
                    project_priority = max(priority_counts, key=priority_counts.get)
                    print(f"   🎯 Selected priority: {project_priority}")
                if dev_status_counts:
                    project_development_status = max(dev_status_counts, key=dev_status_counts.get)
                    print(f"   🎯 Selected development status: {project_development_status}")
            else:
                print(f"   ❌ No tasks found, using defaults")
            
            print(f"   🏁 Final project values:")
            print(f"      - Priority: {project_priority}")
            print(f"      - Development Status: {project_development_status}")
            print(f"   === END PROJECT PROCESSING ===\n")
            
            # Calculate progress based on tasks
            total_tasks = project.tasks.count()
            completed_tasks = project.tasks.filter(status='completed').count()
            progress = 0
            if total_tasks > 0:
                progress = (completed_tasks / total_tasks) * 100
            
            # Get project timeline from task dates
            tasks = project.tasks.all()
            if tasks.exists():
                # Get tasks with valid dates
                tasks_with_dates = [task for task in tasks if task.start_date and task.end_date]
                
                if tasks_with_dates:
                    # Calculate project start and end dates from task dates
                    earliest_start = min(task.start_date for task in tasks_with_dates)
                    latest_end = max(task.end_date for task in tasks_with_dates)
                    
                    start_date = earliest_start
                    end_date = latest_end
                    
                    # Update project dates if they're not set
                    if not project.start_date or not project.end_date:
                        project.start_date = start_date
                        project.end_date = end_date
                        project.save()
                else:
                    # Tasks exist but don't have dates, use project dates or defaults
                    start_date = project.start_date or timezone.now().date()
                    end_date = project.end_date or (start_date + timedelta(days=7))
            else:
                # No tasks, use project dates or defaults
                start_date = project.start_date or timezone.now().date()
                end_date = project.end_date or (start_date + timedelta(days=7))
            
            current_date = timezone.now().date()
            
            # Calculate timeline position
            total_days = (end_date - start_date).days
            elapsed_days = (current_date - start_date).days
            timeline_position = min(max((elapsed_days / total_days) * 100, 0), 100) if total_days > 0 else 0
            
            # Get tasks with their timeline data
            tasks_data = []
            for task in tasks.order_by('start_date', 'created_at'):
                if task.start_date and task.end_date:
                    # Calculate task position and width
                    task_start_offset = (task.start_date - start_date).days
                    task_duration = (task.end_date - task.start_date).days + 1
                    
                    task_data = {
                        'id': task.id,
                        'title': task.title,
                        'description': task.description,
                        'status': task.status,
                        'priority': getattr(task, 'priority', 'medium'),
                        'development_status': getattr(task, 'development_status', 'original_quoted'),
                        'start_date': task.start_date.isoformat(),
                        'end_date': task.end_date.isoformat(),
                        'start_offset': task_start_offset,
                        'duration': task_duration,
                        'subtasks': [
                            {
                                'id': subtask.id,
                                'title': subtask.title,
                                'is_completed': subtask.is_completed,
                                'start_date': subtask.start_date.isoformat() if subtask.start_date else None,
                                'end_date': subtask.end_date.isoformat() if subtask.end_date else None
                            } for subtask in task.subtasks.all().order_by('created_at')
                        ]
                    }
                    tasks_data.append(task_data)
                else:
                    # Include tasks without dates but mark them as not positioned
                    task_data = {
                        'id': task.id,
                        'title': task.title,
                        'description': task.description,
                        'status': task.status,
                        'priority': getattr(task, 'priority', 'medium'),
                        'development_status': getattr(task, 'development_status', 'original_quoted'),
                        'start_date': None,
                        'end_date': None,
                        'start_offset': 0,
                        'duration': 1,
                        'subtasks': [
                            {
                                'id': subtask.id,
                                'title': subtask.title,
                                'is_completed': subtask.is_completed,
                                'start_date': subtask.start_date.isoformat() if subtask.start_date else None,
                                'end_date': subtask.end_date.isoformat() if subtask.end_date else None
                            } for subtask in task.subtasks.all().order_by('created_at')
                        ]
                    }
                    tasks_data.append(task_data)
            
            # Calculate project duration in days
            project_duration = (end_date - start_date).days + 1
            
            projects_data.append({
                'id': project.id,
                'name': project.name,
                'client': project.client,
                'status': project.status,
                'status_display': project.get_status_display(),
                'priority': project_priority,
                'development_status': project_development_status,
                'progress': progress,
                'created_at': project.created_at.isoformat(),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'duration_days': project_duration,
                'timeline_position': timeline_position,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'tasks': tasks_data
            })
        
        # Generate real activity data based on actual database records
        activities = []
        
        # Recent project creations
        recent_projects = Project.objects.all().order_by('-created_at')[:3]
        for project in recent_projects:
            time_diff = timezone.now() - project.created_at
            if time_diff.days == 0:
                time_str = f"{time_diff.seconds // 3600} hours ago"
            elif time_diff.days == 1:
                time_str = "1 day ago"
            else:
                time_str = f"{time_diff.days} days ago"
            
            activities.append({
                'type': 'project_created',
                'title': f'New project "{project.name}" created',
                'time': time_str,
                'status': 'Completed',
                'project_id': project.id
            })
        
        # Recent task completions
        recent_tasks = Task.objects.filter(status='completed').order_by('-updated_at')[:3]
        for task in recent_tasks:
            time_diff = timezone.now() - task.updated_at
            if time_diff.days == 0:
                time_str = f"{time_diff.seconds // 3600} hours ago"
            elif time_diff.days == 1:
                time_str = "1 day ago"
            else:
                time_str = f"{time_diff.days} days ago"
            
            activities.append({
                'type': 'task_completed',
                'title': f'Task "{task.title}" completed in {task.project.name}',
                'time': time_str,
                'status': 'Completed',
                'project_id': task.project.id
            })
        
        # Recent task updates
        recent_updates = Task.objects.exclude(status='completed').order_by('-updated_at')[:2]
        for task in recent_updates:
            time_diff = timezone.now() - task.updated_at
            if time_diff.days == 0:
                time_str = f"{time_diff.seconds // 3600} hours ago"
            elif time_diff.days == 1:
                time_str = "1 day ago"
            else:
                time_str = f"{time_diff.days} days ago"
            
            activities.append({
                'type': 'task_updated',
                'title': f'Task "{task.title}" updated in {task.project.name}',
                'time': time_str,
                'status': task.get_status_display(),
                'project_id': task.project.id
            })
        
        # Calculate summary statistics
        total_projects = len(projects_data)
        on_track_projects = len([p for p in projects_data if p['timeline_position'] <= 100])
        overall_progress = sum([p['progress'] for p in projects_data]) / total_projects if total_projects > 0 else 0
        
        # Calculate additional statistics for dashboard stats
        total_tasks = sum([p['total_tasks'] for p in projects_data])
        completed_tasks = sum([p['completed_tasks'] for p in projects_data])
        active_projects = len([p for p in projects_data if p['status'] == 'in_progress'])
        pending_tasks = total_tasks - completed_tasks
        
        # Calculate completed tasks this week
        week_ago = timezone.now() - timedelta(days=7)
        completed_this_week = Task.objects.filter(
            status='completed',
            updated_at__gte=week_ago
        ).count()
        
        # Calculate percentages
        active_percentage = (active_projects / total_projects * 100) if total_projects > 0 else 0
        pending_percentage = (pending_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Debug final response data
        print("\n🎯 === FINAL RESPONSE DEBUG ===")
        print(f"📊 Total projects in response: {len(projects_data)}")
        for i, project in enumerate(projects_data):
            print(f"\n📋 Project {i+1} in response:")
            print(f"   - Name: {project.get('name', 'NO_NAME')}")
            print(f"   - Development status: {project.get('development_status', 'NO_DEV_STATUS')}")
            print(f"   - Priority: {project.get('priority', 'NO_PRIORITY')}")
            print(f"   - Tasks count: {project.get('total_tasks', 0)}")
            print(f"   - Status: {project.get('status', 'NO_STATUS')}")
            print(f"   - Progress: {project.get('progress', 0)}%")
        print("=== END FINAL RESPONSE DEBUG ===\n")
        
        return JsonResponse({
            'success': True,
            'projects': projects_data,
            'activities': activities,
            'summary': {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'active_percentage': round(active_percentage, 1),
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'completed_this_week': completed_this_week,
                'pending_tasks': pending_tasks,
                'pending_percentage': round(pending_percentage, 1),
                'on_track_projects': on_track_projects,
                'overall_progress': round(overall_progress, 1)
            }
        })
    except Exception as e:
        print(f"Error in dashboard_gantt_data: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to load timeline data',
            'projects': [],
            'activities': [],
            'summary': {
                'total_projects': 0,
                'on_track_projects': 0,
                'overall_progress': 0
            }
        }, status=500)

@login_required
def send_report(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    # Log navigation to send report page
    SystemLog.log_navigation(
        user=request.user,
        page_name='Send Report',
        page_url=request.path,
        request=request
    )
    
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    from .services import GoogleCloudEmailService
    import json
    
    if request.method == 'POST':
        # Get form data
        recipient_email = request.POST.get('recipient_email')
        date_range = request.POST.get('date_range', '30')
        custom_message = request.POST.get('custom_message', '')
        
        # Validate required fields
        if not recipient_email:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Recipient email is required.'})
            else:
                messages.error(request, 'Recipient email is required.')
                return redirect('send_report')
        
        try:
            date_range = int(date_range)
        except ValueError:
            date_range = 30
        
        end_date = timezone.now()
        start_date = end_date - timedelta(days=date_range)
        
        # Generate report data (same as reports view)
        total_projects = Project.objects.count()
        projects_in_progress = Project.objects.filter(status='in_progress').count()
        projects_completed = Project.objects.filter(status='completed').count()
        projects_planned = Project.objects.filter(status='planned').count()
        
        total_tasks = Task.objects.count()
        completed_tasks = Task.objects.filter(status='completed').count()
        in_progress_tasks = Task.objects.filter(status='in_progress').count()
        not_started_tasks = Task.objects.filter(status='not_started').count()
        
        total_subtasks = SubTask.objects.count()
        completed_subtasks = SubTask.objects.filter(is_completed=True).count()
        
        total_users = User.objects.count()
        active_users = User.objects.filter(last_login__gte=start_date).count()
        
        # Calculate rates
        project_completion_rate = (projects_completed / total_projects * 100) if total_projects > 0 else 0
        task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        user_engagement_rate = (active_users / total_users * 100) if total_users > 0 else 0
        
        # Prepare report data for email service
        report_data = {
            'total_projects': total_projects,
            'projects_completed': projects_completed,
            'projects_in_progress': projects_in_progress,
            'projects_planned': projects_planned,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'not_started_tasks': not_started_tasks,
            'total_subtasks': total_subtasks,
            'completed_subtasks': completed_subtasks,
            'total_users': total_users,
            'active_users': active_users,
            'project_completion_rate': project_completion_rate,
            'task_completion_rate': task_completion_rate,
            'user_engagement_rate': user_engagement_rate,
            'date_range': f"{start_date.strftime('%B %d')} to {end_date.strftime('%B %d, %Y')}",
            'generated_date': timezone.now().strftime("%B %d, %Y at %I:%M %p"),
            'days_filter': date_range,  # Pass the days filter to use the exact same date range
        }
        
        try:
            print(f"Sending report to: {recipient_email}")
            print(f"Report data: {report_data}")
            print(f"Custom message: {custom_message}")
            print(f"Date range: {date_range}")
            
            # Send email using Gmail API
            gmail_service = GoogleCloudEmailService()
            result = gmail_service.send_email(
                to_email=recipient_email,
                subject=f"E-Click Project Management Report - {report_data['date_range']}",
                body=f"""
                Dear Team,

                {custom_message if custom_message else 'Please find below the detailed project management report covering the recent period.'}

                Report Summary:
                • Total Projects: {report_data['total_projects']}
                • Completed Projects: {report_data['projects_completed']}
                • Projects In Progress: {report_data['projects_in_progress']}
                • Total Tasks: {report_data['total_tasks']}
                • Completed Tasks: {report_data['completed_tasks']}
                • Task Completion Rate: {report_data['task_completion_rate']:.1f}%
                • User Engagement Rate: {report_data['user_engagement_rate']:.1f}%

                Generated on: {report_data['generated_date']}

                Best regards,
                E-Click Project Management Team
                """,
                from_email=None  # Will use OAuth2 account email
            )
            print(f"Email service result: {result}")
            
            # Log the result for debugging
            if result['success']:
                print(f"Report sent successfully to {recipient_email}")
            else:
                print(f"Failed to send report: {result.get('error', 'Unknown error')}")
            
            if result['success']:
                # Track the sent report
                from .models import SentReport
                SentReport.log_report_sent(
                    report_type='general',
                    sent_by=request.user,
                    recipient_email=recipient_email,
                    report_title=f'General Report - {date_range} Days',
                    report_data=report_data,
                    custom_message=custom_message
                )
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': f'Report sent successfully to {recipient_email}'})
                else:
                    messages.success(request, f'Report sent successfully to {recipient_email}')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': result.get("error", "Unknown error")})
                else:
                    messages.error(request, f'Error sending report: {result.get("error", "Unknown error")}')
            
            return redirect('send_report')
            
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            else:
                messages.error(request, f'Error sending report: {str(e)}')
                return redirect('send_report')
    
    # GET request - show the form
    return render(request, 'home/send_report.html')

@login_required
def send_complete_report(request):
    """Send complete report page with report history"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    # Log navigation to send complete report page
    SystemLog.log_navigation(
        user=request.user,
        page_name='Send Complete Report',
        page_url=request.path,
        request=request
    )
    
    # Get recent sent reports
    from .models import SentReport
    sent_reports = SentReport.objects.all()[:10]  # Get last 10 reports
    
    context = {
        'sent_reports': sent_reports,
    }
    
    return render(request, 'home/send_complete_report.html', context)

def logout_view(request):
    # Check if it's a client logout
    if 'client_id' in request.session:
        # Clear client session
        del request.session['client_id']
        del request.session['client_username']
        messages.success(request, 'Logged out successfully.')
        return redirect('login')
    else:
        # Admin logout
        if request.user.is_authenticated:
            # Log the logout activity
            SystemLog.log_logout(request.user, request)
        logout(request)
        return redirect('login')



@login_required
def send_project_report(request, project_id):
    """
    Send a project-specific report to the client email associated with the project
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    # Log navigation to send project report page
    SystemLog.log_navigation(
        user=request.user,
        page_name='Send Project Report',
        page_url=request.path,
        request=request
    )
    
    from .services import GoogleCloudEmailService
    from django.utils import timezone
    
    # Get the project
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        # Get form data
        custom_message = request.POST.get('custom_message', '')
        date_range = request.POST.get('date_range', '30')
        
        try:
            date_range = int(date_range)
        except ValueError:
            date_range = 30
        
        # Check if project has a client email
        if not project.client_email:
            messages.error(request, f'Project "{project.name}" does not have a client email associated with it.')
            return redirect('projects_page')
        
        # Generate comprehensive report data (same format as client report)
        total_tasks = project.tasks.count()
        completed_tasks = project.tasks.filter(status='completed').count()
        in_progress_tasks = project.tasks.filter(status='in_progress').count()
        not_started_tasks = project.tasks.filter(status='not_started').count()
        on_hold_tasks = project.tasks.filter(status='on_hold').count()
        
        total_subtasks = SubTask.objects.filter(task__project=project).count()
        completed_subtasks = SubTask.objects.filter(task__project=project, is_completed=True).count()
        
        # Calculate rates
        task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        subtask_completion_rate = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
        
        # Get date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=date_range)
        
        # Calculate timeline progress
        timeline_progress = 0
        if project.start_date and project.end_date:
            total_duration = (project.end_date - project.start_date).days
            elapsed_duration = (end_date - project.start_date).days
            if total_duration > 0:
                timeline_progress = (elapsed_duration / total_duration) * 100
        
        # Prepare comprehensive report data
        report_data = {
            'project_id': project_id,
            'project_name': project.name,
            'client_name': project.client,
            'client_email': project.client_email,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'not_started_tasks': not_started_tasks,
            'on_hold_tasks': on_hold_tasks,
            'total_subtasks': total_subtasks,
            'completed_subtasks': completed_subtasks,
            'task_completion_rate': task_completion_rate,
            'subtask_completion_rate': subtask_completion_rate,
            'project_status': project.get_status_display(),
            'project_duration': f"{(project.end_date - project.start_date).days + 1} days" if project.start_date and project.end_date else "Not set",
            'date_range': f"{start_date.strftime('%B %d')} to {end_date.strftime('%B %d, %Y')}",
            'generated_date': timezone.now().strftime("%B %d, %Y at %I:%M %p"),
            'days_filter': date_range,
            'timeline_progress': timeline_progress,
        }
        
        try:
            # Generate comprehensive client report for ALL projects of this client
            # Find the client associated with this project using client_username
            client = None
            if project.client_username:
                client = Client.objects.filter(username=project.client_username).first()
                print(f"Found client by client_username: {project.client_username} -> {client}")
            elif project.client:
                # Fallback: try to find client by the client name field
                client = Client.objects.filter(username=project.client).first()
                print(f"Found client by client field: {project.client} -> {client}")
            else:
                print(f"No client found. project.client_username: '{project.client_username}', project.client: '{project.client}'")
            
            if client:
                # Generate comprehensive client report using the same function
                pdf_path = generate_client_specific_pdf_report(client.id, date_range)
                
                # Send comprehensive client report email using Gmail API
                gmail_service = GoogleCloudEmailService()
                result = gmail_service.send_email(
                    to_email=project.client_email,
                    subject=f"E-Click Comprehensive Client Report: {project.client}",
                    body=f"""
                    Dear {project.client},

                    {custom_message if custom_message else 'Please find attached your comprehensive client report covering all your projects for the recent period.'}

                    This report includes:
                    • All your projects and their current status
                    • Complete task breakdown across all projects
                    • Performance metrics and completion rates
                    • Timeline analysis and progress tracking
                    • Date Range: {report_data['date_range']}

                    Best regards,
                    E-Click Project Management Team
                    """,
                    from_email=None,  # Will use OAuth2 account email
                    attachments=[pdf_path]
                )
            else:
                # Fallback to project-specific report if client not found
                pdf_path = generate_comprehensive_project_pdf_report(project_id, date_range)
                
                gmail_service = GoogleCloudEmailService()
                result = gmail_service.send_email(
                    to_email=project.client_email,
                    subject=f"E-Click Project Report: {project.name}",
                    body=f"""
                    Dear {project.client},

                    {custom_message if custom_message else 'Please find attached your comprehensive project report covering the recent period.'}

                Project Summary:
                • Project Name: {project.name}
                • Project Status: {project.get_status_display()}
                • Total Tasks: {total_tasks}
                • Completed Tasks: {completed_tasks}
                • Tasks In Progress: {in_progress_tasks}
                • Task Completion Rate: {task_completion_rate:.1f}%
                • SubTask Completion Rate: {subtask_completion_rate:.1f}%
                • Date Range: {report_data['date_range']}

                Best regards,
                E-Click Project Management Team
                """,
                    from_email=None,  # Will use OAuth2 account email
                    attachments=[pdf_path]
                )
            
            # Cleanup temporary PDF
            try:
                import os
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
            except Exception:
                pass
            
            if result['success']:
                # Track the sent report
                from .models import SentReport
                if client:
                    SentReport.log_report_sent(
                        report_type='client',
                        sent_by=request.user,
                        recipient_email=project.client_email,
                        report_title=f'Comprehensive Client Report - {project.client}',
                        report_data=report_data,
                        custom_message=custom_message,
                        related_client=client
                    )
                else:
                    SentReport.log_report_sent(
                        report_type='project',
                        sent_by=request.user,
                        recipient_email=project.client_email,
                        report_title=f'Project Report - {project.name}',
                        report_data=report_data,
                        custom_message=custom_message,
                        related_project=project
                    )
                
                if client:
                    messages.success(request, f'Comprehensive client report for {project.client} sent successfully to {project.client_email}')
                else:
                    messages.success(request, f'Comprehensive project report sent successfully to {project.client_email}')
            else:
                messages.error(request, f'Error sending project report: {result.get("error", "Unknown error")}')
            
            return redirect('projects_page')
            
        except Exception as e:
            messages.error(request, f'Error sending project report: {str(e)}')
            return redirect('projects_page')
    
    # GET request - show the form
    # Calculate client-wide statistics for the comprehensive report
    client = None
    if project.client_username:
        client = Client.objects.filter(username=project.client_username).first()
    elif project.client:
        # Fallback: try to find client by the client name field
        client = Client.objects.filter(username=project.client).first()
    
    if client:
        # Get all projects for this client
        client_projects = Project.objects.filter(client_username=client.username)
        total_projects = client_projects.count()
        completed_projects = client_projects.filter(status='completed').count()
        in_progress_projects = client_projects.filter(status='in_progress').count()
        planned_projects = client_projects.filter(status='planned').count()
        
        # Get all tasks for this client's projects
        client_tasks = Task.objects.filter(project__in=client_projects)
        total_tasks = client_tasks.count()
        completed_tasks = client_tasks.filter(status='completed').count()
        in_progress_tasks = client_tasks.filter(status='in_progress').count()
        
        context = {
            'project': project,
            'client': client,
            'completed_projects': completed_projects,
            'in_progress_projects': in_progress_projects,
            'planned_projects': planned_projects,
            'total_projects': total_projects,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'total_tasks': total_tasks,
        }
    else:
        # Fallback to project-specific data if client not found
        total_tasks = project.tasks.count()
        completed_tasks = project.tasks.filter(status='completed').count()
        in_progress_tasks = project.tasks.filter(status='in_progress').count()
        not_started_tasks = project.tasks.filter(status='not_started').count()
        on_hold_tasks = project.tasks.filter(status='on_hold').count()
        
        context = {
            'project': project,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'not_started_tasks': not_started_tasks,
            'on_hold_tasks': on_hold_tasks,
            'total_tasks': total_tasks,
        }
    
    return render(request, 'home/send_project_report.html', context)

@login_required
def send_client_report(request):
    """Send a comprehensive report for a specific client with all their projects"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    # Log navigation to send client report page
    SystemLog.log_navigation(
        user=request.user,
        page_name='Send Client Report',
        page_url=request.path,
        request=request
    )
    
    from .services import GoogleCloudEmailService
    from django.utils import timezone
    import os
    
    if request.method == 'POST':
        try:
            client_id = request.POST.get('client_id')
            client_email = request.POST.get('client_email')
            client_username = request.POST.get('client_username')
            
            if not client_id or not client_email:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Missing client information.'})
                else:
                    messages.error(request, 'Missing client information.')
                    return redirect('reports')
            
            # Get the client and their projects
            try:
                client = get_object_or_404(Client, id=client_id)
                client_projects = Project.objects.filter(client_username=client.username)
                
                if not client_projects.exists():
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': f'No projects found for client {client.username}.'})
                    else:
                        messages.warning(request, f'No projects found for client {client.username}.')
                        return redirect('reports')
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': f'Client not found: {str(e)}'})
                else:
                    messages.error(request, f'Client not found: {str(e)}')
                    return redirect('reports')
            
            # Calculate client statistics
            total_projects = client_projects.count()
            completed_projects = client_projects.filter(status='completed').count()
            in_progress_projects = client_projects.filter(status='in_progress').count()
            planned_projects = client_projects.filter(status='planned').count()
            
            # Get all tasks for this client's projects
            client_tasks = Task.objects.filter(project__in=client_projects)
            total_tasks = client_tasks.count()
            completed_tasks = client_tasks.filter(status='completed').count()
            in_progress_tasks = client_tasks.filter(status='in_progress').count()
            
            # Calculate completion rates
            project_completion_rate = (completed_projects / total_projects * 100) if total_projects > 0 else 0
            task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            
            # Prepare report data
            report_data = {
                'client_id': client_id,
                'client_name': client_username,
                'client_email': client_email,
                'total_projects': total_projects,
                'completed_projects': completed_projects,
                'in_progress_projects': in_progress_projects,
                'planned_projects': planned_projects,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'in_progress_tasks': in_progress_tasks,
                'project_completion_rate': project_completion_rate,
                'task_completion_rate': task_completion_rate,
                'generated_date': timezone.now().strftime("%B %d, %Y at %I:%M %p"),
                'projects': [
                    {
                        'id': project.id,
                        'name': project.name,
                        'status': project.status,
                        'start_date': project.start_date.isoformat() if project.start_date else None,
                        'end_date': project.end_date.isoformat() if project.end_date else None,
                        'created_at': project.created_at.isoformat() if project.created_at else None
                    }
                    for project in client_projects
                ]
            }
            
            print(f"Sending client report to: {client_email}")
            # Send client report email using Gmail API
            gmail_service = GoogleCloudEmailService()
            # Build polished HTML email body for client - EXACTLY like the image
            email_body = f"""
<html>
  <body style="margin:0;padding:0;background:#f8fafc;font-family:Segoe UI, Roboto, Helvetica, Arial, sans-serif;color:#111827;">
    <div style="max-width:720px;margin:0 auto;padding:24px;">
      <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
        <div style="padding:24px 24px 8px 24px;border-bottom:1px solid #f3f4f6;">
          <h1 style="margin:0 0 6px 0;font-size:22px;color:#dc2626;">Your E-Click Client Progress Report</h1>
          <p style="margin:0;color:#6b7280;font-size:13px;">Generated on {report_data['generated_date']}</p>
        </div>
        <div style="padding:24px;">
          <p style="margin:0 0 12px 0;color:#000000;font-weight:bold;">Dear {client_username},</p>
          

          
          <p style="margin:0 0 16px 0;color:#000000;">Please find your summary below. A detailed, presentation-ready PDF is attached for your records.</p>

          <table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;margin:0 0 16px 0;">
            <tr>
              <td style="padding:10px 12px;border:1px solid #000000;background:#2d3748;color:#ffffff;font-weight:600;width:60%;">Project Summary</td>
              <td style="padding:10px 12px;border:1px solid #000000;background:#2d3748;color:#ffffff;font-weight:600;width:40%;">Totals</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">Total Projects</td>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">{report_data['total_projects']}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">Completed Projects</td>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">{report_data['completed_projects']}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">Projects In Progress</td>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">{report_data['in_progress_projects']}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">Total Tasks</td>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">{report_data['total_tasks']}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">Completed Tasks</td>
              <td style="padding:10px 12px;border:1px solid #000000;background:#ffffff;color:#000000;">{report_data['completed_tasks']}</td>
            </tr>
          </table>

          <div style="display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 16px 0;">
            <div style="flex:1;min-width:240px;background:#ffffff;border:1px solid #000000;border-radius:10px;padding:12px;">
              <div style="font-size:12px;color:#000000;margin-bottom:6px;">Project Completion Rate</div>
              <div style="font-size:18px;font-weight:700;color:#000000;">{report_data['project_completion_rate']:.1f}%</div>
            </div>
            <div style="flex:1;min-width:240px;background:#ffffff;border:1px solid #000000;border-radius:10px;padding:12px;">
              <div style="font-size:12px;color:#000000;margin-bottom:6px;">Task Completion Rate</div>
              <div style="font-size:18px;font-weight:700;color:#000000;">{report_data['task_completion_rate']:.1f}%</div>
            </div>
          </div>

          <h3 style="margin:18px 0 8px 0;color:#dc2626;font-size:16px;">Highlights</h3>
          <ul style="margin:0 0 16px 20px;color:#000000;">
            <li>Clear visibility of your portfolio progress and current workload.</li>
            <li>Attached PDF includes detailed tables, charts, and next-step recommendations.</li>
            <li>We'll continue to monitor and update you proactively.</li>
          </ul>



          <!-- Closing section removed -->
        </div>
        <div style="padding:14px 24px;background:#2d3748;color:#ffffff;text-align:center;font-size:12px;">
          WE CARE, WE CAN, WE DELIVER
        </div>
      </div>
    </div>
  </body>
</html>
            """

            # Generate client-specific PDF and attach it
            try:
                pdf_path = generate_client_specific_pdf_report(client_id)
                
                # Verify PDF was generated successfully
                if not pdf_path:
                    raise Exception("PDF generation failed - no path returned")
                
                if not os.path.exists(pdf_path):
                    raise Exception(f"PDF file not found at generated path: {pdf_path}")
                
                # Check file size
                file_size = os.path.getsize(pdf_path)
                if file_size == 0:
                    raise Exception("Generated PDF file is empty")
                
                print(f"PDF generated successfully: {pdf_path} ({file_size} bytes)")
                
            except Exception as pdf_error:
                error_msg = f"Failed to generate PDF report: {str(pdf_error)}"
                print(f"PDF Generation Error: {error_msg}")
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"PDF Generation Error: {error_msg}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    messages.error(request, error_msg)
                    return redirect('reports')

            result = gmail_service.send_email(
                to_email=client_email,
                subject=f"Client Report - {client_username} - E-Click",
                body=email_body,
                from_email=None,  # Will use OAuth2 account email
                attachments=[pdf_path]
            )

            # Cleanup temporary PDF
            try:
                import os
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
            except Exception:
                pass
            print(f"Client email service result: {result}")
            
            if result['success']:
                # Track the sent report
                from .models import SentReport
                SentReport.log_report_sent(
                    report_type='client',
                    sent_by=request.user,
                    recipient_email=client_email,
                    report_title=f'Client Report - {client_username}',
                    report_data=report_data,
                    related_client=client
                )
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': f'Client report sent successfully to {client_email}!'})
                else:
                    messages.success(request, f'Client report sent successfully to {client_email}!')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': result.get("error", "Unknown error")})
                else:
                    messages.error(request, f'Failed to send client report: {result.get("error", "Unknown error")}')
            
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            else:
                messages.error(request, f'Error sending client report: {str(e)}')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    else:
        return redirect('reports')



def client_dashboard(request):
    """Client dashboard showing their projects"""
    if 'client_id' not in request.session:
        return redirect('login')
    
    client_id = request.session['client_id']
    try:
        client = Client.objects.get(id=client_id, is_active=True)
        # Get projects where this client is involved
        projects = Project.objects.filter(client_email=client.email).order_by('-created_at')
        
        # Calculate project statistics
        total_projects = projects.count()
        active_projects = projects.filter(status='in_progress').count()
        completed_projects = projects.filter(status='completed').count()
        planned_projects = projects.filter(status='planned').count()
        
        # Get recent tasks for all projects and calculate task counts
        recent_tasks = []
        total_all_tasks = 0
        total_completed_tasks = 0
        
        for project in projects:
            project_tasks = project.tasks.all().order_by('-updated_at')[:3]
            completed_tasks_count = project.tasks.filter(status='completed').count()
            total_tasks_count = project.tasks.count()
            
            project.completed_tasks_count = completed_tasks_count
            total_all_tasks += total_tasks_count
            total_completed_tasks += completed_tasks_count
            
            for task in project_tasks:
                recent_tasks.append({
                    'task': task,
                    'project': project
                })
        
        # Calculate overall progress percentage
        overall_progress = (total_completed_tasks / total_all_tasks * 100) if total_all_tasks > 0 else 0
        
        # Sort by task update date
        recent_tasks.sort(key=lambda x: x['task'].updated_at, reverse=True)
        recent_tasks = recent_tasks[:6]  # Show only 6 most recent tasks
        
        return render(request, 'home/client_dashboard.html', {
            'client': client,
            'projects': projects,
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'planned_projects': planned_projects,
            'recent_tasks': recent_tasks,
            'overall_progress': overall_progress
        })
    except Client.DoesNotExist:
        messages.error(request, 'Client not found.')
        return redirect('login')

def client_project_detail(request, project_id):
    """Client view of project details including tasks"""
    if 'client_id' not in request.session:
        return redirect('login')
    
    client_id = request.session['client_id']
    try:
        client = Client.objects.get(id=client_id, is_active=True)
        project = get_object_or_404(Project, id=project_id, client_email=client.email)
        
        # Get all tasks for this project with their subtasks
        tasks = project.tasks.all().order_by('start_date', 'created_at')
        
        # Calculate project progress
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(status='completed').count()
        in_progress_tasks = tasks.filter(status='in_progress').count()
        on_hold_tasks = tasks.filter(status='on_hold').count()
        not_started_tasks = tasks.filter(status='not_started').count()
        
        # Calculate progress percentage
        progress_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Get task updates and recent activity
        task_updates = TaskUpdate.objects.filter(task__project=project).order_by('-created_at')[:10]
        
        return render(request, 'home/client_project_detail.html', {
            'client': client,
            'project': project,
            'tasks': tasks,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'on_hold_tasks': on_hold_tasks,
            'not_started_tasks': not_started_tasks,
            'progress_percentage': progress_percentage,
            'task_updates': task_updates
        })
    except Client.DoesNotExist:
        messages.error(request, 'Client not found.')
        return redirect('login')
    except Project.DoesNotExist:
        messages.error(request, 'Project not found.')
        return redirect('client_dashboard')

def client_logout(request):
    """Client logout"""
    if 'client_id' in request.session:
        del request.session['client_id']
    if 'client_username' in request.session:
        del request.session['client_username']
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')

def client_settings(request):
    """Client settings page for profile management"""
    if 'client_id' not in request.session:
        return redirect('login')
    
    client_id = request.session['client_id']
    try:
        client = Client.objects.get(id=client_id, is_active=True)
        
        if request.method == 'POST':
            # Handle profile updates
            username = request.POST.get('username')
            email = request.POST.get('email')
            
            if username and email:
                # Check if username or email already exists for other clients
                existing_client = Client.objects.filter(
                    (models.Q(username=username) | models.Q(email=email)) & 
                    ~models.Q(id=client_id)
                ).first()
                
                if existing_client:
                    if existing_client.username == username:
                        messages.error(request, 'Username already exists.')
                    else:
                        messages.error(request, 'Email already exists.')
                else:
                    # Update client profile
                    old_username = client.username
                    old_email = client.email
                    
                    client.username = username
                    client.email = email
                    
                    # Handle profile picture upload
                    if 'profile_picture' in request.FILES:
                        profile_picture = request.FILES['profile_picture']
                        # Delete old profile picture if it exists
                        if client.profile_picture:
                            client.profile_picture.delete(save=False)
                        client.profile_picture = profile_picture
                    
                    client.save()
                    
                    # Log the changes for admin visibility
                    from .models import SystemLog
                    SystemLog.objects.create(
                        action='client_profile_updated',
                        description=f'Client {old_username} ({old_email}) updated profile: username to "{username}", email to "{email}"',
                        related_client=client,
                        user=None  # No user since this is client action
                    )
                    
                    messages.success(request, 'Profile updated successfully!')
                    return redirect('client_settings')
        
        return render(request, 'home/client_settings.html', {
            'client': client
        })
    except Client.DoesNotExist:
        messages.error(request, 'Client not found.')
        return redirect('login')

def send_client_otp(request):
    """Send OTP to client for password setup"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('projects_page')
    
    if request.method == 'POST':
        project_id = request.POST.get('project_id')
        client_username = request.POST.get('client_username')
        client_email = request.POST.get('client_email')
        
        try:
            project = Project.objects.get(id=project_id)
            
            # Check if client already exists by email or username
            client = None
            
            # First try to find by email
            try:
                client = Client.objects.get(email=client_email)
                # Client exists by email, use existing client
                
                # Check if this client is associated with any active projects
                active_projects = Project.objects.filter(client_email=client_email).exists()
                if not active_projects:
                    # Client exists but has no active projects, update username if needed
                    if client.username != client_username:
                        client.username = client_username
                        client.save()
                        print(f"Updated client username from {client.username} to {client_username}")
            except Client.DoesNotExist:
                # Try to find by username
                try:
                    client = Client.objects.get(username=client_username)
                    # Client exists by username, update email if needed
                    if client.email != client_email:
                        client.email = client_email
                        client.save()
                        print(f"Updated client email from {client.email} to {client_email}")
                except Client.DoesNotExist:
                    # Create new client
                    client = Client.objects.create(
                        username=client_username,
                        email=client_email,
                        is_active=True
                    )
                    print(f"Created new client: {client_username} ({client_email})")
            
            # Generate OTP (this already creates the OTP record)
            otp = client.generate_otp()
            
            # Use localhost for development
            site_url = "http://127.0.0.1:8000"
            
            # Send OTP email using Gmail API
            gmail_service = GoogleCloudEmailService()
            email_result = gmail_service.send_email(
                to_email=client_email,
                subject=f"Set Your Password - {project.name} Project",
                body=f"""
                Dear {client_username},

                Welcome to the {project.name} project! Please use the following OTP to set your password:

                🔐 Your OTP: {otp}

                Please visit: {site_url}/client/setup-password/?username={client_username}

                Best regards,
                E-Click Project Management Team
                """,
                from_email=None  # Will use OAuth2 account email
            )
            
            if email_result['success']:
                messages.success(request, f'We have sent an OTP to the client at {client_email}')
            else:
                messages.error(request, f'Error sending OTP: {email_result["error"]}')
                
        except Project.DoesNotExist:
            messages.error(request, 'Project not found.')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    return redirect('projects_page')

def client_setup_password(request):
    """Client password setup using OTP"""
    if request.method == 'POST':
        username = request.POST.get('username')
        otp = request.POST.get('otp')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not all([username, otp, new_password, confirm_password]):
            messages.error(request, 'All fields are required.')
            return render(request, 'home/client_setup_password.html', {'username': username})
        
        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'home/client_setup_password.html', {'username': username})
        
        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'home/client_setup_password.html', {'username': username})
        
        try:
            client = Client.objects.get(username=username)
            
            # Verify OTP
            try:
                otp_obj = ClientOTP.objects.filter(
                    client=client,
                    otp=otp,
                    is_used=False
                ).first()
                
                if not otp_obj:
                    messages.error(request, 'Invalid OTP code.')
                    return render(request, 'home/client_setup_password.html')
                
                if not otp_obj.is_valid():
                    messages.error(request, 'OTP has expired or is invalid.')
                    return render(request, 'home/client_setup_password.html')
                
                # Mark OTP as used
                otp_obj.is_used = True
                otp_obj.save()
                
                # Set client password
                client.password = new_password
                client.has_changed_password = True
                client.save()
                
                messages.success(request, 'Password set successfully! You can now log in.')
                return redirect('client_dashboard')
                
            except ClientOTP.DoesNotExist:
                messages.error(request, 'Invalid OTP code.')
                return render(request, 'home/client_setup_password.html')
                
        except Client.DoesNotExist:
            messages.error(request, 'Client not found.')
            return render(request, 'home/client_setup_password.html')
    
    # GET request - show form
    username = request.GET.get('username', '')
    return render(request, 'home/client_setup_password.html', {'username': username})

def user_setup_password(request):
    """User password setup using OTP"""
    if request.method == 'POST':
        username = request.POST.get('username')
        otp = request.POST.get('otp')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not all([username, otp, new_password, confirm_password]):
            messages.error(request, 'All fields are required.')
            return render(request, 'home/user_setup_password.html')
        
        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'home/user_setup_password.html')
        
        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'home/user_setup_password.html')
        
        try:
            user = User.objects.get(username=username)
            
            # Verify OTP
            try:
                from .models import UserOTP
                otp_obj = UserOTP.objects.filter(
                    user=user,
                    otp=otp,
                    is_used=False
                ).first()
                
                if not otp_obj:
                    messages.error(request, 'Invalid OTP code.')
                    return render(request, 'home/user_setup_password.html')
                
                if not otp_obj.is_valid():
                    messages.error(request, 'OTP has expired or is invalid.')
                    return render(request, 'home/user_setup_password.html')
                
                # Mark OTP as used
                otp_obj.is_used = True
                otp_obj.save()
                
                # Set user password
                user.set_password(new_password)
                user.save()
                
                # Automatically log the user in
                from django.contrib.auth import login
                login(request, user)
                
                messages.success(request, 'Password set successfully! Welcome to your dashboard.')
                return redirect('dashboard')
                
            except UserOTP.DoesNotExist:
                messages.error(request, 'Invalid OTP code.')
                return render(request, 'home/user_setup_password.html')
                
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return render(request, 'home/user_setup_password.html')
    
    # GET request - show form
    username = request.GET.get('username', '')
    return render(request, 'home/user_setup_password.html', {'username': username})

def client_change_password(request):
    """Client change password page after login"""
    # Check if client is logged in
    client_id = request.session.get('client_id')
    if not client_id:
        messages.error(request, 'Please login first.')
        return redirect('login')
    
    try:
        client = Client.objects.get(id=client_id, is_active=True)
    except Client.DoesNotExist:
        messages.error(request, 'Client not found.')
        return redirect('login')
    
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Verify old password
        old_password_hash = hashlib.sha256(old_password.encode()).hexdigest()
        if client.password != old_password_hash:
            messages.error(request, 'Current password is incorrect.')
            return render(request, 'home/client_change_password.html')
        
        # Validate new password
        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
            return render(request, 'home/client_change_password.html')
        
        if len(new_password) < 6:
            messages.error(request, 'Password must be at least 6 characters long.')
            return render(request, 'home/client_change_password.html')
        
        # Update password and mark as changed
        client.password = hashlib.sha256(new_password.encode()).hexdigest()
        client.has_changed_password = True
        client.save()
        
        messages.success(request, 'Password changed successfully!')
        return redirect('client_dashboard')
    
    return render(request, 'home/client_change_password.html')

def user_reset_password(request):
    """User password reset using OTP sent by admin"""
    if request.method == 'POST':
        username = request.POST.get('username')
        otp = request.POST.get('otp')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not all([username, otp, new_password, confirm_password]):
            messages.error(request, 'All fields are required.')
            return render(request, 'home/user_reset_password.html', {'username': username})
        
        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'home/user_reset_password.html', {'username': username})
        
        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'home/user_reset_password.html', {'username': username})
        
        try:
            user = User.objects.get(username=username)
            
            # Verify OTP
            try:
                from .models import UserOTP
                otp_obj = UserOTP.objects.filter(
                    user=user,
                    otp=otp,
                    is_used=False
                ).first()
                
                if not otp_obj:
                    messages.error(request, 'Invalid OTP code.')
                    return render(request, 'home/user_reset_password.html', {'username': username})
                
                if not otp_obj.is_valid():
                    messages.error(request, 'OTP has expired or is invalid.')
                    return render(request, 'home/user_reset_password.html', {'username': username})
                
                # Mark OTP as used
                otp_obj.is_used = True
                otp_obj.save()
                
                # Set user password
                user.set_password(new_password)
                user.save()
                
                messages.success(request, 'Password reset successfully! You can now log in with your new password.')
                return redirect('login')
                
            except UserOTP.DoesNotExist:
                messages.error(request, 'Invalid OTP code.')
                return render(request, 'home/user_reset_password.html', {'username': username})
                
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return render(request, 'home/user_reset_password.html', {'username': username})
    
    # GET request - show form
    username = request.GET.get('username', '')
    return render(request, 'home/user_reset_password.html', {'username': username})

@login_required
def team_dashboard(request):
    """Team member dashboard showing assigned projects and tasks"""
    # Get user's assigned projects
    assigned_projects = Project.objects.filter(assigned_users=request.user)
    
    # Get user's assigned tasks from those projects
    assigned_tasks = Task.objects.filter(project__in=assigned_projects)
    
    # Calculate statistics
    total_projects = assigned_projects.count()
    active_projects = assigned_projects.filter(status='in_progress').count()
    completed_projects = assigned_projects.filter(status='completed').count()
    
    total_tasks = assigned_tasks.count()
    completed_tasks = assigned_tasks.filter(status='completed').count()
    pending_tasks = assigned_tasks.filter(status__in=['not_started', 'in_progress']).count()
    
    # Get upcoming tasks (due in next 7 days)
    from datetime import timedelta
    current_date = timezone.now()
    upcoming_tasks = assigned_tasks.filter(
        end_date__gte=current_date.date(),
        end_date__lte=current_date.date() + timedelta(days=7),
        status__in=['not_started', 'in_progress']
    ).order_by('end_date')
    
    # Get urgent tasks (tasks due soon)
    urgent_tasks = assigned_tasks.filter(
        end_date__lte=current_date.date() + timedelta(days=3),
        status__in=['not_started', 'in_progress']
    ).order_by('end_date')
    
    # Get high priority tasks
    high_priority_tasks = assigned_tasks.filter(
        priority__in=['high', 'urgent'],
        status__in=['not_started', 'in_progress']
    ).order_by('priority', 'end_date')
    
    context = {
        'assigned_projects': assigned_projects,
        'assigned_tasks': assigned_tasks,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks,
        'upcoming_tasks': upcoming_tasks,
        'urgent_tasks': urgent_tasks,
        'high_priority_tasks': high_priority_tasks,
    }
    
    return render(request, 'home/team_dashboard.html', context)

@login_required
def user_planner(request):
    """User planner page showing assigned tasks with planner interface"""
    user = request.user
    
    # Get all projects where user is assigned
    assigned_projects = Project.objects.filter(assigned_users=user)
    
    # Get all tasks from assigned projects
    tasks = Task.objects.filter(project__in=assigned_projects).select_related('project')
    
    # Group tasks by status for planner view
    task_groups = {
        'not_started': tasks.filter(status='not_started'),
        'in_progress': tasks.filter(status='in_progress'),
        'on_hold': tasks.filter(status='on_hold'),
        'completed': tasks.filter(status='completed')
    }
    
    # Get user's unread notifications
    notifications = Notification.objects.filter(recipient=user, is_read=False).order_by('-created_at')[:5]
    
    context = {
        'task_groups': task_groups,
        'assigned_projects': assigned_projects,
        'notifications': notifications,
        'total_tasks': tasks.count(),
        'completed_tasks': tasks.filter(status='completed').count(),
        'pending_tasks': tasks.exclude(status='completed').count()
    }
    
    return render(request, 'home/user_planner.html', context)

@login_required
def update_task_status(request, task_id):
    """Update task status and create notification"""
    print(f"DEBUG: update_task_status called for task {task_id} by user {request.user.username}")
    
    if request.method == 'POST':
        try:
            task = Task.objects.get(id=task_id)
            
            # Check if user is assigned to this task's project
            if request.user not in task.project.assigned_users.all():
                return JsonResponse({'success': False, 'message': 'You are not assigned to this project'})
            
            update_type = request.POST.get('update_type')
            reason = request.POST.get('reason', '')
            estimated_completion = request.POST.get('estimated_completion')
            
            # Create task update
            task_update = TaskUpdate.objects.create(
                task=task,
                user=request.user,
                update_type=update_type,
                reason=reason,
                estimated_completion=estimated_completion if estimated_completion else None
            )
            
            # Update task status based on update type
            if update_type == 'completed':
                task.status = 'completed'
            elif update_type == 'delayed':
                task.status = 'on_hold'
            elif update_type == 'on_hold':
                task.status = 'on_hold'
            elif update_type == 'in_progress':
                task.status = 'in_progress'
            elif update_type == 'not_started':
                task.status = 'not_started'
            
            task.save()
            
            # Create ONE system-wide notification for all admins to see
            notification_title = f"Task Update: {task.title}"
            notification_message = f"{request.user.username} marked task '{task.title}' as {update_type}"
            if reason:
                notification_message += f". Reason: {reason}"
            
            print(f"DEBUG: Creating system-wide notification for task update")
            try:
                notification = Notification.create_if_not_exists(
                    recipient=None,  # System-wide notification
                    notification_type='task_update',
                    title=notification_title,
                    message=notification_message,
                    related_task=task,
                    related_project=task.project,
                    triggered_by=request.user,
                    is_admin_notification=True
                )
                print(f"DEBUG: Successfully created/updated system notification {notification.id}")
            except Exception as e:
                print(f"DEBUG: Error creating system notification: {str(e)}")
            
            return JsonResponse({
                'success': True, 
                'message': 'Task status updated successfully',
                'new_status': task.get_status_display()
            })
            
        except Task.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Task not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def update_subtask_status(request, subtask_id):
    """Update subtask status"""
    print(f"DEBUG: update_subtask_status called for subtask {subtask_id} by user {request.user.username}")
    
    if request.method == 'POST':
        try:
            subtask = Subtask.objects.get(id=subtask_id)
            
            # Check if user is assigned to this subtask's task's project
            if request.user not in subtask.task.project.assigned_users.all():
                return JsonResponse({'success': False, 'message': 'You are not assigned to this project'})
            
            new_status = request.POST.get('new_status')
            reason = request.POST.get('reason', '')
            
            if not new_status:
                return JsonResponse({'success': False, 'message': 'Status is required'})
            
            # Update subtask status
            old_status = subtask.status
            subtask.status = new_status
            subtask.save()
            
            # Log the status change
            SystemLog.log_subtask_status_change(request.user, subtask, old_status, new_status, request)
            
            # Create ONE system-wide notification for all admins to see
            notification_title = f"Subtask Update: {subtask.title}"
            notification_message = f"{request.user.username} updated subtask '{subtask.title}' status from {old_status} to {new_status}"
            if reason:
                notification_message += f". Reason: {reason}"
            
            print(f"DEBUG: Creating system-wide notification for subtask update")
            try:
                notification = Notification.create_if_not_exists(
                    recipient=None,  # System-wide notification
                    notification_type='subtask_status_change',
                    title=notification_title,
                    message=notification_message,
                    related_task=subtask.task,
                    related_project=subtask.task.project,
                    triggered_by=request.user,
                    is_admin_notification=True
                )
                print(f"DEBUG: Successfully created/updated system notification {notification.id}")
            except Exception as e:
                print(f"DEBUG: Error creating system notification: {str(e)}")
            
            return JsonResponse({
                'success': True, 
                'message': 'Subtask status updated successfully',
                'new_status': subtask.get_status_display()
            })
            
        except Subtask.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Subtask not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})
@login_required
def add_subtask_comment(request, subtask_id):
    """Add comment to subtask"""
    if request.method == 'POST':
        try:
            subtask = Subtask.objects.get(id=subtask_id)
            
            # Check if user is assigned to this subtask's task's project
            if request.user not in subtask.task.project.assigned_users.all():
                return JsonResponse({'success': False, 'message': 'You are not assigned to this project'})
            
            comment_text = request.POST.get('comment_text', '')
            
            if not comment_text:
                return JsonResponse({'success': False, 'message': 'Comment text is required'})
            
            # Create the comment (you may need to create a SubtaskComment model or use existing comment system)
            # For now, we'll just return success
            # TODO: Implement subtask comment storage
            
            # Create system-wide notification for all admins
            notification_title = f"Subtask Comment: {subtask.title}"
            notification_message = f"{request.user.username} added a comment to subtask '{subtask.title}': {comment_text[:100]}..."
            
            Notification.create_if_not_exists(
                recipient=None,  # System-wide notification
                notification_type='subtask_comment_added',
                title=notification_title,
                message=notification_message,
                related_task=subtask.task,
                related_project=subtask.task.project,
                triggered_by=request.user,
                is_admin_notification=True
            )
            
            return JsonResponse({
                'success': True, 
                'message': 'Comment added successfully'
            })
            
        except Subtask.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Subtask not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def extend_subtask_deadline(request, subtask_id):
    """Extend subtask deadline"""
    if request.method == 'POST':
        try:
            subtask = Subtask.objects.get(id=subtask_id)
            
            # Check if user is assigned to this subtask's task's project
            if request.user not in subtask.task.project.assigned_users.all():
                return JsonResponse({'success': False, 'message': 'You are not assigned to this project'})
            
            new_end_date = request.POST.get('new_end_date', '')
            reason = request.POST.get('reason', '')
            
            if not new_end_date:
                return JsonResponse({'success': False, 'message': 'New end date is required'})
            
            # Update the task's end date (since subtasks inherit from tasks)
            task = subtask.task
            task.end_date = new_end_date
            task.save()
            
            # Create system-wide notification for all admins
            notification_title = f"Subtask Deadline Extended: {subtask.title}"
            notification_message = f"{request.user.username} extended deadline for subtask '{subtask.title}' to {new_end_date}"
            if reason:
                notification_message += f". Reason: {reason}"
            
            Notification.create_if_not_exists(
                recipient=None,  # System-wide notification
                notification_type='subtask_deadline_extended',
                title=notification_title,
                message=notification_message,
                related_task=task,
                related_project=task.project,
                triggered_by=request.user,
                is_admin_notification=True
            )
            
            return JsonResponse({
                'success': True, 
                'message': 'Deadline extended successfully'
            })
            
        except Subtask.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Subtask not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def get_notifications(request):
    """Get user's notifications"""
    # Regular users only see their personal notifications (not system-wide ones)
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:10]
    
    notification_data = []
    for notification in notifications:
        notification_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'type': notification.get_notification_type_display(),
            'is_read': notification.is_read,
            'created_at': notification.created_at.strftime('%M minutes ago') if (timezone.now() - notification.created_at).seconds < 3600 else notification.created_at.strftime('%b %d, %Y'),
            'related_task_id': notification.related_task.id if notification.related_task else None,
            'related_project_id': notification.related_project.id if notification.related_project else None
        })
    
    return JsonResponse({'notifications': notification_data})

@login_required
def mark_notification_read(request, notification_id):
    """Mark notification as read"""
    try:
        print(f"DEBUG: mark_notification_read called for notification {notification_id}")
        print(f"DEBUG: User is staff: {request.user.is_staff}")
        
        # Allow admins to mark any notification as read, regular users can only mark their own
        if request.user.is_staff:
            notification = Notification.objects.get(id=notification_id)
            print(f"DEBUG: Admin accessing notification {notification_id}")
        else:
            notification = Notification.objects.get(id=notification_id, recipient=request.user)
            print(f"DEBUG: Regular user accessing notification {notification_id}")
        
        print(f"DEBUG: Found notification {notification_id}. Current status: {notification.is_read}")
        print(f"DEBUG: Notification details - Type: {notification.notification_type}, Recipient: {notification.recipient.username if notification.recipient else 'System-wide'}")
        
        # Check if notification is already read
        if notification.is_read:
            print(f"DEBUG: Notification {notification_id} is already read, no change needed")
            return JsonResponse({'success': True, 'message': 'Already read'})
        
        # Mark as read
        notification.is_read = True
        notification.save()
        
        # Verify the save worked by refreshing from database
        notification.refresh_from_db()
        print(f"DEBUG: After save, notification {notification_id} status: {notification.is_read}")
        
        # Double-check by querying the database directly
        verification = Notification.objects.get(id=notification_id)
        print(f"DEBUG: Verification query shows notification {notification_id} status: {verification.is_read}")
        
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        print(f"DEBUG: Notification {notification_id} not found")
        return JsonResponse({'success': False, 'message': 'Notification not found'})
    except Exception as e:
        print(f"DEBUG: Error updating notification {notification_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Error updating notification: {str(e)}'})

@login_required
def delete_notification(request, notification_id):
    """Delete a notification (admin only)"""
    print(f"DEBUG: delete_notification called by user: {request.user.username}")
    print(f"DEBUG: User is_staff: {request.user.is_staff}")
    print(f"DEBUG: User is_superuser: {request.user.is_superuser}")
    
    # Check if user has admin privileges
    if not request.user.is_staff:
        print(f"DEBUG: Access denied - user is not staff")
        return JsonResponse({'success': False, 'message': 'Admin privileges required'})
    
    # Additional check for specific admin permissions if user profile exists
    try:
        if hasattr(request.user, 'profile'):
            print(f"DEBUG: User profile permissions:")
            print(f"DEBUG: - can_access_admin: {request.user.profile.can_access_admin}")
            print(f"DEBUG: - can_manage_users: {request.user.profile.can_manage_users}")
            
            if not request.user.profile.can_access_admin:
                print(f"DEBUG: Access denied - user does not have admin access permission")
                return JsonResponse({'success': False, 'message': 'Admin access permission required'})
    except Exception as e:
        print(f"DEBUG: Error checking user profile: {str(e)}")
        # Continue with staff check if profile check fails
    
    try:
        print(f"DEBUG: Attempting to delete notification {notification_id}")
        
        # Use explicit transaction to ensure deletion is committed
        with transaction.atomic():
            # Get the notification and verify it exists
            notification = Notification.objects.get(id=notification_id)
            print(f"DEBUG: Found notification {notification_id}")
            print(f"DEBUG: Notification details - Type: {notification.notification_type}, Recipient: {notification.recipient.username if notification.recipient else 'System-wide'}")
            
            # Store notification details for debugging
            notification_details = {
                'id': notification.id,
                'type': notification.notification_type,
                'recipient': notification.recipient.username if notification.recipient else 'System-wide',
                'related_task': notification.related_task.id if notification.related_task else None,
                'related_project': notification.related_project.id if notification.related_project else None,
            }
            print(f"DEBUG: Notification details before deletion: {notification_details}")
            
            # Delete the notification
            print(f"DEBUG: Calling notification.delete()...")
            notification.delete()
            print(f"DEBUG: notification.delete() completed")
            
            # Verify deletion by trying to get it again
            try:
                verification = Notification.objects.get(id=notification_id)
                print(f"DEBUG: WARNING - Notification {notification_id} still exists after deletion!")
                print(f"DEBUG: This suggests the deletion failed or was rolled back")
                return JsonResponse({'success': False, 'message': 'Deletion failed - notification still exists'})
            except Notification.DoesNotExist:
                print(f"DEBUG: Confirmed - Notification {notification_id} was successfully deleted from database")
            
            # Also check if there are other notifications with similar content
            if notification_details['recipient'] != 'System-wide':
                similar_notifications = Notification.objects.filter(
                    notification_type=notification_details['type'],
                    recipient__username=notification_details['recipient']
                )
            else:
                similar_notifications = Notification.objects.filter(
                    notification_type=notification_details['type'],
                    recipient__isnull=True
                )
            print(f"DEBUG: Found {similar_notifications.count()} similar notifications after deletion")
        
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        print(f"DEBUG: Notification {notification_id} not found for deletion")
        return JsonResponse({'success': False, 'message': 'Notification not found'})
    except Exception as e:
        print(f"DEBUG: Error deleting notification {notification_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Error deleting notification: {str(e)}'})

@login_required
def admin_notifications(request):
    """Admin notifications page"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    # Get all notifications for admin, prioritizing system-wide notifications
    notifications = Notification.objects.select_related(
        'recipient', 'triggered_by', 'related_project', 'related_task', 'related_subtask'
    ).order_by('-created_at')  # Order by creation date, newest first
    
    # Get filter parameters
    notification_type = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Apply filters
    if notification_type:
        notifications = notifications.filter(notification_type=notification_type)
    
    if status_filter == 'unread':
        notifications = notifications.filter(is_read=False)
    elif status_filter == 'read':
        notifications = notifications.filter(is_read=True)
    
    if date_from:
        notifications = notifications.filter(created_at__date__gte=date_from)
    
    if date_to:
        notifications = notifications.filter(created_at__date__lte=date_to)
    
    # Calculate statistics
    total_notifications = Notification.objects.count()
    unread_count = Notification.objects.filter(is_read=False).count()
    today_count = Notification.objects.filter(created_at__date=timezone.now().date()).count()
    week_count = Notification.objects.filter(created_at__date__gte=timezone.now().date() - timedelta(days=7)).count()
    
    # Pagination
    paginator = Paginator(notifications, 20)  # 20 notifications per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'notifications': page_obj,
        'total_notifications': total_notifications,
        'unread_count': unread_count,
        'today_count': today_count,
        'week_count': week_count,
        'notification_types': Notification.NOTIFICATION_TYPES,
        'notification_type': notification_type,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'home/admin_notifications.html', context)


@login_required
def admin_notifications_enhanced(request):
    """Enhanced admin view for managing all notifications with comment responses"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    # Get all notifications with related data
    notifications = Notification.objects.select_related(
        'recipient', 'triggered_by', 'related_project', 'related_task', 'related_subtask'
    ).prefetch_related(
        'related_comment', 'related_subtask_comment'
    ).order_by('-created_at')
    
    # Filter by type if specified
    notification_type = request.GET.get('type')
    if notification_type:
        notifications = notifications.filter(notification_type=notification_type)
    
    # Filter by status if specified
    status_filter = request.GET.get('status')
    if status_filter == 'unread':
        notifications = notifications.filter(is_read=False)
    elif status_filter == 'read':
        notifications = notifications.filter(is_read=True)
    
    # Filter by admin notifications if specified
    admin_filter = request.GET.get('admin')
    if admin_filter == 'true':
        notifications = notifications.filter(is_admin_notification=True)
    elif admin_filter == 'false':
        notifications = notifications.filter(is_admin_notification=False)
    
    # Get notification counts for stats
    total_notifications = Notification.objects.count()
    unread_notifications = Notification.objects.filter(is_read=False).count()
    admin_notifications = Notification.objects.filter(is_admin_notification=True).count()
    team_notifications = Notification.objects.filter(is_admin_notification=False).count()
    
    # Get recent comments that might need admin response
    recent_task_comments = TaskComment.objects.filter(
        is_admin_response=False
    ).select_related('user', 'task').order_by('-created_at')[:10]
    
    recent_subtask_comments = SubTaskComment.objects.filter(
        is_admin_response=False
    ).select_related('user', 'subtask', 'subtask__task').order_by('-created_at')[:10]
    
    # Get users for message sending based on admin permissions
    if hasattr(request.user, 'profile') and request.user.profile.can_manage_users:
        available_users = User.objects.all().order_by('username')
    else:
        available_users = User.objects.filter(id=request.user.id)
    
    context = {
        'notifications': notifications,
        'total_notifications': total_notifications,
        'unread_notifications': unread_notifications,
        'admin_notifications': admin_notifications,
        'team_notifications': team_notifications,
        'recent_task_comments': recent_task_comments,
        'recent_subtask_comments': recent_subtask_comments,
        'notification_types': Notification.NOTIFICATION_TYPES,
        'available_users': available_users,
    }
    
    return render(request, 'home/admin_notifications_enhanced.html', context)


@login_required
def admin_respond_to_task_comment(request, comment_id):
    """Admin responds to a task comment"""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Admin privileges required'})
    
    if request.method == 'POST':
        try:
            task_comment = TaskComment.objects.get(id=comment_id)
            response_text = request.POST.get('response_text', '').strip()
            
            if not response_text:
                return JsonResponse({'success': False, 'message': 'Response text is required'})
            
            # Create admin response comment
            admin_response = TaskComment.objects.create(
                task=task_comment.task,
                user=request.user,
                comment=response_text,
                is_admin_response=True,
                parent_comment=task_comment
            )
            
            # Create notification for the original commenter
            Notification.create_if_not_exists(
                recipient=task_comment.user,
                notification_type='task_comment_response',
                title=f'Admin Response to Your Comment',
                message=f'Admin {request.user.get_full_name()} has responded to your comment on task "{task_comment.task.title}": {response_text}',
                is_admin_notification=True,
                related_task=task_comment.task,
                related_comment=admin_response
            )
            
            return JsonResponse({'success': True, 'message': 'Response sent successfully'})
            
        except TaskComment.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Comment not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def update_task_with_notification(request, task_id):
    """Update task and create notification with user tracking"""
    if request.method == 'POST':
        try:
            task = Task.objects.get(id=task_id)
            update_type = request.POST.get('update_type')
            new_value = request.POST.get('new_value')
            reason = request.POST.get('reason', '')
            
            # Store old value before updating
            old_value = None
            if update_type == 'status_changed':
                old_value = task.get_status_display()
                task.status = new_value

            elif update_type == 'deadline_extended':
                old_value = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'Not set'
                task.end_date = new_value
            
            task.save()
            
            # Create notification with user tracking
            create_notification_for_task_update(
                task=task,
                user=request.user,
                update_type=update_type,
                old_value=old_value,
                new_value=new_value,
                reason=reason
            )
            
            # Create TaskUpdate record
            from .models import TaskUpdate
            TaskUpdate.objects.create(
                task=task,
                user=request.user,
                update_type=update_type,
                reason=reason,
                old_value=old_value,
                new_value=new_value
            )
            
            return JsonResponse({'success': True, 'message': 'Task updated successfully'})
            
        except Task.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Task not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def notification_demo(request):
    """Demo page for the enhanced notification system"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    # Get notification statistics
    from .models import Notification
    from django.utils import timezone
    from datetime import timedelta
    
    total_notifications = Notification.objects.count()
    unread_count = Notification.objects.filter(is_read=False).count()
    today_count = Notification.objects.filter(created_at__date=timezone.now().date()).count()
    tracked_count = Notification.objects.filter(triggered_by__isnull=False).count()
    
    # Get available tasks for testing
    from .models import Task
    available_tasks = Task.objects.select_related('project').all()[:20]  # Limit to 20 tasks
    
    # Get available users for testing
    from .models import User
    available_users = User.objects.filter(is_active=True).order_by('username')[:20]  # Limit to 20 users
    
    context = {
        'total_notifications': total_notifications,
        'unread_count': unread_count,
        'today_count': today_count,
        'tracked_count': tracked_count,
        'available_tasks': available_tasks,
        'available_users': available_users,
    }
    
    return render(request, 'home/notification_demo.html', context)


def create_notification_for_task_update(task, user, update_type, old_value=None, new_value=None, reason=None):
    """Create notification when a task is updated"""
    from .models import Notification
    
    # Determine notification type and message
    if update_type == 'status_changed':
        notification_type = 'task_status_change'
        title = f'Task Status Changed: {task.title}'
        message = f'Task "{task.title}" status changed from {old_value} to {new_value}'
        if reason:
            message += f'. Reason: {reason}'

    elif update_type == 'deadline_extended':
        notification_type = 'deadline_extended'
        title = f'Task Deadline Extended: {task.title}'
        message = f'Task "{task.title}" deadline extended to {new_value}'
        if reason:
            message += f'. Reason: {reason}'
    else:
        notification_type = 'task_update'
        title = f'Task Updated: {task.title}'
        message = f'Task "{task.title}" was updated'
        if reason:
            message += f'. Reason: {reason}'
    
    # Create notification for project owner/admin
    if task.project and task.project.client:
        # Notify the client
        Notification.create_if_not_exists(
            recipient=task.project.client,
            notification_type=notification_type,
            title=title,
            message=message,
            triggered_by=user,
            related_task=task,
            related_project=task.project
        )
    
    # Notify task assignee if different from the user making the change
    if task.assigned_to and task.assigned_to != user:
        Notification.create_if_not_exists(
            recipient=task.assigned_to,
            notification_type=notification_type,
            title=title,
            message=message,
            triggered_by=user,
            related_task=task,
            related_project=task.project
            )


@login_required
def admin_respond_to_subtask_comment(request, comment_id):
    """Admin responds to a subtask comment"""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Admin privileges required'})
    
    if request.method == 'POST':
        try:
            subtask_comment = SubTaskComment.objects.get(id=comment_id)
            response_text = request.POST.get('response_text', '').strip()
            
            if not response_text:
                return JsonResponse({'success': False, 'message': 'Response text is required'})
            
            # Create admin response comment
            admin_response = SubTaskComment.objects.create(
                subtask=subtask_comment.subtask,
                user=request.user,
                comment=response_text,
                is_admin_response=True,
                parent_comment=subtask_comment
            )
            
            # Create notification for the original commenter
            Notification.create_if_not_exists(
                recipient=subtask_comment.user,
                notification_type='subtask_comment_response',
                title=f'Admin Response to Your Comment',
                message=f'Admin {request.user.get_full_name()} has responded to your comment on subtask "{subtask_comment.subtask.title}": {response_text}',
                is_admin_notification=True,
                related_subtask=subtask_comment.subtask,
                related_subtask_comment=admin_response
            )
            
            return JsonResponse({'success': True, 'message': 'Response sent successfully'})
            
        except SubTaskComment.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Comment not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def admin_send_message(request):
    """Admin sends a message to a specific user or all users"""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Admin privileges required'})
    
    if request.method == 'POST':
        try:
            recipient_id = request.POST.get('recipient_id')
            message_text = request.POST.get('message_text', '').strip()
            message_title = request.POST.get('message_title', '').strip()
            
            if not message_text or not message_title:
                return JsonResponse({'success': False, 'message': 'Message title and text are required'})
            
            if recipient_id == 'all':
                # Send to all users
                users = User.objects.filter(is_active=True)
                for user in users:
                    Notification.create_if_not_exists(
                        recipient=user,
                        notification_type='admin_message',
                        title=message_title,
                        message=message_text,
                        is_admin_notification=True
                    )
                message = f'Message sent to {users.count()} users'
            else:
                # Send to specific user
                recipient = User.objects.get(id=recipient_id)
                Notification.create_if_not_exists(
                    recipient=recipient,
                    notification_type='admin_message',
                    title=message_title,
                    message=message_text,
                    is_admin_notification=True
                )
                message = f'Message sent to {recipient.get_full_name()}'
            
            return JsonResponse({'success': True, 'message': message})
            
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'User not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def system_logs(request):
    """System logs page for admins"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    # Log navigation to system logs page
    SystemLog.log_navigation(
        user=request.user,
        page_name='System Logs',
        page_url=request.path,
        request=request
    )
    
    # Get filter parameters
    action_filter = request.GET.get('action', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Start with all logs
    logs = SystemLog.objects.all()
    
    # Apply filters
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)
    
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)
    
    # Pagination
    paginator = Paginator(logs, 50)  # 50 logs per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'action_choices': SystemLog.ACTION_CHOICES,
        'action_filter': action_filter,
        'user_filter': user_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    # If it's an AJAX request, return only the logs table
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'home/system_logs_table.html', context)
    
    return render(request, 'home/system_logs.html', context)

def update_project_dates_from_tasks(project):
    """Update project start and end dates based on its tasks"""
    tasks = project.tasks.all()
    
    if not tasks.exists():
        return
    
    # Get all tasks with start and end dates
    tasks_with_dates = tasks.filter(start_date__isnull=False, end_date__isnull=False)
    
    if not tasks_with_dates.exists():
        return
    
    # Find earliest start date and latest end date
    earliest_start = tasks_with_dates.aggregate(Min('start_date'))['start_date__min']
    latest_end = tasks_with_dates.aggregate(Max('end_date'))['end_date__max']
    
    # Project dates are automatically calculated from task dates
    # No need to set them manually - they are read-only properties
    # Just save the project to trigger any other updates
    project.save()
@login_required
def edit_task(request, project_id, task_id):
    project = get_object_or_404(Project, id=project_id)
    task = get_object_or_404(Task, id=task_id, project=project)
    
    # Check if user is assigned to this project or is staff
    if not request.user.is_staff and request.user not in project.assigned_users.all():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Access denied. You are not assigned to this project.'})
        messages.error(request, 'Access denied. You are not assigned to this project.')
        return redirect('project_tasks', project_id=project_id)
    
    if request.method == 'POST':
        try:
            # Check if this is a JSON request for status-only update
            if request.headers.get('Content-Type') == 'application/json':
                import json
                data = json.loads(request.body)
                print(f"JSON data received: {data}")  # Debug print
                
                if 'status' in data and len(data) == 1:
                    # Status-only update
                    new_status = data['status']
                    print(f"Updating task status from '{task.status}' to '{new_status}'")  # Debug print
                    print(f"Status value type: {type(new_status)}")  # Debug print
                    print(f"Status value length: {len(new_status) if new_status else 'None'}")  # Debug print
                    
                    # Validate status value
                    valid_statuses = [choice[0] for choice in Task.STATUS_CHOICES]
                    print(f"Valid statuses: {valid_statuses}")  # Debug print
                    
                    if new_status in valid_statuses:
                        task.status = new_status
                        task.save()
                        print(f"Task status updated to '{task.status}'")  # Debug print
                        
                        # Update project dates based on all tasks
                        update_project_dates_from_tasks(project)
                        
                        return JsonResponse({'success': True, 'message': f'Task status updated to {task.get_status_display()}'})
                    else:
                        print(f"Invalid status value: '{new_status}'")  # Debug print
                        return JsonResponse({'success': False, 'error': f'Invalid status value: {new_status}'})
            
            # Regular form submission
            task.title = request.POST.get('title')
            task.description = request.POST.get('description', '')
            task.priority = request.POST.get('priority', 'medium')
            task.status = request.POST.get('status')
            task.development_status = request.POST.get('development_status', 'original_quoted')
            
            # Handle dates
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            if start_date == '':
                start_date = None
            if end_date == '':
                end_date = None
            
            task.start_date = start_date
            task.end_date = end_date
            
            # Handle assigned users
            assigned_user_ids = request.POST.getlist('assigned_users')
            task.assigned_users.clear()
            if assigned_user_ids:
                users = User.objects.filter(id__in=assigned_user_ids)
                task.assigned_users.add(*users)
            
            task.save()
            
            # Update project dates based on all tasks
            update_project_dates_from_tasks(project)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': f'Task "{task.title}" updated successfully!'})
            
            messages.success(request, f'Task "{task.title}" updated successfully!')
            return redirect('project_tasks', project_id=project_id)
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': f'Error updating task: {str(e)}'})
            messages.error(request, f'Error updating task: {str(e)}')
    
    # For AJAX requests, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # For regular requests, render the template
    context = {
        'project': project,
        'task': task,

        'status_choices': Task.STATUS_CHOICES,
    }
    
    return render(request, 'home/edit_task.html', context)

@login_required
def edit_subtask(request, project_id, task_id, subtask_id):
    project = get_object_or_404(Project, id=project_id)
    task = get_object_or_404(Task, id=task_id, project=project)
    subtask = get_object_or_404(SubTask, id=subtask_id, task=task)
    
    # Check if user is assigned to this project or is staff
    if not request.user.is_staff and request.user not in project.assigned_users.all():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Access denied. You are not assigned to this project.'})
        messages.error(request, 'Access denied. You are not assigned to this project.')
        return redirect('project_tasks', project_id=project_id)
    
    if request.method == 'POST':
        try:
            # Check if this is a JSON request for status-only update
            if request.headers.get('Content-Type') == 'application/json':
                import json
                data = json.loads(request.body)
                print(f"Subtask JSON data received: {data}")  # Debug print
                
                if 'status' in data and len(data) == 1:
                    # Status-only update
                    new_status = data['status']
                    print(f"DEBUG JSON: Updating subtask status from '{subtask.status}' to '{new_status}'")
                    print(f"DEBUG JSON: Status value type: {type(new_status)}")
                    print(f"DEBUG JSON: Status value length: {len(new_status) if new_status else 'None'}")
                    
                    # Validate status value
                    valid_statuses = [choice[0] for choice in SubTask.STATUS_CHOICES]
                    print(f"DEBUG JSON: Valid statuses: {valid_statuses}")
                    
                    if new_status in valid_statuses:
                        print(f"DEBUG JSON: Before update - Status: '{subtask.status}', Is Completed: {subtask.is_completed}")
                        subtask.status = new_status
                        # Also update is_completed based on status
                        subtask.is_completed = (new_status == 'completed')
                        subtask.save()
                        print(f"DEBUG JSON: After update - Status: '{subtask.status}', Is Completed: {subtask.is_completed}")
                        print(f"DEBUG JSON: Database save successful: {subtask.pk}")
                        
                        return JsonResponse({'success': True, 'message': f'Subtask status updated to {subtask.get_status_display()}'})
                    else:
                        print(f"DEBUG JSON: Invalid status value: '{new_status}'")
                        return JsonResponse({'success': False, 'error': f'Invalid status value: {new_status}'})
            
            # Regular form submission
            print(f"DEBUG: Form data received: {request.POST}")
            print(f"DEBUG: Current subtask status: {subtask.status}")
            
            subtask.title = request.POST.get('title')
            subtask.description = request.POST.get('description', '')
            new_status = request.POST.get('status', 'not_started')
            print(f"DEBUG: New status from form: {new_status}")
            
            subtask.status = new_status

            
            # Handle dates
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            if start_date == '': start_date = None
            if end_date == '': end_date = None
            subtask.start_date = start_date
            subtask.end_date = end_date
            
            # Update is_completed based on status
            subtask.is_completed = (new_status == 'completed')
            print(f"DEBUG: Before save - Status: '{subtask.status}', Is Completed: {subtask.is_completed}")
            subtask.save()
            print(f"DEBUG: After save - Status: '{subtask.status}', Is Completed: {subtask.is_completed}")
            print(f"DEBUG: Database save successful: {subtask.pk}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': f'Subtask "{subtask.title}" updated successfully!'})
            
            messages.success(request, f'Subtask "{subtask.title}" updated successfully!')
            return redirect('project_tasks', project_id=project_id)
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': f'Error updating subtask: {str(e)}'})
            messages.error(request, f'Error updating subtask: {str(e)}')
    
    # For AJAX requests, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # For regular requests, render the template
    context = {
        'project': project,
        'task': task,
        'subtask': subtask,
    }
    
    return render(request, 'home/edit_subtask.html', context)

@login_required
def download_report(request):
    """
    Download a PDF report directly to the user's computer
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    if request.method == 'POST':
        # Get form data
        date_range = request.POST.get('date_range', '30')
        
        try:
            date_range = int(date_range)
        except ValueError:
            date_range = 30
        
        try:
            # Generate PDF report
            pdf_file = generate_exact_pdf_report(days_filter=date_range)
            
            # Read the PDF file
            with open(pdf_file, 'rb') as f:
                pdf_content = f.read()
            
            # Clean up the temporary file
            try:
                os.unlink(pdf_file)
            except:
                pass
            
            # Create response with PDF content
            from django.http import HttpResponse
            from datetime import datetime
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            
            return response
            
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': f'Error generating PDF: {str(e)}'})
            else:
                messages.error(request, f'Error generating PDF: {str(e)}')
                return redirect('reports')
    
    # If not POST, redirect to reports page
    return redirect('reports')

@login_required
def send_project_report_ajax(request):
    """Send a comprehensive project-specific report via AJAX POST request"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff privileges required.')
        return redirect('login')
    
    from .services import GoogleCloudEmailService
    from django.utils import timezone
    from django.db.models import Q, Count, Avg
    from datetime import timedelta
    
    if request.method == 'POST':
        try:
            project_id = request.POST.get('project_id')
            client_email = request.POST.get('client_email')
            client_username = request.POST.get('client_username')
            
            if not project_id or not client_email:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Missing project information.'})
                else:
                    messages.error(request, 'Missing project information.')
                    return redirect('reports')
            
            # Get the project with related data
            try:
                project = Project.objects.select_related().prefetch_related(
                    'tasks__subtasks',
                    'tasks__assigned_users',
                    'tasks__comments',
                    'assigned_users'
                ).get(id=project_id)
                
                if not project:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': f'Project not found.'})
                    else:
                        messages.warning(request, f'Project not found.')
                        return redirect('reports')
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': f'Project not found: {str(e)}'})
                else:
                    messages.error(request, f'Project not found: {str(e)}')
                    return redirect('reports')
            
            # Enhanced project data collection
            total_tasks = project.tasks.count()
            completed_tasks = project.tasks.filter(status='completed').count()
            in_progress_tasks = project.tasks.filter(status='in_progress').count()
            not_started_tasks = project.tasks.filter(status='not_started').count()
            on_hold_tasks = project.tasks.filter(status='on_hold').count()
            guidance_required_tasks = project.tasks.filter(status='in_progress_guidance_required').count()
            
            # Get detailed subtask information
            project_subtasks = SubTask.objects.filter(task__project=project)
            total_subtasks = project_subtasks.count()
            completed_subtasks = project_subtasks.filter(is_completed=True).count()
            pending_subtasks = total_subtasks - completed_subtasks
            
            # Get priority distribution
            high_priority_tasks = project.tasks.filter(priority='high').count()
            urgent_tasks = project.tasks.filter(priority='urgent').count()
            medium_priority_tasks = project.tasks.filter(priority='medium').count()
            low_priority_tasks = project.tasks.filter(priority='low').count()
            
            # Get development status distribution
            development_statuses = project.tasks.values('development_status').annotate(count=Count('id'))
            
            # Calculate completion rates
            task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            subtask_completion_rate = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
            
            # Calculate project timeline progress
            timeline_progress = 0
            days_remaining = 0
            if project.start_date and project.end_date:
                days_elapsed = (timezone.now().date() - project.start_date).days
                total_days = (project.end_date - project.start_date).days
                if total_days > 0:
                    timeline_progress = (days_elapsed / total_days) * 100
                    days_remaining = max(0, total_days - days_elapsed)
            
            # Get recent activity (last 30 days)
            end_date = timezone.now()
            start_date = end_date - timedelta(days=30)
            
            recent_tasks = project.tasks.filter(created_at__gte=start_date).count()
            recent_subtasks = project_subtasks.filter(created_at__gte=start_date).count()
            recent_comments = sum(task.comments.filter(created_at__gte=start_date).count() for task in project.tasks.all())
            
            # Get team information
            team_members = project.assigned_users.all()
            team_size = team_members.count()
            
            # Calculate average task completion time
            completed_tasks_with_dates = project.tasks.filter(status='completed', start_date__isnull=False, end_date__isnull=False)
            avg_completion_days = 0
            if completed_tasks_with_dates.exists():
                completion_times = [(task.end_date - task.start_date).days for task in completed_tasks_with_dates]
                avg_completion_days = sum(completion_times) / len(completion_times)
            
            # Handle case where client_username might be empty
            display_client_name = client_username if client_username else "Client"
            
            # Prepare comprehensive report data
            report_data = {
                'project_id': project_id,
                'project_name': project.name,
                'client_name': client_username,
                'client_email': client_email,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'in_progress_tasks': in_progress_tasks,
                'not_started_tasks': not_started_tasks,
                'on_hold_tasks': on_hold_tasks,
                'guidance_required_tasks': guidance_required_tasks,
                'total_subtasks': total_subtasks,
                'completed_subtasks': completed_subtasks,
                'pending_subtasks': pending_subtasks,
                'high_priority_tasks': high_priority_tasks,
                'urgent_tasks': urgent_tasks,
                'medium_priority_tasks': medium_priority_tasks,
                'low_priority_tasks': low_priority_tasks,
                'task_completion_rate': task_completion_rate,
                'subtask_completion_rate': subtask_completion_rate,
                'timeline_progress': timeline_progress,
                'days_remaining': days_remaining,
                'project_status': project.get_status_display(),
                'team_size': team_size,
                'recent_activity': {
                    'tasks': recent_tasks,
                    'subtasks': recent_subtasks,
                    'comments': recent_comments
                },
                'avg_completion_days': avg_completion_days,
                'development_statuses': list(development_statuses),
                'generated_date': timezone.now().strftime("%B %d, %Y at %I:%M %p"),
                'project': {
                    'id': project.id,
                    'name': project.name,
                    'status': project.status,
                    'start_date': project.start_date.isoformat() if project.start_date else None,
                    'end_date': project.end_date.isoformat() if project.end_date else None,
                    'created_at': project.created_at.isoformat() if project.created_at else None
                }
            }
            
            print(f"Sending comprehensive project report to: {client_email}")
            
            # Send simple email with "test" message
            gmail_service = GoogleCloudEmailService()
            
            # Create styled email body with project information
            email_body = f"""<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5;">
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 20px auto; background-color: #ffffff; color: #000000; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
    <div style="background-color: #2d3748; color: #ffffff; padding: 20px; text-align: center;">
        <h1 style="margin: 0; font-size: 24px; font-weight: bold; color: #ffffff;">Your E-Click Client Progress Report</h1>
        <p style="margin: 10px 0 0 0; font-size: 14px; color: #9ca3af;">Generated on {timezone.now().strftime("%B %d, %Y at %I:%M %p")}</p>
    </div>
    
    <div style="padding: 20px; background-color: #ffffff;">
        <p style="color: #000000; font-size: 16px; margin-bottom: 10px; font-weight: bold;">Dear {display_client_name},</p>
        

        
        <p style="color: #000000; font-size: 14px; margin-bottom: 20px;">Please find your summary below. A detailed, presentation-ready PDF is attached for your records.</p>
        
        <div style="background-color: #2d3748; border: 1px solid #4a5568; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
            <h2 style="color: #ffffff; font-size: 18px; margin-top: 0; margin-bottom: 15px;">Project Summary</h2>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">
                <tr style="background-color: #4a5568; color: #ffffff;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #718096;">Project Summary</th>
                    <th style="padding: 10px; text-align: center; border: 1px solid #718096;">Totals</th>
                </tr>
                <tr style="background-color: #2d3748;">
                    <td style="padding: 10px; border: 1px solid #718096; font-weight: bold; color: #ffffff;">Total Projects</td>
                    <td style="padding: 10px; border: 1px solid #718096; text-align: center; color: #ffffff;">1</td>
                </tr>
                <tr style="background-color: #2d3748;">
                    <td style="padding: 10px; border: 1px solid #718096; font-weight: bold; color: #ffffff;">Completed Projects</td>
                    <td style="padding: 10px; border: 1px solid #718096; text-align: center; color: #ffffff;">{1 if project.status == 'completed' else 0}</td>
                </tr>
                <tr style="background-color: #2d3748;">
                    <td style="padding: 10px; border: 1px solid #718096; font-weight: bold; color: #ffffff;">Projects In Progress</td>
                    <td style="padding: 10px; border: 1px solid #718096; text-align: center; color: #ffffff;">{1 if project.status == 'in_progress' else 0}</td>
                </tr>
                <tr style="background-color: #2d3748;">
                    <td style="padding: 10px; border: 1px solid #718096; font-weight: bold; color: #ffffff;">Total Tasks</td>
                    <td style="padding: 10px; border: 1px solid #718096; text-align: center; color: #ffffff;">{total_tasks if total_tasks > 0 else 0}</td>
                </tr>
                <tr style="background-color: #2d3748;">
                    <td style="padding: 10px; border: 1px solid #718096; font-weight: bold; color: #ffffff;">Completed Tasks</td>
                    <td style="padding: 10px; border: 1px solid #718096; text-align: center; color: #ffffff;">{completed_tasks if completed_tasks > 0 else 0}</td>
                </tr>
            </table>
            
            <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                <div style="text-align: center; flex: 1; background-color: #4a5568; border-radius: 8px; padding: 15px; margin-right: 10px;">
                    <h3 style="color: #ffffff; margin: 0 0 5px 0; font-size: 16px;">Project Completion Rate</h3>
                    <p style="color: #ffffff; font-size: 18px; font-weight: bold; margin: 0;">{100 if project.status == 'completed' else 0}%</p>
                </div>
                <div style="text-align: center; flex: 1; background-color: #4a5568; border-radius: 8px; padding: 15px; margin-left: 10px;">
                    <h3 style="color: #ffffff; margin: 0 0 5px 0; font-size: 16px;">Task Completion Rate</h3>
                    <p style="color: #ffffff; font-size: 18px; font-weight: bold; margin: 0;">{task_completion_rate:.1f}%</p>
                </div>
            </div>
        </div>
        
        <div style="background-color: #4a5568; border-left: 4px solid #dc2626; padding: 15px; margin-bottom: 20px;">
            <h2 style="color: #ffffff; font-size: 18px; margin-top: 0; margin-bottom: 15px;">Project Details</h2>
            <ul style="color: #ffffff; font-size: 14px; margin: 0; padding-left: 20px;">
                <li style="margin-bottom: 8px;"><strong>Project Name:</strong> {project.name}</li>
                <li style="margin-bottom: 8px;"><strong>Current Status:</strong> {project.get_status_display()}</li>
                <li style="margin-bottom: 8px;"><strong>Team Size:</strong> {team_size} members</li>
                <li style="margin-bottom: 8px;"><strong>Recent Activity:</strong> {recent_tasks} new tasks, {recent_subtasks} new subtasks in last 30 days</li>
            </ul>
        </div>
        
        
        

        
        <!-- Closing section removed -->
    </div>
    
    <div style="background-color: #1f2937; color: #ffffff; padding: 15px; text-align: center;">
        <p style="margin: 0; font-size: 16px; font-weight: bold;">WE CARE, WE CAN, WE DELIVER</p>
    </div>
</div>
</body>
</html>"""
            
            # Generate summary PDF with the same information as the email (no Highlights)
            generated_time_str = timezone.now().strftime("%B %d, %Y at %I:%M %p")
            pdf_path = generate_project_summary_pdf(
                project=project,
                client_name=display_client_name,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                task_completion_rate=task_completion_rate,
                team_size=team_size,
                recent_tasks=recent_tasks,
                recent_subtasks=recent_subtasks,
                generated_time=generated_time_str,
            )
            
            # Send email with simple subject
            subject = f"Project Report: {project.name}"
            
            result = gmail_service.send_email(
                to_email=client_email,
                subject=subject,
                body=email_body,
                from_email=None,  # Will use OAuth2 account email
                attachments=[pdf_path]
            )
            
            # Clean up temporary PDF file
            try:
                import os
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
            except Exception:
                pass
                
            print(f"Enhanced project email service result: {result}")
            
            if result['success']:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True, 
                        'message': f'Enhanced project report sent successfully to {client_email}!',
                        'report_summary': {
                            'tasks_completed': completed_tasks,
                            'completion_rate': f"{task_completion_rate:.1f}%",
                            'timeline_progress': f"{timeline_progress:.1f}%",
                            'days_remaining': days_remaining
                        }
                    })
                else:
                    messages.success(request, f'Enhanced project report sent successfully to {client_email}!')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': result.get("error", "Unknown error")})
                else:
                    messages.error(request, f'Failed to send enhanced project report: {result.get("error", "Unknown error")}')
            
        except Exception as e:
            import traceback
            print(f"Error in enhanced project report: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': f'Error generating enhanced report: {str(e)}'})
            else:
                messages.error(request, f'Error sending enhanced project report: {str(e)}')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    else:
        return redirect('reports')

@login_required
def backup_management(request):
    """Backup management dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Only administrators can manage backups.')
        return redirect('dashboard')
    
    backups = BackupFile.objects.all()
    
    # Get backup statistics
    total_backups = backups.count()
    available_backups = backups.filter(status='available').count()
    total_size_mb = sum(backup.file_size_mb for backup in backups)
    
    context = {
        'backups': backups,
        'total_backups': total_backups,
        'available_backups': available_backups,
        'total_size_mb': round(total_size_mb, 2),
    }
    
    return render(request, 'home/backup_management.html', context)


@login_required
def create_backup(request):
    """Create a new database backup"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Only administrators can create backups.')
        return redirect('backup_management')
    
    if request.method == 'POST':
        description = request.POST.get('description', '')
        export_all = request.POST.get('export_all', 'false')
        
        try:
            from django.core.management import call_command
            from django.conf import settings
            import os
            import hashlib
            from datetime import datetime
            
            # Create backup directory if it doesn't exist
            backup_dir = os.path.join(django_settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if export_all == 'true':
                backup_filename = f"export_all_{timestamp}.json"
                backup_type = 'export'
            else:
                backup_filename = f"backup_{timestamp}.json"
                backup_type = 'manual'
            
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Create backup using Django's dumpdata command
            from io import StringIO
            output = StringIO()
            call_command('dumpdata', '--exclude', 'contenttypes', '--exclude', 'auth.permission', 
                       '--exclude', 'admin.logentry', '--exclude', 'sessions.session',
                       '--indent', '2', stdout=output)
            
            # Write to file
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(output.getvalue())
            
            # Get file size and create checksum
            file_size = os.path.getsize(backup_path)
            with open(backup_path, 'rb') as f:
                checksum = hashlib.sha256(f.read()).hexdigest()
            
            # Create BackupFile record
            backup_file = BackupFile.objects.create(
                filename=backup_filename,
                file_path=backup_path,
                file_size=file_size,
                backup_type=backup_type,
                description=description,
                created_by=request.user,
                backup_checksum=checksum,
                database_version='Django 4.2+',
                total_records=sum([User.objects.count(), Project.objects.count(), Task.objects.count(), 
                                 SubTask.objects.count(), SystemLog.objects.count()])
            )
            
            # Log the backup creation
            SystemLog.log_backup_created(request.user, backup_file, request)
            
            if export_all == 'true':
                # For export, return the file as download
                from django.http import FileResponse
                response = FileResponse(open(backup_path, 'rb'), content_type='application/json')
                response['Content-Disposition'] = f'attachment; filename="{backup_filename}"'
                return response
            else:
                messages.success(request, f'Backup created successfully: {backup_filename}')
                    
        except Exception as e:
            messages.error(request, f'Error creating backup: {str(e)}')
            # Log the error
            SystemLog.log_backup_failed(request.user, 'manual', str(e), request)
        
        return redirect('backup_management')
    

@login_required
def upload_backup(request):
    """Upload a backup file"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Only administrators can upload backups.')
        return redirect('backup_management')
    
    if request.method == 'POST':
        backup_file = request.FILES.get('backup_file')
        description = request.POST.get('description', '')
        
        if not backup_file:
            messages.error(request, 'Please select a backup file to upload.')
            return redirect('backup_management')
        
        # Validate file extension
        if not backup_file.name.endswith('.json'):
            messages.error(request, 'Only JSON backup files are allowed.')
            return redirect('backup_management')
        
        try:
            import os
            import hashlib
            from django.conf import settings
            
            # Create backup directory if it doesn't exist
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"uploaded_backup_{timestamp}.json"
            file_path = os.path.join(backup_dir, filename)
            
            # Save uploaded file
            with open(file_path, 'wb+') as destination:
                for chunk in backup_file.chunks():
                    destination.write(chunk)
            
            # Get file size and create checksum
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as f:
                checksum = hashlib.sha256(f.read()).hexdigest()
            
            # Create BackupFile record
            backup_file = BackupFile.objects.create(
                filename=filename,
                file_path=file_path,
                file_size=file_size,
                backup_type='uploaded',
                description=description,
                created_by=request.user,
                backup_checksum=checksum,
                database_version='Unknown',
                total_records=0
            )
            
            # Log the backup upload
            SystemLog.log_backup_uploaded(request.user, backup_file, request)
            
            messages.success(request, f'Backup uploaded successfully: {filename}')
            
        except Exception as e:
            messages.error(request, f'Error uploading backup: {str(e)}')
            # Log the error
            SystemLog.log_backup_failed(request.user, 'upload', str(e), request)
    
    return redirect('backup_management')


@login_required
def restore_backup(request, backup_id):
    """Restore database from a backup file"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Only administrators can restore backups.')
        return redirect('backup_management')
    
    # Check if this is a POST request
    if request.method != 'POST':
        messages.error(request, 'Invalid request method. Please use the restore button.')
        return redirect('backup_management')
    
    try:
        backup = BackupFile.objects.get(id=backup_id)
        
        if not backup.is_available:
            messages.error(request, 'Backup file is not available for restore.')
            return redirect('backup_management')
        
        # Verify file exists
        if not os.path.exists(backup.file_path):
            messages.error(request, f'Backup file not found on disk: {backup.file_path}')
            backup.status = 'corrupted'
            backup.save()
            return redirect('backup_management')
        

        
        # Verify file integrity if checksum exists
        if backup.backup_checksum:
            try:
                with open(backup.file_path, 'rb') as f:
                    current_checksum = hashlib.sha256(f.read()).hexdigest()
                
                if current_checksum != backup.backup_checksum:
                    messages.error(request, 'Backup file integrity check failed. File may be corrupted.')
                    backup.status = 'corrupted'
                    backup.save()
                    return redirect('backup_management')
            except Exception as e:
                messages.error(request, f'Error checking file integrity: {str(e)}')
                return redirect('backup_management')
        
        # Create a backup before restore (safety measure)
        safety_backup_dir = os.path.join(django_settings.BASE_DIR, 'backups')
        os.makedirs(safety_backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safety_filename = f"pre_restore_backup_{timestamp}.json"
        safety_path = os.path.join(safety_backup_dir, safety_filename)
        
        try:
            # Create safety backup using management command
            from django.core.management import call_command
            from io import StringIO
            
            # Capture the output of dumpdata
            output = StringIO()
            call_command('dumpdata', 
                        '--exclude', 'contenttypes', 
                        '--exclude', 'auth.permission', 
                        '--exclude', 'admin.logentry', 
                        '--exclude', 'sessions.session',
                        '--indent', '2', 
                        stdout=output)
            
            # Write to file
            with open(safety_path, 'w', encoding='utf-8') as f:
                f.write(output.getvalue())
            
            # Create safety backup record
            safety_size = os.path.getsize(safety_path)
            with open(safety_path, 'rb') as f:
                safety_checksum = hashlib.sha256(f.read()).hexdigest()
            
            safety_backup = BackupFile.objects.create(
                filename=safety_filename,
                file_path=safety_path,
                file_size=safety_size,
                backup_type='automatic',
                description='Safety backup created before restore operation',
                created_by=request.user,
                backup_checksum=safety_checksum,
                database_version='Django 4.2+',
                total_records=sum([
                    User.objects.count(), 
                    Project.objects.count(), 
                    Task.objects.count(), 
                    SubTask.objects.count(), 
                    SystemLog.objects.count()
                ])
            )
            
            messages.info(request, f'Safety backup created: {safety_filename}')
            
        except Exception as e:
            messages.warning(request, f'Could not create safety backup: {str(e)}. Proceeding with restore...')
        
        try:
            # Perform the restore
            from django.core.management import call_command
            
            # Log the restore attempt
            messages.info(request, f'Starting restore from backup: {backup.filename}')
            
            # Clear existing data (excluding system tables)
            call_command('flush', '--no-input')
            
            # Restore from backup
            call_command('loaddata', backup.file_path)
            
            # Update backup status
            backup.status = 'restored'
            backup.restored_at = timezone.now()
            backup.restored_by = request.user
            backup.save()
            
            # Log the restore operation
            SystemLog.log_backup_restored(request.user, backup, request)
            
            messages.success(request, f'Database restored successfully from backup: {backup.filename}')
            
        except Exception as e:
            messages.error(request, f'Error during restore operation: {str(e)}')
            SystemLog.log_backup_failed(request.user, 'restore', str(e), request)
            
            # Try to restore from safety backup if it exists
            if 'safety_backup' in locals() and os.path.exists(safety_path):
                try:
                    messages.info(request, 'Attempting to restore from safety backup...')
                    call_command('flush', '--no-input')
                    call_command('loaddata', safety_path)
                    messages.success(request, 'Successfully restored from safety backup.')
                except Exception as restore_error:
                    messages.error(request, f'Failed to restore from safety backup: {str(restore_error)}')
            
            return redirect('backup_management')
        
    except BackupFile.DoesNotExist:
        messages.error(request, 'Backup file not found.')
    except Exception as e:
        messages.error(request, f'Error restoring backup: {str(e)}')
        # Log the error
        SystemLog.log_backup_failed(request.user, 'restore', str(e), request)
    
    return redirect('backup_management')


@login_required
def delete_backup(request, backup_id):
    """Delete a backup file"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Only administrators can delete backups.')
        return redirect('backup_management')
    
    try:
        backup = BackupFile.objects.get(id=backup_id)
        
        # Delete physical file
        import os
        if os.path.exists(backup.file_path):
            os.remove(backup.file_path)
        
        # Log deletion before removing record
        SystemLog.log_backup_deleted(request.user, backup, request)
        
        # Delete database record
        backup.delete()
        
        messages.success(request, f'Backup deleted successfully: {backup.filename}')
        
    except BackupFile.DoesNotExist:
        messages.error(request, 'Backup file not found.')
    except Exception as e:
        messages.error(request, f'Error deleting backup: {str(e)}')
    
    return redirect('backup_management')


@login_required
def download_backup(request, backup_id):
    """Download a backup file"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Only administrators can download backups.')
        return redirect('backup_management')
    
    try:
        backup = BackupFile.objects.get(id=backup_id)
        
        if not backup.is_available:
            messages.error(request, 'Backup file is not available for download.')
            return redirect('backup_management')
        
        import os
        from django.http import FileResponse
        
        if os.path.exists(backup.file_path):
            response = FileResponse(open(backup.file_path, 'rb'))
            response['Content-Type'] = 'application/json'
            response['Content-Disposition'] = f'attachment; filename="{backup.filename}"'
            
            # Log the download
            SystemLog.log_backup_downloaded(request.user, backup, request)
            
            return response
        else:
            messages.error(request, 'Backup file not found on disk.')
            
    except BackupFile.DoesNotExist:
        messages.error(request, 'Backup file not found.')
    except Exception as e:
        messages.error(request, f'Error downloading backup: {str(e)}')
    
    return redirect('backup_management')
def ai_chat(request):
    """AI Chat endpoint for robot interactions"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            question = data.get('question', '').strip()
            user_id = data.get('user_id', '')
            
            if not question:
                return JsonResponse({'error': 'Question is required'}, status=400)
            
            # Generate session ID if not provided
            session_id = request.session.get('ai_session_id')
            if not session_id:
                session_id = str(uuid.uuid4())
                request.session['ai_session_id'] = session_id
            
            # Get AI response
            answer, confidence, response_time = ai_service.get_response(
                question=question,
                user_id=user_id,
                session_id=session_id
            )
            
            return JsonResponse({
                'answer': answer,
                'confidence': round(confidence, 2),
                'response_time': round(response_time, 3),
                'session_id': session_id
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST method required'}, status=405)

def ai_feedback(request):
    """Handle AI conversation feedback for learning"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            conversation_id = data.get('conversation_id')
            was_helpful = data.get('was_helpful')
            
            if conversation_id is not None and was_helpful is not None:
                ai_service.learn_from_feedback(conversation_id, was_helpful)
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'error': 'Missing required fields'}, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST method required'}, status=405)

def ai_stats(request):
    """Get AI learning statistics"""
    if request.method == 'GET':
        try:
            stats = ai_service.get_learning_stats()
            return JsonResponse(stats)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'GET method required'}, status=405)

@login_required
def ai_knowledge_management(request):
    """Admin interface for managing AI knowledge base"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Only administrators can manage AI knowledge.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            question = request.POST.get('question', '').strip()
            answer = request.POST.get('answer', '').strip()
            category = request.POST.get('category', '').strip()
            tags = request.POST.get('tags', '').strip()
            
            if question and answer:
                tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()] if tags else []
                ai_service.add_knowledge(question, answer, category, tag_list)
                messages.success(request, 'Knowledge added successfully!')
            else:
                messages.error(request, 'Question and answer are required.')
        
        elif action == 'initialize':
            ai_service.initialize_knowledge_base()
            messages.success(request, 'Knowledge base initialized with basic information!')
    
    # Get knowledge base entries
    knowledge_entries = AIKnowledgeBase.objects.all()
    stats = ai_service.get_learning_stats()
    
    context = {
        'knowledge_entries': knowledge_entries,
        'stats': stats
    }
    
    return render(request, 'home/ai_knowledge_management.html', context)

def nab_summary(request):
    """NAB Project Summary page with black theme"""
    from datetime import datetime
    
    context = {
        'current_date': datetime.now().strftime('%B %Y'),
    }
    
    return render(request, 'nab_summary.html', context)