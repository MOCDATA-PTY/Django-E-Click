from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth import get_user_model

User = get_user_model()
from django.http import JsonResponse

from django.conf import settings as django_settings
from django.utils import timezone
from django.db.models import Min, Max, Count, Q, Avg, F, ExpressionWrapper, fields
from django.core.paginator import Paginator
from django.db import transaction
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
import logging
from .ai_service import ai_service
from .decorators import require_admin_access
# from .services import GoogleCloudEmailService
import uuid

# Setup logger
logger = logging.getLogger(__name__)


# Create email service instance - now using Gmail API with OAuth2
# email_service = SimpleEmailService()  # Commented out - using Gmail API instead


def captcha_token_view(request):
    """Return a signed, time-limited captcha token. Called via AJAX when the checkbox passes."""
    from django.core import signing
    token = signing.dumps('captcha_ok', salt='eclick-captcha')
    return JsonResponse({'token': token})


def captcha_challenge_view(request):
    """Generate a shape-selection captcha challenge. Correct answers stored in session only."""
    shapes = ['circle', 'triangle', 'square', 'star', 'diamond', 'hexagon']
    colors = ['red', 'blue', 'green', 'orange', 'purple', 'yellow']

    if random.choice([True, False]):  # challenge by shape
        target = random.choice(shapes)
        prompt = 'Select all {}s'.format(target)
        correct = [{'shape': target, 'color': random.choice(colors)} for _ in range(3)]
        others = [s for s in shapes if s != target]
        distractors = [{'shape': random.choice(others), 'color': random.choice(colors)} for _ in range(6)]
    else:  # challenge by color
        target = random.choice(colors)
        prompt = 'Select all {} shapes'.format(target)
        correct = [{'shape': random.choice(shapes), 'color': target} for _ in range(3)]
        other_colors = [c for c in colors if c != target]
        distractors = [{'shape': random.choice(shapes), 'color': random.choice(other_colors)} for _ in range(6)]

    tagged = [dict(t, correct=True) for t in correct] + [dict(t, correct=False) for t in distractors]
    random.shuffle(tagged)

    correct_ids = [i for i, t in enumerate(tagged) if t['correct']]
    tiles = [{'id': i, 'shape': t['shape'], 'color': t['color']} for i, t in enumerate(tagged)]

    request.session['captcha_correct_ids'] = correct_ids
    request.session.modified = True

    return JsonResponse({'prompt': prompt, 'tiles': tiles})


def captcha_verify_view(request):
    """Verify shape-selection captcha. Returns signed token on correct selection."""
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)

    correct_ids = request.session.get('captcha_correct_ids')
    if not correct_ids:
        return JsonResponse({'success': False})

    selected = sorted([int(x) for x in request.POST.getlist('selected') if x.isdigit()])
    if selected == sorted(correct_ids):
        from django.core import signing
        token = signing.dumps('captcha_ok', salt='eclick-captcha')
        del request.session['captcha_correct_ids']
        request.session.modified = True
        return JsonResponse({'success': True, 'token': token})

    return JsonResponse({'success': False})


def home(request):
    """Public Home page (index)"""
    from django.conf import settings
    context = {
        'recaptcha_site_key': settings.RECAPTCHA_PUBLIC_KEY
    }
    return render(request, 'home/index.html', context)

def about(request):
    """Public About page"""
    return render(request, 'home/about.html')

def solutions(request):
    """Public Solutions page"""
    return render(request, 'home/solutions.html')

def contact(request):
    """Public Contact page with form handling"""
    from django.conf import settings
    import requests

    if request.method == 'POST':
        try:
            # Extract form data
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            subject = request.POST.get('subject', '').strip()
            message = request.POST.get('message', '').strip()
            
            # Honeypot — must be empty; bots tend to fill every field
            if request.POST.get('website', '').strip():
                return JsonResponse({'success': False, 'message': 'Invalid submission.'})

            # Rate limiting — 1 submission per 60 seconds per IP
            from django.core.cache import cache
            client_ip = request.META.get('REMOTE_ADDR', 'unknown')
            rate_key = f'contact_rate_{client_ip}'
            if cache.get(rate_key):
                return JsonResponse({'success': False, 'message': 'Too many requests. Please wait before trying again.'})

            # Basic validation
            if not all([first_name, last_name, email, subject, message]):
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.'
                })

            # Google reCAPTCHA v2 verification
            recaptcha_response = request.POST.get('g-recaptcha-response', '').strip()
            if not recaptcha_response:
                return JsonResponse({
                    'success': False,
                    'captcha_error': True,
                    'message': 'Please complete the reCAPTCHA verification.',
                })

            # Verify with Google
            recaptcha_data = {
                'secret': settings.RECAPTCHA_PRIVATE_KEY,
                'response': recaptcha_response,
                'remoteip': request.META.get('REMOTE_ADDR', '')
            }

            try:
                recaptcha_verify = requests.post(
                    'https://www.google.com/recaptcha/api/siteverify',
                    data=recaptcha_data,
                    timeout=5
                )
                recaptcha_result = recaptcha_verify.json()

                if not recaptcha_result.get('success', False):
                    return JsonResponse({
                        'success': False,
                        'captcha_error': True,
                        'message': 'reCAPTCHA verification failed. Please try again.',
                    })
            except Exception as e:
                logger.error(f"reCAPTCHA verification error: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'captcha_error': True,
                    'message': 'reCAPTCHA verification error. Please try again.',
                })

            # Email validation
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                return JsonResponse({
                    'success': False,
                    'message': 'Please enter a valid email address.'
                })
            
            # Send email notification using the same email service that works for reports
            from .email_service import email_service

            # Prepare email content
            email_subject = f"New Contact Form Submission – E-Click Website"
            email_message = f"""New Contact Form Submission – E-Click Website

Name: {first_name} {last_name}
Email: {email}

Phone: {phone}
Subject: {subject}

Message:
{message}"""

            try:
                # Use the same email service that successfully sends reports
                # Send to info@eclick.co.za with CC to admin@eclick.co.za
                result = email_service.send_email(
                    to_email='info@eclick.co.za',
                    subject=email_subject,
                    body=email_message,
                    cc_emails=['admin@eclick.co.za']
                )

                # Set rate-limit cooldown on success
                cache.set(rate_key, True, 60)

                if result.get('success'):
                    return JsonResponse({
                        'success': True,
                        'message': 'Thank you for your message! We will get back to you soon.'
                    })
                else:
                    print(f"Email sending failed: {result.get('error')}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Thank you for your message! We will get back to you soon.'
                    })

            except Exception as e:
                # Log the error but don't expose it to the user
                print(f"Email sending failed: {e}")
                return JsonResponse({
                    'success': True,  # Still return success to avoid user confusion
                    'message': 'Thank you for your message! We will get back to you soon.'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred while processing your request. Please try again.'
            })
    
    context = {
        'recaptcha_site_key': settings.RECAPTCHA_PUBLIC_KEY
    }
    return render(request, 'home/contact.html', context)

def services(request):
    """Public Services page (supports existing template links)"""
    return render(request, 'home/services.html')

def clients(request):
    """Public Clients page"""
    return render(request, 'home/clients.html')

