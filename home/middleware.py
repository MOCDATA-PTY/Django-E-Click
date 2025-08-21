import time
from django.core.cache import cache
from django.conf import settings
from django.db import connection

class DatabaseOptimizationMiddleware:
    """Middleware to optimize database queries and monitor performance"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Start timing
        start_time = time.time()
        
        # Reset query count
        initial_queries = len(connection.queries)
        
        # Process request
        response = self.get_response(request)
        
        # Calculate performance metrics
        end_time = time.time()
        total_time = end_time - start_time
        query_count = len(connection.queries) - initial_queries
        
        # Only cache if response time is significant (> 100ms) to avoid cache bloat
        if total_time > 0.1 and hasattr(request, 'user') and request.user.is_authenticated:
            cache_key = f'user_queries_{request.user.id}_{request.path}'
            cache.set(cache_key, {
                'query_count': query_count,
                'response_time': total_time,
                'timestamp': time.time()
            }, 300)  # Cache for 5 minutes
        
        # Add performance headers for monitoring
        response['X-Query-Count'] = str(query_count)
        response['X-Response-Time'] = f"{total_time:.3f}s"
        
        return response

class QueryLimitMiddleware:
    """Middleware to prevent excessive database queries"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check if user has exceeded query limits
        if hasattr(request, 'user') and request.user.is_authenticated:
            cache_key = f'query_limit_{request.user.id}'
            current_queries = cache.get(cache_key, 0)
            
            if current_queries > settings.DB_OPTIMIZATION.get('MAX_QUERIES_PER_REQUEST', 50):
                # Return cached response or error
                cached_response = cache.get(f'cached_response_{request.path}')
                if cached_response:
                    return cached_response
        
        response = self.get_response(request)
        
        # Update query count
        if hasattr(request, 'user') and request.user.is_authenticated:
            cache_key = f'query_limit_{request.user.id}'
            cache.set(cache_key, current_queries + 1, 60)  # Reset every minute
        
        return response
