# Gunicorn configuration file
import multiprocessing

# Server socket
bind = "unix:/var/www/Django-E-Click/Django-E-Click/eclick.sock"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "/var/www/Django-E-Click/Django-E-Click/logs/gunicorn_access.log"
errorlog = "/var/www/Django-E-Click/Django-E-Click/logs/gunicorn_error.log"
loglevel = "info"

# Process naming
proc_name = "eclick"

# Server mechanics
daemon = False
pidfile = "/var/www/Django-E-Click/Django-E-Click/gunicorn.pid"
user = "www-data"
group = "www-data"
tmp_upload_dir = None

# SSL (uncomment if using HTTPS)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"
