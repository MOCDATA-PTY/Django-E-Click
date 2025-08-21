# Gunicorn Configuration for Production
# E-Click Project - Ubuntu/Debian Hostinger Server

import multiprocessing
import os

# Server socket
bind = "unix:/var/www/Django-E-Click/Django-E-Click/eclick.sock"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Logging
accesslog = "/var/www/Django-E-Click/Django-E-Click/logs/access.log"
errorlog = "/var/www/Django-E-Click/Django-E-Click/logs/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "eclick"

# Server mechanics
daemon = False
pidfile = "/var/run/eclick/gunicorn.pid"
user = "www-data"
group = "www-data"
tmp_upload_dir = None

# SSL (if using HTTPS)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performance
timeout = 30
keepalive = 2
max_requests_jitter = 50
worker_tmp_dir = "/dev/shm"

# Graceful restart
graceful_timeout = 30
