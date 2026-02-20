import hashlib


def get_client_ip(request) -> str:
    """
    Récupère l'adresse IP réelle du client.
    Gère les cas où le serveur est derrière un proxy ou un load balancer
    en lisant le header X-Forwarded-For en priorité.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # Prend uniquement la première IP (l'IP du client original)
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def get_device_fingerprint(request) -> str:
    """
    Génère une empreinte unique de l'appareil à partir des headers HTTP disponibles.
    Cette empreinte est cohérente pour un même navigateur/appareil mais différente
    entre appareils distincts.

    Composants utilisés :
        - HTTP_USER_AGENT     : navigateur + système d'exploitation
        - HTTP_ACCEPT_LANGUAGE: langue du navigateur
        - HTTP_ACCEPT_ENCODING: encodages supportés

    Note : Intentionnellement non-unique à 100% pour respecter la vie privée.
    L'objectif est la détection de changement d'appareil, pas le tracking précis.
    """
    components = [
        request.META.get("HTTP_USER_AGENT", ""),
        request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
        request.META.get("HTTP_ACCEPT_ENCODING", ""),
    ]
    raw_fingerprint = "|".join(components)
    return hashlib.sha256(raw_fingerprint.encode()).hexdigest()


def parse_device_name(user_agent: str) -> str:
    """
    Transforme un User-Agent brut en nom lisible pour affichage
    dans la liste des sessions actives.

    Exemples :
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120..."
        → "Chrome sur Windows"

        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0...) Safari/604..."
        → "Safari sur iPhone"
    """
    if not user_agent:
        return "Appareil inconnu"

    ua_lower = user_agent.lower()

    # Détection du système d'exploitation
    if "windows" in ua_lower:
        os_name = "Windows"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        os_name = "macOS"
    elif "iphone" in ua_lower:
        os_name = "iPhone"
    elif "ipad" in ua_lower:
        os_name = "iPad"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "linux" in ua_lower:
        os_name = "Linux"
    else:
        os_name = "Appareil inconnu"

    # Détection du navigateur
    if "edg/" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower and "chromium" not in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "opera" in ua_lower or "opr/" in ua_lower:
        browser = "Opera"
    else:
        browser = "Navigateur inconnu"

    return f"{browser} sur {os_name}"