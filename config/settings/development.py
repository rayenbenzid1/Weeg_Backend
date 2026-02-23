# """
# Configuration Django pour l'environnement de développement.
# Surcharge base.py avec des paramètres adaptés au développement local.
# """

# from .base import *

# # =============================================================================
# # DÉVELOPPEMENT
# # =============================================================================

# DEBUG = True

# ALLOWED_HOSTS = ["*"]

# # =============================================================================
# # CACHE LOCAL (sans Redis) — remplace Redis en développement
# # Utilise la mémoire locale au lieu de Redis.
# # =============================================================================

# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
#         "LOCATION": "fasi-dev-cache",
#     }
# }

# # =============================================================================
# # EMAIL EN DÉVELOPPEMENT
# # Affiche les emails dans la console au lieu de les envoyer réellement.
# # =============================================================================

# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# # =============================================================================
# # CORS PERMISSIF EN DÉVELOPPEMENT
# # =============================================================================

# CORS_ALLOW_ALL_ORIGINS = True

# # =============================================================================
# # LOGS VERBEUX EN DÉVELOPPEMENT
# # =============================================================================

# # Logs verbeux en développement — console uniquement pour éviter le problème Windows
# LOGGING["loggers"]["django"]["handlers"] = ["console"]
# LOGGING["loggers"]["django"]["level"] = "DEBUG"



"""
config/settings/development.py

Paramètres spécifiques à l'environnement de développement.
Hérite de base.py — ne surcharge que ce qui est nécessaire.
"""

from .base import *  # noqa

# =============================================================================
# DEBUG
# =============================================================================

DEBUG = True
ALLOWED_HOSTS = ['*']

# =============================================================================
# BASE DE DONNÉES — même que base.py (PostgreSQL)
# =============================================================================
# Pas de surcharge nécessaire, base.py lit depuis .env

# =============================================================================
# EMAIL
# ⚠️  NE PAS mettre EMAIL_BACKEND ici en dur.
#     base.py le lit déjà depuis .env via env("EMAIL_BACKEND").
#     Si vous le redéfinissez ici, ça écrase la valeur du .env.
# =============================================================================

# ✅ Rien à mettre ici pour l'email — base.py gère tout depuis .env

# =============================================================================
# LOGS — niveau DEBUG en développement
# =============================================================================

LOGGING["loggers"]["django"]["level"] = "DEBUG"  # type: ignore[index]

# =============================================================================
# CORS — permissif en dev
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = True

# =============================================================================
# CACHE — mémoire locale en dev si Redis non disponible
# =============================================================================
# Décommentez si Redis n'est pas lancé :
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
#     }
# }