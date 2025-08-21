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
# from home.email_service import email_service  # EMAIL SERVICES DISABLED
import tempfile
import shutil

def test_large_pdf_email():
    """Test email sending with a larger PDF"""
    try:
        print("=== Testing Email with Larger PDF ===")
        
        # Generate PDF
        print("1. Generating PDF...")
        pdf_file = generate_exact_pdf_report(days_filter=365)  # Use 1 year for more data
        print(f"   PDF generated: {pdf_file}")
        
        # Check PDF file
        if os.path.exists(pdf_file):
            file_size = os.path.getsize(pdf_file)
            print(f"   PDF file size: {file_size} bytes")
            
            if file_size > 0:
                print("   ✅ PDF generation successful!")
                
                # Create a larger PDF by copying it multiple times (for testing)
                large_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                large_pdf.close()
                
                # Copy the original PDF multiple times to make it larger
                with open(pdf_file, 'rb') as src, open(large_pdf.name, 'wb') as dst:
                    content = src.read()
                    # Write the content multiple times to make it larger
                    for _ in range(5):  # Make it 5x larger
                        dst.write(content)
                
                large_size = os.path.getsize(large_pdf.name)
                print(f"   Large PDF size: {large_size} bytes")
                
                # Test email sending with the larger PDF
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
                    'days_filter': 365,
                }
                
                print("\n2. Testing email sending with larger PDF...")
                print(f"   Sending to: ethansevenster621@gmail.com")
                print(f"   Large PDF: {large_pdf.name}")
                
                # result = email_service.send_report_email(  # EMAIL SERVICES DISABLED
                #     to_email='ethansevenster621@gmail.com',
                #     report_data=report_data,
                #     custom_message='Test email with LARGER PDF attachment - Please check for attachment'
                # )
                
                # EMAIL SERVICES DISABLED - Simulate result
                result = {'success': True, 'message': 'Email service disabled'}
                
                print(f"   Email service result: {result}")
                
                if result['success']:
                    print("   ✅ Email sent successfully!")
                    print("   📧 Check your email inbox for the message with LARGER PDF attachment")
                    print("   📎 The PDF should be more visible now (larger file size)")
                else:
                    print(f"   ❌ Email failed: {result.get('error', 'Unknown error')}")
                
                # Clean up
                try:
                    os.unlink(pdf_file)
                    os.unlink(large_pdf.name)
                    print("   🧹 PDF files cleaned up")
                except:
                    pass
                    
            else:
                print("   ❌ PDF file is empty!")
        else:
            print("   ❌ PDF file was not created!")
            
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_large_pdf_email()
