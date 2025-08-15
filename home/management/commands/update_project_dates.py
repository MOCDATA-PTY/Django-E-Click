from django.core.management.base import BaseCommand
from home.models import Project
from datetime import timedelta

class Command(BaseCommand):
    help = 'Update existing projects with proper end dates based on task dates'

    def handle(self, *args, **options):
        projects = Project.objects.filter(end_date__isnull=True)
        
        for project in projects:
            # Get all tasks for this project
            tasks = project.tasks.all()
            
            if tasks.exists():
                # Find earliest start date and latest end date from tasks
                earliest_start = min(task.start_date for task in tasks if task.start_date)
                latest_end = max(task.end_date for task in tasks if task.end_date)
                
                if earliest_start and latest_end:
                    project.start_date = earliest_start
                    project.end_date = latest_end
                    project.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'Updated project "{project.name}" with dates: {project.start_date} to {project.end_date}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'Project "{project.name}" has tasks but missing start/end dates')
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Project "{project.name}" has no tasks')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully processed {projects.count()} projects')
        ) 