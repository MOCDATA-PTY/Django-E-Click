from django.core.management.base import BaseCommand
from django.db import transaction
from home.models import Project, Client, Task, SubTask, TaskComment, SubTaskComment, ClientOTP
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Clean projects and clients from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clients-only',
            action='store_true',
            help='Clean only clients and related data',
        )
        parser.add_argument(
            '--projects-only',
            action='store_true',
            help='Clean only projects and related data',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation',
        )

    def handle(self, *args, **options):
        clients_only = options['clients_only']
        projects_only = options['projects_only']
        force = options['force']

        if not force:
            # Show current data counts
            project_count = Project.objects.count()
            client_count = Client.objects.count()
            task_count = Task.objects.count()
            subtask_count = SubTask.objects.count()
            
            self.stdout.write(
                self.style.WARNING(
                    f'\nCurrent database state:\n'
                    f'- Projects: {project_count}\n'
                    f'- Clients: {client_count}\n'
                    f'- Tasks: {task_count}\n'
                    f'- Subtasks: {subtask_count}\n'
                )
            )

            if clients_only:
                confirm = input(f'\nAre you sure you want to delete ALL {client_count} clients and related data? (yes/no): ')
            elif projects_only:
                confirm = input(f'\nAre you sure you want to delete ALL {project_count} projects and related data? (yes/no): ')
            else:
                confirm = input(f'\nAre you sure you want to delete ALL projects and clients? This will remove:\n'
                              f'- {project_count} projects\n'
                              f'- {client_count} clients\n'
                              f'- {task_count} tasks\n'
                              f'- {subtask_count} subtasks\n'
                              f'(yes/no): ')

            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Operation cancelled.'))
                return

        try:
            with transaction.atomic():
                if clients_only:
                    self.clean_clients_only()
                elif projects_only:
                    self.clean_projects_only()
                else:
                    self.clean_all()

            self.stdout.write(
                self.style.SUCCESS('Database cleaned successfully!')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error cleaning database: {str(e)}')
            )

    def clean_clients_only(self):
        """Clean only clients and related data"""
        self.stdout.write('Cleaning clients and related data...')
        
        # Delete client OTPs
        otp_count = ClientOTP.objects.count()
        ClientOTP.objects.all().delete()
        self.stdout.write(f'Deleted {otp_count} client OTPs')
        
        # Delete clients
        client_count = Client.objects.count()
        Client.objects.all().delete()
        self.stdout.write(f'Deleted {client_count} clients')

    def clean_projects_only(self):
        """Clean only projects and related data"""
        self.stdout.write('Cleaning projects and related data...')
        
        # Delete subtask comments
        subtask_comment_count = SubTaskComment.objects.count()
        SubTaskComment.objects.all().delete()
        self.stdout.write(f'Deleted {subtask_comment_count} subtask comments')
        
        # Delete task comments
        task_comment_count = TaskComment.objects.count()
        TaskComment.objects.all().delete()
        self.stdout.write(f'Deleted {task_comment_count} task comments')
        
        # Delete subtasks
        subtask_count = SubTask.objects.count()
        SubTask.objects.all().delete()
        self.stdout.write(f'Deleted {subtask_count} subtasks')
        
        # Delete tasks
        task_count = Task.objects.count()
        Task.objects.all().delete()
        self.stdout.write(f'Deleted {task_count} tasks')
        
        # Delete projects
        project_count = Project.objects.count()
        Project.objects.all().delete()
        self.stdout.write(f'Deleted {project_count} projects')

    def clean_all(self):
        """Clean all projects and clients data"""
        self.stdout.write('Cleaning all projects and clients data...')
        
        # Delete subtask comments
        subtask_comment_count = SubTaskComment.objects.count()
        SubTaskComment.objects.all().delete()
        self.stdout.write(f'Deleted {subtask_comment_count} subtask comments')
        
        # Delete task comments
        task_comment_count = TaskComment.objects.count()
        TaskComment.objects.all().delete()
        self.stdout.write(f'Deleted {task_comment_count} task comments')
        
        # Delete subtasks
        subtask_count = SubTask.objects.count()
        SubTask.objects.all().delete()
        self.stdout.write(f'Deleted {subtask_count} subtasks')
        
        # Delete tasks
        task_count = Task.objects.count()
        Task.objects.all().delete()
        self.stdout.write(f'Deleted {task_count} tasks')
        
        # Delete projects
        project_count = Project.objects.count()
        Project.objects.all().delete()
        self.stdout.write(f'Deleted {project_count} projects')
        
        # Delete client OTPs
        otp_count = ClientOTP.objects.count()
        ClientOTP.objects.all().delete()
        self.stdout.write(f'Deleted {otp_count} client OTPs')
        
        # Delete clients
        client_count = Client.objects.count()
        Client.objects.all().delete()
        self.stdout.write(f'Deleted {client_count} clients')
