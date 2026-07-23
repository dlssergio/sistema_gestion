# settings.py
"""
Django settings for erp_project.

Gestión de secretos: todas las variables sensibles se leen desde el archivo
.env usando python-decouple. Nunca hardcodear credenciales aquí.

Para instalar: pip install python-decouple
Luego: copiar .env.example como .env y completar los valores.
"""
import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════════════
# SEGURIDAD
# ═══════════════════════════════════════════════════════════════════════════

SECRET_KEY = config('SECRET_KEY')

# DEBUG se lee del .env — por defecto False para que un olvido no exponga prod
DEBUG = config('DEBUG', default=False, cast=bool)

# ALLOWED_HOSTS se lee del .env como lista separada por comas
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,.localhost', cast=Csv())


# ═══════════════════════════════════════════════════════════════════════════
# APLICACIONES
# ═══════════════════════════════════════════════════════════════════════════

SHARED_APPS = [
    'django_tenants',   # Debe ser la primera
    'companies',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django_extensions',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # Para invalidar tokens en logout
    'corsheaders',
    'auditlog',
    'storages',
]

TENANT_APPS = [
    'djmoney',
    'inventario',
    'compras',
    'entidades',
    'parametros',
    'ventas',
    'finanzas',
    'guardian',
    'users',
]

INSTALLED_APPS = SHARED_APPS + TENANT_APPS


# ═══════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',  # Siempre primero
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'auditlog.middleware.AuditlogMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'erp_project.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'erp_project.wsgi.application'


# ═══════════════════════════════════════════════════════════════════════════
# BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME':     config('DB_NAME',     default='erp_db'),
        'USER':     config('DB_USER',     default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST':     config('DB_HOST',     default='localhost'),
        'PORT':     config('DB_PORT',     default='5432'),
        'CONN_MAX_AGE': 60,  # Reutilizar conexiones hasta 60 segundos
    }
}

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)
TENANT_MODEL        = 'companies.Company'
TENANT_DOMAIN_MODEL = 'companies.Domain'


# ═══════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN
# ═══════════════════════════════════════════════════════════════════════════

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
)


# ═══════════════════════════════════════════════════════════════════════════
# DJANGO REST FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    # Autenticación exclusiva por JWT
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Todo endpoint requiere autenticación salvo que se anote explícitamente
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # ── Paginación global ────────────────────────────────────────────────
    # Todos los ListAPIView y ViewSet.list() devuelven páginas automáticamente.
    # Los endpoints que no deben paginar pueden sobreescribir con:
    #   pagination_class = None
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,

    # ── Filtros y búsqueda ────────────────────────────────────────────────
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],

    # ── Throttling (rate limiting) ────────────────────────────────────────
    # Protege contra abuso. Valores razonables para ERP de uso interno.
    # Aumentar en producción si es necesario.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/hour',      # Usuarios no autenticados (login, etc.)
        'user': '3000/hour',    # Usuarios autenticados (uso normal de ERP)
    },

    # Formato por defecto
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],

    # Manejo de excepciones global
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}


# ═══════════════════════════════════════════════════════════════════════════
# JWT — SIMPLE JWT
# ═══════════════════════════════════════════════════════════════════════════
#
# Criterio aplicado:
#   ACCESS_TOKEN_LIFETIME  = 30 min — corto para limitar el daño si se
#     filtra un token. El frontend lo refresca automáticamente (interceptor
#     Axios ya implementado).
#   REFRESH_TOKEN_LIFETIME = 7 días — una semana de sesión sin re-login.
#     Suficiente para uso laboral normal (L-V + finde). Ajustar a 1 día
#     si el entorno requiere mayor seguridad.
#   ROTATE_REFRESH_TOKENS  = True — cada refresh emite un nuevo refresh.
#     Esto implementa "refresh token rotation": si un refresh robado se usa,
#     el legítimo queda invalidado y el sistema lo detecta.
#   BLACKLIST_AFTER_ROTATION = True — el refresh anterior queda en la
#     blacklist (tabla token_blacklist). Requiere la app en INSTALLED_APPS.
#   UPDATE_LAST_LOGIN = True — actualiza User.last_login en cada login.
#     Útil para auditoría y para detectar cuentas inactivas.

