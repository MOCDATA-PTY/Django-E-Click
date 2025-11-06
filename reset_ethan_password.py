"""
Reset password for EthanSevenster user and send OTP email
"""

import os
import sys
import django
from datetime import timedelta
import random

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from django.utils import timezone
from home.models import User, UserOTP
from home.email_service import SimpleEmailService

print("=" * 70)
print("  RESET PASSWORD FOR ETHANSEVENSTER")
print("=" * 70)

# Get the user
try:
    user = User.objects.get(username="EthanSevenster")
    print(f"\nFound user: {user.username}")
    print(f"Email: {user.email}")
    print(f"User ID: {user.id}")
except User.DoesNotExist:
    print("\nERROR: User 'EthanSevenster' not found")
    sys.exit(1)

# Set password to "123" temporarily for testing
print("\n[STEP 1] Setting current password to '123' for testing...")
user.set_password("123")
user.save()
print("Password set to: 123")

# Generate OTP
print("\n[STEP 2] Generating OTP for password reset...")
otp = ''.join(random.choices('0123456789', k=6))
print(f"Generated OTP: {otp}")

# Mark all existing OTPs as used
existing_otps = UserOTP.objects.filter(user=user, is_used=False).count()
if existing_otps > 0:
    UserOTP.objects.filter(user=user).update(is_used=True)
    print(f"Marked {existing_otps} existing OTP(s) as used")

# Create new OTP record
otp_obj = UserOTP.objects.create(
    user=user,
    otp=otp,
    is_used=False,
    expires_at=timezone.now() + timedelta(minutes=10)
)
print(f"OTP record created (expires in 10 minutes)")
print(f"Expires at: {otp_obj.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")

# Send OTP email
print("\n[STEP 3] Sending OTP email...")
email_service = SimpleEmailService()

email_body = f"""
Dear {user.username},

You have requested a password reset for your E-Click account.

Your OTP Code: {otp}

This OTP will expire in 10 minutes.

To reset your password, please visit:
http://127.0.0.1:8000/user/reset-password/?username={user.username}

Enter the OTP code above and your new password.

If you did not request this password reset, please ignore this email.

Best regards,
E-Click Team
"""

try:
    email_result = email_service.send_email(
        to_email=user.email,
        subject="Password Reset OTP - E-Click",
        body=email_body,
        from_email=None
    )

    if email_result['success']:
        print(f"SUCCESS! Email sent to: {user.email}")
        print(f"Message: {email_result.get('message', 'Email sent')}")
    else:
        print(f"ERROR! Email failed to send")
        print(f"Error: {email_result.get('error', 'Unknown error')}")

except Exception as e:
    print(f"ERROR! Exception sending email: {str(e)}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 70)
print("  SUMMARY")
print("=" * 70)
print(f"\nUser: {user.username}")
print(f"Email: {user.email}")
print(f"Current Password: 123")
print(f"\nOTP Code: {otp}")
print(f"OTP Valid Until: {otp_obj.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"\nReset URL: http://127.0.0.1:8000/user/reset-password/?username={user.username}")
print("\nNext Steps:")
print("1. Check your email at: ethansevenster621@gmail.com")
print("2. Open the reset password URL above")
print(f"3. Enter OTP: {otp}")
print("4. Enter new password (minimum 8 characters)")
print("5. Confirm password")
print("6. Submit to reset password")
print("\n" + "=" * 70)
