from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from home.models import Client, Project, Task
from home.email_service import email_service
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send Friday reports to all active clients automatically'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force send reports even if not Friday (for testing)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending emails',
        )
        parser.add_argument(
            '--client',
            type=str,
            help='Send report to specific client username only',
        )

    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']
        specific_client = options['client']
        
        # Check if it's Friday (unless forced)
        current_date = timezone.now()
        is_friday = current_date.weekday() == 4  # Monday=0, Friday=4
        
        if not is_friday and not force:
            self.stdout.write(
                self.style.WARNING(
                    f'Today is {current_date.strftime("%A")}, not Friday. '
                    'Use --force to send reports anyway.'
                )
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting Friday client report generation for {current_date.strftime("%A, %B %d, %Y")}...'
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No emails will be sent')
            )
        
        # Get current date and week range
        week_start = current_date - timedelta(days=7)
        
        # Get all active clients
        if specific_client:
            clients = Client.objects.filter(username=specific_client, is_active=True)
            if not clients.exists():
                self.stdout.write(
                    self.style.ERROR(f'Client "{specific_client}" not found or not active')
                )
                return
        else:
            clients = Client.objects.filter(is_active=True)
        
        self.stdout.write(f'Found {clients.count()} active clients')
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for client in clients:
            try:
                # Check if client has any projects
                client_projects = Project.objects.filter(client_username=client.username)
                if not client_projects.exists():
                    if not dry_run:
                        self.stdout.write(
                            f'⚠ Skipping {client.username} - no projects found'
                        )
                    skipped_count += 1
                    continue
                
                # Generate report data for this client
                report_data = self._generate_friday_client_report_data(client, week_start, current_date)
                
                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would send Friday report to {client.username} ({client.email})'
                    )
                    self.stdout.write(f'  Projects: {report_data["total_projects"]}')
                    self.stdout.write(f'  Tasks: {report_data["total_tasks"]}')
                    self.stdout.write(f'  Active Projects: {report_data["active_projects"]}')
                    continue
                
                # Send the Friday report
                result = email_service.send_friday_client_report(
                    client_email=client.email,
                    client_username=client.username,
                    report_data=report_data,
                    site_url=settings.SITE_URL if hasattr(settings, 'SITE_URL') else None
                )
                
                if result['success']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Friday report sent to {client.username} ({client.email})'
                        )
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ Failed to send Friday report to {client.username}: {result.get("error", "Unknown error")}'
                        )
                    )
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Error processing client {client.username}: {str(e)}'
                    )
                )
                error_count += 1
                logger.error(f'Error sending Friday report to client {client.username}: {str(e)}')
        
        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[DRY RUN] Would have sent {clients.count() - skipped_count} Friday reports'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Friday reports completed: {success_count} sent, {error_count} failed, {skipped_count} skipped'
                )
            )

    def _generate_friday_client_report_data(self, client, week_start, current_date):
        """Generate Friday report data for a specific client"""
        
        # Get client's projects
        client_projects = Project.objects.filter(client_username=client.username)
        
        # Project statistics
        total_projects = client_projects.count()
        active_projects = client_projects.filter(status='in_progress').count()
        completed_projects = client_projects.filter(status='completed').count()
        planned_projects = client_projects.filter(status='planned').count()
        
        # Task statistics
        total_tasks = Task.objects.filter(project__client_username=client.username).count()
        completed_tasks = Task.objects.filter(
            project__client_username=client.username, 
            status='completed'
        ).count()
        in_progress_tasks = Task.objects.filter(
            project__client_username=client.username, 
            status='in_progress'
        ).count()
        
        # Calculate completion rates
        project_completion_rate = (completed_projects / total_projects * 100) if total_projects > 0 else 0
        task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Get project details for the report
        projects_data = []
        for project in client_projects:
            project_tasks = project.tasks.all()
            if project_tasks.exists():
                completion_rate = (project_tasks.filter(status='completed').count() / project_tasks.count()) * 100
            else:
                completion_rate = 0
                
            projects_data.append({
                'name': project.name,
                'status': project.status,
                'description': project.description or 'No description available',
                'completion_rate': round(completion_rate, 1),
                'start_date': project.start_date,
                'end_date': project.end_date,
                'total_tasks': project_tasks.count(),
                'completed_tasks': project_tasks.filter(status='completed').count()
            })
        
        # Get recent task activity (last 7 days)
        recent_tasks = Task.objects.filter(
            project__client_username=client.username,
            updated_at__gte=week_start
        ).select_related('project').order_by('-updated_at')[:15]
        
        tasks_data = []
        for task in recent_tasks:
            tasks_data.append({
                'title': task.title,
                'status': task.status,
                'project_name': task.project.name,
                'updated_at': task.updated_at,
                'priority': task.priority,
                'description': task.description or 'No description'
            })
        
        # Get upcoming deadlines (next 2 weeks)
        upcoming_deadlines = []
        for project in client_projects.filter(status='in_progress'):
            if project.end_date:
                days_until_deadline = (project.end_date - current_date.date()).days
                if 0 <= days_until_deadline <= 14:
                    upcoming_deadlines.append({
                        'project_name': project.name,
                        'deadline': project.end_date,
                        'days_remaining': days_until_deadline,
                        'completion_rate': next((p['completion_rate'] for p in projects_data if p['name'] == project.name), 0)
                    })
        
        # Sort by urgency (closest deadline first)
        upcoming_deadlines.sort(key=lambda x: x['days_remaining'])
        
        return {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'planned_projects': planned_projects,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'project_completion_rate': round(project_completion_rate, 1),
            'task_completion_rate': round(task_completion_rate, 1),
            'projects': projects_data,
            'recent_tasks': tasks_data,
            'upcoming_deadlines': upcoming_deadlines,
            'report_date': current_date.strftime('%B %d, %Y'),
            'week_range': f"{week_start.strftime('%B %d')} - {current_date.strftime('%B %d, %Y')}",
            'is_friday': True,
            'next_friday': (current_date + timedelta(days=7)).strftime('%B %d, %Y')
        }
