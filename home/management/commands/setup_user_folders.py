from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from home.models import Client


class Command(BaseCommand):
    help = 'Set up profile picture folders for all existing users and clients'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up empty folders after setup',
        )

    def handle(self, *args, **options):
        cleanup = options['cleanup']
        
        self.stdout.write('📁 Setting up user profile picture folders...')
        
        # Import the folder creation functions
        from home.models import ensure_all_user_folders_exist, cleanup_empty_folders
        
        # Create folders for all existing users
        ensure_all_user_folders_exist()
        
        if cleanup:
            self.stdout.write('\n🧹 Cleaning up empty folders...')
            cleanup_empty_folders()
        
        self.stdout.write(self.style.SUCCESS('\n✅ User folder setup completed!'))
        
        # Show summary
        self.show_folder_summary()
    
    def show_folder_summary(self):
        """Show a summary of the folder structure"""
        import os
        from django.conf import settings
        
        self.stdout.write('\n📋 Folder Structure Summary:')
        self.stdout.write('=' * 50)
        
        base_folders = ['admin', 'users', 'clients']
        
        for base_folder in base_folders:
            base_path = os.path.join(settings.MEDIA_ROOT, base_folder)
            if os.path.exists(base_path):
                subfolders = [f for f in os.listdir(base_path) 
                            if os.path.isdir(os.path.join(base_path, f))]
                
                if subfolders:
                    self.stdout.write(f'\n{base_folder.upper()}/')
                    for subfolder in sorted(subfolders):
                        subfolder_path = os.path.join(base_path, subfolder)
                        file_count = len([f for f in os.listdir(subfolder_path) 
                                        if os.path.isfile(os.path.join(subfolder_path, f))])
                        self.stdout.write(f'  ├── {subfolder}/ ({file_count} files)')
                else:
                    self.stdout.write(f'\n{base_folder.upper()}/ (empty)')
            else:
                self.stdout.write(f'\n{base_folder.upper()}/ (not created)')
        
        self.stdout.write('\n💡 New users will automatically get their folders created!')
