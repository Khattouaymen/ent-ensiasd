"""
Paramètres Django de l'ENT ENSIASD.

Les valeurs sensibles (clé secrète, mode debug, hôtes autorisés) sont lues
depuis les variables d'environnement, avec des valeurs par défaut adaptées
au développement local.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-uniquement-a-remplacer-en-production",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Modules de l'ENT
    "comptes",
    "structure",
    "emplois",
    "ressources",
    "documents",
    "absences",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "comptes.middleware.ChangementMotDePasseObligatoire",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "notifications.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Base de données : SQLite pour le développement et la démonstration.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Authentification
AUTH_USER_MODEL = "comptes.Utilisateur"
LOGIN_URL = "connexion"
LOGIN_REDIRECT_URL = "tableau_de_bord"
LOGOUT_REDIRECT_URL = "connexion"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalisation
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Casablanca"
USE_I18N = True
USE_TZ = True


# Fichiers statiques et fichiers déposés (supports de cours, justificatifs, documents)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Les fichiers déposés ne sont jamais servis directement : ils passent par des
# vues qui vérifient les droits de l'utilisateur (confidentialité, BNF02).
MEDIA_ROOT = BASE_DIR / "media"

# Seuils d'alerte : heures d'absence non justifiées, en % du volume horaire de la matière
SEUILS_ABSENCE = {"AVERTISSEMENT": 10, "CRITIQUE": 25}

# E-mails (réinitialisation du mot de passe). En développement, les e-mails sont
# affichés dans la console du serveur au lieu d'être envoyés.
EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("DJANGO_EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "ENT ENSIASD <ne-pas-repondre@ensiasd.test>")

# Sauvegardes de la base et des fichiers déposés (BNF07)
DOSSIER_SAUVEGARDES = BASE_DIR / "sauvegardes"
NB_SAUVEGARDES_CONSERVEES = 14

# Taille maximale des pièces jointes (BNF09)
TAILLE_MAX_JUSTIFICATIF_MO = 5
TAILLE_MAX_RESSOURCE_MO = 20

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
