#!/usr/bin/env python3
"""
Test script for PDF email functionality
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from home.email_service import email_service

def test_pdf_email():
    """Test the PDF email functionality"""
    print("🔧 Testing PDF Email Service...")
    print("=" * 50)
    
    # Test report data
    test_report_data = {
        'total_projects': 15,
        'projects_completed': 8,
        'projects_in_progress': 5,
        'projects_planned': 2,
        'total_tasks': 45,
        'completed_tasks': 32,
        'in_progress_tasks': 10,
        'not_started_tasks': 3,
        'total_subtasks': 120,
        'completed_subtasks': 95,
        'total_users': 12,
        'active_users': 10,
        'project_completion_rate': 53.3,
        'task_completion_rate': 71.1,
        'user_engagement_rate': 83.3,
        'date_range': 'Last 30 Days',
        'generated_date': 'December 15, 2024 at 2:30 PM',
    }
    
    test_email = "ethansevenster621@gmail.com"  # Your email for testing
    custom_message = "This is a test PDF report email from the E-Click system."
    
    print(f"📧 Sending PDF report email to: {test_email}")
    print(f"📋 Custom message: {custom_message}")
    
    try:
        result = email_service.send_report_email(
            to_email=test_email,
            report_data=test_report_data,
            custom_message=custom_message
        )
        
        if result['success']:
            print("✅ PDF report email sent successfully!")
            print("📋 Response:", result['message'])
        else:
            print("❌ PDF report email failed to send")
            print("📋 Error:", result.get('error', 'Unknown error'))
            
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        print("💡 Make sure reportlab is installed: pip install reportlab")
    
    print("\n" + "=" * 50)
    print("🎉 Test completed!")

if __name__ == "__main__":
    test_pdf_email() 