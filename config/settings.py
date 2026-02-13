import os
import socket
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# 2. .env laden (Muss im gleichen Ordner wie manage.py liegen)
load_dotenv(BASE_DIR / ".env")

# 3. Sicherheit (Werte kommen aus der .env)
SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False") == "True"

# Erlaubte Hosts als Liste (in .env mit Komma getrennt)
#ALLOWED_HOSTS = ['physiktrainer.app', 'www.physiktrainer.app', 'rt.uber.space', '127.0.0.1', 'localhost']
ALLOWED_HOSTS = ['*']


# 4. Weiche für Uberspace-Erkennung
ON_UBERSPACE = 'caelum' in socket.gethostname()

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'physik',  # Deine App
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [ BASE_DIR / "templates" ],
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

WSGI_APPLICATION = 'config.wsgi.application'

# 5. Datenbank (Immer SQLite für den Physiktrainer im PT-Ordner)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# 6. Internationalisierung
LANGUAGE_CODE = "de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

# 7. Static & Media (Hier ist der Schutz für den Rechentrainer!)
STATIC_URL = '/static/'
# Auf dem Server landen PT-Statics in seinem eigenen Projektordner
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
if ON_UBERSPACE:
    # Hier legen wir einen NEUEN Ordner an, damit 'medien' vom RT sicher ist
    MEDIA_ROOT = "/home/rt/medien_physik/"
else:
    # Lokal auf Windows
    MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Deine zusätzlichen Einstellungen
LOGOUT_ON_GET = True
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'