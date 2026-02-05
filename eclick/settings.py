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

# Email Configuration - Microsoft Graph API
# Using Microsoft Graph API for info@eclick.co.za
EMAIL_BACKEND = 'eclick.graph_email_backend.GraphEmailBackend'
DEFAULT_FROM_EMAIL = 'info@eclick.co.za'

# Microsoft Graph API Credentials
GRAPH_CLIENT_ID = '2b89897f-049e-467e-9413-9d13a7a9259b'
GRAPH_CLIENT_SECRET = 'p4n8Q~X3z4JW~6kwY8dz~jRuFOXbOpMtBUkHTaCY'
GRAPH_TENANT_ID = 'e1aca71e-e160-4d3d-a40f-5738d03de05e'

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
    # 'django_recaptcha',  # Not needed - using manual Google reCAPTCHA integration
    'main',
    'home',
]

# Google reCAPTCHA v2 Configuration
# Get your keys at: https://www.google.com/recaptcha/admin/create
RECAPTCHA_PUBLIC_KEY = os.getenv('RECAPTCHA_PUBLIC_KEY', '6LcqSGEsAAAAANfaLORHNmAtugZqbOP2gKOehx8L')
RECAPTCHA_PRIVATE_KEY = os.getenv('RECAPTCHA_PRIVATE_KEY', '6LcqSGEsAAAAAAFnRzr7WQvypC8GUj06w1Q6NUuY')
RECAPTCHA_REQUIRED_SCORE = 0.85  # For v3, not used in v2

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'main.User'

# Authentication Backends - allow login with username or email
AUTHENTICATION_BACKENDS = [
    'main.backends.EmailBackend',  # Custom backend that supports username OR email
    'django.contrib.auth.backends.ModelBackend',  # Fallback to default
]
