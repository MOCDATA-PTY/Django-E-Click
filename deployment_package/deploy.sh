#!/bin/bash

# E-Click Django Application Deployment Script
# Run this script on your Ubuntu server

set -e  # Exit on any error

echo "🚀 Starting E-Click Django Application Deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run this script as root (use sudo)"
    exit 1
fi

# Set variables
PROJECT_DIR="/var/www/Django-E-Click/Django-E-Click"
SERVICE_NAME="eclick"
NGINX_SITE="eclick"

print_status "Setting up project directory..."

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"
chown -R www-data:www-data "$PROJECT_DIR/logs"

# Fix Git merge conflicts if they exist
if grep -q "<<<<<<< HEAD" "$PROJECT_DIR/manage.py"; then
    print_warning "Found Git merge conflicts in manage.py, fixing..."
    sed -i '/^<<<<<<< HEAD$/,/^>>>>>>> 0ac10138854dc00c5a1ccb6b57bc156598e58018$/d' "$PROJECT_DIR/manage.py"
    sed -i '/^=======$/d' "$PROJECT_DIR/manage.py"
    print_status "Git merge conflicts fixed"
fi

# Activate virtual environment and install dependencies
print_status "Installing Python dependencies..."
cd "$PROJECT_DIR"
source env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Run Django commands
print_status "Running Django migrations..."
python manage.py migrate --noinput

print_status "Collecting static files..."
python manage.py collectstatic --noinput

# Set proper permissions
print_status "Setting file permissions..."
chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"
chmod 664 "$PROJECT_DIR/db.sqlite3"

# Install and configure Gunicorn
print_status "Installing Gunicorn..."
pip install gunicorn

# Copy systemd service file
print_status "Setting up systemd service..."
cp "$PROJECT_DIR/eclick.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable $SERVICE_NAME

# Configure Nginx
print_status "Configuring Nginx..."
cp "$PROJECT_DIR/nginx.conf" /etc/nginx/sites-available/$NGINX_SITE
ln -sf /etc/nginx/sites-available/$NGINX_SITE /etc/nginx/sites-enabled/

# Remove default Nginx site if it exists
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
fi

# Test Nginx configuration
print_status "Testing Nginx configuration..."
nginx -t

# Start services
print_status "Starting services..."
systemctl start $SERVICE_NAME
systemctl restart nginx

# Check service status
print_status "Checking service status..."
if systemctl is-active --quiet $SERVICE_NAME; then
    print_status "✅ E-Click service is running"
else
    print_error "❌ E-Click service failed to start"
    systemctl status $SERVICE_NAME
    exit 1
fi

if systemctl is-active --quiet nginx; then
    print_status "✅ Nginx is running"
else
    print_error "❌ Nginx failed to start"
    systemctl status nginx
    exit 1
fi

# Create admin user if needed
print_status "Checking for admin user..."
if ! python manage.py shell -c "from django.contrib.auth.models import User; print('Admin exists' if User.objects.filter(is_superuser=True).exists() else 'No admin')" 2>/dev/null | grep -q "Admin exists"; then
    print_warning "No admin user found. You can create one with:"
    echo "cd $PROJECT_DIR && source env/bin/activate && python manage.py createsuperuser"
fi

print_status "🎉 Deployment completed successfully!"
print_status "Your application should be available at: http://167.88.43.168"
print_status ""
print_status "Useful commands:"
echo "  - Check service status: systemctl status $SERVICE_NAME"
echo "  - View logs: journalctl -u $SERVICE_NAME -f"
echo "  - Restart service: systemctl restart $SERVICE_NAME"
echo "  - Restart Nginx: systemctl restart nginx"
echo "  - View Nginx logs: tail -f /var/log/nginx/eclick_error.log"
