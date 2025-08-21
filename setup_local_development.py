#!/usr/bin/env python3
"""
Local Development Setup Script for E-Click Project
Sets up MySQL database connection for local development
"""

import os
import sys
import subprocess
import mysql.connector
from mysql.connector import Error

def install_requirements():
    """Install required packages for local development"""
    print("📦 Installing local development requirements...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.local.txt"])
        print("✅ Requirements installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        return False

def test_mysql_connection():
    """Test MySQL connection with provided credentials"""
    print("🔌 Testing MySQL connection...")
    
    # Database configuration
    config = {
        'host': 'localhost',
        'user': 'admin',
        'password': 'mk7z@Geg123',
        'database': 'E-click-Project-management',
        'charset': 'utf8mb4',
        'autocommit': True
    }
    
    try:
        # Try to connect
        connection = mysql.connector.connect(**config)
        
        if connection.is_connected():
            db_info = connection.get_server_info()
            print(f"✅ Successfully connected to MySQL Server version {db_info}")
            
            # Get cursor
            cursor = connection.cursor()
            
            # Execute a test query
            cursor.execute("SELECT DATABASE();")
            database = cursor.fetchone()
            print(f"📊 Connected to database: {database[0]}")
            
            # Test basic operations
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            print(f"📋 Found {len(tables)} tables in database")
            
            if tables:
                print("📝 Tables:")
                for table in tables[:5]:  # Show first 5 tables
                    print(f"   - {table[0]}")
                if len(tables) > 5:
                    print(f"   ... and {len(tables) - 5} more")
            
            print("\n🎉 MySQL connection test successful!")
            return True
            
        else:
            print("❌ Failed to connect to MySQL")
            return False
            
    except Error as e:
        print(f"❌ Error connecting to MySQL: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Make sure MySQL server is running")
        print("2. Verify credentials are correct")
        print("3. Check if admin user has proper privileges")
        print("4. Ensure firewall allows connections")
        return False
        
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("🔌 MySQL connection closed")

def create_local_env():
    """Create local .env file"""
    print("⚙️ Creating local .env file...")
    
    env_content = """# Local Development Environment Variables for E-Click Project

# Django Settings
SECRET_KEY=django-insecure-local-development-key-change-this
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration - Local MySQL
DB_NAME=E-click-Project-management
DB_USER=admin
DB_PASSWORD=mk7z@Geg123
DB_HOST=localhost
DB_PORT=3306

# Email Configuration (Console backend for development)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=mocdatapty@gmail.com

# Google Cloud API Configuration
GOOGLE_CLOUD_API_KEY=AIzaSyBAHeuA83Rl--GvorBIZlY8UOratOu-X2U

# OAuth2 configuration for development
GOOGLE_OAUTH2_CLIENT_ID=
GOOGLE_OAUTH2_CLIENT_SECRET=
GOOGLE_OAUTH2_REDIRECT_URI=http://localhost:8000/oauth2/callback

# Development settings
CSRF_COOKIE_SECURE=False
SESSION_COOKIE_SECURE=False
SECURE_SSL_REDIRECT=False
"""
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ Local .env file created successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False

def test_django_connection():
    """Test Django database connection"""
    print("🐍 Testing Django database connection...")
    
    try:
        # Set Django settings module
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
        
        # Import Django
        import django
        django.setup()
        
        # Test database connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print(f"✅ Django database connection successful: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Django database connection failed: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Setting up local development environment for E-Click Project...")
    print("=" * 60)
    
    # Step 1: Install requirements
    if not install_requirements():
        print("❌ Setup failed at requirements installation")
        return False
    
    # Step 2: Test MySQL connection
    if not test_mysql_connection():
        print("❌ Setup failed at MySQL connection test")
        return False
    
    # Step 3: Create local .env file
    if not create_local_env():
        print("❌ Setup failed at .env file creation")
        return False
    
    # Step 4: Test Django connection
    if not test_django_connection():
        print("❌ Setup failed at Django connection test")
        return False
    
    print("\n" + "=" * 60)
    print("🎉 Local development environment setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Run Django migrations: python manage.py migrate")
    print("2. Create superuser: python manage.py createsuperuser")
    print("3. Start development server: python manage.py runserver")
    print("\n🌐 Your app will be available at: http://localhost:8000")
    
    return True

if __name__ == "__main__":
    main()
