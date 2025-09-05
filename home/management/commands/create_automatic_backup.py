from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.management import call_command
from django.contrib.auth.models import User
from django.utils import timezone
import os
import hashlib
from datetime import datetime
import json

from home.models import BackupFile, SystemLog


class Command(BaseCommand):
    help = 'Create an automatic database backup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--description',
            type=str,
            default='',
            help='Description for the backup'
        )
        parser.add_argument(
            '--keep-days',
            type=int,
            default=30,
            help='Number of days to keep old backups (default: 30)'
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up old backups after creating new one'
        )

    def handle(self, *args, **options):
        description = options['description'] or f'Automatic backup created on {timezone.now().strftime("%Y-%m-%d %H:%M")}'
        keep_days = options['keep_days']
        cleanup = options['cleanup']

        try:
            self.stdout.write('Creating automatic backup...')
            
            # Create backup directory if it doesn't exist
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"auto_backup_{timestamp}.json"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Create backup using Django's dumpdata command
            with open(backup_path, 'w') as f:
                call_command('dumpdata', '--exclude', 'contenttypes', '--exclude', 'auth.permission', 
                           '--exclude', 'admin.logentry', '--exclude', 'sessions.session',
                           '--indent', '2', stdout=f)
            
            # Get file size and create checksum
            file_size = os.path.getsize(backup_path)
            with open(backup_path, 'rb') as f:
                checksum = hashlib.sha256(f.read()).hexdigest()
            
            # Create BackupFile record
            backup_file = BackupFile.objects.create(
                filename=backup_filename,
                file_path=backup_path,
                file_size=file_size,
                backup_type='automatic',
                description=description,
                created_by=None,  # System backup
                backup_checksum=checksum,
                database_version='Django 4.2+',
                total_records=sum([
                    User.objects.count(),
                    # Add other model counts as needed
                ])
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Automatic backup created successfully: {backup_filename} ({backup_file.file_size_mb} MB)'
                )
            )
            
            # Clean up old backups if requested
            if cleanup:
                self.cleanup_old_backups(keep_days)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating automatic backup: {str(e)}')
            )
            # Log the error if possible
            try:
                SystemLog.log_backup_failed(None, 'automatic', str(e), None)
            except:
                pass
            raise

    def cleanup_old_backups(self, keep_days):
        """Clean up backups older than specified days"""
        try:
            cutoff_date = timezone.now() - timezone.timedelta(days=keep_days)
            old_backups = BackupFile.objects.filter(
                created_at__lt=cutoff_date,
                backup_type='automatic'  # Only clean up automatic backups
            )
            
            deleted_count = 0
            for backup in old_backups:
                try:
                    # Delete physical file
                    if os.path.exists(backup.file_path):
                        os.remove(backup.file_path)
                    
                    # Delete database record
                    backup.delete()
                    deleted_count += 1
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Error deleting old backup {backup.filename}: {str(e)}')
                    )
            
            if deleted_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Cleaned up {deleted_count} old backups')
                )
            else:
                self.stdout.write('No old backups to clean up')
                
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'Error during backup cleanup: {str(e)}')
            )
