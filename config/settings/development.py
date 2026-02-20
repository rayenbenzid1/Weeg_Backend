"""
Configuration Django pour l'environnement de développement.
Surcharge base.py avec des paramètres adaptés au développement local.
"""

from .base import *

# =============================================================================
# DÉVELOPPEMENT
# =============================================================================

DEBUG = True

ALLOWED_HOSTS = ["*"]

# =============================================================================
# CACHE LOCAL (sans Redis) — remplace Redis en développement
# Utilise la mémoire locale au lieu de Redis.
# =============================================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fasi-dev-cache",
    }
}

# =============================================================================
# EMAIL EN DÉVELOPPEMENT
# Affiche les emails dans la console au lieu de les envoyer réellement.
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# =============================================================================
# CORS PERMISSIF EN DÉVELOPPEMENT
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = True

# =============================================================================
# LOGS VERBEUX EN DÉVELOPPEMENT
# =============================================================================

LOGGING["loggers"]["django"]["level"] = "DEBUG"