def login_view(request):
    """Simplified login view for both admin and clients without CSRF"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if not username or not password:
            messages.error(request, 'Username and password are required')
            return render(request, 'home/login.html')
        
        # First try to authenticate as a Django user (admin/staff)
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_active:
            # Admin/Staff login successful
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        
        # Try to authenticate as a client
        try:
            client = Client.objects.get(username=username, is_active=True)
            if client.password:
                # Check if password uses Django hashing (starts with pbkdf2_sha256)
                if client.password.startswith('pbkdf2_sha256'):
                    # Use Django's check_password for proper hashing
                    from django.contrib.auth.hashers import check_password
                    if check_password(password, client.password):
                        # Client login successful
                        client.last_login = timezone.now()
                        client.save(update_fields=['last_login'])
                        request.session['client_id'] = client.id
                        request.session['client_username'] = client.username
                        return redirect('client_dashboard')
                    else:
                        pass
                else:
                    # Legacy SHA256 hashing (for backward compatibility)
                    password_hash = hashlib.sha256(password.encode()).hexdigest()
                    if client.password == password_hash:
                        # Client login successful
                        client.last_login = timezone.now()
                        client.save(update_fields=['last_login'])
                        request.session['client_id'] = client.id
                        request.session['client_username'] = client.username
                        return redirect('client_dashboard')
                    else:
                        pass
            else:
                pass
        except Client.DoesNotExist:
            pass
    
    return render(request, 'home/login.html')

@login_required
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
    
    if request.user.is_staff:
        # Admin/Staff Dashboard - Show all projects and statistics
        # Calculate statistics
        total_projects = Project.objects.count()
        active_projects = Project.objects.filter(status='in_progress').count()
        completed_projects = Project.objects.filter(status='completed').count()
        
        # Calculate new projects this week
        week_ago = current_date - timedelta(days=7)
        new_projects = Project.objects.filter(created_at__gte=week_ago).count()
        
        # Calculate active percentage
        active_percentage = (active_projects / total_projects * 100) if total_projects > 0 else 0
        
        # Task statistics
        total_tasks = Task.objects.count()
        completed_tasks = Task.objects.filter(status='completed').count()
        pending_tasks = Task.objects.filter(status__in=['not_started', 'in_progress']).count()
        
        # Calculate completed tasks this week
        completed_this_week = Task.objects.filter(
            status='completed',
            updated_at__gte=week_ago
        ).count()
        
        # Calculate pending percentage
        pending_percentage = (pending_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Performance metrics
        completion_rate = (completed_projects / total_projects * 100) if total_projects > 0 else 0
        efficiency_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Calculate on-time delivery rate (simplified)
        overdue_tasks = Task.objects.filter(
            end_date__lt=current_date.date(),
            status__in=['not_started', 'in_progress']
        ).count()
        on_time_rate = ((total_tasks - overdue_tasks) / total_tasks * 100) if total_tasks > 0 else 0
        
        # Recent activities (simplified for now)
        recent_activities = []
        
        # Add recent project activities
        recent_projects = Project.objects.order_by('-updated_at')[:5]
        for project in recent_projects:
            recent_activities.append({
                'text': f'Project "{project.name}" was updated',
                'time': project.updated_at.strftime('%b %d, %H:%M')
            })
        
        # Add recent task activities
        recent_tasks = Task.objects.order_by('-updated_at')[:5]
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
        # Get user's assigned projects
        assigned_projects = Project.objects.filter(assigned_users=request.user)
        
        # Calculate user-specific statistics
        total_assigned_projects = assigned_projects.count()
        active_assigned_projects = assigned_projects.filter(status='in_progress').count()
        completed_assigned_projects = assigned_projects.filter(status='completed').count()
        
        # Get user's assigned tasks
        assigned_tasks = Task.objects.filter(project__in=assigned_projects)
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
    
    return render(request, 'home/dashboard.html', context)

@login_required
def analytics(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Admin privileges required.')
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
        client_projects = Project.objects.filter(
            Q(clients=client) | Q(client_username=client.username)
        ).distinct()
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
                            base_username = client_email.split('@')[0]
                            # Check if username already exists and make it unique
                            counter = 1
                            client_username = base_username
                            while Client.objects.filter(username=client_username).exists():
                                client_username = f"{base_username}{counter}"
                                counter += 1
                        
                        # Create new client
                        try:
                            new_client = Client.objects.create(
                                username=client_username,
                                email=client_email,
                                is_active=True
                            )
                        except Exception as e:
                            messages.error(request, f'Error creating client: {str(e)}')
                            return redirect('projects_page')
                        
                        # Generate and send OTP for new client
                        otp = new_client.generate_otp()
                        
                        # Send OTP email using SimpleEmailService with Microsoft SMTP
                        site_url = request.build_absolute_uri('/').rstrip('/')
                        from .email_service import SimpleEmailService
                        email_service = SimpleEmailService()
                        email_result = email_service.send_email(
                            to_email=client_email,
                            subject=f"Set Your Password - {name} Project",
                            body=f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p>Dear {client_username},</p>

    <p>Welcome to the {name} project. Please use the One-Time Password (OTP) below to set your password:</p>

    <p><strong>OTP: {otp}</strong></p>

    <p>You can set your password here: {site_url}/client/setup-password/?username={client_username}</p>

    <p>This OTP is valid for 24 hours.</p>

    <p>Best regards,<br>E-Click Project Management Team</p>
</body>
</html>""",
                            from_email=None  # Will use default from settings
                        )
                        
                        if email_result['success']:
                            messages.success(request, f'Project "{name}" created successfully! OTP email sent to {client_email}')
                        else:
                            messages.warning(request, f'Project "{name}" created successfully! OTP email failed: {email_result.get("error", "Unknown error")}')
                
                # Create project (dates will be calculated from tasks)
                try:
                    project = Project.objects.create(
                        name=name,
                        client=client,
                        client_username=client_username,
                        client_email=client_email,
                        status=status
                    )
                except Exception as e:
                    messages.error(request, f'Error creating project: {str(e)}')
                    return redirect('projects_page')
                
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
                        
                        # Get priority for this task
                        task_priority = request.POST.get(f'task_priority_{task_counter}', 'medium')
                        
                        # Create task
                        try:
                            task = Task.objects.create(
                                project=project,
                                title=task_title,
                                description=task_description,
                                status=task_status,
                                development_status=task_development_status,
                                priority=task_priority,
                                start_date=task_start_date,
                                end_date=task_end_date
                            )
                        except Exception as e:
                            messages.error(request, f'Error creating task "{task_title}": {str(e)}')
                            return redirect('projects_page')
                        
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
                                
                                # Get priority for this subtask
                                subtask_priority = request.POST.get(f'subtask_priority_{task_counter}_{subtask_counter}', 'medium')
                                
                                try:
                                    SubTask.objects.create(
                                        task=task,
                                        title=subtask_title,
                                        description=subtask_description,
                                        status=subtask_status,
                                        priority=subtask_priority,
                                        start_date=subtask_start_date,
                                        end_date=subtask_end_date
                                    )
                                except Exception as e:
                                    messages.error(request, f'Error creating subtask "{subtask_title}": {str(e)}')
                                    return redirect('projects_page')
                            
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
@login_required
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

            # Also update the Client model email if the client exists
            # This ensures the email is synced between Project and Client models
            if project.client_username:
                try:
                    client_obj = Client.objects.get(username=project.client_username)
                    if client_obj.email != project.client_email:
                        old_email = client_obj.email
                        client_obj.email = project.client_email
                        client_obj.save()
                        logger.info(f"Synced client email from {old_email} to {project.client_email} for {project.client_username}")
                except Client.DoesNotExist:
                    logger.warning(f"Client with username {project.client_username} not found in Client model")

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

            # Update assigned clients/investors
            assigned_client_ids = request.POST.getlist('assigned_clients')
            if assigned_client_ids:
                assigned_clients = Client.objects.filter(id__in=assigned_client_ids)
                project.clients.set(assigned_clients)
            else:
                project.clients.clear()

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

    # Get all clients for assignment dropdown
    all_clients = Client.objects.filter(is_active=True).order_by('username')

    return render(request, 'home/edit_project.html', {
        'project': project,
        'all_users': all_users,
        'all_clients': all_clients
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
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Admin privileges required.')
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
        # Get projects for this client using the new ManyToMany relationship
        # Also include projects that have this client in their client_username field (legacy)
        client_projects = Project.objects.filter(
            Q(clients=client) | Q(client_username=client.username)
        ).distinct()
        # Store count separately to avoid overriding the ManyToMany 'projects' attribute
        client.project_list = client_projects
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

def generate_html_pdf_report(days_filter=30):
    """
    Generate PDF report - now uses simplified 2-page version for better information display
    """
    try:
        # Use the new simplified 2-page report
        return generate_simple_2page_report(days_filter)
    except Exception as e:
        logger.error(f"Error generating simplified PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        # Fall back to complex version if simplified fails
        return generate_exact_pdf_report(days_filter)

def generate_html_pdf_report_OLD(days_filter=30):
    """
    OLD VERSION - Generate professional PDF from HTML template using xhtml2pdf
    Guaranteed beautiful layout with E-Click branding - Works on all platforms
    """
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    import tempfile
    import os
    from datetime import datetime

    try:
        # Get report data
        report_data = generate_pdf_report_data(days_filter)

        # Extract variables
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
        total_users = report_data['total_users']
        active_users = report_data['active_users']
        top_projects = report_data['top_projects']

        # Calculate rates
        project_completion_rate = round((projects_completed / total_projects * 100) if total_projects > 0 else 0, 1)
        task_completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)
        user_engagement_rate = round((active_users / total_users * 100) if total_users > 0 else 0, 1)

        # Get projects for Gantt chart
        all_projects = Project.objects.all().prefetch_related('tasks')
        projects_with_dates = [p for p in all_projects if p.start_date and p.end_date]
        projects_with_dates.sort(key=lambda p: p.start_date)
        projects_for_gantt = projects_with_dates[:10]

        # Calculate Gantt chart data
        gantt_projects = []
        if projects_for_gantt:
            min_date = min(p.start_date for p in projects_for_gantt)
            max_date = max(p.end_date for p in projects_for_gantt)
            total_days = (max_date - min_date).days + 1

            for project in projects_for_gantt:
                start_days = (project.start_date - min_date).days
                duration_days = (project.end_date - project.start_date).days + 1
                start_percent = (start_days / total_days) * 100
                duration_percent = (duration_days / total_days) * 100

                # Calculate progress
                proj_tasks = project.tasks.all()
                total_proj_tasks = proj_tasks.count()
                completed_proj_tasks = proj_tasks.filter(status='completed').count()
                progress = round((completed_proj_tasks / total_proj_tasks * 100) if total_proj_tasks > 0 else 0)

                # Status class
                status_class = 'in-progress' if project.status == 'in_progress' else 'completed' if project.status == 'completed' else 'planned'

                gantt_projects.append({
                    'name': project.name,
                    'start_percent': start_percent,
                    'duration_percent': duration_percent,
                    'progress': progress,
                    'status_class': status_class
                })

        # Get all projects for overview table
        all_projects_list = []
        for proj in all_projects[:15]:
            start_str = proj.start_date.strftime('%m/%d/%y') if proj.start_date else 'N/A'
            end_str = proj.end_date.strftime('%m/%d/%y') if proj.end_date else 'N/A'

            proj_tasks = Task.objects.filter(project=proj)
            total_proj_tasks = proj_tasks.count()
            completed_proj_tasks = proj_tasks.filter(status='completed').count()
            progress_pct = round((completed_proj_tasks / total_proj_tasks * 100) if total_proj_tasks > 0 else 0)

            status_map = {
                'planned': 'Planned',
                'in_progress': 'In Progress',
                'completed': 'Completed'
            }
            status_display = status_map.get(proj.status, proj.status)

            all_projects_list.append({
                'name': proj.name,
                'client': proj.client,
                'status': proj.status.replace('_', '-'),
                'status_display': status_display,
                'start_date_str': start_str,
                'end_date_str': end_str,
                'progress_pct': progress_pct
            })

        # Generate recommendations
        recommendations = []
        if project_completion_rate < 60:
            recommendations.append("Accelerate Delivery: Focus on completing projects in progress to improve overall completion rate")
        if task_completion_rate < 50:
            recommendations.append("Task Prioritization: Implement task prioritization framework to increase completion velocity")
        if user_engagement_rate < 70:
            recommendations.append("User Engagement: Develop user engagement strategies to increase active participation")
        if projects_in_progress > projects_completed * 2:
            recommendations.append("Resource Optimization: Consider reallocating resources to balance project pipeline")
        if project_completion_rate >= 80:
            recommendations.append("Maintain Excellence: Current performance is excellent - continue current practices")
        if not recommendations:
            recommendations.append("Continuous Monitoring: Track key metrics regularly to identify improvement opportunities")

        # Prepare context for template
        context = {
            'start_date': start_date.strftime("%B %d, %Y"),
            'end_date': end_date.strftime("%B %d, %Y"),
            'generated_date': timezone.now().strftime("%B %d, %Y at %I:%M %p"),
            'total_projects': total_projects,
            'projects_in_progress': projects_in_progress,
            'projects_completed': projects_completed,
            'projects_planned': projects_planned,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'not_started_tasks': not_started_tasks,
            'total_users': total_users,
            'active_users': active_users,
            'project_completion_rate': project_completion_rate,
            'task_completion_rate': task_completion_rate,
            'user_engagement_rate': user_engagement_rate,
            'projects_for_gantt': gantt_projects,
            'all_projects': all_projects_list,
            'top_projects': top_projects[:5],
            'recommendations': recommendations,
        }

        # Render HTML
        html_string = render_to_string('home/pdf_report_template.html', context)

        # Generate PDF
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        descriptive_filename = f"E-Click_Report_{timestamp}.pdf"
        pdf_path = os.path.join(temp_dir, descriptive_filename)

        # Generate PDF from HTML using xhtml2pdf
        with open(pdf_path, 'wb') as pdf_file:
            pisa_status = pisa.CreatePDF(html_string, dest=pdf_file)

            if pisa_status.err:
                raise Exception(f"xhtml2pdf error: {pisa_status.err}")

        logger.info(f"PDF generated successfully using xhtml2pdf: {pdf_path}")
        return pdf_path

    except Exception as e:
        logger.error(f"Error generating HTML PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        # Fall back to old method if HTML generation fails
        return generate_exact_pdf_report(days_filter)


def create_plotly_gantt_charts(projects):
    """
    Create professional Gantt charts using Plotly for each project
    Returns list of paths to generated image files
    """
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
        import pandas as pd
        from datetime import datetime, timedelta
        import tempfile
        import os

        print("[INFO] Using Plotly for professional Gantt charts")

        if not projects:
            return []

        chart_paths = []
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Color mapping for E-Click branding
        color_map = {
            'completed': '#10b981',  # Green
            'in_progress': '#dc2626',  # E-Click Red
            'planned': '#9ca3af',  # Gray
            'not_started': '#d1d5db'  # Light gray
        }

        # Create a separate chart for each project
        for proj_idx, project in enumerate(projects):
            if not project.start_date or not project.end_date:
                continue

            # Collect items for this project
            tasks_data = []

            # Add project itself
            tasks_data.append({
                'Task': f"<b>{project.name}</b>",
                'Start': project.start_date.strftime('%Y-%m-%d'),
                'Finish': project.end_date.strftime('%Y-%m-%d'),
                'Resource': 'PROJECT',
                'Status': project.status
            })

            # Add tasks
            for task in project.tasks.all():
                if task.start_date and task.end_date:
                    tasks_data.append({
                        'Task': f"  {task.title}",
                        'Start': task.start_date.strftime('%Y-%m-%d'),
                        'Finish': task.end_date.strftime('%Y-%m-%d'),
                        'Resource': 'TASK',
                        'Status': task.status
                    })

                    # Add subtasks
                    for subtask in task.subtasks.all():
                        if subtask.start_date and subtask.end_date:
                            tasks_data.append({
                                'Task': f"    {subtask.title}",
                                'Start': subtask.start_date.strftime('%Y-%m-%d'),
                                'Finish': subtask.end_date.strftime('%Y-%m-%d'),
                                'Resource': 'SUBTASK',
                                'Status': subtask.status
                            })

            if not tasks_data:
                continue

            # Create Plotly Gantt chart using timeline approach
            fig = go.Figure()

            # Add bars for each task/subtask
            for i, task in enumerate(tasks_data):
                color = color_map.get(task['Status'], '#6b7280')

                # Convert to datetime
                start_date = pd.to_datetime(task['Start'])
                finish_date = pd.to_datetime(task['Finish'])
                duration_days = (finish_date - start_date).days + 1

                # Create bar trace with proper date range
                fig.add_trace(go.Bar(
                    name=task['Task'],
                    x=[finish_date],  # End date
                    y=[task['Task']],
                    base=start_date,  # Start date
                    orientation='h',
                    marker=dict(
                        color=color,
                        line=dict(color='black', width=1)
                    ),
                    text=f"{duration_days}d",
                    textposition='inside',
                    textfont=dict(color='white', size=10, family='Arial Bold'),
                    hovertemplate=f"<b>{task['Task']}</b><br>Start: {task['Start']}<br>End: {task['Finish']}<br>Duration: {duration_days} days<br><extra></extra>",
                    showlegend=False,
                    width=0.6
                ))

            # Update layout for professional appearance
            fig.update_layout(
                title=dict(
                    text=f"<b>{project.name} - Project Timeline</b>",
                    font=dict(size=20, color='#000000', family='Arial Black')
                ),
                xaxis=dict(
                    title="Timeline",
                    type='date',
                    gridcolor='#e5e7eb',
                    showgrid=True,
                    tickformat='%b %d<br>%Y',
                    tickfont=dict(size=11),
                    dtick='M1'  # Show monthly ticks
                ),
                yaxis=dict(
                    title="",
                    autorange="reversed",
                    tickfont=dict(size=11),
                    gridcolor='#e5e7eb',
                    showgrid=True
                ),
                plot_bgcolor='white',
                paper_bgcolor='white',
                height=max(500, len(tasks_data) * 40),  # Dynamic height
                width=1400,  # Wide chart
                margin=dict(l=300, r=50, t=80, b=80),  # More left margin for task names
                font=dict(family='Arial', size=12),
                hovermode='closest',
                barmode='overlay'
            )

            # Add legend manually
            fig.add_trace(go.Bar(x=[None], y=[None], marker=dict(color='#dc2626'), name='In Progress', showlegend=True))
            fig.add_trace(go.Bar(x=[None], y=[None], marker=dict(color='#10b981'), name='Completed', showlegend=True))
            fig.add_trace(go.Bar(x=[None], y=[None], marker=dict(color='#9ca3af'), name='Planned', showlegend=True))

            # Save to temp file as high-quality image
            chart_path = os.path.join(temp_dir, f"gantt_project_{proj_idx}_{timestamp}.png")
            fig.write_image(chart_path, format='png', width=1400, height=max(500, len(tasks_data) * 40), scale=2)

            # Verify file was created
            if os.path.exists(chart_path):
                chart_paths.append(chart_path)
                logger.info(f"Plotly chart created: {chart_path}")
                print(f"[OK] Plotly chart {proj_idx + 1} created successfully")
            else:
                logger.error(f"Plotly chart file was not created: {chart_path}")
                print(f"[ERROR] Plotly chart {proj_idx + 1} file not created")

        print(f"[SUCCESS] Created {len(chart_paths)} Plotly charts")
        return chart_paths

    except ImportError as e:
        error_msg = f"Plotly not installed: {str(e)}. Falling back to matplotlib."
        logger.error(error_msg)
        print(f"[WARNING] {error_msg}")
        # Fall back to matplotlib if Plotly not available
        return create_matplotlib_gantt_fallback(projects)
    except Exception as e:
        error_msg = f"Error creating Plotly Gantt charts: {str(e)}"
        logger.error(error_msg)
        print(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        return create_matplotlib_gantt_fallback(projects)


def create_matplotlib_gantt_fallback(projects):
    """
    Matplotlib fallback for Gantt charts if Plotly fails
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime, timedelta
    import tempfile
    import os

    print("[WARNING] Using matplotlib fallback (Plotly unavailable)")

    if not projects:
        return []

    try:
        chart_paths = []
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        color_map = {
            'completed': '#10b981',
            'in_progress': '#dc2626',
            'planned': '#9ca3af',
            'not_started': '#d1d5db'
        }

        for proj_idx, project in enumerate(projects):
            if not project.start_date or not project.end_date:
                continue

            items = []
            items.append({
                'name': f"[PROJECT] {project.name}",
                'start': project.start_date,
                'end': project.end_date,
                'type': 'project',
                'status': project.status,
                'level': 0
            })

            for task in project.tasks.all():
                if task.start_date and task.end_date:
                    items.append({
                        'name': f"  [TASK] {task.title}",
                        'start': task.start_date,
                        'end': task.end_date,
                        'type': 'task',
                        'status': task.status,
                        'level': 1
                    })

                    for subtask in task.subtasks.all():
                        if subtask.start_date and subtask.end_date:
                            items.append({
                                'name': f"    [SUBTASK] {subtask.title}",
                                'start': subtask.start_date,
                                'end': subtask.end_date,
                                'type': 'subtask',
                                'status': subtask.status,
                                'level': 2
                            })

            if not items:
                continue

            height = max(8, len(items) * 0.5)
            fig, ax = plt.subplots(figsize=(16, height))

            for i, item in enumerate(items):
                duration = (item['end'] - item['start']).days
                if duration <= 0:
                    duration = 1

                color = color_map.get(item['status'], '#6b7280')
                ax.barh(i, duration, left=item['start'], height=0.7,
                       color=color, alpha=0.8, edgecolor='black', linewidth=0.8)
                ax.text(item['start'] - timedelta(days=3), i, item['name'],
                       va='center', ha='right', fontsize=10)

            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d, %Y'))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            plt.xticks(rotation=45, ha='right')
            ax.set_yticks([])
            ax.set_xlabel('Date', fontsize=12)
            ax.set_title(f'Project: {project.name}', fontsize=14, fontweight='bold', pad=20)
            ax.grid(True, axis='x', alpha=0.3, linestyle='--')

            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='#dc2626', label='In Progress'),
                Patch(facecolor='#10b981', label='Completed'),
                Patch(facecolor='#9ca3af', label='Planned')
            ]
            ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

            plt.tight_layout()
            chart_path = os.path.join(temp_dir, f"gantt_project_{proj_idx}_{timestamp}.png")
            plt.savefig(chart_path, dpi=200, bbox_inches='tight')
            plt.close(fig)

            if os.path.exists(chart_path):
                chart_paths.append(chart_path)

        return chart_paths

    except Exception as e:
        logger.error(f"Error creating matplotlib Gantt charts: {str(e)}")
        return []


def generate_simple_2page_report(days_filter=30):
    """
    Generate clean PDF report with basic information - Cards, Bar Chart, and Pie Chart only
    NO Gantt charts - just simple visualizations
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from datetime import datetime
    import tempfile
    import os
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # Get report data
    report_data = generate_pdf_report_data(days_filter)

    # Extract data
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
    total_users = report_data['total_users']
    active_users = report_data['active_users']

    # Create PDF
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    pdf_path = os.path.join(temp_dir, f"E-Click_Simple_Report_{timestamp}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    # Enhanced styles - Premium Typography & Color Palette
    dark_red = colors.HexColor('#b91c1c')
    charcoal = colors.HexColor('#374151')
    light_gray = colors.HexColor('#f3f4f6')
    accent_gray = colors.HexColor('#e5e7eb')  # Sophisticated accent
    soft_blue = colors.white    # White background (no tint)

    # Dramatically improved typography hierarchy
    title_style = ParagraphStyle('Title', parent=styles['Title'],
                                 fontSize=26, alignment=0, spaceAfter=3,
                                 textColor=dark_red,
                                 fontName='Helvetica-Bold',
                                 leading=30)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
                                    fontSize=10, alignment=0, spaceAfter=12,
                                    textColor=charcoal)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'],
                                   fontSize=14, spaceAfter=6, spaceBefore=18,
                                   textColor=dark_red,
                                   fontName='Helvetica-Bold',
                                   leading=18)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=9, textColor=charcoal)
    info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=9, textColor=charcoal, leading=14)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=7, textColor=charcoal)

    # Premium Header with logo and improved typography
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'E Click Logo (1).png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=1.5*inch, height=0.75*inch)
    else:
        logo = Paragraph('<b><font size=22 color="#b91c1c">E-CLICK</font></b>', normal_style)

    header_data = [
        [logo,
         Paragraph('<b>E-Click Project Report</b><br/><font size=9 color="#6b7280">Generated: {}</font>'.format(
             datetime.now().strftime("%B %d, %Y at %I:%M %p")), title_style)]
    ]
    header_table = Table(header_data, colWidths=[2.5*inch, 4.5*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(header_table)

    # Elegant separator with gradient effect (using thicker line)
    sep_table = Table([['']], colWidths=[7.0*inch], rowHeights=[3])
    sep_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), dark_red),
    ]))
    story.append(sep_table)
    story.append(Spacer(1, 12))  # More breathing room

    # Calculate metrics
    project_completion_rate = (projects_completed / total_projects * 100) if total_projects > 0 else 0

    # Executive Summary - Projects Only with enhanced typography
    story.append(Paragraph('Executive Summary', heading_style))
    story.append(Spacer(1, 6))
    metrics_intro = f"""Currently managing <b><font size=10>{total_projects} projects</font></b> across the organization with a <b><font size=10 color="#b91c1c">{project_completion_rate:.1f}%</font></b> completion rate."""
    story.append(Paragraph(metrics_intro, info_style))
    story.append(Spacer(1, 12))

    # Premium Info Cards with sophisticated styling (Projects Only)
    summary_data = [
        ['Total Projects', 'Completed', 'In Progress', 'Planned'],
        [str(total_projects), str(projects_completed), str(projects_in_progress), str(projects_planned)]
    ]
    summary_table = Table(summary_data, colWidths=[1.75*inch]*4)
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, 1), 18),
        ('GRID', (0, 0), (-1, -1), 1.5, accent_gray),
        ('BACKGROUND', (0, 0), (-1, 0), dark_red),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, 1), light_gray),
        ('TEXTCOLOR', (0, 1), (-1, 1), dark_red),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 18))  # More whitespace

    # Create Highly Informative Pie Chart - Project Status Distribution
    story.append(Paragraph('Project Status Distribution', heading_style))
    story.append(Spacer(1, 4))

    chart_image_paths = []
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
        fig.patch.set_facecolor('white')

        categories = ['Completed', 'In Progress', 'Planned']
        values = [projects_completed, projects_in_progress, projects_planned]

        # Vibrant, distinct colors - Green for completed, Blue for in progress, Orange for planned
        colors_pie = ['#10b981', '#3b82f6', '#f97316']

        # Calculate percentages
        total = sum(values)
        percentages = [(v/total*100) if total > 0 else 0 for v in values]

        # LEFT CHART: Modern Donut Chart with center text and subtle shadow
        wedges, texts, autotexts = ax1.pie(values, colors=colors_pie,
                                            autopct=lambda pct: f'{pct:.1f}%' if pct > 0 else '',
                                            startangle=90,
                                            textprops={'fontsize': 11, 'fontweight': 'bold', 'color': 'white'},
                                            wedgeprops={'edgecolor': 'white', 'linewidth': 2.5, 'antialiased': True},
                                            pctdistance=0.85)

        # Create donut effect by drawing white circle in center (larger hole for better text fit)
        centre_circle = plt.Circle((0, 0), 0.65, fc='white', linewidth=0)
        ax1.add_artist(centre_circle)

        # Add center text showing total projects
        ax1.text(0, 0.20, str(total_projects), ha='center', va='center',
                fontsize=28, fontweight='bold', color='#b91c1c')
        ax1.text(0, -0.08, 'Total\nProjects', ha='center', va='center',
                fontsize=9, color='#374151', linespacing=1.3)

        # Set aspect ratio to equal for perfect circle
        ax1.set_aspect('equal')
        ax1.set_title('Project Status Distribution', fontsize=14, fontweight='bold',
                     color='#1f2937', pad=20)

        # RIGHT SIDE: Microsoft-style professional table
        ax2.axis('off')
        ax2.set_xlim(0, 1)
        ax2.set_ylim(0.05, 0.95)

        # Microsoft-style table with borders
        table_left = 0.08
        table_right = 0.92
        table_width = table_right - table_left
        col1_width = table_width * 0.15  # Color indicator column
        col2_width = table_width * 0.30  # Status column
        col3_width = table_width * 0.20  # Count column
        col4_width = table_width * 0.35  # Percentage column

        border_color = '#4472C4'  # Microsoft blue

        # Header row (Microsoft blue header)
        header_y = 0.82
        header_height = 0.08
        ax2.add_patch(plt.Rectangle((table_left, header_y), table_width, header_height,
                                   facecolor='#4472C4', edgecolor=border_color, linewidth=1.5))
        ax2.text(table_left + table_width/2, header_y + header_height/2, 'PROJECT STATUS BREAKDOWN',
                ha='center', va='center', fontsize=10, fontweight='bold', color='white')

        # Column headers
        col_header_y = 0.74
        col_header_height = 0.08
        ax2.add_patch(plt.Rectangle((table_left, col_header_y), table_width, col_header_height,
                                   facecolor='#D9E2F3', edgecolor=border_color, linewidth=1))

        # Column header dividers
        col1_x = table_left + col1_width
        col2_x = col1_x + col2_width
        col3_x = col2_x + col3_width

        ax2.plot([col1_x, col1_x], [col_header_y, col_header_y + col_header_height],
                color=border_color, linewidth=1)
        ax2.plot([col2_x, col2_x], [col_header_y, col_header_y + col_header_height],
                color=border_color, linewidth=1)
        ax2.plot([col3_x, col3_x], [col_header_y, col_header_y + col_header_height],
                color=border_color, linewidth=1)

        # Column header text
        ax2.text(table_left + col1_width/2, col_header_y + col_header_height/2, '',
                ha='center', va='center', fontsize=8, fontweight='bold', color='#1f2937')
        ax2.text(col1_x + col2_width/2, col_header_y + col_header_height/2, 'Status',
                ha='center', va='center', fontsize=9, fontweight='bold', color='#1f2937')
        ax2.text(col2_x + col3_width/2, col_header_y + col_header_height/2, 'Projects',
                ha='center', va='center', fontsize=9, fontweight='bold', color='#1f2937')
        ax2.text(col3_x + col4_width/2, col_header_y + col_header_height/2, 'Percentage',
                ha='center', va='center', fontsize=9, fontweight='bold', color='#1f2937')

        # Data rows with light gray backgrounds
        row_data = [
            ('Completed', projects_completed, percentages[0], '#10b981', '#f3f4f6'),  # Light gray
            ('In Progress', projects_in_progress, percentages[1], '#3b82f6', '#f3f4f6'),  # Light gray
            ('Planned', projects_planned, percentages[2], '#f97316', '#f3f4f6')  # Light gray
        ]

        row_height = 0.09  # Slightly taller for better breathing room
        current_y = 0.65

        for idx, (status, count, pct, color, bg_tint) in enumerate(row_data):
            # Subtle color-tinted background for each status type
            ax2.add_patch(plt.Rectangle((table_left, current_y), table_width, row_height,
                                       facecolor=bg_tint, edgecolor=border_color, linewidth=0.8))

            # Vertical dividers
            ax2.plot([col1_x, col1_x], [current_y, current_y + row_height],
                    color=border_color, linewidth=0.8)
            ax2.plot([col2_x, col2_x], [current_y, current_y + row_height],
                    color=border_color, linewidth=0.8)
            ax2.plot([col3_x, col3_x], [current_y, current_y + row_height],
                    color=border_color, linewidth=0.8)

            # Enhanced color indicator (larger square with subtle shadow effect)
            indicator_size = 0.03
            indicator_x = table_left + col1_width/2 - indicator_size/2
            indicator_y = current_y + row_height/2 - indicator_size/2

            # Shadow effect
            shadow_offset = 0.002
            ax2.add_patch(plt.Rectangle((indicator_x + shadow_offset, indicator_y - shadow_offset),
                                       indicator_size, indicator_size,
                                       facecolor='#00000020', edgecolor='none', zorder=1))
            # Main indicator
            ax2.add_patch(plt.Rectangle((indicator_x, indicator_y), indicator_size, indicator_size,
                                       facecolor=color, edgecolor='white', linewidth=1.5, zorder=2))

            # Status text (bolder)
            ax2.text(col1_x + col2_width/2, current_y + row_height/2, status,
                    ha='center', va='center', fontsize=10, fontweight='bold', color='#1f2937')

            # Count text
            ax2.text(col2_x + col3_width/2, current_y + row_height/2, f'{count} projects',
                    ha='center', va='center', fontsize=9, color='#4b5563')

            # Percentage text (larger and bolder)
            ax2.text(col3_x + col4_width/2, current_y + row_height/2, f'{pct:.1f}%',
                    ha='center', va='center', fontsize=10, fontweight='bold', color=color)

            current_y -= row_height

        # Draw outer border now that we know where the last row ends
        # The border should go from the top of the header to the bottom of the last row
        border_top = header_y + header_height
        border_bottom = current_y + row_height  # current_y is now at the bottom of the last row
        border_height = border_top - border_bottom
        ax2.add_patch(plt.Rectangle((table_left, border_bottom), table_width, border_height,
                                   facecolor='none', edgecolor=border_color, linewidth=2.5))

        plt.tight_layout()
        pie_chart_path = os.path.join(temp_dir, f'pie_chart_{timestamp}.png')
        plt.savefig(pie_chart_path, dpi=180, bbox_inches='tight', facecolor='white')
        plt.close()
        chart_image_paths.append(pie_chart_path)

        # Add informative chart to PDF
        img = Image(pie_chart_path, width=7*inch, height=3.2*inch)
        story.append(img)
        story.append(Spacer(1, 8))
    except Exception as e:
        logger.error(f"Error creating pie chart: {str(e)}")
        import traceback
        traceback.print_exc()
        story.append(Paragraph('Chart generation failed', normal_style))
        story.append(Spacer(1, 8))

    # Get all projects for detailed list
    all_projects = Project.objects.all().prefetch_related('tasks')

    # Detailed Project List with enhanced visual hierarchy
    story.append(Spacer(1, 6))
    story.append(Paragraph('Detailed Project Overview', heading_style))
    story.append(Spacer(1, 8))

    if all_projects:
        for idx, project in enumerate(all_projects):
            # Calculate project metrics
            tasks = project.tasks.all()
            total_tasks_count = tasks.count()
            completed_tasks_count = tasks.filter(status='completed').count()
            progress = (completed_tasks_count / total_tasks_count * 100) if total_tasks_count > 0 else 0

            # Status display - NO HTML, use Paragraph for colors
            status_map = {
                'completed': 'Completed',
                'in_progress': 'In Progress',
                'planned': 'Planned'
            }
            status_display = status_map.get(project.status, project.status.title())

            status_colors = {
                'completed': '#10b981',
                'in_progress': '#3b82f6',
                'planned': '#9ca3af'
            }
            status_color = status_colors.get(project.status, '#6b7280')

            # Status background tints
            status_bg_colors = {
                'completed': light_gray,
                'in_progress': soft_blue,
                'planned': light_gray
            }
            bg_color = status_bg_colors.get(project.status, light_gray)

            # Project header with number and icon indicator
            project_header = f'''<b><font color="#b91c1c" size=12>▸ Project {idx+1}: {project.name}</font></b>'''

            # Project details in well-styled table with background
            project_details = [
                ['Client:', project.client if project.client else 'Not Assigned',
                 'Status:', Paragraph(f'<font color="{status_color}"><b>{status_display}</b></font>', normal_style)],
                ['Start Date:', project.start_date.strftime('%b %d, %Y') if project.start_date else 'Not Set',
                 'End Date:', project.end_date.strftime('%b %d, %Y') if project.end_date else 'Not Set'],
                ['Progress:', f'{progress:.1f}%',
                 'Tasks:', f'{completed_tasks_count} of {total_tasks_count} completed']
            ]

            details_table = Table(project_details, colWidths=[1.3*inch, 2.2*inch, 1.1*inch, 2.4*inch])
            details_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
                ('TEXTCOLOR', (0, 0), (-1, -1), charcoal),
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOX', (0, 0), (-1, -1), 1, accent_gray),
            ]))

            # Keep header and table together on the same page
            story.append(KeepTogether([
                Paragraph(project_header, normal_style),
                Spacer(1, 12),
                details_table
            ]))

            # Elegant separator line with color accent
            story.append(Spacer(1, 8))
            sep = Table([['']], colWidths=[7*inch], rowHeights=[2])
            sep.setStyle(TableStyle([
                ('LINEBELOW', (0, 0), (-1, -1), 2, accent_gray),
            ]))
            story.append(sep)
            story.append(Spacer(1, 10))
    else:
        story.append(Paragraph('No projects found in the system.', normal_style))

    story.append(Spacer(1, 10))

    # Footer with E-Click branding
    story.append(Spacer(1, 10))
    footer_text = '''<para align=center>
        <font size=7 color="#9ca3af">─────────────────────────────────────</font><br/>
        <b><font size=8 color="#b91c1c">E-CLICK PROJECT MANAGEMENT</font></b><br/>
        <font size=7 color="#374151">Delivering Excellence Through Innovation</font><br/>
        <font size=6 color="#9ca3af">Report Generated: {}</font>
    </para>'''.format(datetime.now().strftime("%B %d, %Y"))
    story.append(Paragraph(footer_text, normal_style))

    # Build PDF - no headers/footers
    doc.build(story)

    # Clean up chart images after PDF is built
    for chart_path in chart_image_paths:
        if os.path.exists(chart_path):
            try:
                os.unlink(chart_path)
            except:
                pass

    return pdf_path


