"""
Configuration Django pour l'environnement de production.
Surcharge base.py avec des paramètres de sécurité renforcés.
"""

from .base import *

# =============================================================================
# PRODUCTION
# =============================================================================

DEBUG = False

# =============================================================================
# SÉCURITÉ HTTPS
# =============================================================================

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"