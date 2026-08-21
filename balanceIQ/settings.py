import os
from pathlib import Path
import logging
from dotenv import load_dotenv


# ==========================================
# 1. مسارات المشروع الأساسية
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent

# ==========================================
# 2. كشف البيئة تلقائياً
# ==========================================
IS_LOCAL = os.path.exists(BASE_DIR / '.env')

if IS_LOCAL:
    load_dotenv(BASE_DIR / '.env')
else:
    # على السيرفر: نقرأ من مجلد آمن
    if os.path.exists('/etc/balanceIQ/.env'):
        load_dotenv('/etc/balanceIQ/.env')

# ==========================================
# 3. إعدادات الأمان الأساسية
# ==========================================
SECRET_KEY = os.getenv('SECRET_KEY')

if not SECRET_KEY:
    raise ValueError(
        "❌ لم يتم تعيين SECRET_KEY!\n"
        "• محلياً: تأكد من وجوده في ملف .env\n"
        "• على السيرفر: أضفه في /etc/balanceIQ/.env"
    )

# إعداد ذكي: يعمل بوضع التصحيح محلياً، ويتوقف تلقائياً على الاستضافة
DEBUG = IS_LOCAL

# ✅ تم التعديل: إضافة الدومين الجديد
if IS_LOCAL:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.1.108']
else:
    ALLOWED_HOSTS = [
        'balanceiqsoft.com',
        'www.balanceiqsoft.com',
        '82.29.129.53',
        'localhost',
        '127.0.0.1',
    ]

# ==========================================
# 4. التطبيقات المثبتة
# ==========================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts.apps.AccountsConfig',
    'invoice.apps.InvoiceConfig',
    'markdownify',
]

# ==========================================
# 5. البرمجيات الوسيطة (Middleware)
# ==========================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # ================= تمت الإضافة: سياسة أمان المحتوى (CSP) =================
    'balanceIQ.middlewares.CustomCSPMiddleware',
]

ROOT_URLCONF = 'balanceIQ.urls'

# ==========================================
# 6. إعدادات القوالب (Templates)
# ==========================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # ✅ هذه تجلب company_settings (من accounts)
                'accounts.context_processors.site_settings',
                # ✅ هذه تجلب cart_count (من invoice)
                'invoice.context_processors.cart_count',
                # ✅ هذه تجلب csp_nonce (من balanceIQ)
                'balanceIQ.context_processors.csp_nonce',
                # ❌ احذف هذا السطر إذا كان موجوداً
                # 'invoice.context_processors.company_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'balanceIQ.wsgi.application'

# ==========================================
# 7. قاعدة البيانات (MySQL)
# ==========================================
# ✅ تم التعديل: دعم VPS مع الحفاظ على الكشف التلقائي
if IS_LOCAL:
    # ===== وضع التطوير المحلي =====
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'balanceiq_db'),
            'USER': os.getenv('DB_USER', 'root'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            }
        }
    }
else:
    # ===== وضع السيرفر (VPS) =====
    DB_PASSWORD = os.getenv('DB_PASSWORD')

    if not DB_PASSWORD:
        raise ValueError(
            "❌ لم يتم تعيين DB_PASSWORD على السيرفر!\n"
            "أضفه في /etc/balanceIQ/.env"
        )

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'balanceiq_db'),
            'USER': os.getenv('DB_USER', 'root'),
            'PASSWORD': DB_PASSWORD,
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            'TEST': {
                'NAME': f"test_{os.getenv('DB_NAME', 'balanceiq_db')}",
            },
        }
    }

# ==========================================
# 8. التحقق من صحة كلمات المرور
# ==========================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 9}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ==========================================
# 9. اللغة والوقت
# ==========================================
LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Asia/Amman'
USE_I18N = True
USE_TZ = True

# ==========================================
# 10. الملفات الثابتة والملفات المرفوعة
# ==========================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ==========================================
# 11. إعدادات المصادقة وتسجيل الدخول
# ==========================================
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'index'
LOGOUT_REDIRECT_URL = 'accounts:login'

SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 1209600  # 14 يوم
PASSWORD_RESET_TIMEOUT = 86400  # 24 ساعة

# ✅ تم التعديل: إضافة الدومين الجديد
SITE_URL = 'http://localhost:8000' if IS_LOCAL else 'https://balanceiqsoft.com'

# ==========================================
# 12. إعدادات الأمان (تم تحديثها لسد ثغرات check --deploy و Mozilla)
# ==========================================
if IS_LOCAL:
    # محلياً: نستخدم HTTP العادي
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
else:
    # ===== على السيرفر (VPS): نطبق أعلى معايير الأمان =====

    # 1. حماية الكوكيز
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

    # 2. التحويل الإجباري لـ HTTPS
    SECURE_SSL_REDIRECT = True

    # 3. دعم الـ Proxy (لـ Nginx)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # 4. السماح بالطلبات من نفس النطاق
    CSRF_TRUSTED_ORIGINS = [
        'https://balanceiqsoft.com',
        'https://www.balanceiqsoft.com',
    ]

    # 5. إعداد HSTS
    SECURE_HSTS_SECONDS = 31536000  # سنة كاملة
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # 6. إضافات أمان إضافية
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'

# ==========================================
# 13. نظام تسجيل الأحداث (Logging)
# ==========================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{'
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{'
        },
        'detailed': {
            'format': '{asctime} | {levelname:8s} | {name:20s} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'INFO'
        },
        'file_debug': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/debug.log'),
            'formatter': 'detailed',
            'level': 'DEBUG'
        },
        'file_errors': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/errors.log'),
            'formatter': 'verbose',
            'level': 'ERROR'
        },
        'file_info': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/info.log'),
            'formatter': 'detailed',
            'level': 'INFO'
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_info'],
            'level': 'INFO',
            'propagate': True
        },
        'django.request': {
            'handlers': ['file_info', 'file_errors'],
            'level': 'DEBUG',
            'propagate': False
        },
        'invoice': {
            'handlers': ['console', 'file_debug', 'file_errors'],
            'level': 'DEBUG',
            'propagate': False
        },
        'invoice.models': {
            'handlers': ['file_debug'],
            'level': 'DEBUG',
            'propagate': False
        },
        'invoice.views': {
            'handlers': ['console', 'file_debug'],
            'level': 'DEBUG',
            'propagate': False
        },
        'invoice.forms': {
            'handlers': ['file_debug'],
            'level': 'DEBUG',
            'propagate': False
        },
        'accounts': {
            'handlers': ['console', 'file_debug', 'file_errors'],
            'level': 'DEBUG',
            'propagate': False
        },
    },
}

# ==========================================
# 14. إعدادات التخزين المؤقت (Cache)
# ==========================================
if IS_LOCAL:
    # محلياً: ذاكرة مؤقتة في RAM
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'balanceiq-cache',
        }
    }
else:
    # ✅ على السيرفر: استخدام Cache بالملفات (آمن ومستقر)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': os.path.join(BASE_DIR, 'cache'),
        }
    }

# ==========================================
# 15. إعدادات خاصة بالنظام
# ==========================================
PRICING_PASSWORD = os.environ.get('PRICING_PASSWORD', '')
SERVER_BACKUPS_DIR = os.path.join(BASE_DIR, 'server_backups')

# ==========================================
# 16. ✅ إضافات جديدة للنظام (الفترة التجريبية والبريد)
# ==========================================
TRIAL_DAYS = int(os.getenv('TRIAL_DAYS', 10))

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'admin@balanceiqsoft.com')

# ==========================================
# 17. إعدادات CSP (Content Security Policy) - اختيارية
# ==========================================
# CSP_DEFAULT_SRC = ("'self'",)
# CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com")
# CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com")
# CSP_IMG_SRC = ("'self'", "data:", "https:")
# CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")