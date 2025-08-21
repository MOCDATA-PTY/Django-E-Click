from django.core.cache import cache
from django.db.models import Prefetch, Q
from django.db import connection
from django.conf import settings
import time

def optimize_project_queryset(queryset, user, limit=20):
    """Optimize project queries with select_related and prefetch_related"""
    return queryset.select_related(
        'created_by', 'client'
    ).prefetch_related(
        Prefetch(
            'weeks',
            queryset=queryset.model.weeks.through.objects.select_related('week').prefetch_related(
                'week__tasks__assignee',
                'week__tasks__subtasks'
            )
        ),
        'team'
    )[:limit]

def optimize_task_queryset(queryset, limit=10):
    """Optimize task queries with select_related"""
    return queryset.select_related(
        'project', 'assignee'
    ).prefetch_related(
        'subtasks'
    )[:limit]

def optimize_activity_queryset(queryset, limit=10):
    """Optimize activity queries with select_related"""
    return queryset.select_related(
        'project', 'user'
    )[:limit]

def get_cached_or_query(cache_key, queryset_func, timeout=300):
    """Get data from cache or execute query and cache result"""
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Execute query and cache result
    data = queryset_func()
    cache.set(cache_key, data, timeout)
    return data

def bulk_update_with_cache(model, objects, fields, batch_size=100):
    """Bulk update with cache invalidation"""
    # Perform bulk update
    model.objects.bulk_update(objects, fields, batch_size=batch_size)
    
    # Invalidate related caches
    cache_keys = [f'{model.__name__.lower()}_*']
    for key in cache_keys:
        cache.delete_pattern(key)

def optimize_dashboard_queries(user):
    """Optimize all dashboard queries at once"""
    cache_key = f'dashboard_optimized_{user.id}'
    
    def fetch_dashboard_data():
        if user.is_superuser:
            projects = Project.objects.all()
            recent_tasks = Task.objects.all()
            recent_activities = Activity.objects.all()
        else:
            projects = Project.objects.filter(
                Q(team=user) | Q(created_by=user)
            )
            recent_tasks = Task.objects.filter(
                Q(assignee=user) | Q(project__in=projects)
            )
            recent_activities = Activity.objects.filter(
                project__in=projects
            )
        
        return {
            'projects': optimize_project_queryset(projects, user),
            'recent_tasks': optimize_task_queryset(recent_tasks),
            'recent_activities': optimize_activity_queryset(recent_activities),
        }
    
    return get_cached_or_query(cache_key, fetch_dashboard_data, 300)

def monitor_query_performance(func):
    """Decorator to monitor query performance"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        start_queries = len(connection.queries)
        
        result = func(*args, **kwargs)
        
        end_time = time.time()
        end_queries = len(connection.queries)
        
        performance_data = {
            'function': func.__name__,
            'execution_time': end_time - start_time,
            'query_count': end_queries - start_queries,
            'timestamp': time.time()
        }
        
        # Cache performance data for monitoring
        cache_key = f'performance_{func.__name__}_{int(time.time() / 300)}'
        cache.set(cache_key, performance_data, 300)
        
        return result
    return wrapper
