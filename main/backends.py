# main/backends.py
from django.contrib.auth.backends import ModelBackend
from .models import User

class EmailBackend(ModelBackend):
    """Custom authentication backend to login with email instead of username"""
    
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        try:
            # Try to find user by email (username field contains email)
            user = User.objects.get(email=email or username)
            if user.check_password(password) and user.is_active:
                return user
        except User.DoesNotExist:
            return None
        return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return None