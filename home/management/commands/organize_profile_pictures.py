from django.core.management.base import BaseCommand
from django.conf import settings
import os
import shutil
from home.models import UserProfile, Client


class Command(BaseCommand):
    help = 'Organize existing profile pictures into new folder structure'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually moving files',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No files will be moved'))
        
        self.stdout.write('🔄 Organizing profile pictures...')
        
        # Organize user profile pictures
        self.organize_user_profiles(dry_run)
        
        # Organize client profile pictures
        self.organize_client_profiles(dry_run)
        
        self.stdout.write(self.style.SUCCESS('✅ Profile picture organization completed!'))

    def organize_user_profiles(self, dry_run):
        """Organize user profile pictures"""
        self.stdout.write('\n👥 Organizing user profile pictures...')
        
        profiles = UserProfile.objects.filter(profile_picture__isnull=False)
        
        for profile in profiles:
            if profile.profile_picture:
                old_path = profile.profile_picture.path
                if os.path.exists(old_path):
                    # Determine new path based on user type
                    if profile.user.is_staff or profile.user.is_superuser:
                        new_folder = f'admin/{profile.user.username}'
                    else:
                        new_folder = f'users/{profile.user.username}'
                    
                    new_path = os.path.join(settings.MEDIA_ROOT, new_folder, os.path.basename(old_path))
                    
                    if dry_run:
                        self.stdout.write(f'  📁 Would move: {old_path} → {new_path}')
                    else:
                        # Create directory if it doesn't exist
                        os.makedirs(os.path.dirname(new_path), exist_ok=True)
                        
                        # Move file
                        try:
                            shutil.move(old_path, new_path)
                            self.stdout.write(f'  ✅ Moved: {os.path.basename(old_path)} → {new_folder}/')
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'  ❌ Error moving {old_path}: {e}'))

    def organize_client_profiles(self, dry_run):
        """Organize client profile pictures"""
        self.stdout.write('\n👤 Organizing client profile pictures...')
        
        clients = Client.objects.filter(profile_picture__isnull=False)
        
        for client in clients:
            if client.profile_picture:
                old_path = client.profile_picture.path
                if os.path.exists(old_path):
                    new_folder = f'clients/{client.username}'
                    new_path = os.path.join(settings.MEDIA_ROOT, new_folder, os.path.basename(old_path))
                    
                    if dry_run:
                        self.stdout.write(f'  📁 Would move: {old_path} → {new_path}')
                    else:
                        # Create directory if it doesn't exist
                        os.makedirs(os.path.dirname(new_path), exist_ok=True)
                        
                        # Move file
                        try:
                            shutil.move(old_path, new_path)
                            self.stdout.write(f'  ✅ Moved: {os.path.basename(old_path)} → {new_folder}/')
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'  ❌ Error moving {old_path}: {e}'))

    def create_folder_structure(self):
        """Create the new folder structure"""
        folders = [
            'admin',
            'users', 
            'clients'
        ]
        
        for folder in folders:
            folder_path = os.path.join(settings.MEDIA_ROOT, folder)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                self.stdout.write(f'  📁 Created folder: {folder}/')
