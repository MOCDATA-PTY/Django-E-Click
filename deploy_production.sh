#!/bin/bash

# Production Deployment Script for E-Click Project
# Ubuntu/Debian Hostinger Server
# Run as root or with sudo privileges

set -e  # Exit on any error

echo "🚀 Starting E-Click Production Deployment..."

# Update system packages
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install required system packages
echo "🔧 Installing system dependencies..."
apt install -y python3 python3-pip python3-venv nginx mysql-server mysql-client git curl unzip

# Install Python development headers for mysqlclient
apt install -y python3-dev default-libmysqlclient-dev build-essential pkg-config

# Create application directory
echo "📁 Setting up application directory..."
mkdir -p /var/www/eclick
cd /var/www/eclick

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📚 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.mysql.txt

# Verify MySQL database connection
echo "🗄️ Verifying MySQL database connection..."
mysql -u admin -p'mk7z@Geg123' -h localhost -e "USE \`E-click-Project-management\`; SELECT 'Database connection successful' as status;"

# Create .env file from template
echo "⚙️ Setting up environment variables..."
cp production.env.template .env
echo "⚠️  IMPORTANT: Edit .env file with your actual values before continuing!"

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
    server_name your-domain.com www.your-domain.com;

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

# Start and enable services
echo "🚀 Starting services..."
systemctl daemon-reload
systemctl start eclick
systemctl enable eclick
systemctl restart nginx

# Configure firewall (if UFW is enabled)
if command -v ufw &> /dev/null; then
    echo "🔥 Configuring firewall..."
    ufw allow 'Nginx Full'
    ufw allow ssh
    ufw --force enable
fi

echo "✅ Deployment completed successfully!"
echo "🌐 Your application should now be accessible at http://your-domain.com"
echo "⚠️  Don't forget to:"
echo "   1. Edit the .env file with your actual values"
echo "   2. Update the Nginx server_name with your actual domain"
echo "   3. Set up SSL certificate with Let's Encrypt"
echo "   4. Configure your domain DNS settings"
