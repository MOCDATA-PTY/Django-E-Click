# main/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User, Project, Activity, Task
from .forms import ProjectForm, ActivityForm, TaskForm
import json
from datetime import datetime, timedelta

def home(request):
    """Home page view with all sections"""
    
    # Data for different sections
    context = {
        'testimonials': [
            {
                'name': 'Jennifer Smith',
                'role': 'CTO, TechCorp Inc.',
                'message': "E-click transformed our business operations by implementing their custom ERP solution. We've seen a 30% increase in productivity and significant cost savings.",
                'rating': 5,
                'initials': 'JS'
            },
            {
                'name': 'Michael Johnson',
                'role': 'CEO, Startup Ventures',
                'message': 'As a startup, we needed a flexible solution that could grow with us. E-click delivered an outstanding platform that has been instrumental in our rapid growth.',
                'rating': 5,
                'initials': 'MJ'
            },
            {
                'name': 'Sarah Williams',
                'role': 'Operations Director, Global Retail',
                'message': 'The e-commerce platform developed by E-click has completely revolutionized our online presence. Our sales have increased by 45% since implementation.',
                'rating': 4,
                'initials': 'SW'
            },
            {
                'name': 'Robert Chen',
                'role': 'IT Manager, Healthcare Solutions',
                'message': "E-click's attention to detail and understanding of our industry's compliance requirements made them the perfect partner for our digital transformation journey.",
                'rating': 5,
                'initials': 'RC'
            }
        ],
        'companies': [
            {
                'name': 'FSA',
                'logo_url': 'images/FSA LOGO.png',
                'alt': 'FSA logo'
            },
            {
                'name': 'NAB',
                'logo_url': 'images/NAB Logo.jpg',
                'alt': 'NAB logo'
            },
            {
                'name': 'Prokon',
                'logo_url': 'images/Prokon Logo.png',
                'alt': 'Prokon logo'
            }
        ],
        'services': [
            {
                'title': 'Custom Software Development',
                'description': 'Tailor-made software solutions designed to meet your specific business requirements and challenges.',
                'icon': 'code'
            },
            {
                'title': 'Cloud-Based Solutions', 
                'description': 'Scalable and secure cloud infrastructure that grows with your business needs and reduces IT costs.',
                'icon': 'database'
            },
            {
                'title': 'Business Process Automation',
                'description': 'Streamline your operations with intelligent automation solutions that reduce manual tasks and increase efficiency.',
                'icon': 'zap'
            },
            {
                'title': 'Enterprise Integration',
                'description': 'Seamless integration of your existing systems with modern software solutions for improved efficiency.',
                'icon': 'server'
            },
            {
                'title': 'Technical Consultancy',
                'description': 'Expert advice and strategic planning to optimize your technology investments and digital transformation.',
                'icon': 'settings'
            }
        ],
        'solutions': [
            {
                'id': 'enterprise',
                'title': 'Enterprise Solutions',
                'description': 'Powerful infrastructure for large organizations with complex requirements.',
                'features': [
                    'ERP Integration',
                    'Workflow Automation', 
                    'Business Analytics',
                    'Multi-department Collaboration'
                ]
            },
            {
                'id': 'smb',
                'title': 'Small Business Solutions',
                'description': 'Affordable software that scales with your small to medium business.',
                'features': [
                    'CRM Systems',
                    'Payment Solutions',
                    'Marketing Automation',
                    'Cloud Storage'
                ]
            },
            {
                'id': 'startup',
                'title': 'Startup Innovation',
                'description': 'Agile solutions for startups looking to disrupt their industries.',
                'features': [
                    'MVP Development',
                    'Rapid Prototyping',
                    'API Integration',
                    'Scalable Architecture'
                ]
            }
        ]
    }
    
    return render(request, 'home.html', context)