def create_gantt_chart(projects):
    """
    Create a Gantt chart visualization for project timelines
    Uses E-Click branding colors: Red (#dc2626), Black, Gray
    """
    from reportlab.graphics.shapes import Drawing, Rect, String, Line
    from reportlab.lib import colors
    from datetime import datetime, timedelta

    if not projects:
        return None

    try:
        # Chart dimensions - optimized for clarity
        chart_width = 500
        bar_height = 16
        row_spacing = 26
        margin_left = 130
        margin_right = 20
        margin_top = 45
        margin_bottom = 25

        timeline_width = chart_width - margin_left - margin_right
        chart_height = margin_top + (len(projects) * row_spacing) + margin_bottom

        # Create drawing
        drawing = Drawing(chart_width, chart_height)

        # Find overall date range
        all_start_dates = [p.start_date for p in projects if p.start_date]
        all_end_dates = [p.end_date for p in projects if p.end_date]

        if not all_start_dates or not all_end_dates:
            return None

        min_date = min(all_start_dates)
        max_date = max(all_end_dates)
        total_days = (max_date - min_date).days + 1

        if total_days <= 0:
            return None

        # Draw timeline axis
        axis_y = chart_height - margin_top + 10
        drawing.add(Line(margin_left, axis_y, margin_left + timeline_width, axis_y,
                        strokeColor=colors.HexColor('#d1d5db'), strokeWidth=1))

        # Add simplified date labels (start, middle, end only)
        # This prevents overlapping dates
        date_labels = [
            (min_date, margin_left, 'start'),
            (min_date + timedelta(days=total_days//2), margin_left + timeline_width//2, 'middle'),
            (max_date, margin_left + timeline_width, 'end')
        ]

        for date, x_pos, position in date_labels:
            label = date.strftime('%b %d, %y')
            drawing.add(String(x_pos, axis_y + 8, label,
                              fontSize=6, fillColor=colors.HexColor('#374151'), textAnchor='middle'))
            # Small tick
            drawing.add(Line(x_pos, axis_y, x_pos, axis_y + 4,
                           strokeColor=colors.HexColor('#9ca3af'), strokeWidth=0.5))

        # Draw project bars
        y_position = axis_y - 20
        today = datetime.now().date()

        for project in projects:
            if not project.start_date or not project.end_date:
                continue

            # Calculate bar position
            start_days = (project.start_date - min_date).days
            duration_days = (project.end_date - project.start_date).days + 1
            bar_x = margin_left + (start_days / total_days) * timeline_width
            bar_width = max(8, (duration_days / total_days) * timeline_width)

            # Calculate progress
            proj_tasks = project.tasks.all()
            total_tasks = proj_tasks.count()
            completed_tasks = proj_tasks.filter(status='completed').count()
            progress = (completed_tasks / total_tasks) if total_tasks > 0 else 0

            # Bar colors based on status
            if project.status == 'completed':
                bar_color = colors.HexColor('#10b981')  # Green
            elif project.status == 'in_progress':
                bar_color = colors.HexColor('#dc2626')  # E-Click red
            else:
                bar_color = colors.HexColor('#9ca3af')  # Light gray

            # Draw background bar
            drawing.add(Rect(bar_x, y_position, bar_width, bar_height,
                           fillColor=colors.HexColor('#f3f4f6'),
                           strokeColor=colors.HexColor('#d1d5db'),
                           strokeWidth=0.5))

            # Draw progress bar
            progress_width = bar_width * progress
            if progress_width > 2:
                drawing.add(Rect(bar_x, y_position, progress_width, bar_height,
                               fillColor=bar_color, strokeColor=None, strokeWidth=0))

            # Project name label (cleaner, shorter)
            project_name = project.name[:18] + '..' if len(project.name) > 18 else project.name
            drawing.add(String(margin_left - 6, y_position + 5, project_name,
                              fontSize=7, fillColor=colors.HexColor('#111827'), textAnchor='end'))

            # Progress percentage (only if bar is wide enough)
            if bar_width > 25:
                progress_text = f"{progress * 100:.0f}%"
                text_color = colors.white if progress > 0.4 else colors.HexColor('#374151')
                drawing.add(String(bar_x + bar_width / 2, y_position + 4, progress_text,
                                  fontSize=6, fillColor=text_color,
                                  textAnchor='middle', fontName='Helvetica-Bold'))

            y_position -= row_spacing

        # Legend at bottom
        legend_y = margin_bottom - 12
        legend_x = margin_left

        drawing.add(String(legend_x, legend_y, 'Status:',
                          fontSize=7, fillColor=colors.HexColor('#374151'), fontName='Helvetica-Bold'))

        # Legend items
        legend_items = [
            (colors.HexColor('#dc2626'), 'In Progress'),
            (colors.HexColor('#10b981'), 'Completed'),
            (colors.HexColor('#9ca3af'), 'Planned')
        ]

        legend_x += 38
        for color, label in legend_items:
            drawing.add(Rect(legend_x, legend_y - 2, 10, 6, fillColor=color, strokeColor=None))
            drawing.add(String(legend_x + 13, legend_y, label,
                              fontSize=6, fillColor=colors.HexColor('#374151')))
            legend_x += 60

        return drawing

    except Exception as e:
        logger.error(f"Error creating Gantt chart: {str(e)}")
        return None


def generate_exact_pdf_report(days_filter=30):
    """
    Generate simplified 2-page E-Click PDF report focusing on information accuracy
    Page 1: Executive Summary, Performance Analysis, Gantt Chart
    Page 2: All Projects Overview Table
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from datetime import datetime, timedelta
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
    descriptive_filename = f"E-Click_2Page_Report_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, descriptive_filename)
    
    # Create PDF document
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=100,
        bottomMargin=50,
    )
    story = []

    # Get styles
    styles = getSampleStyleSheet()

    # Simple styles - focus on readability
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#dc2626'),
        alignment=1,
        spaceAfter=10,
    )

    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#dc2626'),
        spaceAfter=8,
        spaceBefore=12,
    )

    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=4,
    )

    # Simple header/footer
    PAGE_WIDTH, PAGE_HEIGHT = A4

    def draw_header_footer(canvas, doc):
        canvas.saveState()
        # Header
        canvas.setFont('Helvetica-Bold', 16)
        canvas.setFillColor(colors.HexColor('#dc2626'))
        canvas.drawString(40, PAGE_HEIGHT - 40, 'E-CLICK')
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.black)
        canvas.drawRightString(PAGE_WIDTH - 40, PAGE_HEIGHT - 35, 'support@eclick.co.za')
        canvas.drawRightString(PAGE_WIDTH - 40, PAGE_HEIGHT - 48, '(+27)')
        # Footer
        canvas.setFont('Helvetica-Bold', 8)
        canvas.setFillColor(colors.HexColor('#dc2626'))
        canvas.drawCentredString(PAGE_WIDTH / 2, 30, 'WE CARE, WE CAN, WE DELIVER')
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.black)
        canvas.drawCentredString(PAGE_WIDTH / 2, 18, f'Page {doc.page}')
        canvas.restoreState()

    # ===== PAGE 1: Summary & Metrics =====
    story.append(Paragraph('E-Click Project Management Report', title_style))
    story.append(Paragraph(f'{start_date.strftime("%B %d")} - {end_date.strftime("%B %d, %Y")}',
                          ParagraphStyle('Subtitle', parent=normal_style, alignment=1, spaceAfter=15)))

    # Executive Summary
    story.append(Paragraph('Executive Summary', heading_style))

    # Calculate metrics
    project_completion_rate = (projects_completed / total_projects * 100) if total_projects > 0 else 0
    task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    user_engagement_rate = (active_users / total_users * 100) if total_users > 0 else 0

    # Summary table - 4 columns
    summary_data = [
        ['Total Projects', 'Total Tasks', 'Completion Rate', 'Active Users'],
        [str(total_projects), str(total_tasks), f'{project_completion_rate:.1f}%', str(active_users)]
    ]
    summary_table = Table(summary_data, colWidths=[2.4*inch]*4)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONT NAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Key Metrics
    story.append(Paragraph('Key Metrics', heading_style))
    metrics_text = f"""
    • Project Completion: {project_completion_rate:.1f}% ({projects_completed} of {total_projects} completed)<br/>
    • Task Completion: {task_completion_rate:.1f}% ({completed_tasks} of {total_tasks} completed)<br/>
    • Active Projects: {projects_in_progress} currently in progress<br/>
    • User Engagement: {user_engagement_rate:.1f}% ({active_users} of {total_users} users active)
    """
    story.append(Paragraph(metrics_text, normal_style))
    story.append(Spacer(1, 12))
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

    # Project Timeline - Gantt Chart Visualization
    story.append(PageBreak())
    story.append(Paragraph('Project Timeline - Gantt Chart', heading_style))
    story.append(Spacer(1, 10))

    # Get all projects with their dates for Gantt chart
    try:
        # Get all projects and filter in Python (since start_date/end_date are properties)
        all_projects = Project.objects.all().prefetch_related('tasks')
        all_projects_for_gantt = [p for p in all_projects if p.start_date and p.end_date]
        # Sort by start date
        all_projects_for_gantt.sort(key=lambda p: p.start_date)
        all_projects_for_gantt = all_projects_for_gantt[:10]  # Show max 10 projects

        if all_projects_for_gantt:
            # Create Gantt chart
            gantt_chart = create_gantt_chart(all_projects_for_gantt)
            if gantt_chart:
                story.append(gantt_chart)
                story.append(Spacer(1, 10))
                story.append(Paragraph('<i>Timeline visualization showing project start and end dates with current progress</i>',
                    ParagraphStyle('ItalicSmall', parent=normal_style, fontSize=8, textColor=colors.HexColor('#6b7280'), alignment=1)))
            else:
                story.append(Paragraph('No projects with defined timelines available for Gantt visualization', normal_style))
        else:
            story.append(Paragraph('No projects with defined timelines available', normal_style))
    except Exception as e:
        logger.error(f"Error creating Gantt chart: {str(e)}")
        story.append(Paragraph('Gantt chart visualization temporarily unavailable', normal_style))

    story.append(Spacer(1, 15))

    # All Projects Overview Table
    story.append(Paragraph('All Projects Overview', heading_style))
    story.append(Spacer(1, 10))

    try:
        all_projects_list = Project.objects.all().order_by('-created_at')

        if all_projects_list:
            # Create comprehensive projects table
            projects_overview_data = [['Project Name', 'Client', 'Status', 'Start Date', 'End Date', 'Progress']]

            for proj in all_projects_list[:15]:  # Show max 15 projects
                # Format dates
                start_str = proj.start_date.strftime('%m/%d/%y') if proj.start_date else 'N/A'
                end_str = proj.end_date.strftime('%m/%d/%y') if proj.end_date else 'N/A'

                # Calculate progress
                proj_tasks = Task.objects.filter(project=proj)
                total_proj_tasks = proj_tasks.count()
                completed_proj_tasks = proj_tasks.filter(status='completed').count()
                progress_pct = (completed_proj_tasks / total_proj_tasks * 100) if total_proj_tasks > 0 else 0

                # Status display
                status_map = {
                    'planned': 'Planned',
                    'in_progress': 'In Progress',
                    'completed': 'Completed'
                }
                status_display = status_map.get(proj.status, proj.status)

                projects_overview_data.append([
                    proj.name[:30] + '...' if len(proj.name) > 30 else proj.name,
                    proj.client[:20] + '...' if len(proj.client) > 20 else proj.client,
                    status_display,
                    start_str,
                    end_str,
                    f"{progress_pct:.0f}%"
                ])

            overview_table = Table(projects_overview_data, colWidths=[2.2*inch, 1.5*inch, 1.1*inch, 0.7*inch, 0.7*inch, 1.1*inch])
            overview_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),  # E-Click red header
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (5, 0), (5, -1), 'CENTER'),  # Center progress column
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),  # Light gray grid
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),  # Alternating rows
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(overview_table)
        else:
            story.append(Paragraph('No projects available', normal_style))
    except Exception as e:
        logger.error(f"Error creating projects overview: {str(e)}")
        story.append(Paragraph('Projects overview temporarily unavailable', normal_style))

    story.append(Spacer(1, 15))

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
    story.append(Paragraph(f'Generated on {timezone.now().strftime("%B %d, %Y at %I:%M %p")} | E-Click Project Management', ParagraphStyle(
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
    
    # EMAIL CLOSING
    closing_text = """If you have any questions, simply reply to this email and our team will assist you.<br/><br/>
Warm regards,<br/><br/>
E-Click Project Management Team"""
    story.append(Paragraph(closing_text, body_style))
    story.append(Spacer(1, 8))
    
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
    from reportlab.graphics.shapes import Drawing, String
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
    temp_dir = tempfile.gettempdir()
    safe_project = re.sub(r'[^a-zA-Z0-9_-]+', '_', project.name).strip('_')[:40]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    descriptive_filename = f"E-Click_ProjectReport_{safe_project}_{timestamp}.pdf"
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
        textColor=colors.HexColor('#374151')  # Dark gray
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
    story.append(Paragraph('E-Click', signature_style))
    story.append(Spacer(1, 5))
    
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
    story.append(Paragraph(f'Generated on {timezone.now().strftime("%B %d, %Y at %I:%M %p")} | E-Click Project Management', ParagraphStyle(
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
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem, KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String
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
    
    # Create PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
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
        textColor=colors.HexColor('#374151'),  # Dark gray
        fontName='Helvetica'
    )
    
    # Build content for comprehensive project report
    elements = []

    # Title + Project Info
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
    
    # Task completion donut chart
    try:
        drawing = Drawing(380, 180)
        pie = Pie()
        pie.x = 120
        pie.y = 20
        pie.width = 140
        pie.height = 140
        
        # Create donut chart showing completed vs remaining
        pie.data = [completed_tasks, total_tasks - completed_tasks]
        pie.labels = ['', '']
        pie.slices[0].fillColor = colors.HexColor('#dc2626')  # Red for completed
        pie.slices[1].fillColor = colors.HexColor('#e5e7eb')  # Light gray for remaining
        
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 1
        drawing.add(pie)
        
        # Add center circle for donut effect
        from reportlab.graphics.shapes import Circle, String
        cx, cy = 190, 90
        ring = Circle(cx, cy, 48, fillColor=colors.white, strokeColor=colors.white)
        drawing.add(ring)
        
        # Add percentage in center
        pct_label = String(cx, cy - 4, f"{task_completion_rate:.1f}%", textAnchor='middle')
        pct_label.fontName = 'Helvetica-Bold'
        pct_label.fontSize = 18
        pct_label.fillColor = colors.HexColor('#111827')
        drawing.add(pct_label)
        
        elements.append(drawing)
        elements.append(Spacer(1, 6))
    except Exception:
        pass
    
    # Task completion labels
    elements.append(Paragraph('Completed', normal_style))
    elements.append(Paragraph('Remaining', normal_style))
    elements.append(Spacer(1, 12))
    
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

def generate_client_specific_pdf_report(client_id, days_filter=30):
    """
    Generate a client-specific PDF report with comprehensive project and task data
    This function creates a detailed report for one specific client using professional styling
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem, KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    from io import BytesIO
    from datetime import datetime
    import tempfile
    
    # Get the client and their projects
    client = get_object_or_404(Client, id=client_id)
    client_projects = Project.objects.filter(
        Q(clients=client) | Q(client_username=client.username)
    ).distinct()
    
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
    temp_dir = tempfile.gettempdir()
    safe_client = re.sub(r'[^a-zA-Z0-9_-]+', '_', (client.username or client.email or 'Client')).strip('_')[:40]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    descriptive_filename = f"E-Click_ClientReport_{safe_client}_{timestamp}.pdf"
    pdf_path = os.path.join(temp_dir, descriptive_filename)
    
    # Create PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
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
        'NormalText',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        textColor=colors.HexColor('#374151'),  # Dark gray
        fontName='Helvetica'
    )
    
    # Build content strictly matching the email and fit on one page
    elements = []

    # Title + generated date
    elements.append(Paragraph('Your E-Click Client Progress Report', title_style))
    elements.append(Paragraph(f'Generated on {timezone.now().strftime("%B %d, %Y at %I:%M %p")}', subtitle_style))
    elements.append(Spacer(1, 6))

    # Greeting
    client_display = client.username or client.email or 'Client'
    elements.append(Paragraph(f'Dear {client_display},', normal_style))
    elements.append(Spacer(1, 6))

    # Donut chart (refined styling)
    try:
        # Use project completion as the primary metric (matches user expectation)
        completed_count = completed_projects if total_projects > 0 else completed_tasks
        overall_total = total_projects if total_projects > 0 else total_tasks
        overall_total = max(1, overall_total)
        overall_pct = (completed_count / overall_total) * 100
        drawing = Drawing(380, 180)
        pie = Pie()
        pie.x = 120
        pie.y = 20
        pie.width = 140
        pie.height = 140
        # If multiple projects exist, give each project its own colored slice
        if total_projects > 1:
            pie.data = [1] * total_projects
            pie.labels = [''] * total_projects
            # Color mapping: completed (red), in-progress (near black), planned (gray)
            palette = [colors.HexColor('#dc2626'), colors.HexColor('#111827'), colors.HexColor('#9ca3af')]
            for i in range(total_projects):
                if i < completed_projects:
                    pie.slices[i].fillColor = palette[0]
                elif i < completed_projects + in_progress_projects:
                    pie.slices[i].fillColor = palette[1]
                else:
                    pie.slices[i].fillColor = palette[2]
        else:
            # Fallback to completed vs remaining donut
            pie.data = [max(0, completed_count), max(0, overall_total - completed_count)]
            pie.labels = ['', '']
            pie.slices[0].fillColor = colors.HexColor('#dc2626')
            pie.slices[1].fillColor = colors.HexColor('#e5e7eb')
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 1
        drawing.add(pie)
        from reportlab.graphics.shapes import Circle, String
        cx, cy = 190, 90
        ring = Circle(cx, cy, 48, fillColor=colors.white, strokeColor=colors.white)
        drawing.add(ring)
        pct_label = String(cx, cy - 4, f"{overall_pct:.1f}%", textAnchor='middle')
        pct_label.fontName = 'Helvetica-Bold'
        pct_label.fontSize = 18
        pct_label.fillColor = colors.HexColor('#111827')
        drawing.add(pct_label)
        elements.append(drawing)
        elements.append(Spacer(1, 6))
    except Exception:
        pass

    # Intro line before summary
    elements.append(Paragraph('Please find your summary below. A detailed, presentation-ready PDF is attached for your records.', normal_style))
    elements.append(Spacer(1, 8))

    # Summary table (Project Summary | Totals)
    summary_data = [
        ['Project Summary', 'Totals'],
        ['Total Projects', str(total_projects)],
        ['Completed Projects', str(completed_projects)],
        ['Projects In Progress', str(in_progress_projects)],
        ['Total Tasks', str(total_tasks)],
        ['Completed Tasks', str(completed_tasks)],
    ]
    # Make the summary table wider and close to the content edges (even wider)
    summary_table = Table(summary_data, colWidths=[doc.width * 0.7, doc.width * 0.3])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('LEADING', (0, 1), (-1, -1), 12),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 8))

    # Remove KPI cards to match request (cleaner look like the email)

    # Highlights list
    elements.append(Paragraph('Highlights', heading_style))
    highlights = [
        'Clear visibility of your portfolio progress and current workload.',
        'Attached PDF includes detailed tables, charts, and next-step recommendations.',
        "We'll continue to monitor and update you proactively.",
    ]
    elements.append(
        ListFlowable(
            [ListItem(Paragraph(h, normal_style)) for h in highlights],
            bulletType='bullet',
            leftIndent=12,
            bulletIndent=6,
            bulletFontName='Helvetica',
            bulletFontSize=9,
        )
    )
    elements.append(Spacer(1, 6))

    # Next Steps list
    elements.append(Paragraph('Next Steps', heading_style))
    next_steps = [
        'Review the attached PDF for full insights and project-level details.',
        "Reply with any priorities you'd like us to fast-track this week.",
        "Book a 15-minute review if you'd like us to walk you through the data.",
    ]
    elements.append(
        ListFlowable(
            [ListItem(Paragraph(n, normal_style)) for n in next_steps],
            bulletType='bullet',
            leftIndent=12,
            bulletIndent=6,
            bulletFontName='Helvetica',
            bulletFontSize=9,
        )
    )
    elements.append(Spacer(1, 8))

    # Closing
    elements.append(Paragraph('If you have any questions, simply reply to this email and our team will assist you.', normal_style))
    elements.append(Paragraph('Warm regards,', normal_style))
    elements.append(Paragraph('<b>E-Click Project Management Team</b>', normal_style))
    elements.append(Spacer(1, 10))

    # Footer banner with rounded corners via a custom Flowable
    from reportlab.platypus import Flowable
    class RoundedBanner(Flowable):
        def __init__(self, width: float, height: float, text: str):
            super().__init__()
            self._width = width
            self._height = height
            self._text = text
        def wrap(self, availWidth, availHeight):
            self._width = min(self._width, availWidth)
            return self._width, self._height
        def draw(self):
            radius = 6
            self.canv.setFillColor(colors.HexColor('#111827'))
            self.canv.setStrokeColor(colors.HexColor('#111827'))
            try:
                self.canv.roundRect(0, 0, self._width, self._height, radius, stroke=1, fill=1)
            except Exception:
                # Fallback to regular rectangle
                self.canv.rect(0, 0, self._width, self._height, stroke=1, fill=1)
            self.canv.setFillColor(colors.white)
            self.canv.setFont('Helvetica', 10)
            self.canv.drawString(12, (self._height - 10) / 2, self._text)
    elements.append(RoundedBanner(doc.width, 26, 'WE CARE, WE CAN, WE DELIVER'))

    # Fit all content into one page using KeepInFrame with shrink
    # Fit to one page; use mode='shrink' for ReportLab versions without 'shrink' kw arg
    try:
        one_page = KeepInFrame(doc.width, doc.height - 20, elements, hAlign='LEFT', vAlign='TOP', mode='shrink')
    except TypeError:
        one_page = KeepInFrame(doc.width, doc.height - 20, elements, hAlign='LEFT', vAlign='TOP')
    doc.build([one_page])
    return pdf_path

