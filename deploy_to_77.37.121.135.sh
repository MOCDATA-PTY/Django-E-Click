#!/bin/bash

# Quick Deployment Script for E-Click Project
# Server: 77.37.121.135
# Database: E-click-Project-management (already configured)

echo "🚀 Deploying E-Click Project to 77.37.121.135..."

# Update system packages
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install required packages
echo "🔧 Installing dependencies..."
apt install -y python3 python3-pip python3-venv nginx mysql-client git curl

# Install Python development headers for mysqlclient
apt install -y python3-dev default-libmysqlclient-dev build-essential pkg-config

# Create application directory
echo "📁 Setting up application directory..."
mkdir -p /var/www/eclick
cd /var/www/eclick

# Clone or copy your project files here
echo "📥 Copying project files..."
# If you have the files locally, copy them:
# cp -r /path/to/your/project/* /var/www/eclick/

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📚 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.mysql.txt

# Test database connection
echo "🗄️ Testing database connection..."
mysql -u admin -p'mk7z@Geg123' -h localhost -e "USE \`E-click-Project-management\`; SELECT 'Database connection successful' as status;"

# Create .env file
echo "⚙️ Creating environment file..."
cat > .env << EOF
# Django Settings
SECRET_KEY=your-super-secret-production-key-here-change-this
DEBUG=False
ALLOWED_HOSTS=77.37.121.135,your-domain.com,www.your-domain.com

# Database Configuration
DB_NAME=E-click-Project-management
DB_USER=admin
DB_PASSWORD=mk7z@Geg123
DB_HOST=localhost
DB_PORT=3306

# Security Settings
CSRF_TRUSTED_ORIGINS=http://77.37.121.135,https://77.37.121.135
SECURE_SSL_REDIRECT=False
SECURE_BROWSER_XSS_FILTER=True
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS=DENY
CSRF_COOKIE_SECURE=False
SESSION_COOKIE_SECURE=False

# Static and Media Files
STATIC_ROOT=/var/www/eclick/staticfiles
MEDIA_ROOT=/var/www/eclick/media
EOF

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Run database migrations
echo "🔄 Running database migrations..."
python manage.py migrate

# Create superuser (optional)
echo "👤 Creating superuser..."
python manage.py createsuperuser

# Set up Gunicorn service
echo "🔧 Setting up Gunicorn service..."
cat > /etc/systemd/system/eclick.service << EOF
[Unit]
Description=E-Click Django Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/eclick
Environment="PATH=/var/www/eclick/venv/bin"
ExecStart=/var/www/eclick/venv/bin/gunicorn --workers 3 --bind unix:/var/www/eclick/eclick.sock eclick.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Set up Nginx configuration
echo "🌐 Setting up Nginx..."
cat > /etc/nginx/sites-available/eclick << EOF
server {
    listen 80;
    server_name 77.37.121.135 your-domain.com www.your-domain.com;

    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        root /var/www/eclick;
    }
    
    location /media/ {
        root /var/www/eclick;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/eclick/eclick.sock;
    }
}
EOF

# Enable site and restart services
echo "🔄 Enabling services..."
ln -s /etc/nginx/sites-available/eclick /etc/nginx/sites-enabled
rm -f /etc/nginx/sites-enabled/default

# Set proper permissions
echo "🔐 Setting file permissions..."
chown -R www-data:www-data /var/www/eclick
chmod -R 755 /var/www/eclick

# Create log directories
mkdir -p /var/log/eclick
mkdir -p /var/run/eclick
chown -R www-data:www-data /var/log/eclick /var/run/eclick

# Start and enable services
echo "🚀 Starting services..."
systemctl daemon-reload
systemctl start eclick
systemctl enable eclick
systemctl restart nginx

# Configure firewall
echo "🔥 Configuring firewall..."
ufw allow 'Nginx Full'
ufw allow ssh
ufw --force enable

echo "✅ Deployment completed successfully!"
echo "🌐 Your application should now be accessible at http://77.37.121.135"
echo "⚠️  Don't forget to:"
echo "   1. Edit the .env file with your actual SECRET_KEY"
echo "   2. Update the Nginx server_name with your actual domain"
echo "   3. Set up SSL certificate with Let's Encrypt"
echo "   4. Configure your domain DNS settings"

# Show service status
echo "📊 Service Status:"
systemctl status eclick --no-pager -l
systemctl status nginx --no-pager -l
