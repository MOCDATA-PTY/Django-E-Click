from django.core.management.base import BaseCommand
from django.db import transaction
from home.models import Project, Client, Task, SubTask
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Add sample projects with specific emails'

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                self.add_projects()
            self.stdout.write(
                self.style.SUCCESS('Sample projects created successfully!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating projects: {str(e)}')
            )

    def add_projects(self):
        # Get existing clients
        client1 = Client.objects.get(email='info@eclick.co.za')
        client2 = Client.objects.get(email='admin@eclick.co.za')
        
        self.stdout.write(f'Found client 1: {client1.username} ({client1.email})')
        self.stdout.write(f'Found client 2: {client2.username} ({client2.email})')
        
        # Project 1: Web Development Project
        project1 = Project.objects.create(
            name='E-Commerce Website Development',
            client=client1.username,
            client_username=client1.username,
            client_email=client1.email,
            status='in_progress'
        )
        self.stdout.write(f'Created project: {project1.name}')
        
        # Tasks for Project 1
        task1_1 = Task.objects.create(
            project=project1,
            title='Frontend Development',
            description='Develop responsive user interface using React.js',
            status='in_progress',
            development_status='new_development',
            priority='high',
            start_date=datetime.now().date(),
            end_date=(datetime.now() + timedelta(days=14)).date(),
            estimated_hours=40.0
        )
        self.stdout.write(f'Created task: {task1_1.title}')
        
        # Subtasks for Task 1
        SubTask.objects.create(
            task=task1_1,
            title='Design System Setup',
            description='Create reusable component library',
            status='completed',
            priority='high',
            start_date=datetime.now().date(),
            end_date=(datetime.now() + timedelta(days=3)).date()
        )
        
        SubTask.objects.create(
            task=task1_1,
            title='Product Catalog Page',
            description='Build product listing and filtering functionality',
            status='in_progress',
            priority='medium',
            start_date=(datetime.now() + timedelta(days=4)).date(),
            end_date=(datetime.now() + timedelta(days=10)).date()
        )
        
        task1_2 = Task.objects.create(
            project=project1,
            title='Backend API Development',
            description='Develop RESTful API endpoints using Django',
            status='not_started',
            development_status='new_development',
            priority='high',
            start_date=(datetime.now() + timedelta(days=7)).date(),
            end_date=(datetime.now() + timedelta(days=21)).date(),
            estimated_hours=60.0
        )
        self.stdout.write(f'Created task: {task1_2.title}')
        
        # Project 2: Mobile App Development
        project2 = Project.objects.create(
            name='Inventory Management Mobile App',
            client=client2.username,
            client_username=client2.username,
            client_email=client2.email,
            status='planned'
        )
        self.stdout.write(f'Created project: {project2.name}')
        
        # Tasks for Project 2
        task2_1 = Task.objects.create(
            project=project2,
            title='Mobile App Design',
            description='Design user interface and user experience for mobile app',
            status='not_started',
            development_status='original_quoted',
            priority='medium',
            start_date=datetime.now().date(),
            end_date=(datetime.now() + timedelta(days=10)).date(),
            estimated_hours=25.0
        )
        self.stdout.write(f'Created task: {task2_1.title}')
        
        # Subtasks for Task 2_1
        SubTask.objects.create(
            task=task2_1,
            title='Wireframe Creation',
            description='Create low-fidelity wireframes for all screens',
            status='not_started',
            priority='medium',
            start_date=datetime.now().date(),
            end_date=(datetime.now() + timedelta(days=3)).date()
        )
        
        SubTask.objects.create(
            task=task2_1,
            title='UI Design',
            description='Create high-fidelity UI designs with proper styling',
            status='not_started',
            priority='medium',
            start_date=(datetime.now() + timedelta(days=4)).date(),
            end_date=(datetime.now() + timedelta(days=7)).date()
        )
        
        task2_2 = Task.objects.create(
            project=project2,
            title='Database Schema Design',
            description='Design and implement database structure for inventory management',
            status='not_started',
            development_status='new_development_qms',
            priority='high',
            start_date=(datetime.now() + timedelta(days=5)).date(),
            end_date=(datetime.now() + timedelta(days=15)).date(),
            estimated_hours=30.0
        )
        self.stdout.write(f'Created task: {task2_2.title}')
        
        task2_3 = Task.objects.create(
            project=project2,
            title='API Development',
            description='Develop backend API for mobile app integration',
            status='not_started',
            development_status='new_development',
            priority='high',
            start_date=(datetime.now() + timedelta(days=10)).date(),
            end_date=(datetime.now() + timedelta(days=25)).date(),
            estimated_hours=45.0
        )
        self.stdout.write(f'Created task: {task2_3.title}')
        
        # Subtasks for Task 2_3
        SubTask.objects.create(
            task=task2_3,
            title='Authentication API',
            description='Implement user authentication and authorization endpoints',
            status='not_started',
            priority='high',
            start_date=(datetime.now() + timedelta(days=10)).date(),
            end_date=(datetime.now() + timedelta(days=15)).date()
        )
        
        SubTask.objects.create(
            task=task2_3,
            title='Inventory CRUD API',
            description='Create CRUD operations for inventory management',
            status='not_started',
            priority='high',
            start_date=(datetime.now() + timedelta(days=16)).date(),
            end_date=(datetime.now() + timedelta(days=22)).date()
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSuccessfully created:\n'
                f'- Project 1: {project1.name} for {client1.email}\n'
                f'- Project 2: {project2.name} for {client2.email}\n'
                f'- Total tasks: {Task.objects.count()}\n'
                f'- Total subtasks: {SubTask.objects.count()}'
            )
        )
