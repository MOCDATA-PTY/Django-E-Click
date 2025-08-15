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
from django.utils import timezone

def create_admin_account(username, email, password, first_name="", last_name=""):
    """Create a new admin account with superuser privileges"""
    try:
        # Check if user already exists
        if User.objects.filter(username=username).exists():
            print(f"❌ User '{username}' already exists")
            return False
        
        if User.objects.filter(email=email).exists():
            print(f"❌ Email '{email}' is already registered")
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
        
        print(f"✅ Admin account created successfully!")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Full Name: {first_name} {last_name}".strip())
        print(f"   Is Superuser: {user.is_superuser}")
        print(f"   Is Staff: {user.is_staff}")
        print(f"   Is Active: {user.is_active}")
        print(f"   Profile ID: {profile.id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating admin account: {e}")
        return False

def create_default_admin():
    """Create a default admin account with common credentials"""
    return create_admin_account(
        username="newadmin",
        email="newadmin@example.com",
        password="admin123",
        first_name="New",
        last_name="Admin"
    )

def create_custom_admin():
    """Create a custom admin account with user input"""
    print("🔧 Create Custom Admin Account")
    print("=" * 40)
    
    username = input("Enter username: ").strip()
    if not username:
        print("❌ Username cannot be empty")
        return False
    
    email = input("Enter email: ").strip()
    if not email:
        print("❌ Email cannot be empty")
        return False
    
    password = input("Enter password: ").strip()
    if not password:
        print("❌ Password cannot be empty")
        return False
    
    first_name = input("Enter first name (optional): ").strip()
    last_name = input("Enter last name (optional): ").strip()
    
    return create_admin_account(username, email, password, first_name, last_name)

def list_admin_accounts():
    """List all admin accounts"""
    admin_users = User.objects.filter(is_superuser=True)
    
    if admin_users.exists():
        print("👑 Admin Accounts:")
        print("=" * 50)
        for user in admin_users:
            print(f"Username: {user.username}")
            print(f"Email: {user.email}")
            print(f"Full Name: {user.get_full_name()}")
            print(f"Active: {user.is_active}")
            print(f"Date Joined: {user.date_joined}")
            print("-" * 30)
    else:
        print("❌ No admin accounts found")

if __name__ == "__main__":
    print("👑 Admin Account Creation Tool")
    print("=" * 40)
    
    # List existing admin accounts
    list_admin_accounts()
    print()
    
    # Create default admin account
    print("🔧 Creating default admin account...")
    if create_default_admin():
        print("\n✅ Default admin account created!")
        print("   Username: newadmin")
        print("   Password: admin123")
        print("   Email: newadmin@example.com")
    else:
        print("❌ Failed to create default admin account")
    
    print()
    
    # Ask if user wants to create a custom admin account
    create_custom = input("Do you want to create a custom admin account? (y/n): ").strip().lower()
    if create_custom in ['y', 'yes']:
        print()
        create_custom_admin()
    
    print("\n🎉 Admin account setup complete!")
    print("You can now login with:")
    print("Username: newadmin")
    print("Password: admin123")
    print("\n🌐 Open your browser and go to: http://localhost:8000/login/")
