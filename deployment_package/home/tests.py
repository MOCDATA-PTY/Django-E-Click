from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from home.models import Client, Project


class FridayReportCommandTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            username='acme', email='acme@example.com', is_active=True
        )
        Project.objects.create(
            name='Proj A', client_username='acme', client_email='acme@example.com', status='completed'
        )

    def test_send_friday_reports_dry_run(self):
        # Should run even if not Friday when forced, and not raise
        call_command('send_friday_reports', '--force', '--dry-run')

from django.test import TestCase

# Create your tests here.