SIMPLE_JWT = {
    # Tiempos de vida
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),

    # Rotación de refresh tokens
    'ROTATE_REFRESH_TOKENS':     True,
    'BLACKLIST_AFTER_ROTATION':  True,

    # Seguridad adicional
    'UPDATE_LAST_LOGIN':         True,
    'ALGORITHM':                 'HS256',
    'SIGNING_KEY':               SECRET_KEY,

    # Headers
    'AUTH_HEADER_TYPES':         ('Bearer',),
    'AUTH_HEADER_NAME':          'HTTP_AUTHORIZATION',
    'USER_ID_FIELD':             'id',
    'USER_ID_CLAIM':             'user_id',

    # Tipo de token en las respuestas
    'TOKEN_OBTAIN_SERIALIZER':
        'rest_framework_simplejwt.serializers.TokenObtainPairSerializer',
    'TOKEN_REFRESH_SERIALIZER':
        'rest_framework_simplejwt.serializers.TokenRefreshSerializer',
}


# ═══════════════════════════════════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════════════════════════════════

CORS_ALLOW_CREDENTIALS = True

# En producción, leer los orígenes del .env para no hardcodear dominios.
# En desarrollo, usar el regex que acepta cualquier subdominio de localhost.
_cors_origins = config('CORS_ALLOWED_ORIGINS', default='')
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]
else:
    # Solo en desarrollo (cuando CORS_ALLOWED_ORIGINS está vacío en .env)
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r'^http://localhost:5173$',
        r'^http://127\.0\.0\.1:5173$',
        r'^http://.*\.localhost:5173$',
    ]

CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']

CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]


# ═══════════════════════════════════════════════════════════════════════════
# CELERY
# ═══════════════════════════════════════════════════════════════════════════

REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CELERY_BROKER_URL        = REDIS_URL
CELERY_RESULT_BACKEND    = REDIS_URL
CELERY_ACCEPT_CONTENT    = ['json']
CELERY_TASK_SERIALIZER   = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE          = 'America/Argentina/Buenos_Aires'


# ═══════════════════════════════════════════════════════════════════════════
# ALMACENAMIENTO (S3 / MINIO)
# ═══════════════════════════════════════════════════════════════════════════

USE_S3 = config('USE_S3', default=False, cast=bool)

AWS_ACCESS_KEY_ID      = config('AWS_ACCESS_KEY_ID',      default='')
AWS_SECRET_ACCESS_KEY  = config('AWS_SECRET_ACCESS_KEY',  default='')
AWS_STORAGE_BUCKET_NAME= config('AWS_STORAGE_BUCKET_NAME',default='erp-media-local')
AWS_S3_ENDPOINT_URL    = config('AWS_S3_ENDPOINT_URL',    default='http://localhost:9000')
AWS_S3_CUSTOM_DOMAIN   = config('AWS_S3_CUSTOM_DOMAIN',   default='')
AWS_S3_URL_PROTOCOL    = 'http:'
AWS_S3_USE_SSL         = False
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_S3_FILE_OVERWRITE  = False
AWS_QUERYSTRING_AUTH   = False

if USE_S3:
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

MEDIA_URL  = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# ═══════════════════════════════════════════════════════════════════════════
# EMAIL
# ═══════════════════════════════════════════════════════════════════════════

EMAIL_BACKEND   = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST      = config('EMAIL_HOST',    default='smtp.gmail.com')
EMAIL_PORT      = config('EMAIL_PORT',    default=587, cast=int)
EMAIL_USE_TLS   = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL', default='ERP <noreply@example.com>')


