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

def unlock_user_account(username):
    """Unlock a user account by resetting failed login attempts"""
    try:
        # Get the user
        user = User.objects.get(username=username)
        
        # Get or create the user profile
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Reset login attempts and unlock account
        profile.current_login_attempts = 0
        profile.account_locked_until = None
        profile.save()
        
        print(f"✅ Account unlocked successfully for user: {username}")
        print(f"   Email: {user.email}")
        print(f"   Is active: {user.is_active}")
        print(f"   Is staff: {user.is_staff}")
        print(f"   Is superuser: {user.is_superuser}")
        print(f"   Failed login attempts reset to: {profile.current_login_attempts}")
        print(f"   Account locked until: {profile.account_locked_until}")
        
        return True
        
    except User.DoesNotExist:
        print(f"❌ User '{username}' not found")
        return False
    except Exception as e:
        print(f"❌ Error unlocking account for {username}: {e}")
        return False

def list_locked_accounts():
    """List all currently locked accounts"""
    locked_profiles = UserProfile.objects.filter(
        account_locked_until__isnull=False,
        account_locked_until__gt=timezone.now()
    )
    
    if locked_profiles.exists():
        print("🔒 Currently locked accounts:")
        print("=" * 50)
        for profile in locked_profiles:
            print(f"Username: {profile.user.username}")
            print(f"Email: {profile.user.email}")
            print(f"Locked until: {profile.account_locked_until}")
            print(f"Failed attempts: {profile.current_login_attempts}")
            print("-" * 30)
    else:
        print("✅ No accounts are currently locked")

def unlock_all_accounts():
    """Unlock all currently locked accounts"""
    locked_profiles = UserProfile.objects.filter(
        account_locked_until__isnull=False,
        account_locked_until__gt=timezone.now()
    )
    
    if locked_profiles.exists():
        print(f"🔓 Unlocking {locked_profiles.count()} locked accounts...")
        for profile in locked_profiles:
            profile.current_login_attempts = 0
            profile.account_locked_until = None
            profile.save()
            print(f"✅ Unlocked: {profile.user.username}")
    else:
        print("✅ No accounts to unlock")

if __name__ == "__main__":
    print("🔓 Account Unlock Tool")
    print("=" * 30)
    
    # List locked accounts first
    list_locked_accounts()
    print()
    
    # Unlock specific admin accounts
    admin_users = ['admin', 'User 2', 'Ethan']
    
    print("🔓 Unlocking admin accounts...")
    for username in admin_users:
        unlock_user_account(username)
        print()
    
    # Optionally unlock all accounts
    print("🔓 Unlocking all locked accounts...")
    unlock_all_accounts()
    
    print("\n🎉 You can now try logging in with:")
    print("Username: admin")
    print("Username: User 2") 
    print("Username: Ethan")
    print("\n🌐 Open your browser and go to: http://localhost:8000/login/")
