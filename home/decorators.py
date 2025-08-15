from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from functools import wraps
from .models import UserProfile


def require_permission(permission_name):
    """
    Decorator to check if user has a specific permission.
    Usage: @require_permission('dashboard')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                profile = request.user.profile
                if not profile.has_permission(permission_name):
                    messages.error(request, f'Access denied. You do not have permission to access this feature.')
                    return HttpResponseForbidden('Access Denied')
            except UserProfile.DoesNotExist:
                # If profile doesn't exist, create one with default permissions
                profile = UserProfile.objects.create(user=request.user)
                if not profile.has_permission(permission_name):
                    messages.error(request, f'Access denied. You do not have permission to access this feature.')
                    return HttpResponseForbidden('Access Denied')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def require_admin_access(view_func):
    """
    Decorator to check if user has admin access.
    Usage: @require_admin_access
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has admin privileges
        has_admin_access = False
        try:
            profile = request.user.profile
            has_admin_access = profile.can_access_admin
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
            has_admin_access = profile.can_access_admin
        
        # If user doesn't have admin access, still allow them to view but with warning
        if not has_admin_access:
            # Add a warning message but don't block access
            messages.warning(request, 'You are viewing the admin panel with limited access. Some features require admin privileges.')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def require_user_management(view_func):
    """
    Decorator to check if user can manage other users.
    Usage: @require_user_management
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        try:
            profile = request.user.profile
            if not profile.can_manage_users:
                messages.error(request, 'Access denied. User management privileges required.')
                return HttpResponseForbidden('User Management Access Required')
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
            if not profile.can_manage_users:
                messages.error(request, 'Access denied. User management privileges required.')
                return HttpResponseForbidden('User Management Access Required')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def require_client_management(view_func):
    """
    Decorator to check if user can manage clients.
    Usage: @require_client_management
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        try:
            profile = request.user.profile
            if not profile.can_manage_clients:
                messages.error(request, 'Access denied. Client management privileges required.')
                return HttpResponseForbidden('Client Management Access Required')
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
            if not profile.can_manage_clients:
                messages.error(request, 'Access denied. Client management privileges required.')
                return HttpResponseForbidden('Client Management Access Required')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def require_project_permission(action):
    """
    Decorator to check project-related permissions.
    Usage: @require_project_permission('create')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                profile = request.user.profile
                permission_name = f'can_{action}_projects'
                if not profile.has_permission(permission_name):
                    messages.error(request, f'Access denied. You do not have permission to {action} projects.')
                    return HttpResponseForbidden(f'Project {action.title()} Access Required')
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=request.user)
                permission_name = f'can_{action}_projects'
                if not profile.has_permission(permission_name):
                    messages.error(request, f'Access denied. You do not have permission to {action} projects.')
                    return HttpResponseForbidden(f'Project {action.title()} Access Required')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def require_task_permission(action):
    """
    Decorator to check task-related permissions.
    Usage: @require_task_permission('create')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                profile = request.user.profile
                permission_name = f'can_{action}_tasks'
                if not profile.has_permission(permission_name):
                    messages.error(request, f'Access denied. You do not have permission to {action} tasks.')
                    return HttpResponseForbidden(f'Task {action.title()} Access Required')
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=request.user)
                permission_name = f'can_{action}_tasks'
                if not profile.has_permission(permission_name):
                    messages.error(request, f'Access denied. You do not have permission to {action} tasks.')
                    return HttpResponseForbidden(f'Task {action.title()} Access Required')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def check_account_status(view_func):
    """
    Decorator to check if user account is active and not locked.
    Usage: @check_account_status
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        try:
            profile = request.user.profile
            
            # Check if account is suspended
            if not profile.is_account_active():
                messages.error(request, f'Account suspended: {profile.suspension_reason or "No reason provided"}')
                return redirect('login')
            
            # Check if account is locked
            if profile.is_account_locked():
                messages.error(request, 'Account temporarily locked due to multiple failed login attempts. Please try again later.')
                return redirect('login')
                
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            profile = UserProfile.objects.create(user=request.user)
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def require_superuser(view_func):
    """
    Decorator to check if user is a superuser.
    Usage: @require_superuser
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not request.user.is_superuser:
            messages.error(request, 'Access denied. Superuser privileges required.')
            return HttpResponseForbidden('Superuser Access Required')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view
