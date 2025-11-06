"""
Test script to send a comprehensive E-Click Admin Dashboard report
Uses the same functionality as the Send Report page to generate PDF report
and send to ethansevenster621@gmail.com
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from django.utils import timezone
from home.email_service import SimpleEmailService
from home.models import Project, Task, User, SubTask


def generate_report_data(date_range=30):
    """
    Generate comprehensive report data
    Uses the same logic as the send_report view
    """
    try:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=date_range)

        # Project statistics
        total_projects = Project.objects.count()
        projects_in_progress = Project.objects.filter(status='in_progress').count()
        projects_completed = Project.objects.filter(status='completed').count()
        projects_planned = Project.objects.filter(status='planned').count()

        # Task statistics
        total_tasks = Task.objects.count()
        completed_tasks = Task.objects.filter(status='completed').count()
        in_progress_tasks = Task.objects.filter(status='in_progress').count()
        not_started_tasks = Task.objects.filter(status='not_started').count()

        # Subtask statistics
        total_subtasks = SubTask.objects.count()
        completed_subtasks = SubTask.objects.filter(is_completed=True).count()

        # User statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(last_login__gte=start_date).count()

        # Calculate rates
        project_completion_rate = (projects_completed / total_projects * 100) if total_projects > 0 else 0
        task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        user_engagement_rate = (active_users / total_users * 100) if total_users > 0 else 0

        # Prepare report data (same format as send_report view)
        report_data = {
            'total_projects': total_projects,
            'projects_completed': projects_completed,
            'projects_in_progress': projects_in_progress,
            'projects_planned': projects_planned,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'not_started_tasks': not_started_tasks,
            'total_subtasks': total_subtasks,
            'completed_subtasks': completed_subtasks,
            'total_users': total_users,
            'active_users': active_users,
            'project_completion_rate': project_completion_rate,
            'task_completion_rate': task_completion_rate,
            'user_engagement_rate': user_engagement_rate,
            'date_range': f"{start_date.strftime('%B %d')} to {end_date.strftime('%B %d, %Y')}",
            'generated_date': timezone.now().strftime("%B %d, %Y at %I:%M %p"),
            'days_filter': date_range,
        }

        return report_data

    except Exception as e:
        print(f"Error generating report data: {e}")
        import traceback
        traceback.print_exc()
        return None


def send_test_report():
    """
    Send a comprehensive test report email to ethansevenster621@gmail.com
    Uses the same send_report_email method from the Send Report page
    """

    print("=" * 70)
    print("E-Click Admin Dashboard - Send Complete Report (Test)")
    print("=" * 70)
    print()

    # Recipient email
    recipient_email = "ethansevenster621@gmail.com"
    date_range = 30  # Last 30 days
    custom_message = "This is a test report from the E-Click Admin Dashboard."

    print(f"Preparing to send complete report to: {recipient_email}")
    print(f"Date Range: Last {date_range} days")
    print(f"Custom Message: {custom_message}")
    print()

    # Generate report data
    print("Generating comprehensive report data...")
    report_data = generate_report_data(date_range=date_range)

    if not report_data:
        print("ERROR! Failed to generate report data.")
        return

    print()
    print("Report Statistics:")
    print(f"  - Total Projects: {report_data['total_projects']}")
    print(f"  - Completed Projects: {report_data['projects_completed']}")
    print(f"  - In Progress Projects: {report_data['projects_in_progress']}")
    print(f"  - Planned Projects: {report_data['projects_planned']}")
    print(f"  - Total Tasks: {report_data['total_tasks']}")
    print(f"  - Completed Tasks: {report_data['completed_tasks']}")
    print(f"  - Project Completion Rate: {report_data['project_completion_rate']:.2f}%")
    print(f"  - Task Completion Rate: {report_data['task_completion_rate']:.2f}%")
    print(f"  - User Engagement Rate: {report_data['user_engagement_rate']:.2f}%")
    print(f"  - Date Range: {report_data['date_range']}")
    print()

    # Initialize email service
    print("Initializing email service...")
    email_service = SimpleEmailService()

    # Send the comprehensive report with PDF attachment
    print("Generating PDF and sending email with report attachment...")
    print("This may take a moment as the PDF is being generated...")
    print()

    try:
        # Use the same send_report_email method as the Send Report page
        result = email_service.send_report_email(
            to_email=recipient_email,
            report_data=report_data,
            custom_message=custom_message
        )

        print()
        if result.get('success'):
            print("=" * 70)
            print("SUCCESS! Complete report email sent successfully!")
            print("=" * 70)
            print(f"  Recipient: {recipient_email}")
            print(f"  Date Range: {report_data['date_range']}")
            print(f"  Generated: {report_data['generated_date']}")
            print()
            print("The email includes:")
            print("  - Executive Summary")
            print("  - Project Timeline (Gantt Chart)")
            print("  - All Projects Overview")
            print("  - Completion Rates & Charts")
            print("  - Task Analysis")
            print("  - User Engagement")
            print("  - Performance Recommendations")
            print("  - PDF Report Attachment")
            print()
            print(f"Message: {result.get('message', 'Email sent successfully')}")
        else:
            print("=" * 70)
            print("ERROR! Failed to send complete report email.")
            print("=" * 70)
            print(f"  Error: {result.get('error', 'Unknown error')}")
            print("  Check the email configuration in settings.py")
        print()

    except Exception as e:
        print()
        print("=" * 70)
        print("ERROR! Exception occurred while sending email:")
        print("=" * 70)
        print(f"  {str(e)}")
        print()
        import traceback
        traceback.print_exc()

    print("=" * 70)


if __name__ == "__main__":
    send_test_report()
