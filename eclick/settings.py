import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MySQL Database Configuration for Remote Hostinger Server
# Database: E-click-Project-management
# User: admin
# Server: 77.37.121.135
# Install: pip install mysqlclient

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-your-secret-key-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = ['167.88.43.168', 'localhost', '127.0.0.1', 'your-domain.com', '77.37.121.135']

# CSRF settings
CSRF_TRUSTED_ORIGINS = [
    'http://167.88.43.168:1204',
    'http://167.88.43.168',
    'https://167.88.43.168:1204',
    'https://167.88.43.168',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://77.37.121.135',
    'https://77.37.121.135',
]

# Login URL for @login_required decorator
LOGIN_URL = '/login/'

# Email Configuration - EMAIL SERVICES DISABLED
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Console backend for development
DEFAULT_FROM_EMAIL = 'mocdatapty@gmail.com'  # Will be set by OAuth2 account

# OAuth2 configuration for mocdatapty@gmail.com account - EMAIL SERVICES DISABLED
# GOOGLE_OAUTH2_CLIENT_ID = os.getenv('GOOGLE_OAUTH2_CLIENT_ID', '')
# GOOGLE_OAUTH2_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH2_CLIENT_SECRET', '')
# GOOGLE_OAUTH2_REDIRECT_URI = os.getenv('GOOGLE_OAUTH2_REDIRECT_URI', 'http://localhost:55691')

# Google Cloud API Configuration - EMAIL SERVICES DISABLED
# GOOGLE_CLOUD_API_KEY = 'AIzaSyBAHeuA83Rl--GvorBIZlY8UOratOu-X2U'

# Gmail API Scopes - EMAIL SERVICES DISABLED
# GMAIL_SCOPES = [
#     'https://www.googleapis.com/auth/gmail.send',
#     'https://www.googleapis.com/auth/gmail.compose',
#     'https://www.googleapis.com/auth/gmail.modify',
#     'https://www.googleapis.com/auth/userinfo.email'
# ]

# OAuth2 Settings - EMAIL SERVICES DISABLED
# OAUTH2_REDIRECT_URI = 'http://localhost:55691'
# OAUTH2_AUTHORIZATION_BASE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
# OAUTH2_TOKEN_URL = 'https://oauth2.googleapis.com/token'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'home',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Add WhiteNoise for static files
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'home.middleware.DatabaseOptimizationMiddleware',  # Database optimization
    'home.middleware.QueryLimitMiddleware',  # Query limiting
]

ROOT_URLCONF = 'eclick.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'eclick.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'E-click-Project-management',
        'USER': 'admin',
        'PASSWORD': 'mk7z@Geg123',
        'HOST': '77.37.121.135',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'",
            'autocommit': True,
            'connect_timeout': 30,  # Reduced from 60 to 30 seconds
            'read_timeout': 30,     # Reduced from 60 to 30 seconds
            'write_timeout': 30,    # Reduced from 60 to 30 seconds
            'sql_mode': 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO',
            'charset': 'utf8mb4',
            'use_unicode': True,
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'",
        },
        'CONN_MAX_AGE': 300,  # Reduced from 600 to 5 minutes for better connection management
        'CONN_HEALTH_CHECKS': True,  # Enable connection health checks
        'ATOMIC_REQUESTS': False,  # Disable atomic requests for better performance
    }
}

# Production-ready caching configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,  # 5 minutes
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}

# Database query optimization settings
DB_OPTIMIZATION = {
    'QUERY_TIMEOUT': 30,  # 30 seconds max query time
    'MAX_QUERIES_PER_REQUEST': 50,  # Limit queries per request
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# WhiteNoise configuration for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (User uploaded content)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Security settings for production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = 'DENY'
    CSRF_COOKIE_SECURE = False  # Set to False for HTTP
    SESSION_COOKIE_SECURE = False  # Set to False for HTTP
else:
    # Development settings
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
