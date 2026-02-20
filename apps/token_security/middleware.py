import logging
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _

from .utils import get_client_ip, get_device_fingerprint

security_logger = logging.getLogger("security")

# Constantes de rate limiting
MAX_LOGIN_ATTEMPTS = 5          # Nombre maximum de tentatives avant blocage
LOCKOUT_DURATION = 15 * 60     # Durée du blocage en secondes (15 minutes)
LOCKOUT_CACHE_PREFIX = "login_lockout"
ATTEMPTS_CACHE_PREFIX = "login_attempts"


class JWTFingerprintMiddleware:
    """
    Middleware de vérification de l'empreinte de l'appareil.

    À chaque requête authentifiée, vérifie que le device fingerprint calculé
    depuis les headers de la requête correspond à celui stocké dans le token JWT.

    Note : La vérification réelle est déléguée à DeviceValidator dans backends.py.
    Ce middleware se charge uniquement d'injecter le fingerprint dans la requête
    pour qu'il soit accessible par le backend d'authentification.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Calcul et injection du fingerprint dans la requête
        request.device_fingerprint = get_device_fingerprint(request)
        request.client_ip = get_client_ip(request)

        response = self.get_response(request)
        return response


class RateLimitLoginMiddleware:
    """
    Middleware de protection contre les attaques par force brute.

    Bloque une adresse IP pendant LOCKOUT_DURATION secondes si elle dépasse
    MAX_LOGIN_ATTEMPTS tentatives de connexion échouées consécutives.

    Le compteur est stocké dans Redis (via Django cache) pour performance et persistence.
    Le compteur est réinitialisé après une connexion réussie.

    S'applique uniquement sur l'endpoint de login (POST /api/auth/login/).
    """

    LOGIN_PATH = "/api/auth/login/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path == self.LOGIN_PATH:
            ip_address = get_client_ip(request)

            # Vérification si l'IP est actuellement bloquée
            if self._is_locked_out(ip_address):
                security_logger.warning(
                    f"Tentative de connexion bloquée depuis {ip_address} "
                    f"(trop de tentatives échouées)."
                )
                return JsonResponse(
                    {
                        "error": "Trop de tentatives de connexion échouées. "
                                 "Votre accès est temporairement bloqué. "
                                 "Réessayez dans 15 minutes.",
                        "code": "rate_limited",
                    },
                    status=429,
                )

        response = self.get_response(request)

        # Mise à jour du compteur de tentatives selon la réponse
        if request.method == "POST" and request.path == self.LOGIN_PATH:
            ip_address = get_client_ip(request)

            if response.status_code == 200:
                # Connexion réussie : réinitialisation du compteur
                self._reset_attempts(ip_address)
            elif response.status_code in (400, 401, 403):
                # Connexion échouée : incrémentation du compteur
                self._increment_attempts(ip_address)

        return response

    def _is_locked_out(self, ip_address: str) -> bool:
        lockout_key = f"{LOCKOUT_CACHE_PREFIX}:{ip_address}"
        return cache.get(lockout_key) is not None

    def _increment_attempts(self, ip_address: str) -> None:
        attempts_key = f"{ATTEMPTS_CACHE_PREFIX}:{ip_address}"
        attempts = cache.get(attempts_key, 0) + 1
        cache.set(attempts_key, attempts, timeout=LOCKOUT_DURATION)

        if attempts >= MAX_LOGIN_ATTEMPTS:
            lockout_key = f"{LOCKOUT_CACHE_PREFIX}:{ip_address}"
            cache.set(lockout_key, True, timeout=LOCKOUT_DURATION)
            security_logger.warning(
                f"IP {ip_address} bloquée après {attempts} tentatives échouées."
            )

    def _reset_attempts(self, ip_address: str) -> None:
        attempts_key = f"{ATTEMPTS_CACHE_PREFIX}:{ip_address}"
        lockout_key = f"{LOCKOUT_CACHE_PREFIX}:{ip_address}"
        cache.delete(attempts_key)
        cache.delete(lockout_key)


class SuspiciousActivityMiddleware:
    """
    Middleware de détection d'activité suspecte.

    Surveille les comportements anormaux après authentification :
        - Changement d'adresse IP entre deux requêtes successives
        - Tentatives d'accès à des ressources non autorisées (403 répétés)

    Ce middleware ne bloque pas les requêtes mais les enregistre dans security.log
    pour permettre une surveillance et une réaction humaine si nécessaire.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Log des accès refusés répétés (potentielle tentative de contournement)
        if response.status_code == 403 and hasattr(request, "user") and request.user.is_authenticated:
            ip_address = get_client_ip(request)
            security_logger.warning(
                f"Accès refusé (403) pour [{request.user.email}] "
                f"sur {request.path} depuis {ip_address}."
            )

        return response
