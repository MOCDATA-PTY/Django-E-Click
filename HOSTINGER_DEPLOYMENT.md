# 🚀 Hostinger Ubuntu Server Deployment Guide

## 📋 Prerequisites
- SSH access to your Hostinger Ubuntu server: `ssh root@77.37.121.135`
- Git repository set up on GitHub
- Domain pointing to your server IP: `77.37.121.135`

## 🔧 Server Setup Commands

### 1. Connect to your server:
```bash
ssh root@77.37.121.135
```

### 2. Update system and install dependencies:
```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nginx mysql-server git supervisor
```

### 3. Create project directory:
```bash
mkdir -p /var/www/eclick
cd /var/www/eclick
```

### 4. Clone your repository:
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git .
```

## 🌍 Environment Setup

### 1. Create production environment file:
```bash
nano .env
```

### 2. Add these environment variables:
```env
# Production Environment Variables
DEBUG=False
SECRET_KEY=your-super-secret-production-key-here

# Database Configuration
DB_ENGINE=mysql
DB_NAME=E-click-Project-management
DB_USER=admin
DB_PASSWORD=mk7z@Geg123
DB_HOST=localhost
DB_PORT=3306

# Server Configuration
ALLOWED_HOSTS=77.37.121.135,localhost,127.0.0.1,your-domain.com

# Email Configuration - Choose ONE option:

# Option A: Hostinger SMTP
EMAIL_HOST=smtp.hostinger.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=admin@eclick.co.za
EMAIL_HOST_PASSWORD=EClickAdmin@1
DEFAULT_FROM_EMAIL=admin@eclick.co.za

# Option B: Gmail SMTP (recommended)
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_USE_SSL=False
# EMAIL_HOST_USER=your-gmail@gmail.com
# EMAIL_HOST_PASSWORD=your-gmail-app-password
# DEFAULT_FROM_EMAIL=your-gmail@gmail.com
```

## 🐍 Python Environment Setup

### 1. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install requirements:
```bash
pip install -r requirements.txt
```

### 3. Install additional production packages:
```bash
pip install gunicorn mysqlclient
```

## 🗄️ Database Setup

### 1. Secure MySQL:
```bash
mysql_secure_installation
```

### 2. Create database and user:
```bash
mysql -u root -p
```

```sql
CREATE DATABASE `E-click-Project-management` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'admin'@'localhost' IDENTIFIED BY 'mk7z@Geg123';
GRANT ALL PRIVILEGES ON `E-click-Project-management`.* TO 'admin'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

## ⚙️ Django Configuration

### 1. Run migrations:
```bash
python manage.py migrate
```

### 2. Create superuser:
```bash
python manage.py createsuperuser
```

### 3. Collect static files:
```bash
python manage.py collectstatic --noinput
```

## 🚀 Gunicorn Setup

### 1. Create gunicorn service file:
```bash
nano /etc/systemd/system/eclick.service
```

### 2. Add this content:
```ini
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
```

### 3. Enable and start service:
```bash
systemctl enable eclick
systemctl start eclick
```

## 🌐 Nginx Configuration

### 1. Create Nginx site configuration:
```bash
nano /etc/nginx/sites-available/eclick
```

### 2. Add this configuration:
```nginx
server {
    listen 80;
    server_name 77.37.121.135 your-domain.com;

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
```

### 3. Enable site and restart Nginx:
```bash
ln -s /etc/nginx/sites-available/eclick /etc/nginx/sites-enabled
rm /etc/nginx/sites-enabled/default
systemctl restart nginx
```

## 🔒 Firewall Setup

### 1. Configure UFW firewall:
```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

## 📧 Email Testing

### 1. Test email functionality:
```bash
cd /var/www/eclick
source venv/bin/activate
python manage.py shell
```

```python
from home.email_service import SimpleEmailService
service = SimpleEmailService()
result = service.send_email('test@example.com', 'Test Subject', 'Test message')
print('Email test result:', result)
```

## 🔄 Deployment Updates

### 1. For future updates:
```bash
cd /var/www/eclick
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
systemctl restart eclick
```

## 🐛 Troubleshooting

### 1. Check service status:
```bash
systemctl status eclick
journalctl -u eclick -f
```

### 2. Check Nginx status:
```bash
systemctl status nginx
nginx -t
```

### 3. Check logs:
```bash
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

## 📱 SSL/HTTPS Setup (Optional)

### 1. Install Certbot:
```bash
apt install certbot python3-certbot-nginx
```

### 2. Get SSL certificate:
```bash
certbot --nginx -d your-domain.com
```

## ✅ Final Checklist

- [ ] Environment variables configured
- [ ] Database created and migrated
- [ ] Static files collected
- [ ] Gunicorn service running
- [ ] Nginx configured and running
- [ ] Firewall configured
- [ ] Email functionality tested
- [ ] Domain pointing to server IP

## 🆘 Support

If you encounter issues:
1. Check service logs: `journalctl -u eclick -f`
2. Verify environment variables are loaded
3. Test email configuration step by step
4. Ensure all required packages are installed
