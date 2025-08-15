#!/usr/bin/env python3
"""
Django E-Click Deployment Script
This script automates the deployment process on Ubuntu server
"""

import os
import sys
import subprocess
import time
import signal
import psutil
from pathlib import Path

# Configuration
GITHUB_REPO = "https://github.com/MOCDATA-PTY/Django-E-Click.git"
PROJECT_DIR = "/var/www/eclick"
PORT = 1204
VENV_PATH = f"{PROJECT_DIR}/venv"

def run_command(command, cwd=None, check=True):
    """Run a shell command and return the result"""
    print(f"Running: {command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd, 
            check=check,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print("Output:", result.stdout)
        if result.stderr:
            print("Error:", result.stderr)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        if check:
            sys.exit(1)
        return e

def kill_process_on_port(port):
    """Kill any process running on the specified port"""
    print(f"Checking for processes on port {port}...")
    
    try:
        # Find processes using the port
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                connections = proc.info['connections']
                for conn in connections:
                    if conn.laddr.port == port:
                        print(f"Killing process {proc.info['pid']} ({proc.info['name']}) on port {port}")
                        proc.terminate()
                        proc.wait(timeout=5)
                        print(f"Process {proc.info['pid']} terminated successfully")
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                continue
    except Exception as e:
        print(f"Error checking processes: {e}")
    
    print(f"No processes found on port {port}")
    return False

def setup_project_directory():
    """Setup the project directory"""
    if not os.path.exists(PROJECT_DIR):
        print(f"Creating project directory: {PROJECT_DIR}")
        os.makedirs(PROJECT_DIR, exist_ok=True)
        run_command(f"chown www-data:www-data {PROJECT_DIR}")
    else:
        print(f"Project directory exists: {PROJECT_DIR}")

def git_pull_or_clone():
    """Pull from GitHub or clone if directory doesn't exist"""
    if os.path.exists(f"{PROJECT_DIR}/.git"):
        print("Pulling latest changes from GitHub...")
        run_command("git pull origin master", cwd=PROJECT_DIR)
    else:
        print("Cloning repository from GitHub...")
        run_command(f"git clone {GITHUB_REPO} .", cwd=PROJECT_DIR)

def setup_virtual_environment():
    """Setup Python virtual environment"""
    if not os.path.exists(VENV_PATH):
        print("Creating virtual environment...")
        run_command(f"python3 -m venv {VENV_PATH}")
    
    print("Updating pip...")
    run_command(f"{VENV_PATH}/bin/pip install --upgrade pip")
    
    print("Installing requirements...")
    run_command(f"{VENV_PATH}/bin/pip install -r requirements.production.txt", cwd=PROJECT_DIR)

def collect_static_files():
    """Collect static files"""
    print("Collecting static files...")
    run_command(f"{VENV_PATH}/bin/python manage.py collectstatic --noinput", cwd=PROJECT_DIR)

def run_migrations():
    """Run database migrations"""
    print("Running database migrations...")
    run_command(f"{VENV_PATH}/bin/python manage.py migrate", cwd=PROJECT_DIR)

def start_gunicorn():
    """Start Gunicorn server on the specified port"""
    print(f"Starting Gunicorn on port {PORT}...")
    
    # Update gunicorn config to use the correct port
    gunicorn_config = f"""
import multiprocessing

# Server socket
bind = "0.0.0.0:{PORT}"
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
"""
    
    with open(f"{PROJECT_DIR}/gunicorn.conf.py", "w") as f:
        f.write(gunicorn_config)
    
    # Start gunicorn in background
    run_command(
        f"{VENV_PATH}/bin/gunicorn --config gunicorn.conf.py eclick_project.wsgi:application",
        cwd=PROJECT_DIR,
        check=False
    )
    
    # Wait a moment for the server to start
    time.sleep(3)
    
    # Check if server is running
    try:
        import requests
        response = requests.get(f"http://localhost:{PORT}/health/", timeout=5)
        if response.status_code == 200:
            print(f"✅ Gunicorn started successfully on port {PORT}")
        else:
            print(f"⚠️  Server responded with status {response.status_code}")
    except Exception as e:
        print(f"⚠️  Could not verify server status: {e}")

def main():
    """Main deployment function"""
    print("🚀 Starting Django E-Click deployment...")
    
    # Check if running as root
    if os.geteuid() != 0:
        print("❌ This script must be run as root (use sudo)")
        sys.exit(1)
    
    try:
        # Kill any existing processes on the port
        kill_process_on_port(PORT)
        
        # Setup project directory
        setup_project_directory()
        
        # Change to project directory
        os.chdir(PROJECT_DIR)
        
        # Git operations
        git_pull_or_clone()
        
        # Setup virtual environment
        setup_virtual_environment()
        
        # Django operations
        collect_static_files()
        run_migrations()
        
        # Start server
        start_gunicorn()
        
        print("🎉 Deployment completed successfully!")
        print(f"🌐 Application is running on http://167.88.43.168:{PORT}")
        
    except Exception as e:
        print(f"❌ Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
