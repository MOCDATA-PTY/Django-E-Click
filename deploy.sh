#!/bin/bash
# Deployment script for E-Click Project Management System
# Run this on the production server

echo "========================================="
echo "Starting E-Click deployment..."
echo "========================================="

# Navigate to project directory
cd /var/www/Django-E-Click || exit 1

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate || exit 1

# Pull latest changes from GitHub
echo "Pulling latest changes from GitHub..."
git pull origin master || exit 1

# Install/update requirements (if any new dependencies)
echo "Installing Python dependencies..."
pip install -r requirements.txt || exit 1

# Run database migrations (skip if not needed)
# echo "Running database migrations..."
# python3 manage.py migrate || exit 1

# Collect static files
echo "Collecting static files..."
python3 manage.py collectstatic --noinput || exit 1

# Restart Gunicorn
echo "Restarting Gunicorn..."
sudo systemctl restart gunicorn

# Restart Nginx
echo "Restarting Nginx..."
sudo systemctl restart nginx

# Check Gunicorn status
echo "========================================="
echo "Checking Gunicorn status..."
echo "========================================="
sudo systemctl status gunicorn --no-pager -l

echo ""
echo "========================================="
echo "Deployment complete!"
echo "========================================="
echo "E-Click Project Management is now updated with:"
echo "  - Professional email report redesign"
echo "  - Optimized chart rendering"
echo "  - Red/black/white minimalist theme"
echo ""
echo "To verify migrations were applied, run:"
echo "source venv/bin/activate && python3 manage.py showmigrations home | tail -10"
