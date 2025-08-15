#!/usr/bin/env python3
"""
Simple Django E-Click Deployment Script
Run with: sudo python3 deploy_simple.py
"""

import os
import subprocess
import time

# Configuration
PORT = 1204
PROJECT_DIR = "/var/www/eclick"

def run_cmd(cmd, cwd=None):
    """Run a command and print output"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0

def main():
    print("🚀 Starting simple deployment...")
    
    # Check if root
    if os.geteuid() != 0:
        print("❌ Run with sudo")
        return
    
    # Kill processes on port
    print(f"Killing processes on port {PORT}...")
    run_cmd(f"lsof -ti:{PORT} | xargs kill -9")
    time.sleep(2)
    
    # Setup directory
    if not os.path.exists(PROJECT_DIR):
        os.makedirs(PROJECT_DIR, exist_ok=True)
        run_cmd(f"chown www-data:www-data {PROJECT_DIR}")
    
    os.chdir(PROJECT_DIR)
    
    # Git operations
    if os.path.exists(".git"):
        print("Pulling from GitHub...")
        run_cmd("git pull origin master")
    else:
        print("Cloning from GitHub...")
        run_cmd("git clone https://github.com/MOCDATA-PTY/Django-E-Click.git .")
        run_cmd(f"chown -R www-data:www-data {PROJECT_DIR}")
    
    # Setup venv
    venv_path = f"{PROJECT_DIR}/venv"
    if not os.path.exists(venv_path):
        run_cmd("python3 -m venv venv")
    
    # Install requirements
    run_cmd("venv/bin/pip install -r requirements.production.txt")
    
    # Django operations
    run_cmd("venv/bin/python manage.py collectstatic --noinput")
    run_cmd("venv/bin/python manage.py migrate")
    
    # Start gunicorn
    print(f"Starting Gunicorn on port {PORT}...")
    run_cmd(f"venv/bin/gunicorn --bind 0.0.0.0:{PORT} --daemon eclick_project.wsgi:application")
    
    print("✅ Deployment complete!")
    print(f"🌐 App running on http://167.88.43.168:{PORT}")

if __name__ == "__main__":
    main()