# ═══════════════════════════════════════════════════════════════════════════
# LOGGING (Actualizado para Producción SaaS)
# ═══════════════════════════════════════════════════════════════════════════
#
# En desarrollo: logs en consola con nivel INFO.
# En producción (DEBUG=False): logs en archivo con nivel WARNING + errores
# en archivo separado para facilitar monitoreo.
#
# Todos los logs incluyen: timestamp, nivel, módulo, tenant (si disponible),
# y el mensaje. Esto permite filtrar por tenant en un entorno multi-tenant.

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] {name} — {message}',
            'style':  '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style':  '{',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(pathname)s %(lineno)d %(message)s'
        },
    },

    'handlers': {
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'verbose' if not DEBUG else 'simple',
        },
        'file_general': {
            'class':       'logging.handlers.RotatingFileHandler',
            'filename':    LOGS_DIR / 'erp.log',
            'maxBytes':    10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter':   'json' if not DEBUG else 'verbose',
            'encoding':    'utf-8',
        },
        'file_errors': {
            'class':       'logging.handlers.RotatingFileHandler',
            'filename':    LOGS_DIR / 'erp_errors.log',
            'maxBytes':    5 * 1024 * 1024,   # 5 MB
            'backupCount': 10,
            'level':       'ERROR',
            'formatter':   'json' if not DEBUG else 'verbose',
            'encoding':    'utf-8',
        },
    },

    'root': {
        'handlers': ['console'],
        'level':    'INFO',
    },

    'loggers': {
        # Django core
        'django': {
            'handlers': ['console', 'file_general'],
            'level':    'WARNING' if not DEBUG else 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers':  ['console', 'file_errors'],
            'level':     'ERROR',
            'propagate': False,
        },

        # Nuestras apps — logs de operaciones críticas
        'ventas': {
            'handlers':  ['console', 'file_general'],
            'level':     'INFO',
            'propagate': False,
        },
        'finanzas': {
            'handlers':  ['console', 'file_general'],
            'level':     'INFO',
            'propagate': False,
        },
        'inventario': {
            'handlers':  ['console', 'file_general'],
            'level':     'INFO',
            'propagate': False,
        },
        'compras': {
            'handlers':  ['console', 'file_general'],
            'level':     'INFO',
            'propagate': False,
        },

        # AFIP — nivel DEBUG en dev para ver la comunicación con el WS
        'parametros.afip': {
            'handlers':  ['console', 'file_general', 'file_errors'],
            'level':     'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },

        # Silenciar loggers muy verbosos de terceros
        'boto3':    {'level': 'WARNING', 'propagate': True},
        'botocore': {'level': 'WARNING', 'propagate': True},
        's3transfer':{'level': 'WARNING', 'propagate': True},
        'urllib3':  {'level': 'WARNING', 'propagate': True},
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# INTERNACIONALIZACIÓN
# ═══════════════════════════════════════════════════════════════════════════

LANGUAGE_CODE = 'es-ar'
TIME_ZONE     = 'America/Argentina/Buenos_Aires'
USE_I18N      = True
USE_TZ        = True


# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVOS ESTÁTICOS
# ═══════════════════════════════════════════════════════════════════════════

STATIC_URL  = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ═══════════════════════════════════════════════════════════════════════════
# SEGURIDAD EN PRODUCCIÓN
# (ignorados en DEBUG=True, activos cuando DEBUG=False)
# ═══════════════════════════════════════════════════════════════════════════

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER        = True
    SECURE_CONTENT_TYPE_NOSNIFF      = True
    X_FRAME_OPTIONS                  = 'DENY'
    SECURE_HSTS_SECONDS              = 31536000   # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS   = True
    SECURE_HSTS_PRELOAD              = True
    SECURE_SSL_REDIRECT              = True
    SESSION_COOKIE_SECURE            = True
    CSRF_COOKIE_SECURE               = True

# ── Tests ────────────────────────────────────────────────────────────────────
# Las clases de prueba ahora heredan directamente de TenantTestCase.
# No forzamos TEST_RUNNER.