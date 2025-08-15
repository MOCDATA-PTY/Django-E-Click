from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Project, Client, ClientOTP


@receiver(post_delete, sender=Project)
def cleanup_orphaned_clients(sender, instance, **kwargs):
    """
    Clean up client records when a project is deleted
    """
    if instance.client_email:
        # Check if this client email is used by any other projects
        other_projects_with_same_email = Project.objects.filter(
            client_email=instance.client_email
        ).exists()
        
        if not other_projects_with_same_email:
            # No other projects use this email, so we can safely delete client records
            try:
                # Delete related client OTPs
                ClientOTP.objects.filter(client__email=instance.client_email).delete()
                
                # Delete the client
                Client.objects.filter(email=instance.client_email).delete()
                
                print(f"Signals: Cleaned up client records for email: {instance.client_email}")
            except Exception as e:
                print(f"Signals: Warning - Could not clean up client records: {e}")
