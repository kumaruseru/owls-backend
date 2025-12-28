import os
import sys
import environ
from pathlib import Path
from datetime import timedelta

# --- INITIALIZATION ---
env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent.parent

# Tự động load file .env
environ.Env.read_env(BASE_DIR / '.env')

# Thêm thư mục apps vào system path
sys.path.append(str(BASE_DIR / 'apps'))

# --- CORE SETTINGS ---
SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env.bool('DJANGO_DEBUG', default=False)
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'storages',
    'drf_spectacular',
    'django_filters',
    
    # Internal Apps
    'apps.identity.IdentityConfig',   
    'apps.catalog.CatalogConfig',     
    'apps.sales.SalesConfig',         
    'apps.social.SocialConfig',       
    'apps.billing.BillingConfig',     
    'apps.shipping.ShippingConfig',   
    'apps.marketing.MarketingConfig',
    'apps.core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Security middleware
    'apps.utils.middleware.SecurityHeadersMiddleware',
    'apps.utils.middleware.RequestLoggingMiddleware',
    'apps.utils.middleware.SuspiciousActivityMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# --- DATABASE & CACHE ---
DATABASES = {
    'default': env.db('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}
DATABASES['default']['CONN_MAX_AGE'] = env.int('DB_CONN_MAX_AGE', default=600)

CACHES = {
    'default': env.cache('REDIS_URL', default='locmemcache://'),
}

# --- AUTHENTICATION ---
AUTH_USER_MODEL = 'identity.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- INTERNATIONALIZATION ---
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

# --- STATIC & MEDIA ---
USE_R2 = env.bool('USE_S3', default=False)

if USE_R2:
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL')
    AWS_S3_CUSTOM_DOMAIN = env('AWS_S3_CUSTOM_DOMAIN')
    
    AWS_S3_REGION_NAME = 'auto'
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None

    STORAGES = {
        "default": {"BACKEND": "apps.core.storage.MediaStorage"},
        "staticfiles": {"BACKEND": "apps.core.storage.StaticStorage"},
    }
    
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
else:
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# --- EMAIL ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

# --- PAYMENTS ---
SITE_URL = env('SITE_URL', default='http://localhost:8000')
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')

# Stripe
STRIPE_PUBLIC_KEY = env('STRIPE_PUBLIC_KEY', default=None)
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default=None)
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default=None)

# VNPay
VNPAY_TMN_CODE = env('VNPAY_TMN_CODE', default='VNPAYTEST')
VNPAY_HASH_SECRET = env('VNPAY_HASH_SECRET', default='VNPAYTESTHASHSECRET')
VNPAY_PAYMENT_URL = env('VNPAY_PAYMENT_URL', default='https://sandbox.vnpayment.vn/paymentv2/vpcpay.html')
# Redirect directly to Frontend for client-side verification handling
VNPAY_RETURN_URL = f"{FRONTEND_URL}/checkout/success"

# MoMo
MOMO_PARTNER_CODE = env('MOMO_PARTNER_CODE', default='MOMOBKUN20180529')
MOMO_ACCESS_KEY = env('MOMO_ACCESS_KEY', default='klm05TvNBzhg7h7j')
MOMO_SECRET_KEY = env('MOMO_SECRET_KEY', default='at67qH6mk8w5Y1nAyMoYKMWACiEi2bsa')
MOMO_ENDPOINT = env('MOMO_ENDPOINT', default='https://test-payment.momo.vn/v2/gateway/api/create')
MOMO_RETURN_URL = f"{SITE_URL}/api/payments/momo/return/"
MOMO_NOTIFY_URL = f"{SITE_URL}/api/payments/momo/webhook/"

# --- GHN SHIPPING ---
GHN_TOKEN = env('GHN_API_TOKEN')
GHN_SHOP_ID = env('GHN_SHOP_ID')
GHN_SANDBOX = env.bool('GHN_SANDBOX')

# --- API & REST FRAMEWORK ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticatedOrReadOnly',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 12,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': env('THROTTLE_RATE_ANON', default='100/min'),
        'user': env('THROTTLE_RATE_USER', default='1000/min'),
        'login': '60/min',
        '2fa_confirm': '5/min',
        '2fa_login': '5/min',
        '2fa_disable': '5/min',
        '2fa_email': '5/min',
        '2fa_backup_codes': '5/min',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'OWLS E-Commerce API',
    'DESCRIPTION': 'API documentation for OWLS E-Commerce Platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env.int('JWT_ACCESS_MINUTES', default=60)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env.int('JWT_REFRESH_DAYS', default=7)),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
}

# --- SECURITY & LOGGING ---
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=["http://localhost:3000"])
CORS_ALLOW_CREDENTIALS = True

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'mask_sensitive': {
            '()': 'apps.utils.security.SensitiveDataFilter',
        },
    },
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {asctime} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['mask_sensitive'],
        },
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': env('DJANGO_LOG_LEVEL', default='INFO'), 'propagate': True},
        'apps': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
    },
}

# --- SOCIAL AUTH ---
GITHUB_CLIENT_ID = env('GITHUB_CLIENT_ID', default='')
GITHUB_CLIENT_SECRET = env('GITHUB_CLIENT_SECRET', default='')
GOOGLE_CLIENT_ID = env('GOOGLE_CLIENT_ID', default='')
GOOGLE_CLIENT_SECRET = env('GOOGLE_CLIENT_SECRET', default='')