#!/usr/bin/env python3
"""
Test script to verify OAuth2 email sending
"""

import os
import sys
import django
from pathlib import Path

# Add Django project to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

# from home.services import GoogleCloudEmailService  # EMAIL SERVICES DISABLED

def test_oauth2_email():
    """Test sending an email using OAuth2"""
    try:
        print("🧪 Testing OAuth2 email sending...")
        
        # Initialize the Gmail service
        # service = GoogleCloudEmailService()  # EMAIL SERVICES DISABLED
        
        if not service.service:
            print("❌ Gmail service not initialized")
            return
        
        print("✅ Gmail service initialized successfully")
        
        # Test email data - CHANGE THIS TO YOUR EMAIL FOR TESTING
        test_email = "ethansevenster5@gmail.com"  # Change this to your email for testing
        subject = "Test Email from OAuth2 - E-Click"
        body = """
        This is a test email to verify that OAuth2 is working correctly.
        
        This email should be sent from: mocptydata@gmail.com
        
        If you receive this email, OAuth2 is working perfectly! 🎉
        
        Best regards,
        E-Click System
        """
        
        print(f"📧 Sending test email to: {test_email}")
        print(f"📧 From: OAuth2 account (mocptydata@gmail.com)")
        print(f"📧 Subject: {subject}")
        
        # Send the email
        result = service.send_email(
            to_email=test_email,
            subject=subject,
            body=body,
            from_email=None  # This will use the OAuth2 account email
        )
        
        if result.get('success'):
            print("✅ Email sent successfully!")
            print(f"📧 Message ID: {result.get('message_id', 'N/A')}")
            print(f"📧 Message: {result.get('message', 'N/A')}")
            print("\n🎉 OAuth2 email sending is working perfectly!")
            print("📧 All emails will now be sent from: mocptydata@gmail.com")
        else:
            print("❌ Email sending failed!")
            print(f"📧 Error: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error during OAuth2 email test: {str(e)}")

if __name__ == "__main__":
    test_oauth2_email()
