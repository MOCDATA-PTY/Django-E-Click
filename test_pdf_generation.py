#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from home.views import generate_exact_pdf_report
from home.email_service import email_service

def test_pdf_generation():
    """Test PDF generation and email sending"""
    try:
        print("Testing PDF generation...")
        
        # Generate PDF
        pdf_file = generate_exact_pdf_report(days_filter=30)
        print(f"PDF generated successfully: {pdf_file}")
        
        # Check if file exists and has content
        if os.path.exists(pdf_file):
            file_size = os.path.getsize(pdf_file)
            print(f"PDF file size: {file_size} bytes")
            
            if file_size > 0:
                print("✅ PDF generation successful!")
                
                # Test email sending with the PDF
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
                
                print("Testing email sending with PDF attachment...")
                result = email_service.send_report_email(
                    to_email='test@example.com',
                    report_data=report_data,
                    custom_message='Test message'
                )
                
                print(f"Email service result: {result}")
                
                # Clean up
                try:
                    os.unlink(pdf_file)
                    print("PDF file cleaned up")
                except:
                    pass
                    
            else:
                print("❌ PDF file is empty!")
        else:
            print("❌ PDF file was not created!")
            
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pdf_generation()
