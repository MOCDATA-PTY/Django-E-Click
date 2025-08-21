#!/usr/bin/env python3
"""
Test script for Google Cloud Email Integration
Run this script to test the email functionality without starting the Django server
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

# from home.services import email_service  # EMAIL SERVICES DISABLED

def test_email_service():
    """Test the email service functionality"""
    print("🔧 Testing Google Cloud Email Service...")
    print("=" * 50)
    
    # Test 1: Check if service is initialized - EMAIL SERVICES DISABLED
    print("1. Checking service initialization...")
    # if email_service.service:  # EMAIL SERVICES DISABLED
    #     print("   ✅ Gmail service is initialized")
    # else:
    #     print("   ⚠️  Gmail service is not initialized (requires OAuth2 credentials)")
    print("   ⚠️  Email services are currently disabled")
    
    # Test 2: Check credentials file
    print("\n2. Checking credentials file...")
    credentials_path = os.path.join('home', 'credentials.json')
    if os.path.exists(credentials_path):
        print("   ✅ credentials.json file found")
        print(f"   📁 Path: {credentials_path}")
    else:
        print("   ❌ credentials.json file not found")
        print("   📝 Please create the credentials file following the setup guide")
    
    # Test 3: Check API key - EMAIL SERVICES DISABLED
    print("\n3. Checking API key...")
    # if email_service.api_key:  # EMAIL SERVICES DISABLED
    #     print("   ✅ API key is configured")
    #     print(f"   🔑 Key: {email_service.api_key[:20]}...")
    # else:
    #     print("   ❌ API key is not configured")
    print("   ⚠️  Email services are currently disabled")
    
    # Test 4: Test email sending (if service is available) - EMAIL SERVICES DISABLED
    print("\n4. Testing email sending...")
    # if email_service.service:  # EMAIL SERVICES DISABLED
    #     test_data = {
    #         'total_projects': 5,
    #         'projects_completed': 3,
    #         'total_tasks': 15,
    #         'completed_tasks': 12,
    #         'project_completion_rate': 60.0,
    #         'task_completion_rate': 80.0,
    #         'user_engagement_rate': 75.0,
    #         'date_range': 'Test Period',
    #         'generated_date': 'Test Date',
    #     }
        
    #     try:
    #         result = email_service.send_report_email(
    #             to_email='test@example.com',
    #             report_data=test_data,
    #             custom_message='This is a test email from the setup script.'
    #         )
            
    #         if result['success']:
    #             print("   ✅ Email service is working correctly")
    #         else:
    #         print(f"   ❌ Email service error: {result.get('error', 'Unknown error')}")
                
    #     except Exception as e:
    #         print(f"   ❌ Email service exception: {str(e)}")
    # else:
    #     print("   ⚠️  Skipping email test (service not initialized)")
    print("   ⚠️  Email services are currently disabled")
    
    # Test 5: Check required packages
    print("\n5. Checking required packages...")
    required_packages = [
        ('google.cloud.storage', 'google-cloud-storage'),
        ('google.auth', 'google-auth'),
        ('google_auth_oauthlib', 'google-auth-oauthlib'),
        ('google_auth_httplib2', 'google-auth-httplib2'),
        ('googleapiclient.discovery', 'google-api-python-client')
    ]
    
    missing_packages = []
    for package_name, pip_name in required_packages:
        try:
            __import__(package_name)
            print(f"   ✅ {package_name}")
        except ImportError as e:
            print(f"   ❌ {package_name} - NOT INSTALLED ({str(e)})")
            missing_packages.append(pip_name)
    
    if missing_packages:
        print(f"\n   📦 Install missing packages with:")
        print(f"   pip install {' '.join(missing_packages)}")
    
    # Summary - EMAIL SERVICES DISABLED
    print("\n" + "=" * 50)
    print("📋 SETUP SUMMARY:")
    
    # if email_service.service and os.path.exists(credentials_path):  # EMAIL SERVICES DISABLED
    #     print("   ✅ Email service is ready to use")
    #     print("   🚀 You can now send emails through the Django application")
    # else:
    #     print("   ⚠️  Email service needs additional setup")
    #     print("   📖 Please follow the setup guide in GOOGLE_CLOUD_EMAIL_SETUP.md")
    
    print("   ⚠️  Email services are currently disabled")
    
    # print("\n🔗 Next steps:")  # EMAIL SERVICES DISABLED
    # print("   1. Follow the setup guide in GOOGLE_CLOUD_EMAIL_SETUP.md")
    # print("   2. Create credentials.json file in the home/ directory")
    # print("   3. Test the email functionality in the Django admin")
    print("   4. Configure your Gmail account for API access")

if __name__ == "__main__":
    test_email_service() 