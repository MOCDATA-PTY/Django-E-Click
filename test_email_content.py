#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from home.email_service import email_service

def test_email_content():
    """Test email content generation"""
    try:
        print("=== Testing Email Content Generation ===")
        
        report_data = {
            'total_projects': 2,
            'projects_completed': 1,
            'projects_in_progress': 1,
            'projects_planned': 0,
            'total_tasks': 1,
            'completed_tasks': 0,
            'in_progress_tasks': 1,
            'not_started_tasks': 0,
            'total_subtasks': 0,
            'completed_subtasks': 0,
            'total_users': 1,
            'active_users': 1,
            'project_completion_rate': 50.0,
            'task_completion_rate': 0.0,
            'user_engagement_rate': 100.0,
            'date_range': 'August 01 to August 08, 2025',
            'generated_date': 'August 08, 2025 at 12:07 PM',
            'days_filter': 30,
        }
        
        print("1. Testing HTML email body generation...")
        html_body = email_service._create_report_html(report_data, "Test custom message")
        print(f"   HTML body length: {len(html_body)} characters")
        print(f"   Contains HTML tags: {'<html>' in html_body}")
        print(f"   Contains div tags: {'<div>' in html_body}")
        
        # Show first 500 characters
        print(f"   First 500 chars: {html_body[:500]}...")
        
        print("\n2. Testing plain text email body generation...")
        text_body = email_service._create_email_body(report_data, "Test custom message")
        print(f"   Text body length: {len(text_body)} characters")
        print(f"   First 300 chars: {text_body[:300]}...")
        
        print("\n3. Testing email sending with explicit HTML...")
        
        # Test sending with HTML content
        result = email_service.send_email(
            to_email='ethansevenster621@gmail.com',
            subject='Test Email with PDF - HTML Content',
            body=html_body,
            from_email='reports@eclick.com',
            attachments=None  # No attachment for this test
        )
        
        print(f"   Email result: {result}")
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_email_content()
