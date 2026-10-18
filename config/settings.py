"""
Paramètres Django de l'ENT ENSIASD.

Les valeurs sensibles (clé secrète, mode debug, hôtes autorisés) sont lues
depuis les variables d'environnement, avec des valeurs par défaut adaptées
au développement local.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

CLE_DE_DEVELOPPEMENT = "django-insecure-dev-uniquement-a-remplacer-en-production"
# La clé secrète vient de DJANGO_SECRET_KEY, ou d'un fichier (DJANGO_SECRET_KEY_FILE) généré
# directement sur le serveur, pour qu'elle n'apparaisse ni dans le code ni dans la configuration.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY and os.environ.get("DJANGO_SECRET_KEY_FILE"):
    SECRET_KEY = Path(os.environ["DJANGO_SECRET_KEY_FILE"]).read_text(encoding="utf-8").strip()
SECRET_KEY = SECRET_KEY or CLE_DE_DEVELOPPEMENT
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

if not DEBUG and SECRET_KEY == CLE_DE_DEVELOPPEMENT:
    raise ImproperlyConfigured("En production (DJANGO_DEBUG=0), définissez une vraie clé secrète dans DJANGO_SECRET_KEY.")

# --- Production : site servi uniquement en HTTPS (hébergeur derrière un proxy) ---
if not DEBUG:
    CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS : le navigateur n'utilisera plus que HTTPS pour ce site (sans les sous-domaines,
    # qui appartiennent à l'hébergeur).
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "3600"))
    # Volontaire : sur un sous-domaine d'hébergeur, ni « includeSubDomains » ni « preload ».
    SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

# En-tête contenant la vraie adresse IP du visiteur derrière le proxy de l'hébergeur
# (utilisé pour le blocage après échecs de connexion). Vide : REMOTE_ADDR.
ENTETE_IP_CLIENT = os.environ.get("DJANGO_ENTETE_IP_CLIENT", "")

# Les erreurs serveur sont écrites dans le journal d'erreurs de l'hébergeur.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["console"], "level": "WARNING"}},
}


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Modules de l'ENT
    "comptes",
    "structure",
    "emplois",
    "ressources",
    "documents",
    "absences",
    "notifications",
    "annonces",
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
# « IMMEDIATE » : une transaction réserve l'écriture dès son début. Deux enregistrements
# simultanés (appel, justification…) passent alors l'un après l'autre au lieu d'échouer
# avec « database is locked » ; le second attend au plus « timeout » secondes.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
    }
}

# Cache stocké dans la base (table créée par « migrate ») : les compteurs de tentatives de
# connexion survivent aux redémarrages du site et sont partagés entre ses processus.
# MAX_ENTRIES élevé : une rafale d'essais sur des identifiants inventés ne doit pas effacer
# les compteurs existants.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_ent",
        "OPTIONS": {"MAX_ENTRIES": 10_000},
    }
}


# Authentification
AUTH_USER_MODEL = "comptes.Utilisateur"
LOGIN_URL = "connexion"
LOGIN_REDIRECT_URL = "tableau_de_bord"
LOGOUT_REDIRECT_URL = "connexion"

# Ordinateurs partagés (salles informatiques) : la session se termine à la fermeture du
# navigateur, et au plus tard 10 heures après la connexion (une journée de cours).
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 10 * 60 * 60

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
STOCKAGE_STATIQUES_PRODUCTION = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
if not DEBUG:
    # « collectstatic » ajoute une empreinte au nom des fichiers (ent.3f1a9c….css) : après une
    # mise à jour, les navigateurs chargent la nouvelle version au lieu de garder l'ancienne en cache.
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": STOCKAGE_STATIQUES_PRODUCTION},
    }

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
