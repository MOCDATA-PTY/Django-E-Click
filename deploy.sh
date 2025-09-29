#!/bin/bash

# Django E-Click Deployment Script for Ubuntu Server
# Run with: sudo bash deploy.sh

set -e  # Exit on any error

# Configuration
GITHUB_REPO="https://github.com/MOCDATA-PTY/Django-E-Click.git"
PROJECT_DIR="/var/www/eclick"
PORT=1204
VENV_PATH="$PROJECT_DIR/venv"

echo "🚀 Starting Django E-Click deployment..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

# Function to kill processes on port
kill_port() {
    echo "Checking for processes on port $PORT..."
    PID=$(lsof -ti:$PORT)
    if [ ! -z "$PID" ]; then
        echo "Killing process $PID on port $PORT"
        kill -9 $PID
        sleep 2
    else
        echo "No processes found on port $PORT"
    fi
}

# Function to run commands with error handling
run_cmd() {
    echo "Running: $1"
    if ! eval "$1"; then
        echo "❌ Command failed: $1"
        exit 1
    fi
}

# Kill any existing processes on the port
kill_port

# Setup project directory
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Creating project directory: $PROJECT_DIR"
    mkdir -p "$PROJECT_DIR"
    chown www-data:www-data "$PROJECT_DIR"
else
    echo "Project directory exists: $PROJECT_DIR"
fi

# Change to project directory
cd "$PROJECT_DIR"

# Git operations
if [ -d ".git" ]; then
    echo "Pulling latest changes from GitHub..."
    run_cmd "git pull origin master"
else
    echo "Cloning repository from GitHub..."
    run_cmd "git clone $GITHUB_REPO ."
    chown -R www-data:www-data "$PROJECT_DIR"
fi

# Setup virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment..."
    run_cmd "python3 -m venv $VENV_PATH"
fi

echo "Updating pip..."
run_cmd "$VENV_PATH/bin/pip install --upgrade pip"

echo "Installing requirements..."
run_cmd "$VENV_PATH/bin/pip install -r requirements.production.txt"

# Django operations
echo "Collecting static files..."
run_cmd "$VENV_PATH/bin/python manage.py collectstatic --noinput"

echo "Running database migrations..."
run_cmd "$VENV_PATH/bin/python manage.py migrate"

# Update gunicorn config for the specific port
echo "Updating Gunicorn configuration for port $PORT..."
cat > gunicorn.conf.py << EOF
import multiprocessing

# Server socket
bind = "0.0.0.0:$PORT"
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
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "eclick"

# Server mechanics
daemon = True
pidfile = "/tmp/gunicorn.pid"
user = "www-data"
group = "www-data"
tmp_upload_dir = None
EOF

# Start gunicorn
echo "Starting Gunicorn on port $PORT..."
run_cmd "$VENV_PATH/bin/gunicorn --config gunicorn.conf.py eclick_project.wsgi:application"

# Wait for server to start
sleep 3

# Check if server is running
if curl -s "http://localhost:$PORT/health/" > /dev/null; then
    echo "✅ Gunicorn started successfully on port $PORT"
else
    echo "⚠️  Server health check failed, but continuing..."
fi

echo "🎉 Deployment completed successfully!"
echo "🌐 Application is running on http://77.37.121.135:$PORT"
echo ""
echo "To check server status: sudo systemctl status eclick"
echo "To view logs: sudo journalctl -u eclick -f"
echo "To restart: sudo systemctl restart eclick"
