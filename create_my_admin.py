#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from django.contrib.auth.models import User
from home.models import UserProfile

def create_my_admin():
    """Create a new admin account with custom credentials"""
    try:
        # Custom admin credentials - you can change these
        username = "myadmin"
        email = "myadmin@example.com"
        password = "mypassword123"
        first_name = "My"
        last_name = "Admin"
        
        # Check if user already exists
        if User.objects.filter(username=username).exists():
            print(f"❌ User '{username}' already exists")
            return False
        
        # Create the user with superuser privileges
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_superuser=True,
            is_active=True
        )
        
        # Create user profile with admin permissions
        profile = UserProfile.objects.create(
            user=user,
            can_access_dashboard=True,
            can_access_projects=True,
            can_access_reports=True,
            can_access_analytics=True,
            can_access_admin=True,
            can_manage_users=True,
            can_manage_clients=True,
            can_access_system_logs=True,
            can_create_projects=True,
            can_edit_projects=True,
            can_delete_projects=True,
            can_create_tasks=True,
            can_edit_tasks=True,
            can_delete_tasks=True,
            can_view_system_logs=True,
            can_access_backup_management=True,
            can_access_system_monitoring=True
        )
        
        print("✅ Your admin account has been created successfully!")
        print("=" * 50)
        print(f"Username: {username}")
        print(f"Password: {password}")
        print(f"Email: {email}")
        print(f"Full Name: {first_name} {last_name}")
        print(f"Is Superuser: {user.is_superuser}")
        print(f"Is Staff: {user.is_staff}")
        print(f"Is Active: {user.is_active}")
        print("=" * 50)
        print("\n🎉 You can now login to your dashboard!")
        print("🌐 Go to: http://localhost:8000/login/")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating admin account: {e}")
        return False

if __name__ == "__main__":
    print("👑 Creating Your Admin Account")
    print("=" * 30)
    create_my_admin()
