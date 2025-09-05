import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-your-secret-key'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '167.88.43.168', '77.37.121.135', 'eclick.co.za', 'www.eclick.co.za', '*']

# Login URL for @login_required decorator
LOGIN_URL = '/login/'

# Email Configuration - Using your eclick.co.za email server
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'mail.eclick.co.za'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'sender@eclick.co.za'
EMAIL_HOST_PASSWORD = 'EClickSender@1'
DEFAULT_FROM_EMAIL = 'sender@eclick.co.za'

# Alternative: Use Gmail SMTP if you prefer
# EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
# EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
# EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'

# Google Cloud API Configuration - DISABLED
# GOOGLE_CLOUD_API_KEY = 'AIzaSyBAHeuA83Rl--GvorBIZlY8UOratOu-X2U'

# Google OAuth 2.0 Configuration for Gmail - DISABLED
# GOOGLE_OAUTH2_CLIENT_ID = os.getenv('GOOGLE_OAUTH2_CLIENT_ID', '')
# GOOGLE_OAUTH2_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH2_CLIENT_SECRET', '')
# GOOGLE_OAUTH2_REDIRECT_URI = os.getenv('GOOGLE_OAUTH2_REDIRECT_URI', 'http://localhost:55691')

# Gmail API Scopes - DISABLED
# GMAIL_SCOPES = [
#     'https://www.googleapis.com/auth/gmail.send',
#     'https://www.googleapis.com/auth/gmail.compose',
#     'https://www.googleapis.com/auth/gmail.modify',
#     'https://www.googleapis.com/auth/userinfo.email'
# ]

# OAuth2 Settings - DISABLED
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
    'main',
    'home',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'csp.middleware.CSPMiddleware',
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
            'connect_timeout': 60,  # Increased timeout for better stability
            'read_timeout': 60,     # Increased timeout for better stability
            'write_timeout': 60,    # Increased timeout for better stability
            'use_unicode': True,
        },
        'CONN_MAX_AGE': 0,  # Disable persistent connections to avoid connection issues
        'ATOMIC_REQUESTS': False,  # Disable atomic requests for better performance
    }
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
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files (User uploaded content)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Security Headers Configuration
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Cross-Origin Headers for Development
if DEBUG:
    # For development, use less restrictive COOP settings
    SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'
else:
    # For production, use strict COOP settings
    SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# Additional Security Headers
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Content Security Policy (CSP) - Updated configuration
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://cdn.tailwindcss.com", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com")
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://cdn.tailwindcss.com", "https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'", "https:", "https://fonts.gstatic.com")
CSP_FRAME_SRC = ("'self'", "https://www.google.com", "https://maps.google.com", "https://www.google.com/maps")
CSP_FRAME_ANCESTORS = ("'self'",)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model - temporarily disabled
# AUTH_USER_MODEL = 'main.User'
