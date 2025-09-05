from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()
from home.models import Project

class Command(BaseCommand):
    help = 'Set password for a specific user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to set password for')
        parser.add_argument('password', type=str, help='New password')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        
        try:
            user = User.objects.get(username=username)
            user.set_password(password)
            user.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'Password set successfully for user: {user.username}')
            )
            self.stdout.write(f'Email: {user.email}')
            self.stdout.write(f'Is active: {user.is_active}')
            self.stdout.write(f'Is staff: {user.is_staff}')
            self.stdout.write(f'Is superuser: {user.is_superuser}')
            
            # Check if user has projects assigned
            assigned_projects = user.assigned_projects.all()
            if assigned_projects:
                self.stdout.write(f'\nAssigned projects: {[p.name for p in assigned_projects]}')
            else:
                self.stdout.write('\nNo projects assigned to this user')
                
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User "{username}" not found')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error: {e}')
            )
