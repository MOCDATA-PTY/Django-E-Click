from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from home.models import Client, Project, Task
from home.email_service import email_service
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send weekly client reports to all active clients'

    def add_arguments(self, parser):
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
        dry_run = options['dry_run']
        specific_client = options['client']
        
        self.stdout.write(
            self.style.SUCCESS('Starting weekly client report generation...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No emails will be sent')
            )
        
        # Get current date and week range
        current_date = timezone.now()
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
        
        for client in clients:
            try:
                # Generate report data for this client
                report_data = self._generate_client_report_data(client, week_start, current_date)
                
                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would send report to {client.username} ({client.email})'
                    )
                    self.stdout.write(f'  Projects: {report_data["total_projects"]}')
                    self.stdout.write(f'  Tasks: {report_data["total_tasks"]}')
                    continue
                
                # Send the report
                result = email_service.send_weekly_client_report(
                    client_email=client.email,
                    client_username=client.username,
                    report_data=report_data,
                    site_url=settings.SITE_URL if hasattr(settings, 'SITE_URL') else None
                )
                
                if result['success']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Report sent to {client.username} ({client.email})'
                        )
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ Failed to send report to {client.username}: {result.get("error", "Unknown error")}'
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
                logger.error(f'Error sending weekly report to client {client.username}: {str(e)}')
        
        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[DRY RUN] Would have sent {clients.count()} reports'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Weekly reports completed: {success_count} sent, {error_count} failed'
                )
            )

    def _generate_client_report_data(self, client, week_start, current_date):
        """Generate weekly report data for a specific client"""

        # Get client's projects using both new ManyToMany relationship and legacy client_username
        client_projects = Project.objects.filter(
            Q(clients=client) | Q(client_username=client.username)
        ).distinct()
        
        # Project statistics
        total_projects = client_projects.count()
        active_projects = client_projects.filter(status='in_progress').count()
        completed_projects = client_projects.filter(status='completed').count()
        
        # Task statistics
        total_tasks = Task.objects.filter(project__client_username=client.username).count()
        
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
                'end_date': project.end_date
            })
        
        # Get recent task activity (last 7 days)
        recent_tasks = Task.objects.filter(
            project__client_username=client.username,
            updated_at__gte=week_start
        ).select_related('project').order_by('-updated_at')[:10]
        
        tasks_data = []
        for task in recent_tasks:
            tasks_data.append({
                'title': task.title,
                'status': task.status,
                'project_name': task.project.name,
                'updated_at': task.updated_at,
                'priority': task.priority
            })
        
        return {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'total_tasks': total_tasks,
            'projects': projects_data,
            'recent_tasks': tasks_data,
            'report_date': current_date.strftime('%B %d, %Y'),
            'week_range': f"{week_start.strftime('%B %d')} - {current_date.strftime('%B %d, %Y')}"
        }
