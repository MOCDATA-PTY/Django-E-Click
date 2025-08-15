from django.core.management.base import BaseCommand
from home.models import Client, ClientOTP, Project


class Command(BaseCommand):
    help = 'Clean up orphaned client records that are not associated with any projects'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup of orphaned client records...')
        
        # Find all clients
        all_clients = Client.objects.all()
        cleaned_count = 0
        
        for client in all_clients:
            # Check if this client is associated with any active projects
            has_active_projects = Project.objects.filter(
                client_email=client.email
            ).exists()
            
            if not has_active_projects:
                self.stdout.write(f'Found orphaned client: {client.username} ({client.email})')
                
                # Delete related OTPs first
                otp_count = ClientOTP.objects.filter(client=client).count()
                ClientOTP.objects.filter(client=client).delete()
                
                # Delete the client
                client.delete()
                
                cleaned_count += 1
                self.stdout.write(f'  - Deleted {otp_count} OTPs and client record')
        
        if cleaned_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully cleaned up {cleaned_count} orphaned client records')
            )
        else:
            self.stdout.write(self.style.SUCCESS('No orphaned client records found'))
