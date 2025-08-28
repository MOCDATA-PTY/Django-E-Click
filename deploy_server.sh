#!/bin/bash

# 🚀 E-Click Server Deployment Script
# Run this script on your Hostinger Ubuntu server after git pull

echo "🚀 Starting E-Click deployment..."

# Navigate to project directory
cd /var/www/eclick

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Install/update requirements
echo "📦 Installing requirements..."
pip install -r requirements.txt

# Run database migrations
echo "🗄️ Running database migrations..."
python manage.py migrate

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Restart services
echo "🔄 Restarting services..."
systemctl restart eclick
systemctl restart nginx

echo "✅ Deployment completed successfully!"
echo "🌐 Your application should now be running at: http://77.37.121.135"
echo "📧 Email functionality should be working with your configured SMTP settings"

# Show service status
echo "📊 Service Status:"
systemctl status eclick --no-pager -l
echo ""
systemctl status nginx --no-pager -l