@login_required
def projects_page(request):
    SystemLog.log_navigation(
        user=request.user,
        page_name='Projects Page',
        page_url=request.path,
        request=request
    )
    try:
        profile = request.user.profile
        can_create_projects = profile.can_create_projects or request.user.is_staff
        can_edit_projects = profile.can_edit_projects or request.user.is_staff
        can_delete_projects = profile.can_delete_projects or request.user.is_staff
    except UserProfile.DoesNotExist:
        can_create_projects = request.user.is_staff
        can_edit_projects = request.user.is_staff
        can_delete_projects = request.user.is_staff
    if request.user.is_staff:
        projects = Project.objects.all().order_by('-created_at')
        all_users = User.objects.all().order_by('username')
        existing_clients = Client.objects.filter(is_active=True).order_by('username')
    else:
        projects = Project.objects.filter(assigned_users=request.user).order_by('-created_at')
        all_users = User.objects.filter(id=request.user.id)
        existing_clients = Client.objects.filter(is_active=True).order_by('username')
    return render(request, 'home/projects_page.html', {
        'projects': projects,
        'all_users': all_users,
        'existing_clients': existing_clients,
        'can_create_projects': can_create_projects,
        'can_edit_projects': can_edit_projects,
        'can_delete_projects': can_delete_projects,
    })

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
    # Require superuser access
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')

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
                    
                    # Send OTP email using SimpleEmailService with Microsoft SMTP
                    site_url = request.build_absolute_uri('/').rstrip('/')
                    from .email_service import SimpleEmailService
                    email_service = SimpleEmailService()
                    email_result = email_service.send_email(
                        to_email=email,
                        subject="Set Your Password - Welcome to E-Click",
                        body=f"""<html>
<body>
<p><img src="https://drive.google.com/uc?id=1v_KeFPd25pTVK57IJdE9LhFniHnjKD-A" alt="E-Click Logo" width="140"></p>
<p>Dear {username},</p>
<p>Welcome to E-Click! Please use the One-Time Password (OTP) below to set your password:</p>
<p>OTP: {otp}</p>
<p>You can set your password here: <a href="{site_url}/user/setup-password/?username={username}">Set Up New Password</a></p>
<p>This OTP is valid for 24 hours.</p>
<p>Best regards,<br>E-Click Team</p>
</body>
</html>""",
                        from_email=None  # Will use default from settings
                    )
                    
                    if email_result['success']:
                        messages.success(request, f'User "{username}" created successfully with {role} role. OTP sent to {email} for password setup.')
                    else:
                        messages.warning(request, f'User "{username}" created successfully with {role} role. OTP email failed: {email_result.get("error", "Unknown error")}')
                        
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
        
        elif action == 'reset_password':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id)
            
            try:
                # Generate new OTP for password reset
                from .models import generate_user_otp
                otp = generate_user_otp(user)
                
                # Send password reset email
                site_url = request.build_absolute_uri('/').rstrip('/')
                from .email_service import SimpleEmailService
                email_service = SimpleEmailService()
                
                email_result = email_service.send_email(
                    to_email=user.email,
                    subject="Password Reset - E-Click",
                    body=f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p>Dear {user.username},</p>

    <p>Your password has been reset by an administrator. Use the One-Time Password (OTP) below to set a new password:</p>

    <p><strong>OTP: {otp}</strong></p>

    <p>Reset your password here: {site_url}/user/setup-password/?username={user.username}</p>

    <p>This OTP is valid for 24 hours.</p>

    <p>If you did not request this password reset, please contact our support team immediately.</p>

    <p>Best regards,<br>E-Click Team</p>
</body>
</html>""",
                    from_email=None
                )
                
                if email_result['success']:
                    messages.success(request, f'Password reset email sent to {user.username} at {user.email}')
                else:
                    messages.warning(request, f'Password reset email failed: {email_result.get("error", "Unknown error")}')
                    
            except Exception as e:
                messages.error(request, f'Error resetting password for {user.username}: {str(e)}')
            
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
                    expires_at=timezone.now() + timedelta(hours=24)
                )
                
                print(f"DEBUG: OTP record created for user {user.username}")
                print(f"DEBUG: User email: {user.email}")
                
                # Send OTP email using SimpleEmailService with Microsoft SMTP
                print(f"DEBUG: About to send email to {user.email}")
                from .email_service import SimpleEmailService
                email_service = SimpleEmailService()
                email_result = email_service.send_email(
                    to_email=user.email,
                    subject="Password Reset OTP - E-Click",
                    body=f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p>Dear {user.username},</p>

    <p>You have requested a password reset. Please use the following OTP:</p>

    <p><strong>Your OTP: {otp}</strong></p>

    <p>This OTP will expire in 24 hours.</p>

    <p>Best regards,<br>E-Click Team</p>
</body>
</html>""",
                    from_email=None  # Will use default from settings
                )
                print(f"DEBUG: Email result: {email_result}")
                
                if not email_result['success']:
                    print(f"DEBUG: Email failed with error: {email_result['error']}")
                    messages.error(request, f'Failed to send OTP email: {email_result["error"]}')
                    return render(request, 'home/admin_control_enhanced.html')
                
                print(f"DEBUG: Email sent successfully")
                messages.success(request, f'Password reset OTP sent successfully to {user.email}.')
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

        elif action == 'add_client':
            # Handle adding new client
            username = request.POST.get('client_username', '').strip()
            email = request.POST.get('client_email', '').strip()
            full_name = request.POST.get('client_full_name', '').strip()
            phone = request.POST.get('client_phone', '').strip()
            company = request.POST.get('client_company', '').strip()

            # Validation
            if not all([username, email]):
                messages.error(request, 'Username and email are required.')
            elif Client.objects.filter(username=username).exists():
                messages.error(request, f'Client username "{username}" already exists.')
            elif Client.objects.filter(email=email).exists():
                messages.error(request, f'Client email "{email}" already exists.')
            else:
                try:
                    # Create new client (only fields that exist in the model)
                    client = Client.objects.create(
                        username=username,
                        email=email,
                        is_active=True
                    )

                    # Generate OTP for the new client
                    otp = client.generate_otp()

                    # Use full name in email if provided, otherwise use username
                    greeting_name = full_name if full_name else username

                    # Send password setup email using SimpleEmailService with Microsoft SMTP
                    site_url = request.build_absolute_uri('/').rstrip('/')
                    from .email_service import SimpleEmailService
                    email_service = SimpleEmailService()
                    email_result = email_service.send_email(
                        to_email=email,
                        subject="Set Your Password - E-Click",
                        body=f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p>Dear {greeting_name},</p>

    <p>Welcome to E-Click. Your client account has been created.</p>

    <p>Please use the following One-Time Password (OTP) to set your password:</p>

    <p><strong>Your OTP: {otp}</strong></p>

    <p>You can set your password here: {site_url}/client/setup-password/?username={username}</p>

    <p>Please note: This OTP is valid for 24 hours.</p>

    <p>If you did not request this account, please contact our support team immediately.</p>

    <p>Best regards,<br>E-Click Project Management Team</p>
</body>
</html>""",
                        from_email=None  # Will use default from settings
                    )

                    if email_result['success']:
                        messages.success(request, f'Client "{username}" created successfully. Password setup email sent to {email}.')
                    else:
                        messages.warning(request, f'Client "{username}" created successfully. Email sending failed: {email_result.get("error", "Unknown error")}. Please use the password reset feature.')

                except Exception as e:
                    messages.error(request, f'Error creating client: {str(e)}')

            return redirect('admin_control')

        elif action == 'reset_client_password':
            # Handle client password reset - send OTP email
            client_id = request.POST.get('client_id')

            try:
                client = Client.objects.get(id=client_id)

                # Generate OTP for password reset
                otp = client.generate_otp()

                # Send password reset OTP email
                site_url = request.build_absolute_uri('/').rstrip('/')
                from .email_service import email_service

                email_result = email_service.send_password_reset_otp_email(
                    to_email=client.email,
                    otp=otp,
                    username=client.username,
                    site_url=site_url
                )

                if email_result['success']:
                    messages.success(request, f'Password reset OTP has been sent to {client.email}.')
                else:
                    messages.error(request, f'Failed to send password reset email: {email_result.get("error", "Unknown error")}')

            except Client.DoesNotExist:
                messages.error(request, 'Client not found.')
            except Exception as e:
                messages.error(request, f'Error sending password reset email: {str(e)}')

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
    
    # Database size (for MySQL, we'll use a placeholder since we can't easily get file size)
    try:
        # For MySQL databases, we can't easily get the file size like with SQLite
        # You could implement a more sophisticated approach using MySQL queries if needed
        db_size = 0.0  # Placeholder - would need MySQL-specific implementation
    except Exception:
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
            # Sync status field with is_completed field to prevent inconsistency
            if is_completed:
                subtask.status = 'completed'
            else:
                # If uncompleting, set to in_progress (or could use previous status if tracked)
                subtask.status = 'in_progress'
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
@login_required
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
                                'status': subtask.status,
                                'priority': subtask.priority,
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
                                'status': subtask.status,
                                'priority': subtask.priority,
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
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Admin privileges required.')
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
    # from .services import GoogleCloudEmailService
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
            logger.info(f"Sending comprehensive PDF report to: {recipient_email}")
            logger.info(f"Date range: {date_range} days")
            logger.info(f"Custom message: {custom_message}")

            # Send email with PDF attachment using SimpleEmailService
            from .email_service import SimpleEmailService
            email_service = SimpleEmailService()

            # Use the existing send_report_email method which generates and attaches PDF
            result = email_service.send_report_email(
                to_email=recipient_email,
                report_data=report_data,
                custom_message=custom_message
            )

            logger.info(f"Email service result: {result}")
            
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
    
    # from .services import GoogleCloudEmailService
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
            elapsed_duration = (end_date.date() - project.start_date).days
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
                
                # Send comprehensive client report email using SimpleEmailService with Microsoft SMTP
                from .email_service import SimpleEmailService
                email_service = SimpleEmailService()
                result = email_service.send_email(
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
                    from_email=None,  # Will use default from settings
                    attachments=[pdf_path]
                )
            else:
                # Fallback to project-specific report if client not found
                pdf_path = generate_comprehensive_project_pdf_report(project_id, date_range)
                
                # Send project report email using SimpleEmailService with Microsoft SMTP
                from .email_service import SimpleEmailService
                email_service = SimpleEmailService()
                result = email_service.send_email(
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
                    from_email=None,  # Will use default from settings
                    attachments=[pdf_path]
                )
            
            # Cleanup temporary PDF
            try:
                import os
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
            except Exception:
                pass
            
            # Handle email service result
            if result['success']:
                if client:
                    messages.success(request, f'Comprehensive client report for {project.client} sent successfully to {project.client_email}')
                else:
                    messages.success(request, f'Comprehensive project report sent successfully to {project.client_email}')
            else:
                if client:
                    messages.error(request, f'Error sending client report: {result.get("error", "Unknown error")}')
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
        client_projects = Project.objects.filter(
            Q(clients=client) | Q(client_username=client.username)
        ).distinct()
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
    
    # from .services import GoogleCloudEmailService
    from django.utils import timezone
    
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
                # Support both new ManyToMany relationship and legacy client_username field
                client_projects = Project.objects.filter(
                    Q(clients=client) | Q(client_username=client.username)
                ).distinct()

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

            # Generate matplotlib donut chart
            from .chart_utils import generate_donut_chart
            from email.mime.image import MIMEImage
            from django.core.mail import EmailMultiAlternatives
            from django.conf import settings
            import os

            chart_buffer = generate_donut_chart(report_data['task_completion_rate'])

            # Load E-Click logo
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'E Click Logo (1).png')
            with open(logo_path, 'rb') as f:
                logo_data = f.read()

            # Build polished HTML email body for client with inline chart
            email_body = f"""
<html>
  <body style="margin:0;padding:0;background:#f8fafc;font-family:Segoe UI, Roboto, Helvetica, Arial, sans-serif;color:#111827;">
    <div style="max-width:720px;margin:0 auto;padding:24px;">
      <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
        <div style="padding:24px 24px 8px 24px;border-bottom:1px solid #f3f4f6;position:relative;">
          <div style="display:flex;align-items:center;position:relative;">
            <img src="cid:eclick_logo" alt="E-Click Logo" style="max-width:60px;height:auto;margin-right:15px;"/>
            <div style="flex:1;">
              <h1 style="margin:0 0 6px 0;font-size:22px;color:#dc2626;">Your E-Click Client Progress Report</h1>
              <p style="margin:0;color:#6b7280;font-size:13px;">Generated on {report_data['generated_date']}</p>
            </div>
          </div>
        </div>
        <div style="padding:24px;">
          <p style="margin:0 0 12px 0;color:#000000;font-weight:bold;">Dear {client_username},</p>

          <!-- DONUT CHART - Matplotlib generated inline image -->
          <div style="text-align:center;margin:30px 0;">
            <img src="cid:progress_chart" alt="Progress Chart" style="max-width:400px;height:auto;"/>
          </div>

          <!-- Legend -->
          <div style="text-align:center;margin:20px 0;">
            <span style="display:inline-block;margin:0 15px;">
              <span style="display:inline-block;width:15px;height:15px;background:#dc2626;border-radius:50%;vertical-align:middle;"></span>
              <span style="margin-left:5px;color:#000000;">Completed: {report_data['task_completion_rate']:.1f}%</span>
            </span>
            <span style="display:inline-block;margin:0 15px;">
              <span style="display:inline-block;width:15px;height:15px;background:#e5e7eb;border-radius:50%;vertical-align:middle;border:1px solid #ccc;"></span>
              <span style="margin-left:5px;color:#000000;">Remaining: {100 - report_data['task_completion_rate']:.1f}%</span>
            </span>
          </div>
          
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

          <h3 style="margin:18px 0 8px 0;color:#dc2626;font-size:16px;">Next Steps</h3>
          <ul style="margin:0 0 16px 20px;color:#000000;">
            <li>Review the attached PDF for full insights and project-level details.</li>
            <li>Reply with any priorities you'd like us to fast-track this week.</li>
            <li>Book a 15-minute review if you'd like us to walk you through the data.</li>
          </ul>

          <p style="margin:0 0 18px 0;color:#000000;">If you have any questions, simply reply to this email and our team will assist you.</p>
          <p style="margin:0;color:#000000;">Warm regards,<br/><strong>E-Click Project Management Team</strong></p>
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
            pdf_path = generate_client_specific_pdf_report(client_id)

            # Create email with HTML and attachments
            email = EmailMultiAlternatives(
                subject=f"Client Report - {client_username} - E-Click",
                body='Please view this email in HTML mode.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[client_email]
            )
            email.attach_alternative(email_body, "text/html")

            # Attach E-Click logo as inline image
            logo_img = MIMEImage(logo_data, 'png')
            logo_img.add_header('Content-ID', '<eclick_logo>')
            logo_img.add_header('Content-Disposition', 'inline', filename='eclick_logo.png')
            email.attach(logo_img)

            # Attach progress chart as inline image
            chart_img = MIMEImage(chart_buffer.read(), 'png')
            chart_img.add_header('Content-ID', '<progress_chart>')
            chart_img.add_header('Content-Disposition', 'inline', filename='progress_chart.png')
            email.attach(chart_img)

            # Attach PDF report
            if pdf_path:
                email.attach_file(pdf_path)

            try:
                email.send()
                result = {'success': True, 'message': 'Email sent successfully'}
            except Exception as e:
                result = {'success': False, 'error': str(e)}

            # Cleanup temporary PDF
            try:
                import os
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
            except Exception:
                pass
            print(f"Client email service result: {result}")
            
            # Handle email service result
            if result['success']:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': f'Client report sent successfully to {client_email}'})
                else:
                    messages.success(request, f'Client report sent successfully to {client_email}')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': result.get("error", "Unknown error")})
                else:
                    messages.error(request, f'Error sending client report: {result.get("error", "Unknown error")}')
            
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
        # Get projects where this client is involved (supports both old and new methods)
        projects = Project.objects.filter(
            Q(client_email=client.email) | Q(clients=client)
        ).distinct().order_by('-created_at')
        
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
            project.remaining_tasks_count = total_tasks_count - completed_tasks_count
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
        return redirect('login')

def client_project_detail(request, project_id):
    """Client view of project details including tasks"""
    if 'client_id' not in request.session:
        return redirect('login')
    
    client_id = request.session['client_id']
    try:
        client = Client.objects.get(id=client_id, is_active=True)
        # Get project where this client is involved (supports both old and new methods)
        project = Project.objects.filter(
            Q(id=project_id) & (Q(client_email=client.email) | Q(clients=client))
        ).first()

        if not project:
            return redirect('client_dashboard')
        
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
        return redirect('login')
    except Project.DoesNotExist:
        return redirect('client_dashboard')

def client_gantt_data(request):
    """API endpoint for client Gantt chart data"""
    if 'client_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'})

    client_id = request.session['client_id']
    try:
        client = Client.objects.get(id=client_id, is_active=True)
        # Get projects where this client is involved (supports both old and new methods)
        projects = Project.objects.filter(
            Q(client_email=client.email) | Q(clients=client)
        ).distinct().order_by('-created_at')

        gantt_data = []
        for project in projects:
            project_data = {
                'id': project.id,
                'name': project.name,
                'client': project.client,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'end_date': project.end_date.isoformat() if project.end_date else None,
                'status': project.status,
                'tasks': []
            }

            # Get tasks for this project
            tasks = project.tasks.all().order_by('start_date', 'created_at')
            for task in tasks:
                task_data = {
                    'id': task.id,
                    'title': task.title,
                    'start_date': task.start_date.isoformat() if task.start_date else None,
                    'end_date': task.end_date.isoformat() if task.end_date else None,
                    'status': task.status,
                    'priority': task.priority,
                    'subtasks': []
                }

                # Get subtasks for this task
                subtasks = task.subtasks.all().order_by('start_date', 'created_at')
                for subtask in subtasks:
                    subtask_data = {
                        'id': subtask.id,
                        'title': subtask.title,
                        'start_date': subtask.start_date.isoformat() if subtask.start_date else None,
                        'end_date': subtask.end_date.isoformat() if subtask.end_date else None,
                        'status': subtask.status,
                        'priority': subtask.priority
                    }
                    task_data['subtasks'].append(subtask_data)

                project_data['tasks'].append(task_data)

            gantt_data.append(project_data)

        return JsonResponse({'success': True, 'projects': gantt_data})
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Client not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def client_logout(request):
    """Client logout"""
    if 'client_id' in request.session:
        del request.session['client_id']
    if 'client_username' in request.session:
        del request.session['client_username']
    return redirect('login')

