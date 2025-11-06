from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
import os
import hashlib
from datetime import datetime

from home.models import BackupFile, SystemLog


class Command(BaseCommand):
    help = 'Restore database from a backup file'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_id',
            type=int,
            help='ID of the backup to restore from'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force restore without confirmation'
        )
        parser.add_argument(
            '--no-safety-backup',
            action='store_true',
            help='Skip creating safety backup before restore'
        )

    def handle(self, *args, **options):
        backup_id = options['backup_id']
        force = options['force']
        no_safety_backup = options['no_safety_backup']

        try:
            # Get the backup
            try:
                backup = BackupFile.objects.get(id=backup_id)
            except BackupFile.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Backup with ID {backup_id} not found')
                )
                return

            # Check if backup is available
            if not backup.is_available:
                self.stdout.write(
                    self.style.ERROR(f'Backup file is not available for restore')
                )
                return

            # Verify file integrity
            self.stdout.write('Verifying backup file integrity...')
            with open(backup.file_path, 'rb') as f:
                current_checksum = hashlib.sha256(f.read()).hexdigest()

            if current_checksum != backup.backup_checksum:
                self.stdout.write(
                    self.style.ERROR('Backup file integrity check failed. File may be corrupted.')
                )
                backup.status = 'corrupted'
                backup.save()
                return

            # Confirm restore
            if not force:
                self.stdout.write(
                    self.style.WARNING(
                        f'This will restore the database from backup: {backup.filename}'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        'This action will overwrite all current data and cannot be undone!'
                    )
                )
                confirm = input('Type "YES" to confirm: ')
                if confirm != 'YES':
                    self.stdout.write('Restore cancelled')
                    return

            # Create safety backup if not disabled
            if not no_safety_backup:
                self.stdout.write('Creating safety backup of current data...')
                safety_backup = self.create_safety_backup()
                if safety_backup:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Safety backup created: {safety_backup.filename}'
                        )
                    )

            # Perform the restore
            self.stdout.write('Restoring database from backup...')
            
            # Clear existing data (excluding system tables)
            call_command('flush', '--no-input')
            
            # Restore from backup
            call_command('loaddata', backup.file_path)
            
            # Update backup status
            backup.status = 'restored'
            backup.restored_at = timezone.now()
            backup.restored_by = None  # System restore
            backup.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Database restored successfully from backup: {backup.filename}'
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error restoring backup: {str(e)}')
            )
            # Log the error if possible
            try:
                SystemLog.log_backup_failed(None, 'restore', str(e), None)
            except:
                pass
            raise

    def create_safety_backup(self):
        """Create a safety backup of current data before restore"""
        try:
            # Create backup directory if it doesn't exist
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Generate safety backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safety_filename = f"pre_restore_safety_{timestamp}.json"
            safety_path = os.path.join(backup_dir, safety_filename)
            
            # Create safety backup
            with open(safety_path, 'w') as f:
                call_command('dumpdata', '--exclude', 'contenttypes', '--exclude', 'auth.permission', 
                           '--exclude', 'admin.logentry', '--exclude', 'sessions.session',
                           '--indent', '2', stdout=f)
            
            # Get file size and create checksum
            safety_size = os.path.getsize(safety_path)
            with open(safety_path, 'rb') as f:
                safety_checksum = hashlib.sha256(f.read()).hexdigest()
            
            # Create safety backup record
            safety_backup = BackupFile.objects.create(
                filename=safety_filename,
                file_path=safety_path,
                file_size=safety_size,
                backup_type='automatic',
                description='Safety backup created before restore operation',
                created_by=None,  # System backup
                backup_checksum=safety_checksum,
                database_version='Django 4.2+',
                total_records=0  # Will be updated after restore
            )
            
            return safety_backup
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'Error creating safety backup: {str(e)}')
            )
            return None