@require_POST
def toggle_theme(request):
    """Toggle between light and dark theme"""
    current_theme = request.session.get('theme', 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    request.session['theme'] = new_theme
    
    return JsonResponse({'theme': new_theme})

def contact(request):
    """Contact page view"""
    return render(request, 'contact.html')

@csrf_exempt
@require_POST 
def subscribe(request):
    """Newsletter subscription endpoint"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        
        # Here you would typically save to database or send to email service
        # For now, just return success
        
        return JsonResponse({
            'status': 'success',
            'message': 'Thank you for subscribing!'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error', 
            'message': 'Failed to subscribe. Please try again.'
        }, status=400)

def signup(request):
    """User registration view"""
    if request.method == 'POST':
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        company_name = request.POST.get('company_name')
        position = request.POST.get('position')
        phone_number = request.POST.get('phone_number')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return redirect('main:signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return redirect('main:signup')

        user = User.objects.create_user(
            email=email,
            username=username,
            password=password,
            company_name=company_name,
            position=position,
            phone_number=phone_number
        )

        login(request, user)
        messages.success(request, 'Account created successfully!')
        return redirect('main:home')

    return render(request, 'auth/signup.html')

def login_view(request):
    """User login view"""
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        user = authenticate(request, email=email, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Logged in successfully!')
            return redirect('main:dashboard')
        else:
            messages.error(request, 'Invalid email or password')
            return redirect('main:login')

    return render(request, 'auth/login.html')

@login_required
def logout_view(request):
    """User logout view"""
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('main:home')

@login_required
def dashboard(request):
    """User dashboard view"""
    # Get project statistics
    projects = request.user.projects.all()
    total_projects = projects.count()
    in_progress = projects.filter(status='in-progress').count()
    completed = projects.filter(status='completed').count()
    planning = projects.filter(status='planning').count()
    
    # Get recent activities from all projects
    recent_activities = Activity.objects.filter(project__in=projects).order_by('-created_at')[:5]
    
    # Generate weeks for Gantt chart
    all_weeks = []
    for project in projects:
        current_date = project.start_date
        while current_date <= project.end_date:
            if current_date not in all_weeks:
                all_weeks.append(current_date)
            current_date += timedelta(days=7)
    all_weeks.sort()
    
    context = {
        'total_projects': total_projects,
        'in_progress': in_progress,
        'completed': completed,
        'planning': planning,
        'projects': projects,
        'weeks': all_weeks,
        'recent_activities': recent_activities,
    }
    return render(request, 'dashboard.html', context)

@login_required
def project_list(request):
    """View for listing all projects"""
    projects = Project.objects.filter(team=request.user).order_by('-start_date')
    return render(request, 'projects/project_list.html', {'projects': projects})

@login_required
def project_detail(request, project_id):
    """View for project details and Gantt chart"""
    project = get_object_or_404(Project, id=project_id)
    
    # Generate list of weeks for the Gantt chart
    start_date = project.start_date
    end_date = project.end_date
    weeks = []
    current_date = start_date
    while current_date <= end_date:
        weeks.append(current_date)
        current_date += timedelta(days=7)
    
    context = {
        'project': project,
        'weeks': weeks,
    }
    return render(request, 'projects/project_detail.html', context)

@login_required
def create_project(request):
    """View for creating a new project"""
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()
            form.save_m2m()  # Save many-to-many relationships
            messages.success(request, 'Project created successfully!')
            return redirect('main:project_detail', project_id=project.id)
    else:
        form = ProjectForm()
    return render(request, 'projects/project_form.html', {'form': form, 'action': 'Create'})

@login_required
def update_project(request, project_id):
    """View for updating a project"""
    project = get_object_or_404(Project, id=project_id)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project updated successfully!')
            return redirect('main:project_detail', project_id=project.id)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'projects/project_form.html', {'form': form, 'action': 'Update'})

@login_required
def create_activity(request, project_id):
    """View for creating a new activity"""
    project = get_object_or_404(Project, id=project_id)
    if request.method == 'POST':
        print("POST data:", request.POST)  # Debug print
        form = ActivityForm(request.POST, project=project)
        print("Form is valid:", form.is_valid())  # Debug print
        if form.is_valid():
            try:
                activity = form.save(commit=False)
                activity.project = project
                activity.activity_number = project.activities.count() + 1
                activity.save()
                print("Activity saved successfully:", activity.id)  # Debug print
                messages.success(request, 'Activity created successfully!')
                return redirect('main:project_detail', project_id=project.id)
            except Exception as e:
                print("Error saving activity:", str(e))  # Debug print
                messages.error(request, f'Error creating activity: {str(e)}')
        else:
            print("Form errors:", form.errors)  # Debug print
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ActivityForm(project=project)
    
    context = {
        'form': form,
        'project': project,
        'action': 'Create'
    }
    print("Rendering form with context:", context)  # Debug print
    return render(request, 'projects/activity_form.html', context)

@login_required
def update_activity(request, project_id, activity_id):
    """View for updating an activity"""
    project = get_object_or_404(Project, id=project_id)
    activity = get_object_or_404(Activity, id=activity_id, project=project)
    if request.method == 'POST':
        form = ActivityForm(request.POST, instance=activity)
        if form.is_valid():
            form.save()
            messages.success(request, 'Activity updated successfully!')
            return redirect('main:project_detail', project_id=project.id)
    else:
        form = ActivityForm(instance=activity)
    return render(request, 'projects/activity_form.html', {'form': form, 'project': project, 'action': 'Update'})

@login_required
def toggle_task(request, project_id, activity_id, task_id):
    """View for toggling task completion status"""
    project = get_object_or_404(Project, id=project_id)
    activity = get_object_or_404(Activity, id=activity_id, project=project)
    task = get_object_or_404(Task, id=task_id, activity=activity)
    
    task.completed = not task.completed
    task.save()
    
    # Update activity progress
    total_tasks = activity.tasks.count()
    completed_tasks = activity.tasks.filter(completed=True).count()
    activity.progress = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    activity.status = 'completed' if activity.progress == 100 else 'in-progress' if activity.progress > 0 else 'planning'
    activity.save()
    
    # Update project progress
    total_activities = project.activities.count()
    completed_activities = project.activities.filter(status='completed').count()
    project.progress = int((completed_activities / total_activities) * 100) if total_activities > 0 else 0
    project.status = 'completed' if project.progress == 100 else 'in-progress' if project.progress > 0 else 'planning'
    project.save()
    
    return JsonResponse({
        'task_completed': task.completed,
        'activity_progress': activity.progress,
        'activity_status': activity.status,
        'project_progress': project.progress,
        'project_status': project.status
    })