def client_settings(request):
    """Client settings page for profile management"""
    if 'client_id' not in request.session:
        return redirect('login')
    
    client_id = request.session['client_id']
    try:
        client = Client.objects.get(id=client_id, is_active=True)
        
        if request.method == 'POST':
            # Handle AJAX profile picture upload
            if request.POST.get('upload_only') == 'true':
                if 'profile_picture' in request.FILES:
                    try:
                        profile_picture = request.FILES['profile_picture']
                        # Delete old profile picture if it exists
                        if client.profile_picture:
                            client.profile_picture.delete(save=False)
                        client.profile_picture = profile_picture
                        client.save()
                        return JsonResponse({'success': True})
                    except Exception as e:
                        return JsonResponse({'success': False, 'error': str(e)})
                return JsonResponse({'success': False, 'error': 'No file provided'})

            # Handle profile updates
            username = request.POST.get('username')
            email = request.POST.get('email')

            if username and email:
                # Check if username or email already exists for other clients
                existing_client = Client.objects.filter(
                    (Q(username=username) | Q(email=email)) &
                    ~Q(id=client_id)
                ).first()
                
                if existing_client:
                    if existing_client.username == username:
                        pass
                    else:
                        pass
                else:
                    # Update client profile (username and email only)
                    old_username = client.username
                    old_email = client.email

                    client.username = username
                    client.email = email
                    client.save()

                    return redirect('client_settings')

        return render(request, 'home/client_settings.html', {
            'client': client
        })
    except Client.DoesNotExist:
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
            site_url = request.build_absolute_uri('/').rstrip('/')
            
            # Send OTP email using SimpleEmailService with Microsoft SMTP
            from .email_service import SimpleEmailService
            email_service = SimpleEmailService()
            email_result = email_service.send_email(
                to_email=client_email,
                subject=f"Set Your Password - {project.name} Project",
                body=f"""<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <p>Dear {client_username},</p>
    
    <p>Welcome to the {project.name} project! Please use the following OTP to set your password:</p>
    
    <p style="font-size: 18px; font-weight: bold; color: #2563eb;">🔐 Your OTP: {otp}</p>
    
    <p>You can set your password here:</p>
    <p><a href="{site_url}/client/setup-password/?username={client_username}" style="display: inline-block; background-color: #dc2626; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Set Up New Password</a></p>

    <p style="color: #dc2626; font-weight: bold;">⚠️ Please note: This OTP is valid for 24 hours.</p>

    <p>Best regards,<br>E-Click Project Management Team</p>
</body>
</html>""",
                from_email=None  # Will use default from settings
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
            return render(request, 'home/client_setup_password.html', {'username': username})

        if new_password != confirm_password:
            return render(request, 'home/client_setup_password.html', {'username': username})

        if len(new_password) < 8:
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
                    return render(request, 'home/client_setup_password.html')

                if not otp_obj.is_valid():
                    return render(request, 'home/client_setup_password.html')

                # Mark OTP as used
                otp_obj.is_used = True
                otp_obj.save()

                # Set client password
                client.password = new_password
                client.has_changed_password = True
                client.save()

                return redirect('client_dashboard')

            except ClientOTP.DoesNotExist:
                return render(request, 'home/client_setup_password.html')

        except Client.DoesNotExist:
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
        return redirect('login')

    try:
        client = Client.objects.get(id=client_id, is_active=True)
    except Client.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        # Verify old password
        old_password_hash = hashlib.sha256(old_password.encode()).hexdigest()
        if client.password != old_password_hash:
            return render(request, 'home/client_change_password.html')

        # Validate new password
        if new_password != confirm_password:
            return render(request, 'home/client_change_password.html')

        if len(new_password) < 6:
            return render(request, 'home/client_change_password.html')

        # Update password and mark as changed
        client.password = hashlib.sha256(new_password.encode()).hexdigest()
        client.has_changed_password = True
        client.save()

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
    """Team member dashboard showing assigned projects and tasks (Staff/Employees only)"""
    # Redirect clients to client dashboard
    if not request.user.is_staff:
        return redirect('client_dashboard')

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
            subtask = SubTask.objects.get(id=subtask_id)
            
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
            # Sync is_completed field with status field to prevent inconsistency
            subtask.is_completed = (new_status == 'completed')
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

        except SubTask.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Subtask not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def add_subtask_comment(request, subtask_id):
    """Add comment to subtask"""
    if request.method == 'POST':
        try:
            subtask = SubTask.objects.get(id=subtask_id)
            
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


def create_notification_for_project_update(project, user, update_type, old_value=None, new_value=None, reason=None):
    """Create notification when a project is updated"""
    from .models import Notification
    
    # Determine notification type and message
    if update_type == 'status_changed':
        notification_type = 'project_status_change'
        title = f'Project Status Changed: {project.name}'
        message = f'Project "{project.name}" status changed from {old_value} to {new_value}'
        if reason:
            message += f'. Reason: {reason}'
    elif update_type == 'created':
        notification_type = 'project_created'
        title = f'New Project Created: {project.name}'
        message = f'New project "{project.name}" has been created'
    elif update_type == 'deadline_extended':
        notification_type = 'deadline_extended'
        title = f'Project Deadline Extended: {project.name}'
        message = f'Project "{project.name}" deadline extended to {new_value}'
        if reason:
            message += f'. Reason: {reason}'
    else:
        notification_type = 'project_update'
        title = f'Project Updated: {project.name}'
        message = f'Project "{project.name}" was updated'
        if reason:
            message += f'. Reason: {reason}'
    
    # Create notification for project client
    if project.client:
        Notification.create_if_not_exists(
            recipient=project.client,
            notification_type=notification_type,
            title=title,
            message=message,
            triggered_by=user,
            related_project=project
        )
    
    # Notify all team members assigned to the project (but prevent duplicates)
    for task in project.tasks.all():
        if task.assigned_to and task.assigned_to != user:
            Notification.create_if_not_exists(
                recipient=task.assigned_to,
                notification_type=notification_type,
                title=title,
                message=message,
                triggered_by=user,
                related_project=project
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
    if not request.user.is_superuser:
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
            response['Content-Disposition'] = f'attachment; filename="E-Click_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            
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
    
    # from .services import GoogleCloudEmailService
    from django.utils import timezone
    from django.db.models import Q, Count, Avg
    from datetime import timedelta
    from django.conf import settings

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

            # Generate matplotlib donut chart and load logo
            from .chart_utils import generate_donut_chart
            from email.mime.image import MIMEImage
            from django.core.mail import EmailMultiAlternatives
            import os

            chart_buffer = generate_donut_chart(task_completion_rate)

            # Load E-Click logo
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'E Click Logo (1).png')
            with open(logo_path, 'rb') as f:
                logo_data = f.read()

            # Create styled email body with project information
            email_body = f"""<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5;">
<div style="font-family: Arial, sans-serif; max-width: 720px; margin: 20px auto; background-color: #ffffff; color: #000000; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
    <div style="background-color: #ffffff; padding: 20px; border-bottom: 1px solid #f3f4f6; text-align: center;">
        <img src="cid:eclick_logo" alt="E-Click Logo" style="max-width: 150px; height: auto;"/>
    </div>

    <div style="padding: 20px; background-color: #ffffff;">
        <p style="color: #000000; font-size: 16px; margin-bottom: 10px; font-weight: bold;">Dear {client_username},</p>

        <!-- DONUT CHART - Matplotlib generated inline image -->
        <div style="text-align:center;margin:30px 0;">
            <img src="cid:progress_chart" alt="Progress Chart" style="max-width:400px;height:auto;"/>
        </div>

        <!-- Legend -->
        <div style="text-align:center;margin:20px 0;">
            <span style="display:inline-block;margin:0 15px;">
                <span style="display:inline-block;width:15px;height:15px;background:#dc2626;border-radius:50%;vertical-align:middle;"></span>
                <span style="margin-left:5px;color:#000000;">Completed: {task_completion_rate:.1f}%</span>
            </span>
            <span style="display:inline-block;margin:0 15px;">
                <span style="display:inline-block;width:15px;height:15px;background:#e5e7eb;border-radius:50%;vertical-align:middle;border:1px solid #ccc;"></span>
                <span style="margin-left:5px;color:#000000;">Remaining: {100 - task_completion_rate:.1f}%</span>
            </span>
        </div>
        
        <p style="color: #000000; font-size: 14px; margin-bottom: 20px;">Please find your summary below. A detailed, presentation-ready PDF is attached for your records.</p>
        
        <div style="background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
            <h2 style="color: #1f2937; font-size: 18px; margin-top: 0; margin-bottom: 15px;">Project Summary</h2>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">
                <tr style="background-color: #2d3748; color: #ffffff;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #000000;">Project Summary</th>
                    <th style="padding: 10px; text-align: center; border: 1px solid #000000;">Totals</th>
                </tr>
                <tr style="background-color: #ffffff;">
                    <td style="padding: 10px; border: 1px solid #000000; font-weight: bold; color: #000000;">Total Projects</td>
                    <td style="padding: 10px; border: 1px solid #000000; text-align: center; color: #000000;">1</td>
                </tr>
                <tr style="background-color: #ffffff;">
                    <td style="padding: 10px; border: 1px solid #000000; font-weight: bold; color: #000000;">Completed Projects</td>
                    <td style="padding: 10px; border: 1px solid #000000; text-align: center; color: #000000;">{1 if project.status == 'completed' else 0}</td>
                </tr>
                <tr style="background-color: #ffffff;">
                    <td style="padding: 10px; border: 1px solid #000000; font-weight: bold; color: #000000;">Projects In Progress</td>
                    <td style="padding: 10px; border: 1px solid #000000; text-align: center; color: #000000;">{1 if project.status == 'in_progress' else 0}</td>
                </tr>
                <tr style="background-color: #ffffff;">
                    <td style="padding: 10px; border: 1px solid #000000; font-weight: bold; color: #000000;">Total Tasks</td>
                    <td style="padding: 10px; border: 1px solid #000000; text-align: center; color: #000000;">{total_tasks if total_tasks > 0 else 0}</td>
                </tr>
                <tr style="background-color: #ffffff;">
                    <td style="padding: 10px; border: 1px solid #000000; font-weight: bold; color: #000000;">Completed Tasks</td>
                    <td style="padding: 10px; border: 1px solid #000000; text-align: center; color: #000000;">{completed_tasks if completed_tasks > 0 else 0}</td>
                </tr>
            </table>
            
            <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                <div style="text-align: center; flex: 1; background-color: #f9fafb; border-radius: 8px; padding: 15px; margin-right: 10px;">
                    <h3 style="color: #1f2937; margin: 0 0 5px 0; font-size: 16px;">Project Completion Rate</h3>
                    <p style="color: #000000; font-size: 18px; font-weight: bold; margin: 0;">{100 if project.status == 'completed' else 0}%</p>
                </div>
                <div style="text-align: center; flex: 1; background-color: #f9fafb; border-radius: 8px; padding: 15px; margin-left: 10px;">
                    <h3 style="color: #1f2937; margin: 0 0 5px 0; font-size: 16px;">Task Completion Rate</h3>
                    <p style="color: #000000; font-size: 18px; font-weight: bold; margin: 0;">{task_completion_rate:.1f}%</p>
                </div>
            </div>
        </div>
        
        <div style="background-color: #f9fafb; border-left: 4px solid #dc2626; padding: 15px; margin-bottom: 20px;">
            <h2 style="color: #dc2626; font-size: 18px; margin-top: 0; margin-bottom: 15px;">Project Details</h2>
            <ul style="color: #000000; font-size: 14px; margin: 0; padding-left: 20px;">
                <li style="margin-bottom: 8px;"><strong>Project Name:</strong> {project.name}</li>
                <li style="margin-bottom: 8px;"><strong>Current Status:</strong> {project.get_status_display()}</li>
                <li style="margin-bottom: 8px;"><strong>Team Size:</strong> {team_size} members</li>
                <li style="margin-bottom: 8px;"><strong>Recent Activity:</strong> {recent_tasks} new tasks, {recent_subtasks} new subtasks in last 30 days</li>
            </ul>
        </div>
        
        
        
        <div style="background-color: #f9fafb; border-left: 4px solid #dc2626; padding: 15px; margin-bottom: 20px;">
            <h2 style="color: #dc2626; font-size: 18px; margin-top: 0; margin-bottom: 15px;">Next Steps</h2>
            <ul style="color: #000000; font-size: 14px; margin: 0; padding-left: 20px;">
                <li style="margin-bottom: 8px;">Review the attached PDF for full insights and project-level details.</li>
                <li style="margin-bottom: 8px;">Reply with any priorities you'd like us to fast-track this week.</li>
                <li style="margin-bottom: 8px;">Book a 15-minute review if you'd like us to walk you through the data.</li>
            </ul>
        </div>
        
        <p style="color: #000000; font-size: 14px; margin-bottom: 20px;">If you have any questions, simply reply to this email and our team will assist you.</p>
        
        <div style="text-align: center; margin-top: 30px;">
            <p style="color: #000000; font-size: 14px; margin-bottom: 10px;">Warm regards,</p>
            <p style="color: #000000; font-size: 14px; font-weight: bold; margin-bottom: 5px;">E-Click Project Management Team</p>
        </div>
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
                client_name=client_username,
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

            # Create email with HTML and attachments
            email = EmailMultiAlternatives(
                subject=subject,
                body='Please view this email in HTML mode.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[client_email]
            )
            email.attach_alternative(email_body, "text/html")

            # Attach E-Click logo as inline image
            logo_img = MIMEImage(logo_data, 'png')
            logo_img.add_header('Content-ID', '<eclick_logo>')
            logo_img.add_header('Content-Disposition', 'inline', filename='eclick_logo.png')
            email.attach(logo_img)

            # Attach progress chart as inline image
            chart_img = MIMEImage(chart_buffer.read(), 'png')
            chart_img.add_header('Content-ID', '<progress_chart>')
            chart_img.add_header('Content-Disposition', 'inline', filename='progress_chart.png')
            email.attach(chart_img)

            # Attach PDF report
            if pdf_path:
                email.attach_file(pdf_path)

            try:
                email.send()
                result = {'success': True, 'message': 'Email sent successfully'}
            except Exception as e:
                result = {'success': False, 'error': str(e)}
            
            # Clean up temporary PDF file
            try:
                import os
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
            except Exception:
                pass
                
            print(f"Enhanced project email service result: {result}")
            
            # Handle email service result
            if result['success']:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True, 
                        'message': f'Enhanced project report sent successfully to {client_email}',
                        'report_summary': {
                            'tasks_completed': completed_tasks,
                            'completion_rate': f"{task_completion_rate:.1f}%",
                            'timeline_progress': f"{timeline_progress:.1f}%",
                            'days_remaining': days_remaining
                        }
                    })
                else:
                    messages.success(request, f'Enhanced project report sent successfully to {client_email}')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': f'Error sending report: {result.get("error", "Unknown error")}'})
                else:
                    messages.error(request, f'Error sending enhanced project report: {result.get("error", "Unknown error")}')
            
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

@csrf_exempt
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
def client_forgot_password(request):
    """Client forgot password - Request OTP for password reset"""
    if request.method == 'POST':
        username_or_email = request.POST.get('username_or_email', '').strip()

        if not username_or_email:
            return render(request, 'home/client_forgot_password.html')

        try:
            # Try to find client by username or email
            from django.db.models import Q
            client = Client.objects.filter(
                Q(username=username_or_email) | Q(email=username_or_email)
            ).first()

            if not client:
                return render(request, 'home/client_forgot_password.html')

            # Generate OTP
            otp = client.generate_otp()

            # Send OTP email
            from .email_service import email_service
            site_url = request.build_absolute_uri('/')[:-1]

            email_result = email_service.send_password_reset_otp_email(
                to_email=client.email,
                otp=otp,
                username=client.username,
                site_url=site_url
            )

            if email_result['success']:
                return redirect('client_reset_password')
            else:
                return render(request, 'home/client_forgot_password.html')

        except Exception as e:
            return render(request, 'home/client_forgot_password.html')

    return render(request, 'home/client_forgot_password.html')


def client_reset_password(request):
    """Client password reset using OTP"""
    if request.method == 'POST':
        username = request.POST.get('username')
        otp = request.POST.get('otp')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if not all([username, otp, new_password, confirm_password]):
            return render(request, 'home/client_reset_password.html', {'username': username})

        if new_password != confirm_password:
            return render(request, 'home/client_reset_password.html', {'username': username})

        if len(new_password) < 8:
            return render(request, 'home/client_reset_password.html', {'username': username})

        try:
            client = Client.objects.get(username=username)

            # Verify OTP
            try:
                from .models import ClientOTP
                otp_obj = ClientOTP.objects.filter(
                    client=client,
                    otp=otp,
                    is_used=False
                ).first()

                if not otp_obj:
                    return render(request, 'home/client_reset_password.html', {'username': username})

                if not otp_obj.is_valid():
                    return render(request, 'home/client_reset_password.html', {'username': username})

                # Mark OTP as used
                otp_obj.is_used = True
                otp_obj.save()

                # Set client password
                from django.contrib.auth.hashers import make_password
                client.password = make_password(new_password)
                client.has_changed_password = True
                client.save()

                return redirect('login')

            except ClientOTP.DoesNotExist:
                return render(request, 'home/client_reset_password.html', {'username': username})

        except Client.DoesNotExist:
            return render(request, 'home/client_reset_password.html', {'username': username})

    # GET request - show form
    username = request.GET.get('username', '')
    return render(request, 'home/client_reset_password.html', {'username': username})


# =======================
# Chatbot Feedback Views
# =======================

@csrf_exempt
def chatbot_feedback(request):
    """Handle chatbot feedback and satisfaction ratings"""
    if request.method == 'POST':
        try:
            import json
            from .models import ChatbotFeedback
            
            data = json.loads(request.body)
            
            # Get session ID (generate if not provided)
            session_id = data.get('session_id', request.session.session_key or f'anon-{timezone.now().timestamp()}')
            
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
            
            # Create feedback record
            feedback = ChatbotFeedback.objects.create(
                session_id=session_id,
                feedback_type=data.get('feedback_type', 'general'),
                feedback_text=data.get('feedback_text', ''),
                satisfaction_rating=data.get('satisfaction_rating'),
                user_email=data.get('user_email'),
                user_name=data.get('user_name'),
                conversation_context=data.get('conversation_context', {}),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                ip_address=ip_address
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Thank you for your feedback!',
                'feedback_id': feedback.id
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'POST request required'}, status=405)


@csrf_exempt  
def chatbot_satisfaction(request):
    """Handle satisfaction rating submission"""
    if request.method == 'POST':
        try:
            import json
            from .models import ChatbotFeedback
            
            data = json.loads(request.body)
            rating = data.get('rating')
            
            if not rating or not (1 <= int(rating) <= 5):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid rating. Must be between 1 and 5'
                }, status=400)
            
            # Get session ID
            session_id = data.get('session_id', request.session.session_key or f'anon-{timezone.now().timestamp()}')
            
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
            
            # Create satisfaction feedback
            feedback = ChatbotFeedback.objects.create(
                session_id=session_id,
                feedback_type='satisfaction',
                satisfaction_rating=int(rating),
                conversation_context=data.get('conversation_context', {}),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                ip_address=ip_address
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Thank you! You rated {rating} out of 5',
                'feedback_id': feedback.id
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'POST request required'}, status=405)


def chatbot_stats(request):
    """Get chatbot satisfaction statistics (for admin)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    from .models import ChatbotFeedback
    from django.db.models import Count, Avg
    
    # Get average satisfaction
    avg_satisfaction = ChatbotFeedback.get_average_satisfaction()
    
    # Get distribution
    distribution = list(ChatbotFeedback.get_satisfaction_distribution())
    
    # Get total feedback count
    total_feedback = ChatbotFeedback.objects.count()
    total_ratings = ChatbotFeedback.objects.filter(satisfaction_rating__isnull=False).count()
    
    # Get recent feedback
    recent_feedback = ChatbotFeedback.objects.filter(
        feedback_text__isnull=False
    ).exclude(feedback_text='').values(
        'id', 'feedback_type', 'feedback_text', 'satisfaction_rating', 'created_at'
    ).order_by('-created_at')[:10]
    
    return JsonResponse({
        'success': True,
        'stats': {
            'average_satisfaction': avg_satisfaction,
            'distribution': distribution,
            'total_feedback': total_feedback,
            'total_ratings': total_ratings,
            'recent_feedback': list(recent_feedback)
        }
    })


@login_required
def satisfaction_report(request):
    """Satisfaction report page (Admin only)"""
    # Check if user is admin
    if not request.user.is_superuser:
        return redirect('home:index')

    from .models import ChatbotFeedback
    from django.db.models import Count, Avg, Q
    from django.utils import timezone
    from datetime import timedelta

    # Get average satisfaction
    avg_satisfaction = ChatbotFeedback.get_average_satisfaction()

    # Get distribution
    distribution = list(ChatbotFeedback.get_satisfaction_distribution())

    # Get total feedback count
    total_feedback = ChatbotFeedback.objects.count()
    total_ratings = ChatbotFeedback.objects.filter(satisfaction_rating__isnull=False).count()

    # Get recent feedback (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_count = ChatbotFeedback.objects.filter(created_at__gte=thirty_days_ago).count()

    # Get feedback by day for the last 30 days for trend chart
    daily_feedback = []
    chart_labels = []
    chart_ratings = []
    chart_counts = []

    for i in range(30):
        day = timezone.now() - timedelta(days=29-i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        count = ChatbotFeedback.objects.filter(
            created_at__gte=day_start,
            created_at__lte=day_end
        ).count()

        avg_rating = ChatbotFeedback.objects.filter(
            created_at__gte=day_start,
            created_at__lte=day_end,
            satisfaction_rating__isnull=False
        ).aggregate(Avg('satisfaction_rating'))['satisfaction_rating__avg']

        daily_feedback.append({
            'date': day.strftime('%Y-%m-%d'),
            'day_name': day.strftime('%a'),
            'count': count,
            'avg_rating': round(avg_rating, 2) if avg_rating else 0
        })

        # Data for chart
        chart_labels.append(day.strftime('%b %d'))
        chart_ratings.append(round(avg_rating, 2) if avg_rating else None)
        chart_counts.append(count)

    # Get recent detailed feedback
    recent_feedback = ChatbotFeedback.objects.filter(
        Q(feedback_text__isnull=False) | Q(satisfaction_rating__isnull=False)
    ).select_related().order_by('-created_at')[:20]

    import json

    context = {
        'avg_satisfaction': avg_satisfaction,
        'distribution': distribution,
        'total_feedback': total_feedback,
        'total_ratings': total_ratings,
        'recent_count': recent_count,
        'daily_feedback': daily_feedback,
        'recent_feedback': recent_feedback,
        'chart_labels': json.dumps(chart_labels),
        'chart_ratings': json.dumps(chart_ratings),
        'chart_counts': json.dumps(chart_counts),
    }

    return render(request, 'home/satisfaction_report.html', context)


# Password Reset Views
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.core.mail import send_mail

def password_reset_request(request):
    """Handle password reset request"""
    if request.method == 'POST':
        username_or_email = request.POST.get('username_or_email', '').strip()

        if not username_or_email:
            messages.error(request, 'Please enter your username or email address.')
            return render(request, 'home/password_reset.html')

        # Try to find user by username or email (both User and Client)
        user = None
        is_client = False
        user_email = None

        # Check Django users first - try username then email
        try:
            user = User.objects.get(username=username_or_email)
            user_email = user.email
        except User.DoesNotExist:
            try:
                user = User.objects.get(email=username_or_email)
                user_email = user.email
            except User.DoesNotExist:
                # Check clients - try username then email
                try:
                    user = Client.objects.get(username=username_or_email)
                    user_email = user.email
                    is_client = True
                except Client.DoesNotExist:
                    try:
                        user = Client.objects.get(email=username_or_email)
                        user_email = user.email
                        is_client = True
                    except Client.DoesNotExist:
                        pass

        if user and user_email:
            # Generate token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            # Build reset URL
            reset_url = request.build_absolute_uri(
                f'/password-reset-confirm/{uid}/{token}/'
            )

            # Build logo URL (URL-encoded)
            logo_url = request.build_absolute_uri('/static/images/E%20Click%20Logo%20(1).png')

            # Get user's name
            user_name = getattr(user, 'first_name', None) or getattr(user, 'username', 'User')

            # Send simple email
            from django.core.mail import EmailMultiAlternatives

            subject = 'Password Reset Request - E-Click Technologies'

            # Plain text version
            text_content = f"""E-CLICK TECHNOLOGIES

Dear {user_name},

We received a request to reset your password for your E-Click Technologies account.

To reset your password, please click the following link:
{reset_url}

This link will expire in 24 hours for security purposes.

If you did not request a password reset, please disregard this email and your password will remain unchanged. For security concerns, please contact us immediately.

Best regards,
E-Click Technologies Team

---
Need assistance? Contact us:
Email: info@eclick.co.za
Phone: +27 76 740 1777"""

            # Simple HTML version (just makes "Reset Password" clickable instead of showing URL)
            html_content = f"""<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="text-align: center; margin-bottom: 30px;">
        <img src="{logo_url}" alt="E-Click Technologies" style="height: 50px; width: auto;">
    </div>

    <p>Dear {user_name},</p>

    <p>We received a request to reset your password for your E-Click Technologies account.</p>

    <p>To reset your password, please click: <a href="{reset_url}" style="color: #dc2626; text-decoration: none; font-weight: bold;">Reset Password</a></p>

    <p style="color: #666; font-size: 14px;"><strong>Important:</strong> This link will expire in 24 hours for security purposes.</p>

    <p>If you did not request a password reset, please disregard this email and your password will remain unchanged. For security concerns, please contact us immediately.</p>

    <p>Best regards,<br>
    <strong>E-Click Technologies Team</strong></p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">

    <p style="font-size: 12px; color: #666;">
        <strong>Need assistance?</strong><br>
        Email: <a href="mailto:info@eclick.co.za" style="color: #dc2626; text-decoration: none;">info@eclick.co.za</a><br>
        Phone: <a href="tel:+27767401777" style="color: #dc2626; text-decoration: none;">+27 76 740 1777</a>
    </p>
</body>
</html>"""

            try:
                email = EmailMultiAlternatives(
                    subject,
                    text_content,
                    django_settings.DEFAULT_FROM_EMAIL,
                    [user_email]
                )
                email.attach_alternative(html_content, "text/html")
                email.send(fail_silently=False)

                messages.success(request, 'Password reset email sent! Please check your inbox.')
                return redirect('password_reset_done')
            except Exception as e:
                messages.error(request, f'Error sending email: {str(e)}')
                return render(request, 'home/password_reset.html')
        else:
            # Don't reveal if username/email exists or not (security best practice)
            messages.success(request, 'If an account with that username or email exists, a password reset link has been sent.')
            return redirect('password_reset_done')

    return render(request, 'home/password_reset.html')

def password_reset_done(request):
    """Show confirmation that reset email was sent"""
    return render(request, 'home/password_reset_done.html')

def password_reset_confirm(request, uidb64, token):
    """Handle password reset with token"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))

        # Try User first
        user = None
        is_client = False
        try:
            user = User.objects.get(pk=uid)
        except User.DoesNotExist:
            try:
                user = Client.objects.get(pk=uid)
                is_client = True
            except Client.DoesNotExist:
                user = None

        if user and default_token_generator.check_token(user, token):
            if request.method == 'POST':
                password1 = request.POST.get('password1')
                password2 = request.POST.get('password2')

                if password1 != password2:
                    messages.error(request, 'Passwords do not match.')
                    return render(request, 'home/password_reset_confirm.html')

                if len(password1) < 8:
                    messages.error(request, 'Password must be at least 8 characters long.')
                    return render(request, 'home/password_reset_confirm.html')

                # Set new password
                if is_client:
                    from django.contrib.auth.hashers import make_password
                    user.password = make_password(password1)
                    user.save()
                else:
                    user.set_password(password1)
                    user.save()

                messages.success(request, 'Password reset successful! You can now login with your new password.')
                return redirect('password_reset_complete')

            return render(request, 'home/password_reset_confirm.html')
        else:
            messages.error(request, 'Invalid or expired password reset link.')
            return redirect('password_reset')

    except Exception as e:
        messages.error(request, 'Invalid password reset link.')
        return redirect('password_reset')

def password_reset_complete(request):
    """Show confirmation that password was reset"""
    return render(request, 'home/password_reset_complete.html')


@login_required
def eclick_chats(request):
    """Eclick Chats page - where clients and employees can send messages to devs"""
    from .models import DevMessage, Project
    from django.db.models import Count, Q
    from django.contrib import messages as django_messages

    # Handle POST request (sending new message)
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'send_message':
            message_type = request.POST.get('message_type', 'feedback')
            subject = request.POST.get('subject', '').strip()
            message = request.POST.get('message', '').strip()
            priority = request.POST.get('priority', 'medium')
            project_id = request.POST.get('project')

            # Truncate subject to fit database limit (1000 chars)
            max_subject_length = 1000
            if len(subject) > max_subject_length:
                subject = subject[:max_subject_length - 3] + '...'

            if subject and message:
                dev_message = DevMessage.objects.create(
                    user=request.user,
                    message_type=message_type,
                    subject=subject,
                    message=message,
                    priority=priority,
                    project_id=project_id if project_id else None
                )

                # Send email notification to admin
                try:
                    from .email_service import email_service

                    # Get project name if available
                    project_name = 'None'
                    if project_id:
                        try:
                            project = Project.objects.get(id=project_id)
                            project_name = project.name
                        except Project.DoesNotExist:
                            pass

                    # Prepare email content
                    email_subject = f"New Message from {request.user.get_full_name() or request.user.username}"

                    # Read and encode the logo
                    import base64
                    logo_path = os.path.join(django_settings.BASE_DIR, 'static', 'images', 'E Click Logo (1).png')
                    with open(logo_path, 'rb') as logo_file:
                        logo_data = base64.b64encode(logo_file.read()).decode()

                    # Build HTML email body with logo
                    email_body = f"""<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="text-align: center; margin-bottom: 20px;">
        <img src="data:image/png;base64,{logo_data}" alt="E-Click Logo" style="max-width: 200px;">
    </div>

    <p><strong>Subject:</strong> {subject}</p>

    <p><strong>Message:</strong></p>
    <p>{message}</p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="text-align: center; color: #666; font-size: 14px;">E-Click Project Management System</p>
</body>
</html>"""

                    # Send email to admin
                    email_service.send_email(
                        to_email='ethan.sevenster@moc-pty.com',
                        subject=email_subject,
                        body=email_body
                    )
                except Exception as e:
                    # Log error but don't fail the message submission
                    logger.error(f"Failed to send email notification: {e}")

                django_messages.success(request, 'Your message has been sent successfully!')
                return redirect('eclick_chats')
            else:
                django_messages.error(request, 'Please provide both subject and message.')

        elif action == 'respond' and request.user.is_staff:
            message_id = request.POST.get('message_id')
            response = request.POST.get('response', '').strip()

            if message_id and response:
                try:
                    dev_message = DevMessage.objects.get(id=message_id)
                    dev_message.admin_response = response
                    dev_message.responded_by = request.user
                    dev_message.responded_at = timezone.now()
                    dev_message.status = 'resolved'
                    dev_message.save()
                    django_messages.success(request, 'Response sent successfully!')
                except DevMessage.DoesNotExist:
                    django_messages.error(request, 'Message not found.')

        elif action == 'update_status' and request.user.is_staff:
            message_id = request.POST.get('message_id')
            new_status = request.POST.get('status')

            if message_id and new_status:
                try:
                    dev_message = DevMessage.objects.get(id=message_id)
                    dev_message.status = new_status
                    dev_message.save()
                    django_messages.success(request, 'Status updated successfully!')
                except DevMessage.DoesNotExist:
                    django_messages.error(request, 'Message not found.')

        elif action == 'delete_message' and request.user.is_staff:
            message_id = request.POST.get('message_id')

            if message_id:
                try:
                    dev_message = DevMessage.objects.get(id=message_id)
                    dev_message.delete()
                    django_messages.success(request, 'Message deleted successfully!')
                    return redirect('eclick_chats')
                except DevMessage.DoesNotExist:
                    django_messages.error(request, 'Message not found.')

    # Get messages based on user role
    if request.user.is_staff:
        # Admin sees all messages
        all_messages = DevMessage.objects.select_related('user', 'project', 'responded_by').all()
    else:
        # Regular users see only their messages
        all_messages = DevMessage.objects.filter(user=request.user).select_related('project', 'responded_by').all()

    # Apply filters from GET parameters
    from datetime import timedelta

    # Date filter
    date_filter = request.GET.get('date_filter', 'all')
    if date_filter == 'week':
        week_ago = timezone.now() - timedelta(days=7)
        all_messages = all_messages.filter(created_at__gte=week_ago)
    elif date_filter == 'month':
        month_ago = timezone.now() - timedelta(days=30)
        all_messages = all_messages.filter(created_at__gte=month_ago)
    elif date_filter == 'today':
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        all_messages = all_messages.filter(created_at__gte=today_start)

    # Search filter
    search_query = request.GET.get('search', '').strip()
    if search_query:
        all_messages = all_messages.filter(
            Q(subject__icontains=search_query) |
            Q(message__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )

    # Status filter
    status_filter = request.GET.get('status', '')
    if status_filter:
        all_messages = all_messages.filter(status=status_filter)

    # Message type filter
    type_filter = request.GET.get('type', '')
    if type_filter:
        all_messages = all_messages.filter(message_type=type_filter)

    # Get statistics
    total_messages = all_messages.count()
    new_messages = all_messages.filter(status='new').count()
    resolved_messages = all_messages.filter(status='resolved').count()

    # Get messages by type
    messages_by_type = all_messages.values('message_type').annotate(count=Count('id'))

    # Get user's projects for dropdown
    if request.user.is_staff:
        user_projects = Project.objects.all()
    else:
        user_projects = Project.objects.filter(
            Q(assigned_users=request.user) | Q(client_username=request.user.username)
        ).distinct()

    # Admin sees full dashboard with stats, regular users see simple form
    if request.user.is_staff:
        context = {
            'dev_messages': all_messages.order_by('-created_at')[:100],  # Latest 100 messages
            'total_messages': total_messages,
            'new_messages': new_messages,
            'resolved_messages': resolved_messages,
            'messages_by_type': messages_by_type,
            'user_projects': user_projects,
            'is_admin': request.user.is_staff,
            'current_date_filter': date_filter,
            'current_search': search_query,
            'current_status': status_filter,
            'current_type': type_filter,
        }
        return render(request, 'home/eclickchatsadmin.html', context)
    else:
        context = {
            'user_projects': user_projects,
        }
        return render(request, 'home/eclick_chats.html', context)
