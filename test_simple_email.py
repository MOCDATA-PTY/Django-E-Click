#!/usr/bin/env python3
"""
Test script for the simple email service using Django's built-in email functionality
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

def test_simple_email():
    """Test the simple email service"""
    print("🔧 Testing Simple Email Service...")
    print("=" * 50)
    
    # Test basic email sending
    test_email = "marnus.badenhors@eclick.co.za"  # Test the specific email that was having issues
    subject = "Test Email from E-Click System"
    body = """
    <html>
    <body>
        <h1>Test Email</h1>
        <p>This is a test email from the E-Click system using Django's built-in email functionality.</p>
        <p>If you receive this email, the email service is working correctly!</p>
        <p>Sent to: marnus.badenhors@eclick.co.za</p>
        <p>Time: Test email to verify email service functionality</p>
    </body>
    </html>
    """
    
    print(f"📧 Sending test email to: {test_email}")
    
    try:
        result = email_service.send_email(
            to_email=test_email,
            subject=subject,
            body=body
        )
        
        if result['success']:
            print("✅ Email sent successfully!")
            print("📋 Response:", result['message'])
        else:
            print("❌ Email failed to send")
            print("📋 Error:", result.get('error', 'Unknown error'))
            
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
    
    print("\n" + "=" * 50)
    print("🎉 Test completed!")

if __name__ == "__main__":
    test_simple_email() 